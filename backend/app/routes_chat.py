from fastapi import APIRouter, Request, Body
from fastapi.responses import JSONResponse
import httpx
import json
import time
from pathlib import Path
import re

from backend.app.memory.facts import Fact, add_fact

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
FACTS_PROFILE = {
    "work_time": "10:00–19:00",
    "gym_time": "19:30",
    "zodiac": None,
    "dog_name": None,
    "dog_age": None,
}


# Helper: определение знака зодиака по дате рождения (день, месяц)
def _zodiac_from_day_month(day: int, month: int) -> str:
    # Простое определение знака зодиака по дате (западная система)
    if (month == 3 and day >= 21) or (month == 4 and day <= 19):
        return "Овен"
    if (month == 4 and day >= 20) or (month == 5 and day <= 20):
        return "Телец"
    if (month == 5 and day >= 21) or (month == 6 and day <= 20):
        return "Близнецы"
    if (month == 6 and day >= 21) or (month == 7 and day <= 22):
        return "Рак"
    if (month == 7 and day >= 23) or (month == 8 and day <= 22):
        return "Лев"
    if (month == 8 and day >= 23) or (month == 9 and day <= 22):
        return "Дева"
    if (month == 9 and day >= 23) or (month == 10 and day <= 22):
        return "Весы"
    if (month == 10 and day >= 23) or (month == 11 and day <= 21):
        return "Скорпион"
    if (month == 11 and day >= 22) or (month == 12 and day <= 21):
        return "Стрелец"
    if (month == 12 and day >= 22) or (month == 1 and day <= 19):
        return "Козерог"
    if (month == 1 and day >= 20) or (month == 2 and day <= 18):
        return "Водолей"
    # (month == 2 and day >= 19) or (month == 3 and day <= 20)
    return "Рыбы"

STRICT_RAG = True
RAG_SCORE_THRESHOLD = 0.60


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

    # настройки из payload (фронтовый Settings)
    settings: dict = {}
    if isinstance(payload, dict):
        raw_settings = payload.get("settings") or {}
        if isinstance(raw_settings, dict):
            settings = raw_settings

    tone = str(settings.get("response_tone", "") or "").lower()
    density = str(settings.get("output_density", "") or "").lower()
    temp = settings.get("temperature", None)
    ui_lang = str(settings.get("interface_language", "") or "").lower()

    extra_parts: list[str] = []

    if tone == "bro":
        extra_parts.append(
            "Стиль: токсично-доброжелательный брат. Говори честно, прямо, иногда жёстко, но с уважением и поддержкой. Без лишних извинений и подлизывания."
        )
    elif tone == "strict":
        extra_parts.append(
            "Стиль: строгий, деловой, без лишних эмоций и без воды."
        )
    elif tone == "neutral":
        extra_parts.append(
            "Стиль: спокойный, нейтральный, без излишней эмоциональности."
        )

    if density == "short":
        extra_parts.append(
            "Отвечай максимально кратко: 2–4 коротких предложения или список из 3–5 пунктов."
        )
    elif density == "deep":
        extra_parts.append(
            "Отвечай подробно и глубоко: разбирай по шагам, добавляй примеры и выводы, но без воды."
        )

    if ui_lang in ("ru", "ru-ru", "russian"):
        extra_parts.append("Отвечай по-русски.")
    elif ui_lang in ("en", "en-us", "en-gb", "english"):
        extra_parts.append("Answer in English.")

    if temp is not None:
        extra_parts.append(f"Держи уровень креативности примерно на уровне {temp}.")

    if extra_parts:
        system_preamble = system_preamble + " " + " ".join(extra_parts)

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

    # Авто-запоминание даты рождения -> знак зодиака
    dob_match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", q)
    if dob_match and (
        "дата рождения" in q_l
        or "родился" in q_l
        or "родилась" in q_l
    ):
        try:
            day = int(dob_match.group(1))
            month = int(dob_match.group(2))
            zodiac = _zodiac_from_day_month(day, month)
            FACTS_PROFILE["zodiac"] = zodiac
            reply = f"Запомнил. Твой знак зодиака — {zodiac}."

            # Persist zodiac as a structured fact so it appears in Memory Bank
            try:
                add_fact(
                    Fact(
                        subject="Arch",
                        predicate="zodiac",
                        object=zodiac,
                        category="other",
                        source_session=sess_id,
                    )
                )
            except Exception as e:
                print(f"[FACTS] failed to persist zodiac fact: {e}")
        except Exception:
            reply = "Принял дату рождения, но не смог корректно определить знак зодиака."
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        return {"reply": reply}

    # Жёсткие факты из профиля (обход RAG/LLM)
    if "знак зодиака" in q_l:
        zodiac = FACTS_PROFILE.get("zodiac")
        if zodiac:
            reply = f"Твой знак зодиака — {zodiac}."
        else:
            reply = (
                "У меня нет в профиле данных о твоём знаке зодиака. "
                "Могу запомнить, если скажешь."
            )
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        return {"reply": reply}

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

        # --- RAG auto‑context (safe mode + строгий режим) ---
        rag_ctx = ""
        use_rag = True  # строгий режим: всегда пытаться использовать память
        rag_ok = False

        if use_rag:
            try:
                async with httpx.AsyncClient(timeout=10.0) as c:
                    r = await c.get(
                        "http://127.0.0.1:8000/memory/search",
                        params={"q": q, "k": 3},
                    )
                    js = r.json()
                    hits = js.get("results", [])
                    print("RAG HITS:", hits)
                    # More strict score threshold
                    if (
                        hits
                        and isinstance(hits[0], dict)
                        and hits[0].get("text")
                        and hits[0].get("score") is not None
                        and hits[0]["score"] >= RAG_SCORE_THRESHOLD
                    ):
                        rag_ctx = hits[0]["text"][:1200]
                        rag_ok = True
            except Exception:
                rag_ctx = ""
                rag_ok = False

        # Если включён строгий режим и RAG не нашёл ничего надёжного — не зовём LLM
        if STRICT_RAG and use_rag and not rag_ok:
            answer = (
                "У меня нет надёжных данных в памяти по этому вопросу. "
                "Загрузи документы или переформулируй запрос, либо отключи строгий режим RAG."
            )
            try:
                _append_msg(sess_id, "assistant", answer)
            except Exception:
                pass
            return {"reply": answer, "rag_ctx_head": ""}

        # user payload (RAG only if available)
        if rag_ctx:
            user_payload = f"{q}\n\n[MEMORY]\n{rag_ctx}"
        else:
            user_payload = q

        if rag_ctx:
            system_preamble = (
                system_preamble
                + " ВНИМАНИЕ: отвечай ТОЛЬКО на основе блока [MEMORY] ниже. "
                  "Ничего не придумывай. Если пользователь просит точную фразу, "
                  "верни её дословно из [MEMORY] без изменений."
            )

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
