# backend/app/main.py — AIr4 v0.12.1 (Phase-12 — UI/send3 + sessions + memory)
from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()

import os
import time
import uuid
from typing import Dict, Optional, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

# Phase-9+: memory + chat modules
try:
    from backend.app.memory.manager_chroma import ChromaMemoryManager  # Phase-9 backend
except Exception:
    from app.memory.manager_chroma import ChromaMemoryManager  # type: ignore

try:
    from backend.app import chat as chat_mod
except Exception:
    import app.chat as chat_mod  # type: ignore

# -----------------------------------------------------------------------------
# App + CORS
# -----------------------------------------------------------------------------
app = FastAPI(title="AIr4", version="0.12.1")
from .routes_chat import router as router_chat
app.include_router(router_chat, prefix="/chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static & Templates (UI)
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
_now = lambda: int(time.time())

# -----------------------------------------------------------------------------
# Sessions (in-memory dict; persisted messages live in Chroma via memory manager)
# -----------------------------------------------------------------------------
class Session(BaseModel):
    id: str
    title: str = "New session"
    created_at: int = Field(default_factory=_now)
    updated_at: int = Field(default_factory=_now)
    turns: int = 0  # quick stat for UI

_SESSIONS: Dict[str, Session] = {}


def ensure_session(session_id: Optional[str]) -> Session:
    if session_id and session_id in _SESSIONS:
        return _SESSIONS[session_id]
    sid = session_id or uuid.uuid4().hex[:8]
    sess = Session(id=sid)
    _SESSIONS[sid] = sess
    return sess

# -----------------------------------------------------------------------------
# Debug/Tools: simple memory search endpoint
# -----------------------------------------------------------------------------
from fastapi import Query
import inspect

def _mem_try_search(mem, q: str, k: int):
    """
    Универсальный адаптер: пробует разные сигнатуры .search(...)
    и возвращает список хитов или [].
    """
    fn = getattr(mem, "search", None)
    if not callable(fn):
        return []

    # Узнаем, какие параметры поддерживает функция
    try:
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())  # ['self', 'query', 'k'] или только ['self'] и т.п.
    except Exception:
        params = []

    # Набор попыток (от наиболее информативных к простым)
    attempts = []
    if "query" in params and "k" in params:
        attempts.append(lambda: fn(query=q, k=k))
    if "query" in params:
        attempts.append(lambda: fn(query=q))
    if "q" in params and "k" in params:
        attempts.append(lambda: fn(q=q, k=k))
    if "q" in params:
        attempts.append(lambda: fn(q=q))
    if "text" in params:
        attempts.append(lambda: fn(text=q))
    if "k" in params:
        attempts.append(lambda: fn(k=k))
    # как крайний случай — без аргументов
    attempts.append(lambda: fn())

    for call in attempts:
        try:
            res = call()
            return res or []
        except TypeError:
            continue
        except Exception:
            # если конкретная попытка упала — пробуем следующую
            continue
    return []

@app.get("/memory/search")
async def memory_search(
    q: str = Query(..., description="query text"),
    k: int = Query(5, ge=1, le=50),
    session_id: Optional[str] = Query(None),
):
    if MEMORY is None:
        raise HTTPException(status_code=503, detail="memory disabled")
    try:
        # Your manager's signature: search(*, user_id: str, query: str, k: int=5, score_threshold: float=0.0, dedup: bool=True)
        res = MEMORY.search(user_id="dev", query=q, k=k, score_threshold=0.2, dedup=True)

        # Extract list of items from dict-like response
        if isinstance(res, dict):
            items = res.get("results") or res.get("hits") or res.get("items") or res.get("data") or []
        else:
            items = res or []

        # Session filtering disabled: the current manager doesn't populate meta.session_id
        # Keeping the param for API compatibility, but ignoring it to avoid empty results.
        # If later meta.session_id appears in items, you can re-enable a guarded filter.

        # Normalize output
        out = []
        for it in items:
            if isinstance(it, dict):
                out.append({
                    "id": it.get("id"),
                    "text": it.get("text") or it.get("chunk") or it.get("content") or it.get("value"),
                    "score": it.get("score") or (it.get("meta") or {}).get("score"),
                    "meta": it.get("meta") or {},
                })
            else:
                out.append({
                    "id": getattr(it, "id", None),
                    "text": getattr(it, "text", None),
                    "score": getattr(it, "score", None),
                    "meta": getattr(it, "meta", {}) or {},
                })
        return {"ok": True, "results": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"search failed: {e}")

# -----------------------------------------------------------------------------
# Memory diagnostics endpoint
# -----------------------------------------------------------------------------

@app.get("/memory/debug")
async def memory_debug():
    if MEMORY is None:
        raise HTTPException(status_code=503, detail="memory disabled")
    import inspect as _insp

    def _callables(obj):
        out = []
        for name in dir(obj):
            if name.startswith("_"):
                continue
            attr = getattr(obj, name, None)
            if callable(attr):
                try:
                    sig = str(_insp.signature(attr))
                except Exception:
                    sig = "(?)"
                out.append(f"{name}{sig}")
        return sorted(out)

    info = {
        "type": str(type(MEMORY)),
        "has_add": callable(getattr(MEMORY, "add", None)),
        "has_search": callable(getattr(MEMORY, "search", None)),
        "sig_add": None,
        "sig_search": None,
        "methods": _callables(MEMORY)[:50],  # limit to 50 entries for readability
    }
    try:
        fn = getattr(MEMORY, "add", None)
        if callable(fn):
            info["sig_add"] = str(_insp.signature(fn))
    except Exception:
        pass
    try:
        fn = getattr(MEMORY, "search", None)
        if callable(fn):
            info["sig_search"] = str(_insp.signature(fn))
    except Exception:
        pass
    return info

# -----------------------------------------------------------------------------
# Memory manager (Chroma) + fallback adapter
# -----------------------------------------------------------------------------
class _MemDoc(BaseModel):
    id: str
    text: str
    meta: dict


class InMemoryMemoryAdapter:
    def __init__(self):
        self._by_session: Dict[str, List[_MemDoc]] = {}

    def add(self, text: str, meta: dict) -> str:
        sid = meta.get("session_id", "na")
        did = uuid.uuid4().hex[:12]
        self._by_session.setdefault(sid, []).append(_MemDoc(id=did, text=text, meta=meta))
        return did

    def search(self, query: str, k: int = 3, filters: Optional[dict] = None):
        sid = (filters or {}).get("session_id")
        pool: List[_MemDoc] = []
        if sid and sid in self._by_session:
            pool = list(self._by_session[sid])
        else:
            for v in self._by_session.values():
                pool.extend(v)
        q = (query or "").lower()
        scored = []
        for d in pool:
            s = 0
            if q and q in d.text.lower():
                s += 2
            s += int(d.meta.get("created_at", 0)) / 1_000_000_000
            scored.append((s, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"id": d.id, "text": d.text, "meta": d.meta} for _, d in scored[:k]]


MEMORY: Optional[object] = None


def _init_memory() -> None:
    """Init ChromaMemoryManager with (persist_dir, collection, model_path)."""
    global MEMORY
    if MEMORY is not None:
        return

    persist_dir = os.getenv("AIR4_CHROMA_DIR", "./data/chroma")
    collection = os.getenv("AIR4_CHROMA_COLLECTION", "air4")
    embed_model = os.getenv("AIR4_EMBED_MODEL_PATH") or os.getenv("AIR4_EMBED_MODEL", "all-MiniLM-L6-v2")

    try:
        MEMORY = ChromaMemoryManager(persist_dir, collection, embed_model)
        print("[INFO] ChromaMemoryManager init ok", {
            "persist_dir": persist_dir,
            "collection": collection,
            "model": embed_model,
        })
    except Exception as e:
        print(f"[WARN] Chroma init failed: {e}")
        MEMORY = InMemoryMemoryAdapter()
        print("[INFO] Using InMemoryMemoryAdapter as fallback")


@app.on_event("startup")
def _startup() -> None:
    _init_memory()


# -----------------------------------------------------------------------------
# Schemas for /send3
# -----------------------------------------------------------------------------
class MsgIn(BaseModel):
    role: str = Field(..., description="user/assistant/system")
    content: str


class Send3In(BaseModel):
    text: str = Field(..., description="User message text")
    session_id: Optional[str] = Field(None, description="Existing session id, or omitted for new")
    context: Optional[List[MsgIn]] = Field(None, description="Optional prior turns for UI echo")
    style: Optional[str] = Field(None, description="short | normal | detailed")


class Send3Out(BaseModel):
    session_id: str
    reply: str
    usage: dict = Field(default_factory=dict)
    memory_ids: List[str] = Field(default_factory=list)
    updated_at: int = Field(default_factory=_now)


# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict:
    backend = "chroma" if "ChromaMemoryManager" in str(type(MEMORY)) else "fallback"
    model = os.getenv("OLLAMA_MODEL_DEFAULT", "llama3.1:8b")
    return {
        "ok": True,
        "ts": _now(),
        "sessions": len(_SESSIONS),
        "memory_backend": backend,
        "model": model,
        "offline": False,
    }


# -----------------------------------------------------------------------------
# UI routes (match base.html: /ui/*)
# -----------------------------------------------------------------------------
@app.get("/", response_class=RedirectResponse)
async def ui_root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ui/chat", status_code=307)


@app.get("/ui/chat")
async def ui_chat(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request, "active": "chat"})


@app.get("/ui/sessions", response_class=HTMLResponse)
async def ui_sessions() -> HTMLResponse:
    import datetime as _dt

    def _label(ts: int) -> str:
        dt = _dt.datetime.fromtimestamp(ts)
        today = _dt.datetime.now().date()
        if dt.date() == today:
            return "Today"
        if dt.date() == (today - _dt.timedelta(days=1)):
            return "Yesterday"
        return dt.strftime("%b %d, %Y")

    groups: Dict[str, List[Session]] = {}
    for s in sorted(_SESSIONS.values(), key=lambda x: x.updated_at, reverse=True):
        groups.setdefault(_label(s.updated_at), []).append(s)

    parts: List[str] = []
    for label, items in groups.items():
        parts.append(f'<div class="sb-section"><div class="sb-section-title">{label}</div>')
        for it in items:
            title = (it.title or it.id).strip()
            sub = f"{it.turns} turns"
            parts.append(
                '<div class="sb-item">'
                '  <a href="/ui/chat" hx-get="/ui/chat" hx-push-url="true">'
                '    <svg class="ico" viewBox="0 0 24 24"><path d="M21 15V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14l4-4h12a2 2 0 0 0 2-2Z"/></svg>'
                f'    <span class="sb-title-line" title="{title}">{title}</span>'
                '  </a>'
                f'  <div class="sb-sub">{sub}</div>'
                '</div>'
            )
        parts.append('</div>')
    html = "\n".join(parts) if parts else '<div class="sb-section"><div class="sb-sub">No sessions yet</div></div>'
    return HTMLResponse(content=html)


# -----------------------------------------------------------------------------
# Sessions endpoints (minimal set used by UI)
# -----------------------------------------------------------------------------
@app.get("/sessions")
async def list_sessions() -> List[Session]:
    return sorted(_SESSIONS.values(), key=lambda s: s.updated_at, reverse=True)


@app.post("/sessions")
async def create_session() -> Session:
    return ensure_session(None)


@app.get("/sessions/{session_id}")
async def get_session(session_id: str) -> Session:
    if session_id not in _SESSIONS:
        raise HTTPException(status_code=404, detail="No such session")
    return _SESSIONS[session_id]


# -----------------------------------------------------------------------------
# Core: /send3 — single-shot send used by new UI
# -----------------------------------------------------------------------------
@app.post("/send3", response_model=Send3Out)
async def send3(payload: Send3In) -> Send3Out:
    sess = ensure_session(payload.session_id)

    user_text = (payload.text or "").strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="text is empty")

    mem_ids: List[str] = []
    if MEMORY is not None and hasattr(MEMORY, 'add_text'):
        try:
            res = MEMORY.add_text(user_id="dev", text=user_text, session_id=sess.id, source="user")
            # normalize optional ids
            if isinstance(res, dict):
                rid = res.get("id") or res.get("ids")
                if isinstance(rid, list):
                    mem_ids.extend([str(x) for x in rid])
                elif rid:
                    mem_ids.append(str(rid))
        except Exception as e:
            print(f"[WARN] memory add_text (user) failed: {e}")

    # 4) call chat module (prefers your async chat_endpoint_call)
    reply: Optional[str] = None
    try:
        if hasattr(chat_mod, "chat_endpoint_call"):
            body = {
                "message": user_text,
                "session_id": sess.id,
                "system": None,
                "stream": False,
                "use_rag": True,
                "k_memory": 4,
                "style": payload.style,   # <-- pass-through from UI
            }
            headers = {"X-User": "dev", "X-Style": payload.style or ""}
            try:
                obj = await chat_mod.chat_endpoint_call(body, headers)  # type: ignore[arg-type]
                if isinstance(obj, dict):
                    reply = obj.get("reply") or obj.get("text")
            except Exception as e:
                print(f"[WARN] chat_mod.chat_endpoint_call failed: {e}")
    except Exception as e:
        print(f"[WARN] chat_mod wrapper failed: {e}")

    if not reply:
        # last resort — readable fallback
        reply = f"Принял. {user_text}"

    if MEMORY is not None and hasattr(MEMORY, 'add_text'):
        try:
            res2 = MEMORY.add_text(user_id="dev", text=reply, session_id=sess.id, source="assistant")
            if isinstance(res2, dict):
                rid2 = res2.get("id") or res2.get("ids")
                if isinstance(rid2, list):
                    mem_ids.extend([str(x) for x in rid2])
                elif rid2:
                    mem_ids.append(str(rid2))
            summary = reply[:320]
            MEMORY.add_text(user_id="dev", text=f"summary: {summary}", session_id=sess.id, source="summary")
        except Exception as e:
            print(f"[WARN] memory add_text (assistant/summary) failed: {e}")

    sess.turns += 1
    sess.updated_at = _now()
    if sess.title == "New session":
        t = user_text.replace("\n", " ")[:48].strip()
        sess.title = t or "New session"

    return Send3Out(
        session_id=sess.id,
        reply=reply,
        usage={},
        memory_ids=mem_ids,
        updated_at=sess.updated_at,
    )


# Mount phase-9 memory router if it exists (kept for tools)
try:
    from backend.app.routes_memory import router as memory_router  # noqa: E402
    app.include_router(memory_router)
except Exception:
    pass

# Mount profile router (phase-11)
try:
    from backend.app.routes_profile import router as profile_router  # noqa: E402
    app.include_router(profile_router, tags=['memory-profile'])
except Exception:
    pass

from fastapi import Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List, Optional
try:
    templates
except NameError:
    templates = Jinja2Templates(directory="backend/app/templates")


@app.on_event("startup")
async def _wire_memory_to_state():
    try:
        app.state.memory_manager = MEMORY
    except NameError:
        pass
# also set eagerly for dev reloads
try:
    app.state.memory_manager = MEMORY
except NameError:
    pass

@app.get('/ui/ingest', response_class=HTMLResponse)
async def ui_ingest(request: Request):
    return templates.TemplateResponse('ingest.html', {'request': request, 'active': 'ingest'})

@app.get('/ui/ingest/status', response_class=HTMLResponse)
async def ui_ingest_status():
    return HTMLResponse('<pre>OK: ingest status (stub)</pre>')

@app.post('/ui/ingest/commit-all', response_class=HTMLResponse)
async def ui_ingest_commit_all():
    return HTMLResponse('<pre>OK: committed (stub)</pre>')

@app.delete('/ui/ingest/clear', response_class=HTMLResponse)
async def ui_ingest_clear():
    return HTMLResponse('<pre>OK: cleared (stub)</pre>')

@app.post('/ingest', response_class=HTMLResponse)
async def ingest_endpoint(files: List[UploadFile] = File(default=[]), url: Optional[str] = Form(default=None)):
    # сохраняем файлы в data/ingest/inbox и дописываем URL в urls.txt
    from pathlib import Path
    inbox = Path("data/ingest/inbox")
    inbox.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in (files or []):
        base = (f.filename or "upload.bin")
        name = base
        i = 1
        while (inbox / name).exists():
            if "." in base:
                stem, ext = ".".join(base.split(".")[:-1]), "." + base.split(".")[-1]
            else:
                stem, ext = base, ""
            name = f"{stem}__{i}{ext}"
            i += 1
        (inbox / name).write_bytes(await f.read())
        saved.append(name)

    queued = None
    if url:
        queued = str(url).strip()
        (inbox / "urls.txt").touch(exist_ok=True)
        with (inbox / "urls.txt").open("a", encoding="utf-8") as fh:
            fh.write(queued + "\n")

    lines = [f"saved: {', '.join(saved) if saved else '—'}", f"url: {queued or '—'}"]
    return HTMLResponse("<pre>" + "\n".join(lines) + "</pre>")
    return HTMLResponse(f"<pre>uploaded: {", ".join(names) if names else "—"}; url: {url or "—"}</pre>")

@app.get('/ingest/status')
async def ingest_status():
    """JSON: текущее содержимое инбокса (файлы + urls)."""
    from pathlib import Path
    inbox = Path("data/ingest/inbox")
    inbox.mkdir(parents=True, exist_ok=True)

    files = []
    for f in sorted(inbox.iterdir()):
        if f.is_file() and f.name != "urls.txt":
            try:
                sz = f.stat().st_size
            except Exception:
                sz = None
            files.append({"name": f.name, "size": sz})

    urls = []
    utxt = inbox / "urls.txt"
    if utxt.exists():
        try:
            urls = [line.strip() for line in utxt.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
        except Exception:
            urls = []

    return {"ok": True, "inbox": str(inbox.resolve()), "files": files, "urls": urls}

@app.post('/ingest/commit')
async def ingest_commit(name: str):
    """Перенос файла из data/ingest/inbox в data/ingest/store с SHA256-дедупликацией."""
    import hashlib, json
    from pathlib import Path

    inbox = Path("data/ingest/inbox"); inbox.mkdir(parents=True, exist_ok=True)
    store = Path("data/ingest/store"); store.mkdir(parents=True, exist_ok=True)
    index_path = store / "index.json"

    src = inbox / name
    if not src.exists() or not src.is_file():
        return {"ok": False, "error": "file not found in inbox", "asked": name, "inbox": str(inbox.resolve())}

    # sha256 по потоку
    h = hashlib.sha256()
    with src.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024*1024), b""):
            h.update(chunk)
    digest = h.hexdigest()

    # расширение (все суффиксы)
    ext = "".join(src.suffixes) or ""
    target = store / f"{digest}{ext}"

    # загрузим/инициализируем индекс
    try:
        idx = json.loads(index_path.read_text()) if index_path.exists() else {}
    except Exception:
        idx = {}

    dedup = False
    if target.exists():
        # уже есть такой контент — удаляем исходник, считаем как дубликат
        try:
            src.unlink()
        except Exception:
            pass
        dedup = True
        meta = idx.get(digest) or {"size": target.stat().st_size, "names": []}
        if name not in meta["names"]:
            meta["names"].append(name)
        meta["size"] = meta.get("size") or target.stat().st_size
        idx[digest] = meta
    else:
        # переносим
        src.replace(target)
        size = target.stat().st_size
        meta = idx.get(digest) or {"size": size, "names": []}
        if name not in meta["names"]:
            meta["names"].append(name)
        meta["size"] = size
        idx[digest] = meta

    # сохранить индекс
    try:
        index_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2))
    except Exception as e:
        return {"ok": True, "digest": digest, "stored": target.name, "dedup": dedup, "index_write_error": str(e), "store": str(store.resolve())}

    return {"ok": True, "digest": digest, "stored": target.name, "dedup": dedup, "store": str(store.resolve())}
    
    # --- enqueue for indexing ---
    try:
        qpath = store / "queue.json"
        q = json.loads(qpath.read_text()) if qpath.exists() else []
        q.append({"digest": digest, "file": target.name})
        qpath.write_text(json.dumps(q, ensure_ascii=False, indent=2))
    except Exception:
        pass



@app.post('/ingest/commit-all')
async def ingest_commit_all():
    """Коммитит все файлы из data/ingest/inbox в data/ingest/store с SHA256-дедупликацией."""
    import hashlib, json
    from pathlib import Path

    inbox = Path("data/ingest/inbox"); inbox.mkdir(parents=True, exist_ok=True)
    store = Path("data/ingest/store"); store.mkdir(parents=True, exist_ok=True)
    index_path = store / "index.json"

    # загрузим/инициализируем индекс
    try:
        idx = json.loads(index_path.read_text()) if index_path.exists() else {}
    except Exception:
        idx = {}

    moved, duplicates, errors = [], [], []

    for f in sorted(inbox.iterdir()):
        if not f.is_file() or f.name == "urls.txt":
            continue
        try:
            # sha256 по потоку
            h = hashlib.sha256()
            with f.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1024*1024), b""):
                    h.update(chunk)
            digest = h.hexdigest()

            ext = "".join(f.suffixes) or ""
            target = store / f"{digest}{ext}"

            if target.exists():
                try: f.unlink()
                except Exception: pass
                duplicates.append(f.name)
                meta = idx.get(digest) or {"size": target.stat().st_size, "names": []}
                if f.name not in meta["names"]:
                    meta["names"].append(f.name)
                meta["size"] = meta.get("size") or target.stat().st_size
                idx[digest] = meta
            else:
                f.replace(target)
                moved.append({"from": f.name, "to": target.name})
                size = target.stat().st_size
                meta = idx.get(digest) or {"size": size, "names": []}
                if f.name not in meta["names"]:
                    meta["names"].append(f.name)
                meta["size"] = size
                idx[digest] = meta
        except Exception as e:
            errors.append({"file": f.name, "err": str(e)})

    # сохранить индекс
    try:
        index_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2))
    except Exception as e:
        errors.append({"index_write_error": str(e)})

    return {"ok": True, "store": str(store.resolve()), "moved": moved, "duplicates": duplicates, "errors": errors}


@app.delete('/ingest/clear')
async def ingest_clear():
    """Очищает inbox: удаляет все файлы и обнуляет urls.txt."""
    from pathlib import Path
    inbox = Path("data/ingest/inbox"); inbox.mkdir(parents=True, exist_ok=True)

    removed = []
    for f in inbox.iterdir():
        if f.is_file() and f.name != "urls.txt":
            try:
                f.unlink()
                removed.append(f.name)
            except Exception as e:
                removed.append(f"{f.name}: {e}")

    utxt = inbox / "urls.txt"
    urls_cleared = False
    try:
        utxt.write_text("")  # создаст если не было
        urls_cleared = True
    except Exception:
        urls_cleared = False

    return {"ok": True, "cleared_files": removed, "urls_cleared": urls_cleared}

@app.get('/ingest/queue')
async def ingest_queue():
    import json
    from pathlib import Path
    qfile = Path("data/ingest/store/queue.json")
    if not qfile.exists():
        return {"ok": True, "queue": []}
    try:
        data = json.loads(qfile.read_text())
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "queue": data}



@app.get('/ingest/preview')
async def ingest_preview(name: str):
    # Предпросмотр: TXT/MD/LOG/CSV, PDF (первые 5 стр), DOCX.
    try:
        from pathlib import Path
        inbox = Path("data/ingest/inbox")
        store = Path("data/ingest/store")
        path = inbox / name
        if not path.exists() or not path.is_file():
            alt = store / name
            if alt.exists() and alt.is_file():
                path = alt
        if not path.exists() or not path.is_file():
            return {"ok": False, "error": "file not found", "asked": name}

        ext = "".join(path.suffixes).lower() or path.suffix.lower()
        limit = 1200

        # TXT-like
        if ext in (".txt", ".md", ".log", ".csv"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = path.read_text(errors="ignore")
            text = (text or "").replace("\r", "")
            note = ""
            if len(text) > limit:
                text, note = text[:limit] + "...[truncated]", f"truncated to {limit} chars"
            return {"ok": True, "name": path.name, "size": path.stat().st_size,
                    "ext": ext, "text": text, "note": note}

        # PDF
        if ext == ".pdf":
            try:
                from PyPDF2 import PdfReader
                parts = []
                with path.open("rb") as fh:
                    reader = PdfReader(fh)
                    pages = list(getattr(reader, "pages", []) or [])
                    for page in pages[:5]:
                        try:
                            parts.append(page.extract_text() or "")
                        except Exception:
                            parts.append("")
                text = "\n".join(parts).replace("\r", "").strip()
                note = ""
                if len(text) > limit:
                    text, note = text[:limit] + "...[truncated]", f"truncated to {limit} chars"
                return {"ok": True, "name": path.name, "size": path.stat().st_size,
                        "ext": ext, "text": text, "note": note}
            except Exception as e:
                return {"ok": False, "error": f"pdf extract error: {e}", "name": path.name}

        # DOCX
        if ext == ".docx":
            try:
                import docx
                doc = docx.Document(str(path))
                text = "\n".join(p.text for p in doc.paragraphs)
                text = (text or "").replace("\r", "").strip()
                note = ""
                if len(text) > limit:
                    text, note = text[:limit] + "...[truncated]", f"truncated to {limit} chars"
                return {"ok": True, "name": path.name, "size": path.stat().st_size,
                        "ext": ext, "text": text, "note": note}
            except Exception as e:
                return {"ok": False, "error": f"docx extract error: {e}", "name": path.name}

        return {"ok": False, "error": f"unsupported extension: {ext or 'none'}", "name": path.name}
    except Exception as e:
        return {"ok": False, "error": str(e), "name": name}

@app.get("/ui/ingest/queue", response_class=HTMLResponse)
def get_ingest_queue_partial(request: Request):
    from .memory.queue import get_ingest_queue
    queue = get_ingest_queue()
    return templates.TemplateResponse("partials/ingest_queue.html", {"request": request, "queue": queue})

@app.get("/ui/chat/stream", response_class=HTMLResponse)
@app.get("/ui/chat/stream", response_class=HTMLResponse)

@app.get("/ui/chat/stream", response_class=HTMLResponse)
def get_chat_stream(request: Request):
    from .main import _SESSIONS
    if not _SESSIONS:
        messages = []
    else:
        messages = list(_SESSIONS.values())[-1].messages[-20:]
    return templates.TemplateResponse("partials/chat_stream.html", {
        "request": request,
        "messages": messages
    })
from backend.app.routes_todos import todos_router
app.include_router(todos_router)
from fastapi import Request
@app.get('/ui/summary', response_class=HTMLResponse)
async def ui_summary(request: Request):
    return templates.TemplateResponse('base.html', {'request': request, 'page': 'summary_content'})
@app.get('/ui/summaries', response_class=HTMLResponse)
async def ui_summaries(request: Request):
    return templates.TemplateResponse('base.html', {'request': request, 'page': 'summary_content'})
@app.get("/ui/settings", response_class=HTMLResponse)
@app.get("/ui/settings", response_class=HTMLResponse)
def ui_settings(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})
