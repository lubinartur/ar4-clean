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
try:
    from backend.app.ingest import fetch_url_text, parse_pdf_bytes, synth_session_id
except ModuleNotFoundError:
    from .ingest import fetch_url_text, parse_pdf_bytes, synth_session_id


app = FastAPI()

# ----- CORS -----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_TOKENS: set[str] = set()
MEMORY = MemoryManager()
SUM = Summarizer(llm_fn=chat_llm)


# ================== BASIC ==================

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

    history = MEMORY.fetch_history(user_id=x_user, session_id=x_session, k=20)

    ing = MEMORY.get_recent_ingest(user_id=x_user, limit=3)
    if ing:
        ctx_blocks: List[str] = []
        for r in ing:
            meta = r.get("meta", {}) or {}
            tag = f"[{meta.get('type','doc')}:{meta.get('filename') or meta.get('url') or r.get('doc_id')}]"
            snippet = (r.get("text") or "")[:1200]
            ctx_blocks.append(f"{tag}\n{snippet}")
        rag_context = "\n\n".join(ctx_blocks)
        sys_ctx = (x_system_prompt or "") + f"\n\n[CONTEXT FROM INGEST]\n{rag_context}\n[/CONTEXT]\n"
    else:
        sys_ctx = x_system_prompt

    if stream:
        async def gen():
            full: List[str] = []
            try:
                agen = await chat_llm(
                    user_msg, history=history, system=sys_ctx,
                    model=model, stream=True
                )
                async for chunk in agen:
                    delta = chunk.get("delta") or ""
                    if delta:
                        full.append(delta)
                        yield delta
            except Exception as e:
                yield f"[stream error] {type(e).__name__}: {e}"
                return

            full_text = "".join(full)
            try:
                background.add_task(SUM.summarize_and_store,
                                    user_id=x_user, session_id=x_session,
                                    user_msg=user_msg, assistant_msg=full_text)
                MEMORY.append_turn(x_user, x_session, "user", user_msg)
                MEMORY.append_turn(x_user, x_session, "assistant", full_text)
            except Exception:
                pass

        return StreamingResponse(gen(), media_type="text/plain")

    # non-stream
    try:
        reply = await chat_llm(
            user_msg, history=history, system=sys_ctx,
            model=model, stream=False
        )
        text = reply.get("text") if isinstance(reply, dict) else str(reply)
    except Exception as e:
        return {"ok": False, "error": "chat_llm_failed", "detail": f"{type(e).__name__}: {e}"}

    try:
        background.add_task(
            SUM.summarize_and_store,
            user_id=x_user, session_id=x_session,
            user_msg=user_msg, assistant_msg=text
        )
        MEMORY.append_turn(x_user, x_session, "user", user_msg)
        MEMORY.append_turn(x_user, x_session, "assistant", text)
    except Exception:
        pass

    return {"ok": True, "reply": text}


# ================== MEMORY ==================

@app.get("/memory/summary/{session_id}")
def get_summary(session_id: str, x_user: Optional[str] = Header(default="dev", alias="X-User")):
    s = MEMORY.get_summary(user_id=x_user, session_id=session_id)
    return {"ok": True, "summary": s}


@app.post("/memory/summarize/{session_id}")
async def force_summarize(session_id: str, request: Request, x_user: Optional[str] = Header(default="dev", alias="X-User")):
    body = await request.json()
    user_msg = body.get("user_msg", "")
    assistant_msg = body.get("assistant_msg", "")
    await SUM.summarize_and_store(
        user_id=x_user, session_id=session_id,
        user_msg=user_msg, assistant_msg=assistant_msg
    )
    return {"ok": True}


# ================== TODOS ==================

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
async def todos_create(request: Request, x_user: Optional[str] = Header(default="dev", alias="X-User"), x_session: Optional[str] = Header(default=None, alias="X-Session")):
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


# ================== INGEST ==================

@app.post("/ingest/url")
async def ingest_url(request: Request, background: BackgroundTasks, x_user: Optional[str] = Header(default="dev", alias="X-User"), x_session: Optional[str] = Header(default=None, alias="X-Session")):
    body = await request.json()
    url = (body.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "url_required"}

    text, content_type = await fetch_url_text(url)
    if not text:
        return {"ok": False, "error": "empty_text_from_url"}

    session_id = x_session or synth_session_id("url", url)
    MEMORY.save_ingest_raw(x_user, session_id, text, {"type": "url", "url": url, "content_type": content_type})
    MEMORY.add_rag_document(x_user, session_id, text, {"type": "url", "url": url})
    background.add_task(
        SUM.summarize_and_store,
        user_id=x_user, session_id=session_id,
        user_msg=f"INGEST URL: {url}",
        assistant_msg=text
    )
    return {"ok": True, "session_id": session_id, "chars": len(text)}


@app.post("/ingest/file")
async def ingest_file(background: BackgroundTasks, x_user: Optional[str] = Header(default="dev", alias="X-User"), x_session: Optional[str] = Header(default=None, alias="X-Session"), file: UploadFile = File(...)):
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
