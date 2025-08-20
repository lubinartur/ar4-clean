# backend/app/main.py
from __future__ import annotations

import os, json, time
from typing import List, Dict, Optional, Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .summarizer import AutoSummarizer
from . import llm_client

# --- ENV
# OLLAMA_HOST=http://localhost:11434
# OLLAMA_MODEL=mistral:latest
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:latest")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.4"))
LLM_MAX_CTX = int(os.getenv("LLM_MAX_CTX", "4096"))
HTTP_TIMEOUT = httpx.Timeout(60.0, read=60.0, connect=10.0)

app = FastAPI(title="AIR4 API")

# === инициализация автосаммари ===
summarizer = AutoSummarizer()  # без llm_call — будет fallback на простую выжимку


# === pydantic-модели ===
class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: Optional[str] = "default"
    end_session: Optional[bool] = False
    web_query: Optional[str] = None  # для подмешивания веб-контекста
    stream: bool = False             # ВКЛ/ВЫКЛ стрима

class ChatResponse(BaseModel):
    reply: str
    injected_summaries: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    memory_used: Optional[List[str]] = None

class ToolRequest(BaseModel):
    name: str
    params: Optional[Dict[str, Any]] = None

class ToolResponse(BaseModel):
    ok: bool
    tool: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None


# === вспомогательное ===
def _recent_texts(user_id: str, k: int = 2) -> List[str]:
    rows = summarizer.recent(user_id=user_id, limit=k)
    return [text for (text, _md) in rows]

def _messages_from_req(req: ChatRequest, injected: List[str]) -> List[Dict[str, Any]]:
    msgs: List[Dict[str, Any]] = []
    if injected:
        sys_block = "Короткая память:\n" + "\n\n".join(f"— {t}" for t in injected)
        msgs.append({
            "role": "system",
            "content": sys_block,
            "metadata": {"session_id": req.session_id}
        })
    msgs.append({
        "role": "user",
        "content": req.message,
        "metadata": {"session_id": req.session_id}
    })
    return msgs

# === LLM: вызов Ollama (non-stream) ===
def _ollama_chat(messages: List[Dict[str, Any]], model: Optional[str] = None, timeout: int = 45) -> Dict[str, Any]:
    """
    Прямой чат-запрос в Ollama /api/chat (без стрима).
    Возвращает dict: {"text": str, "metrics": {...}}
    """
    host = OLLAMA_HOST
    model = model or OLLAMA_MODEL
    payload = {
        "model": model,
        "messages": [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") in {"system", "user", "assistant"}
        ],
        "stream": False,
        "options": {"temperature": LLM_TEMPERATURE, "num_ctx": LLM_MAX_CTX},
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(f"{host}/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()
    msg = data.get("message") or {}
    text = (msg.get("content") or data.get("content") or "").strip()
    metrics = data.get("metrics") or {}
    return {"text": text, "metrics": metrics}


# === health ===
@app.get("/health")
async def health():
    return {"ok": True, "model": OLLAMA_MODEL}


# === TOOLS REGISTRY ===
def _run_tool(name: str, params: dict | None):
    params = params or {}

    # ленивые импорты, чтобы /chat грузился быстрее
    if name == "read_text":
        from .tools.files import read_text
        return read_text(**params)

    elif name == "read_pdf":
        from .tools.files import read_pdf
        return read_pdf(**params)

    elif name == "csv_head":
        from .tools.data import csv_head
        return csv_head(**params)

    elif name == "web_search":
        from .tools.web import web_search
        return web_search(**params)

    elif name == "web_fetch":
        from .tools.web import web_fetch
        return web_fetch(**params)

    elif name == "docs_search":
        from .tools.web import docs_search
        return docs_search(**params)

    elif name == "http_get":
        from .tools.web import http_get
        return http_get(**params)

    else:
        raise ValueError(f"Unknown tool: {name}")


@app.post("/tools", response_model=ToolResponse)
def tools(req: ToolRequest):
    try:
        result = _run_tool(req.name, req.params)
        return ToolResponse(ok=True, tool=req.name, result=result)
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content=ToolResponse(ok=False, tool=req.name, error=str(e)).dict()
        )


# === эндпоинт /chat (stream + non-stream) ===
@app.post("/chat")
async def chat(req: ChatRequest):
    injected = _recent_texts(req.user_id or "default", k=2)

    # при наличии web_query — подтягиваем веб-контекст и внедряем в system
    if getattr(req, "web_query", None):
        try:
            from .tools.web import web_search, web_fetch
            hits = web_search(req.web_query, max_results=2)
            chunks: List[str] = []
            for h in hits:
                try:
                    page = web_fetch(h["url"], max_chars=3000)
                    chunks.append(f"# {page['title']}\n{page['url']}\n\n{page['text'][:1200]}")
                except Exception:
                    pass
            if chunks:
                injected.insert(0, "Веб-контекст:\n" + "\n\n---\n\n".join(chunks))
        except Exception:
            pass  # не валим чат

    messages = _messages_from_req(req, injected)

    # системный промт
    sys_prompt = (
        "Ты — техлид проекта AIR4 на macOS.\n"
        "Если в системном сообщении есть блок 'Веб-контекст', считай его единственным источником истины: "
        "опирайся ТОЛЬКО на него.\n"
        "Отвечай строго в формате:\n"
        "1) Цель (1–2 строки)\n"
        "2) Шаги (zsh/код)\n"
        "3) Проверка\n"
        "4) Что сохранить\n"
        "Правила: точность, минимум воды."
    )
    full_messages = [{"role": "system", "content": sys_prompt}, *messages]

    # --- STREAM MODE ---
    if req.stream:
        async def gen():
            start = time.perf_counter()
            buf: List[str] = []
            url = f"{OLLAMA_HOST}/api/chat"
            payload = {
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": m["role"], "content": m["content"]}
                    for m in full_messages
                ],
                "stream": True,
                "options": {"temperature": LLM_TEMPERATURE, "num_ctx": LLM_MAX_CTX},
            }
            prompt_tokens = None
            completion_tokens = None

            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                async with client.stream("POST", url, json=payload) as r:
                    if r.status_code != 200:
                        text = await r.aread()
                        raise HTTPException(status_code=502, detail=text.decode("utf-8", "ignore"))
                    async for line in r.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        msg = data.get("message", {})
                        chunk = msg.get("content")
                        if chunk:
                            buf.append(chunk)
                            yield chunk
                        if data.get("done"):
                            meta = data.get("metrics") or {}
                            prompt_tokens = meta.get("prompt_eval_count")
                            completion_tokens = meta.get("eval_count")
                            break

            # попытка сохранить саммари
            try:
                summarizer.summarize_session(
                    messages, user_id=req.user_id, session_id=req.session_id
                )
            except Exception:
                pass

            tail = json.dumps({
                "meta": {
                    "model": OLLAMA_MODEL,
                    "latency_ms": int((time.perf_counter() - start) * 1000),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }
            }, ensure_ascii=False)
            yield f"\n\n[[META]] {tail}\n"

        return StreamingResponse(gen(), media_type="text/plain")

    # --- NON-STREAM MODE ---
    start = time.perf_counter()
    try:
        if os.getenv("LLM_PROVIDER", "ollama").lower() == "ollama":
            out = _ollama_chat(full_messages)
            reply = out["text"]
            meta = out["metrics"] or {}
        else:
            # кастомный клиент как фоллбек
            reply = llm_client.chat_complete(full_messages)
            meta = {}
        if not reply:
            reply = "(LLM вернул пусто) Я получил: " + req.message
    except Exception as e:
        reply = f"(LLM не доступен: {e}) Я получил: {req.message}"
        meta = {}

    saved_summary: Optional[str] = None
    if req.end_session:
        saved = summarizer.summarize_session(
            messages, user_id=req.user_id, session_id=req.session_id
        )
        saved_summary = saved.get("summary")

    latency_ms = int((time.perf_counter() - start) * 1000)
    return ChatResponse(
        reply=reply,
        injected_summaries=injected,
        summary=saved_summary,
        model=OLLAMA_MODEL,
        prompt_tokens=meta.get("prompt_eval_count"),
        completion_tokens=meta.get("eval_count"),
        latency_ms=latency_ms,
        memory_used=injected or None,
    )
