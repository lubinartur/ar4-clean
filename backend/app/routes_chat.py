from fastapi import APIRouter, Request, Body
from fastapi.responses import JSONResponse
import httpx
import json
import time
from pathlib import Path

# --- Session storage helpers ---
SESS_DIR = Path("data/sessions")
SESS_DIR.mkdir(parents=True, exist_ok=True)
INDEX_PATH = SESS_DIR / "index.json"


def _bump_session(session_id: str, title: str | None = None):
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
        # обновляем заголовок только если он ещё дефолтный
        if not rec.get("title") or rec.get("title") == "New session":
            rec["title"] = title
    rec["updated_at"] = now
    rec["turns"] = int(rec.get("turns", 0)) + 1
    idx[session_id] = rec
    INDEX_PATH.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")


def _append_msg(session_id: str, role: str, content: str):
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


# --- end helpers ---

router = APIRouter()

AGENT_PROFILE = {"priorities": ["финрезерв 10k", "форма", "AIR4/портфолио", "ясность"]}
FACTS_PROFILE = {"work_time": "10:00–19:00", "gym_time": "19:30"}


@router.post("/chat")
async def chat(request: Request, q: str | None = Body(None, embed=True)):
    system_preamble = (
        "Ты — AR4, личный интеллект Arch’a. "
        "Отвечай строго на запрос пользователя. "
        "Не перечисляй цели и приоритеты, если об этом прямо не спросили. "
        "Если вопрос — small talk, ответь 1–2 короткими фразами. "
        "Если просят план — дай 3–5 пунктов без моралей."
    )

    # AIR4: подстройка стиля и языка ответа из профиля
    prefs: dict = {}
    try:
        async with httpx.AsyncClient(timeout=2.0) as c:
            r_prof = await c.get(
                "http://127.0.0.1:8000/memory/profile",
                params={"user_id": "dev"},
            )
            pj = r_prof.json()
            if isinstance(pj, dict):
                prefs = pj.get("preferences", {}) or {}
    except Exception:
        prefs = {}
    reply_style = str(prefs.get("reply_style", "short") or "").lower()
    language = str(prefs.get("language", "ru") or "").lower()

    style_hint = ""
    if reply_style == "short":
        style_hint = "Отвечай максимально кратко: 2–4 коротких предложения или список из 3–5 пунктов."
    elif reply_style == "detailed":
        style_hint = "Отвечай подробно: можно раскрывать детали и использовать списки, но без воды."
    else:
        style_hint = "Отвечай развёрнуто, но без воды: 4–8 предложений или список из 3–7 пунктов."

    lang_hint = ""
    if language == "ru":
        lang_hint = "Отвечай по-русски."
    elif language == "en":
        lang_hint = "Answer in English."
    else:
        lang_hint = "Выбирай язык ответа под вопрос."

    system_preamble = system_preamble + " " + style_hint + " " + lang_hint

    # нормализуем q + вынимаем payload
    payload = {}
    if not q:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        for k in ("q", "text", "input", "prompt", "message"):
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                q = v.strip()
                break
        if not q and isinstance(payload.get("messages"), list):
            for msg in reversed(payload["messages"]):
                if (
                    isinstance(msg, dict)
                    and isinstance(msg.get("content"), str)
                    and msg["content"].strip()
                ):
                    q = msg["content"].strip()
                    break
        if not q:
            return JSONResponse({"reply": "empty"}, status_code=200)

    # session_id из payload (если есть), иначе "ui"
    sess_id = "ui"
    if isinstance(payload, dict):
        sid = (
            payload.get("session_id")
            or payload.get("session")
            or payload.get("sid")
        )
        if isinstance(sid, str) and sid.strip():
            sess_id = sid.strip()

    q_l = q.lower().strip()

    # быстрые режимы (#morning_check, #evening_check, #week_check)
    if any(
        tok in q_l
        for tok in [
            "#morning_check",
            "план на день",
            "план на сегодня",
            "что у нас по плану",
            "что по плану",
            "утро",
            "morning",
        ]
    ):
        work = FACTS_PROFILE.get("work_time", "10:00–19:00")
        gym = FACTS_PROFILE.get("gym_time", "19:30")
        reply = (
            f"План:\n"
            f"— Работа {work}.\n"
            f"— Зал {gym} (45–60 мин): базовые упражнения.\n"
            f"— Вечер 20 мин: AIR4 — один микрошаг (экран/фикс), без перфекционизма.\n"
            f"Финансы: резерва +600€ на неделе."
        )
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        return {"reply": reply}

    if any(
        tok in q_l
        for tok in [
            "#evening_check",
            "итог дня",
            "вечер",
            "вечером",
            "закрыть день",
        ]
    ):
        reply = (
            "Итог дня:\n"
            "— Работа — закрыто, движ есть.\n"
            "— Тренировка — ✅ если был в зале.\n"
            "— AIR4 — +1 шаг, фиксанул без перфекционизма.\n"
            "— В целом — не идеально, но стабильно. Завтра дожмём."
        )
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        return {"reply": reply}

    if any(
        tok in q_l
        for tok in [
            "#week_check",
            "итоги недели",
            "неделя",
            "неделю закрыть",
        ]
    ):
        reply = (
            "Неделя:\n"
            "— Финансы: +620€ (по плану).\n"
            "— Тренировки: 3 / 3 — стабильно.\n"
            "— AIR4: несколько шагов — идёт прогресс.\n"
            "— Общий вывод: ровно, без спешки, но в росте.\n"
            "— Следующая неделя — добавить 1 новый шаг или идею."
        )
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        return {"reply": reply}

    try:
        # логируем запрос пользователя в текущую сессию
        try:
            _append_msg(sess_id, "user", q)
        except Exception:
            pass

        # --- RAG auto‑context (safe mode) ---
        rag_ctx = ""
        use_rag = len(q.split()) >= 4  # RAG only for meaningful queries

        if use_rag:
            try:
                async with httpx.AsyncClient(timeout=10.0) as c:
                    r = await c.get(
                        "http://127.0.0.1:8000/memory/search",
                        params={"q": q, "k": 3},
                    )
                    js = r.json()
                    hits = js.get("results", [])
                    # More strict score threshold
                    if (
                        hits
                        and isinstance(hits[0], dict)
                        and hits[0].get("text")
                        and hits[0].get("score", 0) >= 0.60
                    ):
                        rag_ctx = hits[0]["text"][:1200]
            except Exception:
                rag_ctx = ""

        # user payload (RAG only if available)
        if rag_ctx:
            user_payload = f"{q}\n\n[MEMORY]\n{rag_ctx}"
        else:
            user_payload = q

        # --- call LLM via Ollama chat ---
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                "http://localhost:11434/api/chat",
                json={
                    "model": "mistral",
                    "messages": [
                        {"role": "system", "content": system_preamble},
                        {"role": "user", "content": user_payload},
                    ],
                },
            ) as res:
                chunks = []
                async for line in res.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        json_line = json.loads(line)
                        content = json_line.get("message", {}).get("content", "")
                        if content:
                            chunks.append(content)
                    except Exception:
                        continue
                answer = "".join(chunks)

        try:
            _append_msg(sess_id, "assistant", answer)
        except Exception:
            pass

        return {"reply": answer, "rag_ctx_head": (rag_ctx or "")[:200]}
    except Exception as e:
        return {"reply": f"echo: {q} (ollama failed: {e})"}


@router.get("/sessions")
def list_sessions():
    """
    AIR4: список сессий для UI.
    Читаем index.json и возвращаем отсортированный список.
    """
    try:
        idx = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
    except Exception:
        idx = {}

    sessions = list(idx.values())
    sessions.sort(key=lambda r: r.get("updated_at", 0), reverse=True)
    return {"ok": True, "sessions": sessions}


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    """
    AIR4: вернуть сообщения по сессии.
    Берём JSONL data/sessions/<session_id>.jsonl
    """
    f = SESS_DIR / f"{session_id}.jsonl"
    if not f.exists():
        return {"ok": True, "messages": []}

    messages = []
    try:
        with f.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line))
                except Exception:
                    continue
    except Exception as e:
        return {"ok": False, "error": str(e), "messages": []}

    return {"ok": True, "messages": messages}


@router.post("/sessions/{session_id}/clear")
def clear_session(session_id: str):
    """
    AIR4: очистить историю сессии.
    Удаляет JSONL-файл и запись из index.json.
    """
    # удалить файл истории
    f = SESS_DIR / f"{session_id}.jsonl"
    if f.exists():
        try:
            f.unlink()
        except Exception:
            pass

    # обновить индекс
    try:
        idx = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
    except Exception:
        idx = {}
    if session_id in idx:
        idx.pop(session_id, None)
        try:
            INDEX_PATH.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    return {"ok": True, "session_id": session_id}
