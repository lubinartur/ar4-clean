# backend/app/chat.py — AIr4 v0.11.1 (Phase 11 — Profile + RAG)
from __future__ import annotations

import os
import re
import uuid
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field

from backend.app.routes_profile import load_profile as _load_user_profile

# ==== ENV / defaults ====
PORT = int(os.getenv("PORT", "8000"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL_DEFAULT = os.getenv("OLLAMA_MODEL_DEFAULT", "llama3.1:8b")


def _memory_backend() -> str:
    return "fallback" if os.getenv("AIR4_MEMORY_FORCE_FALLBACK", "0") == "1" else "chroma"


RAG_MIN_SCORE_FALLBACK = float(os.getenv("AIR4_RAG_MIN_SCORE_FALLBACK", "0.60"))
RAG_MIN_SCORE_CHROMA = float(os.getenv("AIR4_RAG_MIN_SCORE_CHROMA", "0.20"))


def _min_score() -> float:
    return RAG_MIN_SCORE_FALLBACK if _memory_backend() == "fallback" else RAG_MIN_SCORE_CHROMA


GREETING_RE = re.compile(r"^(hi|hello|hey|привет|здрав|qq|ку|yo|sup)\b", re.I)


def _is_greeting(q: str) -> bool:
    q = (q or "").strip()
    return (len(q) < 5) or bool(GREETING_RE.search(q))


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class ChatBody(BaseModel):
    message: str
    session_id: Optional[str] = None
    system: Optional[str] = None
    stream: bool = False
    use_rag: bool = True
    k_memory: int = Field(4, ge=1, le=50)


class ChatResult(BaseModel):
    ok: bool = True
    reply: str
    session_id: str
    memory_used: Optional[List[str]] = None


# -----------------------------------------------------------------------------
# Memory retrieval
# -----------------------------------------------------------------------------
async def _memory_search_http(query: str, k: int) -> List[Dict[str, Any]]:
    import httpx

    url = f"http://127.0.0.1:{PORT}/memory/search"
    params = {"q": query, "k": k}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params)
        r.raise_for_status()
        obj = r.json() or {}
    except Exception:
        return []

    results = obj.get("results") or []
    out: List[Dict[str, Any]] = []
    for it in results:
        rid = it.get("id") or it.get("h") or it.get("hash") or ""
        txt = it.get("text") or it.get("chunk") or it.get("content") or it.get("value") or ""
        scr = it.get("score", 0.0)
        if isinstance(txt, dict):
            txt = txt.get("text") or txt.get("content") or ""
        if str(txt).strip():
            out.append({"id": str(rid), "text": str(txt), "score": float(scr)})
    return out[:k]


def _format_sources_for_system(blocks: List[str]) -> str:
    return "Relevant context (top-k):\n" + "\n\n---\n".join(blocks)


def _profile_block_from_request(headers: Dict[str, str]) -> str:
    try:
        user_id = headers.get("X-User", "dev")
    except Exception:
        user_id = "dev"
    try:
        prof = _load_user_profile(user_id)
    except Exception:
        return ""

    prefs = getattr(prof, "preferences", {}) or {}
    facts = getattr(prof, "facts", {}) or {}
    goals = getattr(prof, "goals", []) or []

    parts = []
    if getattr(prof, "name", None):
        parts.append(f"name={prof.name}")
    if prefs:
        parts.append("prefs=" + ",".join([f"{k}:{v}" for k, v in list(prefs.items())[:5]]))
    if facts:
        parts.append("facts=" + ",".join([f"{k}:{v}" for k, v in list(facts.items())[:6]]))
    if goals:
        parts.append("goals=" + "; ".join([getattr(g, 'title', getattr(g, 'id', '')) for g in goals][:3]))

    return "USER_PROFILE: " + " | ".join(parts) if parts else ""


def build_messages(system: Optional[str], memory_blocks: List[str], user_text: str, headers: Dict[str, str]) -> List[dict]:
    profile_block = _profile_block_from_request(headers)
    if profile_block:
        system = (system + "\n" + profile_block) if system else profile_block

    messages: List[dict] = []
    if system:
        messages.append({"role": "system", "content": str(system)})
    if memory_blocks:
        messages.append({"role": "system", "content": _format_sources_for_system(memory_blocks)})
    messages.append({"role": "user", "content": str(user_text)})
    return messages


def _summarize_for_sources_display(text: str, limit: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else (text[:limit].rstrip() + "…")


# -----------------------------------------------------------------------------
# Ollama call
# -----------------------------------------------------------------------------
async def call_ollama(messages: List[dict], session_id: Optional[str]) -> str:
    import httpx

    payload = {"model": OLLAMA_MODEL_DEFAULT, "messages": messages, "stream": False}
    timeout = httpx.Timeout(60.0, read=300.0, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        r.raise_for_status()
        obj = r.json() or {}
        msg = (obj.get("message") or {}).get("content") or ""
        return str(msg).strip()
    except Exception as e:
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        return f"echo: {last_user} (ollama failed: {e})"


def generate_session_id() -> str:
    return str(uuid.uuid4())[:12]


# -----------------------------------------------------------------------------
# Public entry
# -----------------------------------------------------------------------------
async def chat_endpoint_call(body: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    data = ChatBody(**body)

    memory_blocks: List[str] = []
    if data.use_rag and not _is_greeting(data.message):
        try:
            rel = await _memory_search_http(data.message, data.k_memory)
            threshold = _min_score()
            rel = [r for r in rel if float(r.get("score", 0.0)) >= threshold]
            seen = set()
            for r in rel:
                t = r.get("text") or ""
                tnorm = " ".join(str(t).split())
                if tnorm in seen:
                    continue
                seen.add(tnorm)
                memory_blocks.append(t)
        except Exception:
            memory_blocks = []

    messages = build_messages(data.system, memory_blocks, data.message, headers)
    reply_text = await call_ollama(messages, session_id=data.session_id)

    session_id = data.session_id or generate_session_id()
    memory_used = [_summarize_for_sources_display(t) for t in memory_blocks] if memory_blocks else []

    return {
        "ok": True,
        "reply": reply_text,
        "session_id": session_id,
        "memory_used": memory_used,
    }