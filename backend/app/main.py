# backend/app/main.py
from __future__ import annotations

import os
import secrets
import uuid
from typing import Optional, Iterable

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import httpx
import json
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .llm_client import LLMClient

# ─── App & CORS ────────────────────────────────────────────────────────────────
app = FastAPI(title="AIR4 API", version="0.6.4-phase6.4")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # можно ужесточить позже
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Env ──────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "0000")

# Лимиты/настройки (меняй в .env при желании)
MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "4000"))    # входящее поле message
MAX_CONCURRENCY  = int(os.getenv("MAX_CONCURRENCY", "3"))      # одновременные LLM-запросы
LLM_TIMEOUT_SEC  = float(os.getenv("LLM_TIMEOUT_SEC", "60"))    # httpx timeout для /api/chat
STREAM_TIMEOUT_SEC = float(os.getenv("STREAM_TIMEOUT_SEC", "120"))

# Параметры генерации по умолчанию (поддерживаются Ollama)
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.2"))
DEFAULT_NUM_PREDICT = int(os.getenv("DEFAULT_NUM_PREDICT", "512"))  # ограничение длины ответа

# ─── Глобальные семафоры для ограничения одновременных запросов ───────────────
_llm_semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

# ─── Auth (простой токен под smoke) ───────────────────────────────────────────
_TOKENS: set[str] = set()

class LoginBody(BaseModel):
    password: str = Field(..., min_length=1)

class LoginReply(BaseModel):
    ok: bool
    token: str

def _bearer_token(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    return authorization.split(" ", 1)[1].strip()

def require_auth(token: str = Depends(_bearer_token)) -> None:
    if token not in _TOKENS:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@app.post("/auth/login", response_model=LoginReply)
def login(body: LoginBody):
    if body.password != AUTH_PASSWORD:
        raise HTTPException(status_code=403, detail="Invalid credentials")
    token = secrets.token_hex(16)
    _TOKENS.add(token)
    return LoginReply(ok=True, token=token)

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
        "phase": "6.4",
        "llm_model": OLLAMA_MODEL,
        "limits": {
            "max_input_chars": MAX_INPUT_CHARS,
            "max_concurrency": MAX_CONCURRENCY,
            "timeout_chat_sec": LLM_TIMEOUT_SEC,
            "timeout_stream_sec": STREAM_TIMEOUT_SEC,
            "num_predict": DEFAULT_NUM_PREDICT,
        },
    }

# ─── /chat → LLM (через Ollama) ───────────────────────────────────────────────
class ChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=20000)
    system: Optional[str] = Field(
        default="You are AIr4, a strict but helpful local assistant. Be concise, logical, and actionable."
    )
    temperature: float = DEFAULT_TEMPERATURE

class ChatReply(BaseModel):
    ok: bool
    reply: str
    request_id: str

def _validate_message_length(text: str) -> None:
    if len(text) > MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Input too large: {len(text)} chars > {MAX_INPUT_CHARS}. Trim the message."
        )

def _ollama_chat_payload(messages: list[dict], temperature: float) -> dict:
    return {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": DEFAULT_NUM_PREDICT,
        },
    }

def _ollama_stream_payload(messages: list[dict], temperature: float) -> dict:
    return {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_predict": DEFAULT_NUM_PREDICT,
        },
    }

# Ретраи для нестабильных сетевых ошибок/таймаутов
_retry_decorator = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=3),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError)),
)

async def _async_with_timeout(coro, seconds: float):
    return await asyncio.wait_for(coro, timeout=seconds)

@app.post("/chat", response_model=ChatReply)
async def chat(
    body: ChatBody,
    _auth: None = Depends(require_auth),
    x_system_prompt: Optional[str] = Header(default=None, alias="X-System-Prompt"),
):
    _validate_message_length(body.message)
    system_text = x_system_prompt.strip() if (x_system_prompt and x_system_prompt.strip()) else body.system

    messages = []
    if system_text:
        messages.append({"role": "system", "content": system_text})
    messages.append({"role": "user", "content": body.message})

    # Используем прямой запрос к Ollama для контроля таймаута/ретраев
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload = _ollama_chat_payload(messages, body.temperature)

    async with _llm_semaphore:
        try:
            @_retry_decorator
            async def _do() -> str:
                async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SEC) as client:
                    r = await client.post(url, json=payload)
                    r.raise_for_status()
                    data = r.json()
                if isinstance(data, dict) and "message" in data and isinstance(data["message"], dict):
                    return data["message"].get("content", "").strip()
                if isinstance(data, dict) and "response" in data:
                    return str(data["response"]).strip()
                return str(data).strip()

            answer = await _async_with_timeout(_do(), LLM_TIMEOUT_SEC + 5)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="LLM timeout")
        except httpx.HTTPStatusError as e:
            # 5xx — пробовали ретраи, но не вышло
            code = e.response.status_code
            raise HTTPException(status_code=502, detail=f"Ollama HTTP {code}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    return ChatReply(ok=True, reply=answer, request_id=uuid.uuid4().hex[:8])

# ─── /chat/stream → SSE (стрим токенов) ───────────────────────────────────────
@app.post("/chat/stream")
async def chat_stream(
    body: ChatBody,
    _auth: None = Depends(require_auth),
    x_system_prompt: Optional[str] = Header(default=None, alias="X-System-Prompt"),
):
    _validate_message_length(body.message)
    system_text = x_system_prompt.strip() if (x_system_prompt and x_system_prompt.strip()) else body.system

    messages = []
    if system_text:
        messages.append({"role": "system", "content": system_text})
    messages.append({"role": "user", "content": body.message})

    async def event_gen():
        url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
        payload = _ollama_stream_payload(messages, body.temperature)

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
                                obj = None
                                try:
                                    obj = json.loads(line)
                                except Exception:
                                    continue
                                msg = (obj or {}).get("message", {})
                                chunk = msg.get("content")
                                if chunk:
                                    yield f"data: {chunk}\n\n"
                                if (obj or {}).get("done"):
                                    break

                # общий таймаут на стрим
                async def _bounded():
                    async for piece in _stream():
                        yield piece

                # оборачиваем в общий таймаут стрима
                try:
                    async with asyncio.timeout(STREAM_TIMEOUT_SEC + 10):
                        async for piece in _bounded():
                            yield piece
                except TimeoutError:
                    yield "event: error\ndata: Stream timeout\n\n"
            except httpx.HTTPStatusError as e:
                yield f"event: error\ndata: Ollama HTTP {e.response.status_code}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {str(e)}\n\n"

        # маркер завершения
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

# ─── /models → список доступных моделей Ollama ────────────────────────────────
class ModelsReply(BaseModel):
    ok: bool
    models: list[str]

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
