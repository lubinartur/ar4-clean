# backend/app/main.py
from __future__ import annotations

import os, json, time
from typing import List, Dict, Optional, Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .memory.manager import add_memory  # запись в память
from .summarizer import AutoSummarizer
from . import llm_client
from .rag import build_messages_with_rag  # RAG
# Security (функции бэкомпат + роутер secure)
from .security import verify_password, issue_session, secure_status, is_locked
from backend.app.security import router as secure_router

# --- FastAPI app (создаём ДО include_router) ---
app = FastAPI(title="AIR4 API", version="0.1.0")

# CORS (можешь ужесточить позже)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем secure роуты /api/v0/secure/*
app.include_router(secure_router)

# --- ENV
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:latest")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.4"))
LLM_MAX_CTX = int(os.getenv("LLM_MAX_CTX", "4096"))
HTTP_TIMEOUT = httpx.Timeout(60.0, read=60.0, connect=10.0)

# === автоcаммари ===
summarizer = AutoSummarizer()  # без llm_call — fallback на простую выжимку

# === модели ===
class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: Optional[str] = "default"
    end_session: Optional[bool] = False
    web_query: Optional[str] = None
    stream: bool = False

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

# --- Memory API models ---
class MemoryAddRequest(BaseModel):
    user_id: str = "default"
    text: Optional[str] = None
    texts: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None
    metas: Optional[List[Dict[str, Any]]] = None

class MemoryAddResponse(BaseModel):
    ok: bool
    added: int
    ids: List[str]

class MemorySearchResponse(BaseModel):
    ok: bool
    query: str
    k: int
    results: List[Dict[str, Any]]

# --- RAG models ---
class ChatRAGRequest(BaseModel):
    query: str
    user_id: str = "default"
    k: int = 6

class ChatRAGResponse(BaseModel):
    reply: str
    model: Optional[str] = None
    latency_ms: Optional[int] = None
    sources: List[str] = Field(default_factory=list)

# --- Security models ---
class AuthLoginRequest(BaseModel):
    password: str

class AuthLoginResponse(BaseModel):
    ok: bool
    token: Optional[str] = None

class AuthLockResponse(BaseModel):
    ok: bool

class SecureStatusResponse(BaseModel):
    ok: bool
    status: Dict[str, Any]

# === вспомогательное ===
def _recent_texts(user_id: str, k: int = 2) -> List[str]:
    rows = summarizer.recent(user_id=user_id, limit=k)
    return [text for (text, _md) in rows]

def _retrieve_relevant(user_id: str, query: str, k: int = 6) -> List[str]:
    try:
        from .memory.manager import retrieve_relevant as mm_retrieve
        blocks = mm_retrieve(user_id=user_id, query=query, k=k) or []
        return [b if isinstance(b, str) else str(b) for b in blocks]
    except Exception:
        return _recent_texts(user_id, k=2)

def _truncate_blocks(blocks: List[str], max_chars: int = 3000) -> List[str]:
    out, total = [], 0
    for b in blocks:
        blen = len(b)
        if total + blen <= max_chars:
            out.append(b); total += blen
        else:
            remain = max_chars - total
            if remain > 0:
                out.append(b[:remain])
            break
    return out

def _messages_from_req(req: ChatRequest, injected: List[str]) -> List[Dict[str, Any]]:
    msgs: List[Dict[str, Any]] = []
    if injected:
        sys_block = "Короткая память:\n" + "\n\n".join(f"— {t}" for t in injected)
        msgs.append({"role": "system","content": sys_block,"metadata": {"session_id": req.session_id}})
    msgs.append({"role": "user","content": req.message,"metadata": {"session_id": req.session_id}})
    return msgs

def _require_auth(authorization: Optional[str] = Header(None)) -> None:
    """
    Проверка Bearer: токен обязателен и должен проходить verify_token внутри security.py.
    Больше не используем STATE.session_token.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    if is_locked():
        # интерфейс заблокирован — запрет
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Interface is locked")
    token = authorization.split(" ", 1)[1].strip()
    # используем verify_token через secure middleware (он вызовется на роутере secure).
    # здесь делаем простую проверку через back-compat: issue_session/verify_token реализованы в security.py.
    from .security import verify_token  # локальный импорт, чтобы избежать циклов
    verify_token(token)  # бросит 401 при проблеме

# === LLM через Ollama (non-stream) ===
def _ollama_chat(messages: List[Dict[str, Any]], model: Optional[str] = None, timeout: int = 45) -> Dict[str, Any]:
    host = OLLAMA_HOST
    model = model or OLLAMA_MODEL
    payload = {
        "model": model,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") in {"system","user","assistant"}],
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

# === инструменты ===
def _run_tool(name: str, params: dict | None):
    params = params or {}
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
        return JSONResponse(status_code=400, content=ToolResponse(ok=False, tool=req.name, error=str(e)).dict())

# === Security API ===
@app.post("/auth/login", response_model=AuthLoginResponse)
def auth_login(body: AuthLoginRequest):
    if not verify_password(body.password):
        return JSONResponse(status_code=401, content=AuthLoginResponse(ok=False).dict())
    token = issue_session()
    return AuthLoginResponse(ok=True, token=token)

@app.post("/auth/lock", response_model=AuthLockResponse)
def auth_lock():
    # мягкая блокировка интерфейса через secure/action можно делать тоже
    from .security import lock as sec_lock
    sec_lock()
    return AuthLockResponse(ok=True)

@app.get("/secure/status", response_model=SecureStatusResponse)
def secure_status_api():
    return SecureStatusResponse(ok=True, status=secure_status())

# === Memory API (защищено Bearer) ===
@app.post("/memory/add", response_model=MemoryAddResponse)
def memory_add(body: MemoryAddRequest, authorization: Optional[str] = Header(None)):
    _require_auth(authorization)
    from .memory import manager
    texts: List[str] = []
    metas: List[Dict[str, Any]] = []
    if body.text:
        texts.append(body.text); metas.append(body.meta or {})
    if body.texts:
        texts.extend(body.texts)
        if body.metas and len(body.metas) == len(body.texts):
            metas.extend(body.metas)
        else:
            metas.extend([{} for _ in body.texts])
    if not texts:
        return JSONResponse(status_code=400, content={"ok": False, "added": 0, "ids": []})
    for m in metas:
        m.setdefault("user_id", body.user_id)
    ids = manager.add_memory(body.user_id, texts, metas)
    return MemoryAddResponse(ok=True, added=len(ids), ids=ids)

@app.get("/memory/search", response_model=MemorySearchResponse)
def memory_search(q: str = Query(..., min_length=1), k: int = Query(5, ge=1, le=20),
                  user_id: str = "default", authorization: Optional[str] = Header(None)):
    _require_auth(authorization)
    try:
        from .memory.manager import retrieve_relevant
        blocks = retrieve_relevant(user_id=user_id, query=q, k=k) or []
        results = [{"text": b} for b in blocks]
        return MemorySearchResponse(ok=True, query=q, k=k, results=results)
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "query": q, "k": k, "results": [], "error": str(e)})

# === /chat_rag (защищено Bearer) ===
@app.post("/chat_rag", response_model=ChatRAGResponse)
def chat_rag(req: ChatRAGRequest, authorization: Optional[str] = Header(None)):
    _require_auth(authorization)
    start = time.perf_counter()
    blocks = _retrieve_relevant(req.user_id, req.query, k=req.k)
    if not blocks:
        reply = "Недостаточно контекста в памяти. Добавьте данные или уточните запрос."
        return ChatRAGResponse(reply=reply, model=OLLAMA_MODEL, latency_ms=int((time.perf_counter()-start)*1000), sources=[])
    messages = build_messages_with_rag(req.query, blocks)
    out = _ollama_chat(messages)
    reply = out["text"] or "(LLM пусто)"
    latency_ms = int((time.perf_counter() - start) * 1000)
    try:
        add_memory(req.user_id, [f"user(RAG): {req.query}", "assistant(RAG): " + reply[:2000]],
                   metas=[{"type":"chat_rag"},{"type":"chat_rag"}])
    except Exception:
        pass
    return ChatRAGResponse(reply=reply, model=OLLAMA_MODEL, latency_ms=latency_ms, sources=blocks[:req.k])

# === /chat (stream + non-stream) ===
@app.post("/chat")
async def chat(req: ChatRequest):
    mem_blocks = _retrieve_relevant(req.user_id or "default", req.message, k=6)
    injected = _truncate_blocks(mem_blocks, max_chars=3000)
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
            pass
    messages = _messages_from_req(req, injected)
    sys_prompt = (
        "Ты — техлид проекта AIR4 на macOS.\n"
        "Если в системном сообщении есть блок 'Веб-контекст', считай его единственным источником истины.\n"
        "Отвечай строго в формате:\n"
        "1) Цель (1–2 строки)\n"
        "2) Шаги (zsh/код)\n"
        "3) Проверка\n"
        "4) Что сохранить\n"
        "Правила: точность, минимум воды."
    )
    full_messages = [{"role": "system", "content": sys_prompt}, *messages]

    if req.stream:
        async def gen():
            start = time.perf_counter()
            buf: List[str] = []
            url = f"{OLLAMA_HOST}/api/chat"
            payload = {
                "model": OLLAMA_MODEL,
                "messages": [{"role": m["role"], "content": m["content"]} for m in full_messages],
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
            try:
                summarizer.summarize_session(messages, user_id=req.user_id, session_id=req.session_id)
            except Exception:
                pass
            try:
                add_memory(req.user_id or "default", [f"user: {req.message}", "assistant: " + "".join(buf)[:2000]],
                           metas=[{"type":"chat"}, {"type":"chat"}])
            except Exception:
                pass
            tail = json.dumps({"meta": {
                "model": OLLAMA_MODEL,
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }}, ensure_ascii=False)
            yield f"\n\n[[META]] {tail}\n"
        return StreamingResponse(gen(), media_type="text/plain")

    start = time.perf_counter()
    try:
        if os.getenv("LLM_PROVIDER", "ollama").lower() == "ollama":
            out = _ollama_chat(full_messages)
            reply = out["text"]; meta = out["metrics"] or {}
        else:
            reply = llm_client.chat_complete(full_messages); meta = {}
        if not reply:
            reply = "(LLM вернул пусто) Я получил: " + req.message
    except Exception as e:
        reply = f"(LLM не доступен: {e}) Я получил: {req.message}"; meta = {}
    saved_summary: Optional[str] = None
    if req.end_session:
        saved = summarizer.summarize_session(messages, user_id=req.user_id, session_id=req.session_id)
        saved_summary = saved.get("summary")
    try:
        add_memory(req.user_id or "default", [f"user: {req.message}", "assistant: " + (reply or "")[:2000]],
                   metas=[{"type":"chat"}, {"type":"chat"}])
    except Exception:
        pass
    latency_ms = int((time.perf_counter() - start) * 1000)
    return ChatResponse(
        reply=reply, injected_summaries=injected, summary=saved_summary, model=OLLAMA_MODEL,
        prompt_tokens=meta.get("prompt_eval_count"), completion_tokens=meta.get("eval_count"),
        latency_ms=latency_ms, memory_used=injected or None,
    )
