# backend/app/main.py — AIr4 v0.8.1 (Phase 9 — Chroma backend + UI)
from __future__ import annotations

import os
import re
import time
import json
import uuid
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, List, Dict
from urllib.parse import urlparse
from html.parser import HTMLParser

from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from backend.app.routes_memory import router as memory_router
from backend.app import chat as chat_mod

from backend.app.routes_ingest import router as ingest_router


# Phase-9: импорт менеджера памяти
from backend.app.memory.manager_chroma import ChromaMemoryManager

# -----------------------------------------------------------------------------
# Конфиг / лог
# -----------------------------------------------------------------------------
log = logging.getLogger("uvicorn.error")
APP_VERSION = os.getenv("AIR4_VERSION", "0.8.1-ui-mvp")
PORT = int(os.getenv("PORT", "8000"))

AIR4_OFFLINE = os.getenv("AIR4_OFFLINE", "1").strip() not in ("0", "false", "False")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL_DEFAULT = os.getenv("OLLAMA_MODEL_DEFAULT", "llama3.1:8b")
MAX_UPLOAD_BYTES = int(os.getenv("AIR4_MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))

def _require_local(url: str):
    if not AIR4_OFFLINE:
        return
    host = urlparse(url).hostname or ""
    if host not in ("127.0.0.1", "localhost"):
        raise RuntimeError(f"AIR4_OFFLINE=1: remote host blocked: {host}")

_require_local(OLLAMA_BASE_URL)

# -----------------------------------------------------------------------------
# Приложение
# -----------------------------------------------------------------------------
app = FastAPI(title="AIr4", version=APP_VERSION)
app.include_router(memory_router)
app.include_router(ingest_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Memory backend (Phase-9)
# -----------------------------------------------------------------------------
_app_memory = None

def get_memory():
    return _app_memory

@app.on_event("startup")
async def _memory_startup():
    """Инициализация backend памяти"""
    global _app_memory
    backend = os.getenv("AIR4_MEMORY_BACKEND", "fallback")
    force_fb = os.getenv("AIR4_MEMORY_FORCE_FALLBACK", "1") == "1"
    if backend == "chroma" and not force_fb:
        persist_dir = os.getenv("AIR4_CHROMA_DIR", "./storage/chroma")
        collection = os.getenv("AIR4_CHROMA_COLLECTION", "air4_memory")
        model_path = os.getenv("AIR4_EMBED_MODEL_PATH", "./models/bge-m3")
        _app_memory = ChromaMemoryManager(
            persist_dir=persist_dir,
            collection=collection,
            model_path=model_path,
        )
    else:
        _app_memory = None

    try:
        app.state.memory_manager = _app_memory
    except Exception:
        pass

# -----------------------------------------------------------------------------
# Health / Debug
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    mem = get_memory()
    memory_info = {
        "backend": "chroma" if mem is not None else "fallback",
        "count": -1,
        "persist_dir": os.getenv("AIR4_CHROMA_DIR", "./storage/chroma"),
        "collection": os.getenv("AIR4_CHROMA_COLLECTION", "air4_memory"),
        "embed_model": os.getenv("AIR4_EMBED_MODEL_PATH", "./models/bge-m3"),
    }
    if mem is not None:
        try:
            memory_info["count"] = mem.count()
        except Exception:
            pass

    return {
        "ok": True,
        "status": "up",
        "version": APP_VERSION,
        "offline": AIR4_OFFLINE,
        "model": OLLAMA_MODEL_DEFAULT,
        "memory": memory_info,
        "memory_backend": memory_info["backend"],
        "ollama_base_url": OLLAMA_BASE_URL,
    }

# -----------------------------------------------------------------------------
# Директории проекта
# -----------------------------------------------------------------------------
def _find_dir(start: Path, name: str) -> Path:
    for base in [start, *start.parents]:
        p = base / name
        if p.exists():
            return p
    p = start / name
    p.mkdir(parents=True, exist_ok=True)
    return p

HERE          = Path(__file__).resolve().parent
TEMPLATES_DIR = _find_dir(HERE, "templates")
STATIC_DIR    = _find_dir(HERE, "static")
STORAGE_DIR   = _find_dir(HERE, "storage")
INGEST_DIR    = STORAGE_DIR / "ingest"
UPLOADS_DIR   = STORAGE_DIR / "uploads"
SUMMARY_DIR   = STORAGE_DIR / "summaries"
SESSIONS_DIR  = STORAGE_DIR / "sessions"
for d in (INGEST_DIR, UPLOADS_DIR, SUMMARY_DIR, SESSIONS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------------
# UI bootstrap
# -----------------------------------------------------------------------------
try:
    from ui_bootstrap import attach_ui
    attach_ui(app)
except Exception as e:
    log.warning(f"[UI] ui_bootstrap.attach_ui не подключён: {e}")

try:
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
except Exception:
    pass
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

def _render_or_hint(request: Request, template_name: str, title: str):
    path = TEMPLATES_DIR / template_name
    if path.exists():
        return templates.TemplateResponse(template_name, {"request": request, "session_id": ""})
    return PlainTextResponse(f"[UI] Ожидался шаблон: {path}", status_code=500)

@app.get("/ui", response_class=HTMLResponse)
async def ui_index(request: Request):      return _render_or_hint(request, "index.html", "AIr4 — GUI")
@app.get("/ui/chat", response_class=HTMLResponse)
async def ui_chat(request: Request):       return _render_or_hint(request, "chat.html", "AIr4 — Chat")
@app.get("/ui/ingest", response_class=HTMLResponse)
async def ui_ingest(request: Request):     return _render_or_hint(request, "ingest.html", "AIr4 — Ingest")
@app.get("/ui/todos", response_class=HTMLResponse)
async def ui_todos(request: Request):      return _render_or_hint(request, "todos.html", "AIr4 — Todos")
@app.get("/ui/summaries", response_class=HTMLResponse)
async def ui_summaries(request: Request):  return _render_or_hint(request, "summaries.html", "AIr4 — Summaries")

# -----------------------------------------------------------------------------
# История сообщений
# -----------------------------------------------------------------------------
def _now() -> str: return datetime.utcnow().isoformat() + "Z"

def _session_path(sid: str) -> Path:
    safe = "".join(c for c in sid if c.isalnum() or c in ("-", "_", "."))
    return SESSIONS_DIR / f"{safe}.jsonl"

def _load_history(sid: str, limit: int = 12) -> List[Dict[str, str]]:
    path = _session_path(sid)
    if not path.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in path.read_text().splitlines()[-limit:]:
        try:
            obj = json.loads(line)
            if obj.get("role") in ("system", "user", "assistant") and obj.get("content"):
                out.append({"role": obj["role"], "content": obj["content"]})
        except Exception:
            continue
    return out

def _append_message(sid: str, role: str, content: str):
    rec = {"role": role, "content": content, "ts": _now()}
    with _session_path(sid).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def _gen_session_id() -> str:
    return str(uuid.uuid4())[:12]

# -----------------------------------------------------------------------------
# Chat (legacy /chat для скриптов)
# -----------------------------------------------------------------------------
@app.post("/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    msg = str(data.get("message","")).strip()
    if not msg: raise HTTPException(status_code=400, detail="message required")
    return {"ok": True, "echo": msg}

@app.get("/sessions/{sid}")
async def get_session(sid: str):
    return {"session_id": sid, "messages": _load_history(sid, limit=100)}

@app.post("/sessions/{sid}/clear")
async def clear_session(sid: str):
    p = _session_path(sid)
    if p.exists(): p.unlink()
    return {"ok": True}

# -----------------------------------------------------------------------------
# UI-прокси (RAG)
# -----------------------------------------------------------------------------
class UiSendBody(BaseModel):
    message: str
    session_id: str | None = None
    use_rag: bool = True
    k_memory: int = Field(4, ge=1, le=50)

@app.post("/ui/chat/send")
async def ui_chat_send(body: UiSendBody):
    sid = body.session_id or _gen_session_id()
    try:
        _append_message(sid, "user", body.message)
    except Exception: pass

    result = await chat_mod.chat_endpoint_call({**body.dict(), "session_id": sid})
    reply_text = result.get("reply","")

    try:
        _append_message(sid, "assistant", reply_text)
    except Exception: pass

    return {
        "reply": reply_text,
        "session_id": sid,
        "memory_used": result.get("memory_used") or [],
    }

# -----------------------------------------------------------------------------
# /models — список из Ollama (/api/tags), кэш
# -----------------------------------------------------------------------------
_MODELS_CACHE = {"ts": 0.0, "data": [{"id": OLLAMA_MODEL_DEFAULT, "title": OLLAMA_MODEL_DEFAULT}]}
_MODELS_TTL = 30.0

@app.get("/models")
async def models_proxy():
    now = time.time()
    if now - _MODELS_CACHE["ts"] < _MODELS_TTL:
        return JSONResponse(_MODELS_CACHE["data"])
    try:
        import httpx
        _require_local(OLLAMA_BASE_URL)
        url = f"{OLLAMA_BASE_URL}/api/tags"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
        if r.status_code == 200:
            data = r.json() or {}
            models = []
            for m in (data.get("models") or []):
                name = m.get("name")
                if name:
                    models.append({"id": name, "title": name})
            if models:
                _MODELS_CACHE["data"] = models
                _MODELS_CACHE["ts"] = now
                return JSONResponse(models)
    except Exception as e:
        log.debug(f"[UI] /models (ollama) fallback: {e}")
    _MODELS_CACHE["ts"] = now
    return JSONResponse(_MODELS_CACHE["data"])

# -----------------------------------------------------------------------------
# Ingest: URL + File + Recent
# -----------------------------------------------------------------------------
def _route_exists(path: str, method: str) -> bool:
    m = method.upper()
    for r in app.router.routes:
        if getattr(r, "path", "") == path and m in getattr(r, "methods", set()):
            return True
    return False

if not _route_exists("/ingest/url", "POST"):
    @app.post("/ingest/url")
    async def ingest_url(payload: dict):
        url = (payload or {}).get("url", "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="Field 'url' is required")
        sid = "ing-" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        rec = {
            "type": "url",
            "url": url,
            "session_id": sid,
            "ts": datetime.utcnow().isoformat() + "Z",
        }
        (INGEST_DIR / f"{sid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        return {"ok": True, "session_id": sid}

if not _route_exists("/ingest/file", "POST"):
    @app.post("/ingest/file")
    async def ingest_file(file: UploadFile = File(...)):
        if not file or not file.filename:
            raise HTTPException(status_code=400, detail="Upload 'file' is required")
        blob = await file.read()

        if len(blob) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"File too large (>{MAX_UPLOAD_BYTES} bytes)")

        sid = "ing-" + uuid.uuid4().hex[:10]
        save_path = UPLOADS_DIR / f"{sid}-{file.filename}"
        save_path.write_bytes(blob)

        rec = {
            "type": "file",
            "filename": file.filename,
            "path": str(save_path),
            "size": len(blob),
            "session_id": sid,
            "ts": datetime.utcnow().isoformat() + "Z",
        }
        (INGEST_DIR / f"{sid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        return {"ok": True, "session_id": sid}

# --- Recent ingests ----------------------------------------------------------
def _list_recent_ingests(limit: int = 20) -> list[dict]:
    items = []
    for p in sorted(INGEST_DIR.glob("ing-*.json")):
        try:
            rec = json.loads(p.read_text())
            sid = p.stem
            kind = rec.get("type")
            src  = rec.get("url") or rec.get("filename") or rec.get("path") or ""
            ts   = rec.get("ts") or ""
            items.append({"session_id": sid, "type": kind, "source": src, "ts": ts})
        except Exception:
            continue
    # sort by ts desc
    items.sort(key=lambda x: x.get("ts") or "", reverse=True)
    return items[:limit]

@app.get("/ingest/recent")
async def ingest_recent(limit: int = 20):
    limit = max(1, min(int(limit), 100))
    return JSONResponse(_list_recent_ingests(limit))

# -----------------------------------------------------------------------------
# Summary helpers и эндпоинты
# -----------------------------------------------------------------------------
def _summary_path(sid: str) -> Path:
    return SUMMARY_DIR / f"{sid}.json"

def _load_json_file(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default

def _make_placeholder_summary(sid: str) -> dict:
    ingest = _load_json_file(INGEST_DIR / f"{sid}.json", {})
    src = ingest.get("url") or ingest.get("filename") or ingest.get("path") or "unknown source"
    t = ingest.get("ts") or datetime.utcnow().isoformat() + "Z"
    return {
        "session_id": sid,
        "tldr": f"Placeholder summary for '{sid}'. Source: {src}. Ingested at {t}.",
        "facts": [f"source: {src}", f"ingested_at: {t}", "status: placeholder"],
        "todos": [],
    }

class _HTMLToText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: List[str] = []
    def handle_data(self, data: str):
        if data.strip():
            self.parts.append(data.strip())
    def text(self) -> str:
        s = " ".join(self.parts)
        return re.sub(r"\s+", " ", s).strip()

async def _fetch_url_text(url: str) -> str:
    if AIR4_OFFLINE:
        raise HTTPException(status_code=409, detail="AIR4_OFFLINE=1: fetching remote URLs is disabled. Use file upload or set AIR4_OFFLINE=0.")
    import httpx
    timeout = httpx.Timeout(20.0, read=40.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent":"air4/0.8"}) as client:
        r = await client.get(url)
    r.raise_for_status()
    ctype = r.headers.get("content-type","").lower()
    if "text/plain" in ctype:
        return r.text
    # naive HTML → text
    parser = _HTMLToText()
    parser.feed(r.text)
    return parser.text()

def _read_pdf_text(path: Path) -> str:
    """Чтение PDF локально через pypdf. Возвращает plain-text."""
    try:
        from pypdf import PdfReader
    except Exception as e:
        return f"[pdf reader not available: install 'pypdf' — {e}]"
    try:
        reader = PdfReader(str(path))
    except Exception as e:
        return f"[failed to open pdf: {e}]"
    parts: List[str] = []
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception as e:
            txt = f"[page {i+1}: extract_text failed: {e}]"
        if txt.strip():
            parts.append(txt.strip())
    text = "\n\n".join(parts).strip()
    if not text:
        return "[empty or scanned PDF (OCR required)]"
    # нормализуем пробелы
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def _read_file_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf_text(path)
    if suffix in (".txt", ".md", ".log", ".csv"):
        return path.read_text(errors="ignore")
    # простая попытка как текст
    try:
        return path.read_text(errors="ignore")
    except Exception:
        return f"[unsupported file format: {suffix}]"

def _truncate_for_model(text: str, max_chars: int = 12000) -> str:
    text = text.strip()
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n…[truncated]…"
    return text

async def _summarize_to_json(model: str, raw_text: str) -> dict:
    content = _truncate_for_model(raw_text)
    system = (
        "Ты помогаешь делать краткие выжимки. "
        "Ответ ВСЕГДА в формате строго валидного JSON UTF-8 без комментариев и подсказок. "
        "Ключи: tldr (строка, 2–4 предложения), facts (массив коротких фактов), todos (массив задач в повелительном наклонении)."
    )
    user = (
        "Суммируй следующий текст. Верни только JSON.\n"
        "Текст между тройными углами:\n<<<\n" + content + "\n>>>"
    )
    messages = [{"role":"system","content":system},{"role":"user","content":user}]
    try:
        raw = await _ollama_chat_complete(OLLAMA_MODEL_DEFAULT, messages)
    except Exception as e:
        log.warning(f"[summary] ollama failed: {e}")
        return {"tldr":"(ошибка LLM)", "facts":[], "todos":[]}

    txt = raw.strip()
    if txt.startswith("```"):
        i = txt.find("{"); j = txt.rfind("}")
        if i >= 0 and j > i:
            txt = txt[i:j+1]
    try:
        obj = json.loads(txt)
        tldr  = str(obj.get("tldr","")).strip()
        facts = [str(x) for x in (obj.get("facts") or [])][:50]
        todos = [str(x) for x in (obj.get("todos") or [])][:50]
        return {"tldr": tldr, "facts": facts, "todos": todos}
    except Exception:
        log.warning("[summary] JSON parse failed; returning fallback")
        return {"tldr": txt[:800], "facts": [], "todos": []}

@app.get("/memory/summary/{sid}")
async def get_summary(sid: str):
    path = _summary_path(sid)
    if path.exists():
        return JSONResponse(_load_json_file(path, {}))
    return JSONResponse(_make_placeholder_summary(sid))

@app.post("/memory/summarize/{sid}")
async def summarize_now(sid: str):
    ingest = _load_json_file(INGEST_DIR / f"{sid}.json", {})
    if not ingest:
        raise HTTPException(status_code=404, detail="Ingest record not found")

    text_source = ""
    if ingest.get("type") == "url":
        url = ingest.get("url","")
        if not url:
            raise HTTPException(status_code=400, detail="Empty URL")
        text_source = await _fetch_url_text(url)
    elif ingest.get("type") == "file":
        p = Path(ingest.get("path",""))
        if not p.exists():
            raise HTTPException(status_code=404, detail="Uploaded file not found")
        text_source = _read_file_text(p)
    else:
        raise HTTPException(status_code=400, detail="Unknown ingest type")

    summary = await _summarize_to_json(OLLAMA_MODEL_DEFAULT, text_source)
    data = {"session_id": sid, **summary}
    _summary_path(sid).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return {"ok": True, "session_id": sid}

# -----------------------------------------------------------------------------
# TODOS: файловое CRUD-хранилище
# -----------------------------------------------------------------------------
TODOS_PATH = STORAGE_DIR / "todos.json"

def _load_todos() -> list[dict]:
    if TODOS_PATH.exists():
        try:
            return json.loads(TODOS_PATH.read_text()) or []
        except Exception:
            pass
    return []

def _save_todos(items: list[dict]) -> None:
    tmp = TODOS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2))
    tmp.replace(TODOS_PATH)

def _new_todo(text: str) -> dict:
    h = hashlib.sha1(f"{text}|{uuid.uuid4().hex}".encode("utf-8")).hexdigest()[:10]
    now = datetime.utcnow().isoformat() + "Z"
    return {"h": h, "text": text, "done": False, "ts": now, "updated_at": now}

@app.get("/todos")
async def list_todos(): return JSONResponse(_load_todos())

@app.post("/todos")
async def add_todo(payload: dict):
    text = (payload or {}).get("text") or (payload or {}).get("title")
    if not text or not str(text).strip():
        raise HTTPException(status_code=400, detail="Field 'text' is required")
    items = _load_todos()
    items.insert(0, _new_todo(str(text).strip()))
    _save_todos(items)
    return {"ok": True}

def _find_idx(items: list[dict], h: str) -> int:
    for i, it in enumerate(items):
        if it.get("h") == h:
            return i
    return -1

@app.post("/todos/{h}/done")
async def todo_done(h: str):
    items = _load_todos()
    i = _find_idx(items, h)
    if i < 0: raise HTTPException(status_code=404, detail="Not found")
    items[i]["done"] = True; items[i]["updated_at"] = datetime.utcnow().isoformat() + "Z"
    _save_todos(items); return {"ok": True}

@app.post("/todos/{h}/undo")
async def todo_undo(h: str):
    items = _load_todos()
    i = _find_idx(items, h)
    if i < 0: raise HTTPException(status_code=404, detail="Not found")
    items[i]["done"] = False; items[i]["updated_at"] = datetime.utcnow().isoformat() + "Z"
    _save_todos(items); return {"ok": True}

@app.delete("/todos/{h}")
async def todo_delete(h: str):
    items = _load_todos()
    i = _find_idx(items, h)
    if i < 0: raise HTTPException(status_code=404, detail="Not found")
    del items[i]; _save_todos(items); return {"ok": True}

# -----------------------------------------------------------------------------
# Локальный запуск
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=PORT, reload=False, log_level="info")
