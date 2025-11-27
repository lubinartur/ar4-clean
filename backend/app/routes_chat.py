from fastapi import APIRouter, Request, Body
from fastapi.responses import JSONResponse
import httpx
import json
import os
# --- Session storage helpers ---
import time
from pathlib import Path
SESS_DIR = Path("data/sessions"); SESS_DIR.mkdir(parents=True, exist_ok=True)
INDEX_PATH = SESS_DIR / "index.json"

def _bump_session(session_id: str):
    try:
        idx = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
    except Exception:
        idx = {}
    now = int(time.time())
    rec = idx.get(session_id) or {"id": session_id, "title": "New session", "created_at": now, "updated_at": now, "turns": 0}
    rec["updated_at"] = now
    idx[session_id] = rec
    INDEX_PATH.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")

def _append_msg(session_id: str, role: str, content: str):
    if not session_id: return
    _bump_session(session_id)
    f = SESS_DIR / f"{session_id}.jsonl"
    line = json.dumps({"ts": int(time.time()), "role": role, "content": content}, ensure_ascii=False)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
# --- end helpers ---

router = APIRouter()

@router.post("/chat")
async def chat(request: Request, q: str | None = Body(None, embed=True)):
    system_preamble = (
        "Ты — AR4, личный интеллект Arch’a. "
        "Отвечай строго на запрос пользователя. "
        "Не перечисляй цели и приоритеты, если об этом прямо не спросили. "
        "Если вопрос — small talk, ответь 1–2 короткими фразами. "
        "Если просят план — дай 3–5 пунктов без моралей."
    )
    if not q:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        for k in ("q","text","input","prompt","message"):
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                q = v.strip(); break
        if not q and isinstance(payload.get("messages"), list):
            for msg in reversed(payload["messages"]):
                if isinstance(msg, dict) and isinstance(msg.get("content"), str) and msg["content"].strip():
                    q = msg["content"].strip(); break
        if not q:
            return JSONResponse({"reply":"empty"}, status_code=200)

    q_l = q.lower().strip()
    if any(tok in q_l for tok in ["#morning_check", "план на день", "план на сегодня", "что у нас по плану", "что по плану", "утро", "morning"]):
        work = facts_profile.get("work_time", "10:00–19:00")
        gym = facts_profile.get("gym_time", "19:30")
        reply = (
            f"План:\n"
            f"— Работа {work}.\n"
            f"— Зал {gym} (45–60 мин): жим 3×5, тяга 3×8, пресс 3×12.\n"
            f"— Вечер 20 мин: AIR4 — один микрошаг (экран/фикс), без перфекционизма.\n"
            f"Финансы: резерва +600€ на неделе."
        )
        return {"reply": reply}

    if any(tok in q_l for tok in ["#evening_check", "итог дня", "вечер", "вечером", "закрыть день"]):
        reply = (
            "Итог дня:\n"
            "— Работа — закрыто, движ есть.\n"
            "— Тренировка — ✅ если был в зале.\n"
            "— AIR4 — +1 шаг, фиксанул без перфекционизма.\n"
            "— В целом — не идеально, но стабильно. Завтра дожмём."
        )
        return {"reply": reply}

    if any(tok in q_l for tok in ["#week_check", "итоги недели", "неделя", "неделю закрыть"]):
        reply = (
            "Неделя:\n"
            "— Финансы: +620€ (по плану).\n"
            "— Тренировки: 3 / 3 — стабильно.\n"
            "— AIR4: 4 шага — идёт прогресс.\n"
            "— Общий вывод: ровно, без спешки, но в росте.\n"
            "— Следующая неделя — добавить 1 новый шаг или идею."
        )
        return {"reply": reply}

    try:
        # --- RAG auto-context ---
        rag_ctx = ""
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get("http://127.0.0.1:8000/memory/search", params={"q": q, "k": 3})
                js = r.json()
                hits = js.get("results", [])
                if hits and isinstance(hits[0], dict) and hits[0].get("text") and hits[0].get("score", 0) >= 0.45:
                    rag_ctx = hits[0]["text"][:1200]
        except Exception:
            rag_ctx = ""
        user_payload = q if not rag_ctx else f"{q}\n\n[MEMORY]\n{rag_ctx}"
        # --- call LLM ---
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", "http://localhost:11434/api/chat", json={
                "model": "mistral",
                "messages": [
                    {"role": "system", "content": system_preamble},
                    {"role": "user", "content": user_payload}
                ]
            }) as res:
                chunks = []
                async for line in res.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        json_line = json.loads(line)
                        content = json_line.get("message", {}).get("content", "")
                        chunks.append(content)
                    except Exception:
                        continue
                answer = "".join(chunks)
                return {"reply": answer, "rag_ctx_head": (rag_ctx or "")[:200]}
    except Exception as e:
        return {"reply": f"echo: {q} (ollama failed: {e})"}