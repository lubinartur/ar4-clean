from __future__ import annotations

from typing import Optional, List
import os
import secrets

import httpx
from fastapi import FastAPI, Request, BackgroundTasks, Header, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.app.llm_ollama import chat_llm, DEFAULT_MODEL
from backend.app.memory.manager import MemoryManager
from backend.app.memory.summarizer import Summarizer
from backend.app.ingest import fetch_url_text, parse_pdf_bytes, synth_session_id


app = FastAPI()

# ----- CORS -----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----- Auth store (in-memory demo) -----
VALID_TOKENS: set[str] = set()

# ----- Globals -----
MEMORY = MemoryManager()
SUM = Summarizer(llm_fn=chat_llm)


# ================== BASIC ENDPOINTS ==================

@app.get("/health")
def health():
    return {"ok": True, "status": "up"}


@app.post("/auth/login")
async def auth_login(request: Request):
    data = await request.json()
    pwd = data.get("password", "")
    expected = os.getenv("AUTH_PASSWORD", "0000")
    if pwd != expected:
        return {"ok": False, "error": "invalid_password"}
    token = secrets.token_hex(16)
    VALID_TOKENS.add(token)
    return {"ok": True, "token": token}


@app.get("/models")
async def list_models():
    """
    Список моделей из Ollama; если недоступно — возвращаем дефолтную.
    """
    try:
        base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        async with httpx.AsyncClient(base_url=base, timeout=httpx.Timeout(10, read=10)) as client:
            r = await client.get("/api/tags")
            r.raise_for_status()
            data = r.json()
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            if not models:
                models = [DEFAULT_MODEL]
            return {"ok": True, "models": models}
    except Exception:
        return {"ok": True, "models": [DEFAULT_MODEL], "warning": "ollama_unreachable"}


# ================== CHAT ==================

@app.post("/chat")
async def chat(
    request: Request,
    background: BackgroundTasks,
    x_system_prompt: Optional[str] = Header(default=None, alias="X-System-Prompt"),
    x_model: Optional[str] = Header(default=None, alias="X-Model"),
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
    x_session: Optional[str] = Header(default=None, alias="X-Session"),
):
    data = await request.json()
    user_msg = data.get("message", "")
    stream = bool(data.get("stream", False))
    model = x_model or DEFAULT_MODEL

    # 1) История для контекста (диалоговая память)
    history = MEMORY.fetch_history(user_id=x_user, session_id=x_session, k=20)

    if stream:
        async def gen():
            full: List[str] = []
            agen = await chat_llm(
                user_msg, history=history, system=x_system_prompt,
                model=model, stream=True
            )
            async for chunk in agen:
                delta = chunk.get("delta") or ""
                if delta:
                    full.append(delta)
                    yield delta
            full_text = "".join(full)

            # 2) Авто‑саммари — в фоне
            background.add_task(
                SUM.summarize_and_store,
                user_id=x_user, session_id=x_session,
                user_msg=user_msg, assistant_msg=full_text
            )
            # 3) История — в конец
            MEMORY.append_turn(x_user, x_session, "user", user_msg)
            MEMORY.append_turn(x_user, x_session, "assistant", full_text)

        return StreamingResponse(gen(), media_type="text/plain")

    # non‑stream
    reply = await chat_llm(
        user_msg, history=history, system=x_system_prompt,
        model=model, stream=False
    )
    text = reply.get("text") if isinstance(reply, dict) else str(reply)

    # авто‑саммари в фоне
    background.add_task(
        SUM.summarize_and_store,
        user_id=x_user, session_id=x_session,
        user_msg=user_msg, assistant_msg=text
    )
    # история
    MEMORY.append_turn(x_user, x_session, "user", user_msg)
    MEMORY.append_turn(x_user, x_session, "assistant", text)

    return {"ok": True, "reply": text}


# ================== MEMORY (Summaries) ==================

@app.get("/memory/summary/{session_id}")
def get_summary(
    session_id: str,
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    s = MEMORY.get_summary(user_id=x_user, session_id=session_id)
    return {"ok": True, "summary": s}


@app.post("/memory/summarize/{session_id}")
async def force_summarize(
    session_id: str,
    request: Request,
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    body = await request.json()
    user_msg = body.get("user_msg", "")
    assistant_msg = body.get("assistant_msg", "")
    await SUM.summarize_and_store(
        user_id=x_user, session_id=session_id,
        user_msg=user_msg, assistant_msg=assistant_msg
    )
    return {"ok": True}


# ================== TODOS API (7.2) ==================

@app.get("/todos")
def todos_list(
    x_user: Optional[str] = Header(default=None, alias="X-User"),
    session_id: Optional[str] = Query(default=None),
    done: Optional[bool] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
):
    items = MEMORY.list_todos(user_id=x_user, session_id=session_id, done=done, limit=limit)
    return {"ok": True, "items": items}


@app.post("/todos")
async def todos_create(
    request: Request,
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
    x_session: Optional[str] = Header(default=None, alias="X-Session"),
):
    body = await request.json()
    text = (body.get("text") or "").strip()
    tags = body.get("tags") or ["manual"]
    if not text:
        return {"ok": False, "error": "text_required"}
    MEMORY.add_todos(user_id=x_user, session_id=x_session or "global", todos=[text], tags=tags, dedup=True)
    return {"ok": True}


@app.post("/todos/{h}/done")
def todos_set_done(h: str, done: Optional[bool] = Query(default=True)):
    changed = MEMORY.set_todo_done(h, done=done)
    return {"ok": changed}


@app.delete("/todos/{h}")
def todos_delete(h: str):
    ok = MEMORY.delete_todo(h)
    return {"ok": ok}


# ================== INGEST API (7.3) ==================

@app.post("/ingest/url")
async def ingest_url(
    request: Request,
    background: BackgroundTasks,
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
    x_session: Optional[str] = Header(default=None, alias="X-Session"),
):
    body = await request.json()
    url = (body.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "url_required"}

    text, content_type = await fetch_url_text(url)
    if not text:
        return {"ok": False, "error": "empty_text_from_url"}

    session_id = x_session or synth_session_id("url", url)

    # сырьё + RAG задел
    MEMORY.save_ingest_raw(x_user, session_id, text, {"type": "url", "url": url, "content_type": content_type})
    MEMORY.add_rag_document(x_user, session_id, text, {"type": "url", "url": url})

    # авто‑саммари по содержимому
    background.add_task(
        SUM.summarize_and_store,
        user_id=x_user, session_id=session_id,
        user_msg=f"INGEST URL: {url}",
        assistant_msg=text
    )
    return {"ok": True, "session_id": session_id, "chars": len(text)}


@app.post("/ingest/file")
async def ingest_file(
    background: BackgroundTasks,
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
    x_session: Optional[str] = Header(default=None, alias="X-Session"),
    file: UploadFile = File(...),
):
    raw = await file.read()
    filename = file.filename or "upload.bin"
    ctype = file.content_type or ""

    if "pdf" in ctype.lower() or filename.lower().endswith(".pdf"):
        text = parse_pdf_bytes(raw) or ""
    else:
        try:
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            text = raw.decode("latin-1", errors="ignore")

    text = text.strip()
    if not text:
        return {"ok": False, "error": "empty_text_from_file"}

    session_id = x_session or synth_session_id("file", filename)

    MEMORY.save_ingest_raw(x_user, session_id, text, {"type": "file", "filename": filename, "content_type": ctype})
    MEMORY.add_rag_document(x_user, session_id, text, {"type": "file", "filename": filename})

    background.add_task(
        SUM.summarize_and_store,
        user_id=x_user, session_id=session_id,
        user_msg=f"INGEST FILE: {filename}",
        assistant_msg=text[:50000]
    )
    return {"ok": True, "session_id": session_id, "chars": len(text)}
