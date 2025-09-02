# backend/app/main.py — AIr4 v0.12.1 (Phase-12 — UI/send3 + sessions + memory)
from __future__ import annotations

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
    app.include_router(memory_router, prefix="/memory", tags=["memory"])
except Exception:
    pass