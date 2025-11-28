from __future__ import annotations

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
import httpx
import json
import time
from pathlib import Path
from typing import AsyncGenerator

router = APIRouter()

# --- Session storage helpers (локальные, без импортов из routes_chat) ---
SESS_DIR = Path("data/sessions")
SESS_DIR.mkdir(parents=True, exist_ok=True)
INDEX_PATH = SESS_DIR / "index.json"


def _bump_session(session_id: str, title: str | None = None) -> None:
    try:
        idx = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
    except Exception:
        idx = {}
    now = int(time.time())
    rec = idx.get(session_id) or {
        "id": session_id,
        "title": "New session",
        "created_at": now,
        "updated_at": now,
        "turns": 0,
    }
    if title:
        # только если заголовок ещё дефолтный
        if not rec.get("title") or rec.get("title") == "New session":
            rec["title"] = title
    rec["updated_at"] = now
    rec["turns"] = int(rec.get("turns", 0)) + 1
    idx[session_id] = rec
    INDEX_PATH.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")


def _append_msg(session_id: str | None, role: str, content: str) -> None:
    if not session_id:
        return
    title = None
    if role == "user":
        # первая строка сообщения, не длиннее 80 символов
        first_line = (content or "").strip().splitlines()[0] if isinstance(content, str) else ""
        snippet = first_line[:80].strip()
        if snippet:
            title = snippet
    _bump_session(session_id, title)
    f = SESS_DIR / f"{session_id}.jsonl"
    line = json.dumps(
        {"ts": int(time.time()), "role": role, "content": content},
        ensure_ascii=False,
    )
    with f.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# --- Обёртка: внутренний вызов /chat ---
async def _call_internal_chat(text: str, session_id: str | None) -> str:
    payload: dict[str, object] = {"text": text}
    if session_id:
        payload["session_id"] = session_id

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post("http://127.0.0.1:8000/chat", json=payload)

    try:
        js = r.json()
    except Exception:
        return r.text

    if isinstance(js, dict):
        return str(js.get("reply", ""))
    return str(js)


# --- Основной SSE-стрим ---
@router.post("/chat/stream")
async def chat_stream(request: Request):
    """
    Стрим поверх /chat:
    - читает text + session_id из тела
    - логирует user/assistant в data/sessions/*.jsonl
    - стримит ответ по символам
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    raw_text = payload.get("text") or payload.get("q") or ""
    text = raw_text.strip() if isinstance(raw_text, str) else ""
    session_id = (
        payload.get("session_id")
        or payload.get("session")
        or payload.get("sid")
        or "ui"
    )

    if not text:
        async def empty_gen() -> AsyncGenerator[str, None]:
            yield "data: \n\n"
            yield "data: [DONE]\n\n"
        return EventSourceResponse(empty_gen())

    # логируем вход пользователя
    _append_msg(str(session_id), "user", text)

    # получаем полный ответ от /chat
    reply = await _call_internal_chat(text, str(session_id))
    if not isinstance(reply, str):
        reply = str(reply)

    async def event_gen() -> AsyncGenerator[str, None]:
        acc = ""
        for ch in reply:
            acc += ch
            # UI склеит всё в одну строку
            yield f"data: {ch}\n\n"
        # после окончания — логируем ассистента и шлём [DONE]
        _append_msg(str(session_id), "assistant", acc)
        yield "data: [DONE]\n\n"

    return EventSourceResponse(event_gen())


# --- Тестовый эндпоинт для scripts/smoke_stream.sh ---
@router.post("/chat/stream-test")
async def chat_stream_test():
    """
    Возвращает ровно:
      data: готово
      data: .
      data: .
      data: .
      data: [DONE]
    """
    async def gen() -> AsyncGenerator[str, None]:
        yield "data: готово\n\n"
        for _ in range(3):
            yield "data: .\n\n"
        yield "data: [DONE]\n\n"

    return EventSourceResponse(gen())
