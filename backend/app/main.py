# backend/app/main.py
from __future__ import annotations

import os
import secrets
import uuid
import json
import asyncio
from typing import Optional, Iterable, Deque, Dict
from collections import deque

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# локальный клиент не обязателен, но оставим импорт на будущее
from .llm_client import LLMClient  # noqa: F401

# ─── App & CORS ────────────────────────────────────────────────────────────────
app = FastAPI(title="AIR4 API", version="0.6.5-phase6.5")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # можно ужесточить позже
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Env ──────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
AUTH_PASSWORD   = os.getenv("AUTH_PASSWORD", "0000")

# Лимиты/настройки
MAX_INPUT_CHARS    = int(os.getenv("MAX_INPUT_CHARS", "4000"))
MAX_CONCURRENCY    = int(os.getenv("MAX_CONCURRENCY", "3"))
LLM_TIMEOUT_SEC    = float(os.getenv("LLM_TIMEOUT_SEC", "60"))
STREAM_TIMEOUT_SEC = float(os.getenv("STREAM_TIMEOUT_SEC", "120"))
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.2"))
DEFAULT_NUM_PREDICT = int(os.getenv("DEFAULT_NUM_PREDICT", "512"))

# История: количество последних ТЁРНОВ (user+assistant = 1 тёрн)
HISTORY_MAX_TURNS  = int(os.getenv("HISTORY_MAX_TURNS", "6"))

# ─── Глобальные структуры ─────────────────────────────────────────────────────
_llm_semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
_TOKENS: set[str] = set()
_HISTORY: Dict[str, Deque[dict]] = {}  # ключ: токен, значение: deque([{"role":...,"content":...}, ...])

# ─── Модели данных ────────────────────────────────────────────────────────────
class LoginBody(BaseModel):
    password: str = Field(..., min_length=1)

class LoginReply(BaseModel):
    ok: bool
    token: str

class ChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=20000)
    system: Optional[str] = Field(
        default="You are AIr4, a strict but helpful local assistant. Be concise, logical, and actionable."
    )
    temperature: float = DEFAULT_TEMPERATURE
    reset_history: bool = False  # можно мягко сбрасывать историю при запросе

class ChatReply(BaseModel):
    ok: bool
    reply: str
    request_id: str

class ModelsReply(BaseModel):
    ok: bool
    models: list[str]

class ResetReply(BaseModel):
    ok: bool
    request_id: str

# ─── Auth ─────────────────────────────────────────────────────────────────────
def _bearer_token(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    return authorization.split(" ", 1)[1].strip()

def require_auth(token: str = Depends(_bearer_token)) -> str:
    if token not in _TOKENS:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return token  # возвращаем сам токен — используем как ключ истории

@app.post("/auth/login", response_model=LoginReply)
def login(body: LoginBody):
    if body.password != AUTH_PASSWORD:
        raise HTTPException(status_code=403, detail="Invalid credentials")
    token = secrets.token_hex(16)
    _TOKENS.add(token)
    # инициализируем историю
    _HISTORY.setdefault(token, deque(maxlen=HISTORY_MAX_TURNS * 2))
    return LoginReply(ok=True, token=token)

# ─── Служебные ────────────────────────────────────────────────────────────────
@app.get("/api/v0/secure/status")
def secure_status():
    return {
        "locked": False,
        "duress_active": False,
        "request_id": uuid.uuid4().hex[:12],
    }

@app.get("/health")
def health():
    return {
        "ok": True,
        "phase": "6.5",
        "llm_model": OLLAMA_MODEL,
        "limits": {
            "max_input_chars": MAX_INPUT_CHARS,
            "max_concurrency": MAX_CONCURRENCY,
            "timeout_chat_sec": LLM_TIMEOUT_SEC,
            "timeout_stream_sec": STREAM_TIMEOUT_SEC,
            "num_predict": DEFAULT_NUM_PREDICT,
            "history_max_turns": HISTORY_MAX_TURNS,
        },
    }

# ─── Утилиты ──────────────────────────────────────────────────────────────────
def _validate_message_length(text: str) -> None:
    if len(text) > MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Input too large: {len(text)} chars > {MAX_INPUT_CHARS}. Trim the message."
        )

def _build_messages(
    token: str,
    user_text: str,
    system_text: Optional[str],
) -> list[dict]:
    msgs: list[dict] = []
    if system_text:
        msgs.append({"role": "system", "content": system_text})
    # подмешиваем короткую историю, если есть
    hist = _HISTORY.get(token)
    if hist:
        msgs.extend(list(hist))
    # текущий пользовательский запрос
    msgs.append({"role": "user", "content": user_text})
    return msgs

def _ollama_chat_payload(model: str, messages: list[dict], temperature: float) -> dict:
    return {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": DEFAULT_NUM_PREDICT,
        },
    }

def _ollama_stream_payload(model: str, messages: list[dict], temperature: float) -> dict:
    return {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_predict": DEFAULT_NUM_PREDICT,
        },
    }

_retry_decorator = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=3),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError)),
)

async def _async_with_timeout(coro, seconds: float):
    return await asyncio.wait_for(coro, timeout=seconds)

def _normalize_model(header_model: Optional[str]) -> str:
    # Если передали X-Model, используем его; иначе дефолт из .env
    if header_model and header_model.strip():
        return header_model.strip()
    return OLLAMA_MODEL

def _remember_turn(token: str, user_text: str, assistant_text: str) -> None:
    dq = _HISTORY.setdefault(token, deque(maxlen=HISTORY_MAX_TURNS * 2))
    dq.append({"role": "user", "content": user_text})
    dq.append({"role": "assistant", "content": assistant_text})

# ─── /chat ────────────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatReply)
async def chat(
    body: ChatBody,
    token: str = Depends(require_auth),
    x_system_prompt: Optional[str] = Header(default=None, alias="X-System-Prompt"),
    x_model: Optional[str] = Header(default=None, alias="X-Model"),
):
    _validate_message_length(body.message)

    if body.reset_history:
        _HISTORY[token] = deque(maxlen=HISTORY_MAX_TURNS * 2)

    system_text = x_system_prompt.strip() if (x_system_prompt and x_system_prompt.strip()) else body.system
    model = _normalize_model(x_model)

    messages = _build_messages(token, body.message, system_text)

    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload = _ollama_chat_payload(model, messages, body.temperature)

    async with _llm_semaphore:
        try:
            @_retry_decorator
            async def _do() -> str:
                async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SEC) as client:
                    r = await client.post(url, json=payload)
                    r.raise_for_status()
                    data = r.json()
                if isinstance(data, dict) and isinstance(data.get("message"), dict):
                    return data["message"].get("content", "").strip()
                if isinstance(data, dict) and "response" in data:
                    return str(data["response"]).strip()
                return str(data).strip()

            answer = await _async_with_timeout(_do(), LLM_TIMEOUT_SEC + 5)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="LLM timeout")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Ollama HTTP {e.response.status_code}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    # сохраняем тёрн в историю
    _remember_turn(token, body.message, answer)
    return ChatReply(ok=True, reply=answer, request_id=uuid.uuid4().hex[:8])

# ─── /chat/stream ─────────────────────────────────────────────────────────────
@app.post("/chat/stream")
async def chat_stream(
    body: ChatBody,
    token: str = Depends(require_auth),
    x_system_prompt: Optional[str] = Header(default=None, alias="X-System-Prompt"),
    x_model: Optional[str] = Header(default=None, alias="X-Model"),
):
    _validate_message_length(body.message)

    if body.reset_history:
        _HISTORY[token] = deque(maxlen=HISTORY_MAX_TURNS * 2)

    system_text = x_system_prompt.strip() if (x_system_prompt and x_system_prompt.strip()) else body.system
    model = _normalize_model(x_model)

    messages = _build_messages(token, body.message, system_text)

    async def event_gen():
        url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
        payload = _ollama_stream_payload(model, messages, body.temperature)

        collected_chunks: list[str] = []

        async with _llm_semaphore:
            try:
                @_retry_decorator
                async def _stream() -> Iterable[str]:
                    async with httpx.AsyncClient(timeout=None) as client:
                        async with client.stream("POST", url, json=payload, timeout=STREAM_TIMEOUT_SEC) as resp:
                            resp.raise_for_status()
                            async for line in resp.aiter_lines():
                                if not line:
                                    continue
                                try:
                                    obj = json.loads(line)
                                except Exception:
                                    continue
                                msg = (obj or {}).get("message", {})
                                chunk = msg.get("content")
                                if chunk:
                                    collected_chunks.append(chunk)
                                    yield f"data: {chunk}\n\n"
                                if (obj or {}).get("done"):
                                    break

                # общий таймаут стрима
                try:
                    async with asyncio.timeout(STREAM_TIMEOUT_SEC + 10):
                        async for piece in _stream():
                            yield piece
                except TimeoutError:
                    yield "event: error\ndata: Stream timeout\n\n"
            except httpx.HTTPStatusError as e:
                yield f"event: error\ndata: Ollama HTTP {e.response.status_code}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {str(e)}\n\n"

        # сохранить весь ответ в историю
        if collected_chunks:
            _remember_turn(token, body.message, "".join(collected_chunks))

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

# ─── /models ──────────────────────────────────────────────────────────────────
@app.get("/models", response_model=ModelsReply)
async def models(_auth: None = Depends(require_auth)):
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama tags error: {e}")

    names = []
    for it in (data or {}).get("models", []):
        name = (it or {}).get("name")
        if name:
            names.append(name)
    return ModelsReply(ok=True, models=names)

# ─── /chat/reset ──────────────────────────────────────────────────────────────
@app.post("/chat/reset", response_model=ResetReply)
def reset_chat(token: str = Depends(require_auth)):
    _HISTORY[token] = deque(maxlen=HISTORY_MAX_TURNS * 2)
    return ResetReply(ok=True, request_id=uuid.uuid4().hex[:8])
