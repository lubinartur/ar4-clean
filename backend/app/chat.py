# backend/app/chat.py — RAG hook (v0.8.1)
# Порог релевантности + анти-«привет» гейт + дедуп источников

from __future__ import annotations

import os
import re
import uuid
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field

# ==== ENV / defaults ====
PORT = int(os.getenv("PORT", "8000"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL_DEFAULT = os.getenv("OLLAMA_MODEL_DEFAULT", "llama3.1:8b")

def _memory_backend() -> str:
    return "fallback" if os.getenv("AIR4_MEMORY_FORCE_FALLBACK", "0") == "1" else "chroma"

# Порог релевантности (тюним через ENV)
RAG_MIN_SCORE_FALLBACK = float(os.getenv("AIR4_RAG_MIN_SCORE_FALLBACK", "0.60"))
RAG_MIN_SCORE_CHROMA   = float(os.getenv("AIR4_RAG_MIN_SCORE_CHROMA",   "0.20"))

def _min_score() -> float:
    return RAG_MIN_SCORE_FALLBACK if _memory_backend() == "fallback" else RAG_MIN_SCORE_CHROMA

GREETING_RE = re.compile(r'^(hi|hello|hey|привет|здрав|qq|ку|yo|sup)\b', re.I)
def _is_greeting(q: str) -> bool:
    q = (q or "").strip()
    # короткие/пустые сообщения или явные приветствия — не подмешиваем RAG
    return (len(q) < 5) or bool(GREETING_RE.search(q))

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class ChatBody(BaseModel):
    message: str
    session_id: Optional[str] = None
    system: Optional[str] = None
    stream: bool = False  # UI-прокси использует non-stream
    use_rag: bool = True
    k_memory: int = Field(4, ge=1, le=50)

class ChatResult(BaseModel):
    ok: bool = True
    reply: str
    session_id: str
    memory_used: Optional[List[str]] = None

# -----------------------------------------------------------------------------
# Memory retrieval (via local HTTP API /memory/search)
# -----------------------------------------------------------------------------
async def _memory_search_http(query: str, k: int) -> List[Dict[str, Any]]:
    """Запрос к локальному API памяти. Возвращает список dict с ключами id,text,score."""
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
    results = obj.get("results") or obj.get("data") or obj.get("items") or []
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

def build_messages(system: Optional[str], memory_blocks: List[str], user_text: str) -> List[dict]:
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
# Ollama non-stream call (для UI JSON-ответа)
# -----------------------------------------------------------------------------
async def call_ollama(messages: List[dict], session_id: Optional[str]) -> str:
    """Простой non-stream вызов Ollama /api/chat."""
    import httpx
    payload = {"model": OLLAMA_MODEL_DEFAULT, "messages": messages, "stream": False}
    timeout = httpx.Timeout(60.0, read=300.0, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        r.raise_for_status()
        obj = r.json() or {}
        msg = (obj.get("message") or {}).get("content") or ""
        return str(msg)
    except Exception as e:
        # Не роняем чат — возвращаем echo
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        return f"echo: {last_user}  (ollama failed: {e})"

def generate_session_id() -> str:
    return str(uuid.uuid4())[:12]

# -----------------------------------------------------------------------------
# Public entry (used by /ui/chat/send)
# -----------------------------------------------------------------------------
async def chat_endpoint_call(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    UI-прокси (main.py) вызывает эту функцию.
    Возвращаем: { ok, reply, session_id, memory_used }
    """
    data = ChatBody(**body)

    # 1) Подтянуть RAG-контекст: гейт по "привет" + порог по score + дедуп
    memory_blocks: List[str] = []
    if data.use_rag and not _is_greeting(data.message):
        try:
            rel = await _memory_search_http(data.message, data.k_memory)
            # фильтр по порогу релевантности
            threshold = _min_score()
            rel = [r for r in rel if float(r.get("score", 0.0)) >= threshold]
            # дедуп по нормализованному тексту
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

    # 2) Собрать сообщения
    messages = build_messages(data.system, memory_blocks, data.message)

    # 3) Вызвать модель
    reply_text = await call_ollama(messages, session_id=data.session_id)

    # 4) Вернуть session_id и использованные источники (с обрезкой)
    session_id = data.session_id or generate_session_id()
    memory_used = [_summarize_for_sources_display(t) for t in memory_blocks] if memory_blocks else []

    return {
        "ok": True,
        "reply": reply_text,
        "session_id": session_id,
        "memory_used": memory_used,
    }
