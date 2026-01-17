from __future__ import annotations

from fastapi import APIRouter, Request, Body, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
import json
import time
from pathlib import Path
import re
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import logging
import uuid
from datetime import datetime
import os
import asyncio

# v0.7 QB integration imports
from backend.app.question_bank.store_singleton import store as qb_store
from backend.app.question_bank.engine import run_engine
from backend.app.question_bank.context import build_qb_context
from backend.app.question_bank.chat_bridge import build_chat_preamble

logger = logging.getLogger(__name__)

# Debug flag for rehydration diagnostics
DEBUG_REHYDRATION = os.getenv("DEBUG_REHYDRATION", "0") == "1"

from backend.app.memory.facts import Fact, add_fact
import importlib

# Helper flag для логирования предупреждения о неподдерживаемых аргументах
_memory_adapter_warning_logged = False


def _get_memory():
    """Lazy import для получения MEMORY и ENABLE_CHAT_MEMORY без циклического импорта."""
    try:
        m = importlib.import_module("backend.app.main")
    except Exception:
        m = importlib.import_module(".main", package=__package__)
    memory = getattr(m, "MEMORY", None)
    enabled = getattr(m, "ENABLE_CHAT_MEMORY", False)
    return enabled, memory


def safe_memory_add(text: str, session_id: str, role: str, user_id: str = "dev") -> None:
    """
    Безопасное сохранение текста в память с graceful degradation.
    Пробует разные сигнатуры адаптера памяти для совместимости.
    
    Args:
        text: Текст для сохранения
        session_id: ID сессии
        role: Роль сообщения ("user" или "assistant")
        user_id: ID пользователя (по умолчанию "dev")
    """
    global _memory_adapter_warning_logged
    
    enabled, memory = _get_memory()
    if not enabled or memory is None:
        return
    
    # Попытка 1: add_text с полными параметрами (ChromaMemoryManager)
    if hasattr(memory, "add_text"):
        try:
            memory.add_text(user_id=user_id, text=text, session_id=session_id, source=role)
            logger.debug(f"[memory] saved turn: role={role!r}, session_id={session_id!r}, len={len(text)}")
            return
        except TypeError as e:
            # Попытка 2: add_text без user_id (если адаптер не требует его)
            try:
                memory.add_text(text=text, session_id=session_id, source=role)
                logger.debug(f"[memory] saved turn (no user_id): role={role!r}, session_id={session_id!r}")
                return
            except (TypeError, AttributeError):
                pass
        except Exception as e:
            logger.warning(f"[memory] add_text failed: {e}")
            return
    
    # Попытка 3: add с meta dict (InMemoryMemoryAdapter)
    if hasattr(memory, "add"):
        try:
            ts = int(time.time())
            meta = {
                "user_id": user_id,
                "session_id": session_id,
                "role": role,
                "source": role,
                "ts": ts,
                "created_at": ts,
            }
            memory.add(text=text, meta=meta)
            logger.debug(f"[memory] saved turn (via add): role={role!r}, session_id={session_id!r}")
            return
        except Exception as e:
            if not _memory_adapter_warning_logged:
                logger.warning(f"[memory] adapter unsupported args: {type(memory).__name__} does not support expected signatures")
                _memory_adapter_warning_logged = True
            return
    
    # Если ничего не сработало
    if not _memory_adapter_warning_logged:
        logger.warning(f"[memory] adapter unsupported: {type(memory).__name__} does not have add_text or add methods")
        _memory_adapter_warning_logged = True


# --- Session storage helpers ---
SESS_DIR = Path("data/sessions")
SESS_DIR.mkdir(parents=True, exist_ok=True)
INDEX_PATH = SESS_DIR / "index.json"


def _now_iso() -> str:
    """Return current timestamp as ISO8601 string with timezone."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _bump_session(session_id: str, title: str | None = None, role: str | None = None):
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
        "summary": None,
    }
    if title:
        # обновляем заголовок только если он ещё дефолтный
        if not rec.get("title") or rec.get("title") == "New session":
            rec["title"] = title
    rec["updated_at"] = now
    if role == "user":
        rec["turns"] = int(rec.get("turns", 0)) + 1
    # Миграция: если нет поля summary, добавляем null
    if "summary" not in rec:
        rec["summary"] = None
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
    _bump_session(session_id, title, role)
    f = SESS_DIR / f"{session_id}.jsonl"
    line = json.dumps(
        {"ts": int(time.time()), "role": role, "content": content},
        ensure_ascii=False,
    )
    with f.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    
    # --- MINIMAL auto-summary: trigger after N user messages (default: 5) ---
    if role == "user":
        try:
            user_turn_count = _count_user_turns(session_id)
            # Auto-generate summary after every N user messages (default: 5)
            AUTO_SUMMARY_INTERVAL = 5
            if user_turn_count > 0 and user_turn_count % AUTO_SUMMARY_INTERVAL == 0:
                # Trigger async summary generation (fire-and-forget)
                # Try to get current event loop (works in async context like FastAPI endpoints)
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_generate_session_summary_chroma(session_id))
                    logger.info(f"[session_summary] auto-triggered for session {session_id} after {user_turn_count} user messages")
                except RuntimeError:
                    # No event loop running - this should not happen in FastAPI async context
                    # But we fail silently to not break message appending
                    logger.debug(f"[session_summary] no event loop available for auto-trigger (session {session_id})")
        except Exception as e:
            # Fail silently - don't break message appending
            logger.debug(f"[session_summary] auto-trigger check failed: {e}")


def append_summary_event(session_id: str, summary_obj: Dict[str, Any]):
    """
    Append summary event to jsonl and update summary stub in index.json.
    
    Args:
        session_id: Session ID
        summary_obj: Summary object with fields: v, updated_at (ISO8601 string), until_user_turn, text, topics
    """
    if not session_id:
        return
    
    # Normalize updated_at to ISO8601 string
    updated_at = summary_obj.get("updated_at")
    if not updated_at or not isinstance(updated_at, str):
        updated_at = _now_iso()
    
    # Prepare summary event for jsonl
    summary_event = {
        "type": "summary",
        "v": summary_obj.get("v", 1),
        "updated_at": updated_at,
        "until_user_turn": summary_obj.get("until_user_turn", 0),
        "text": summary_obj.get("text", ""),
        "topics": summary_obj.get("topics", [])
    }
    
    # Append to jsonl
    f = SESS_DIR / f"{session_id}.jsonl"
    line = json.dumps(summary_event, ensure_ascii=False)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    
    # Update summary stub in index.json
    try:
        idx = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
    except Exception:
        idx = {}
    
    if session_id not in idx:
        # Session doesn't exist in index, skip
        return
    
    rec = idx[session_id]
    rec["summary"] = {
        "v": summary_event["v"],
        "updated_at": summary_event["updated_at"],
        "until_user_turn": summary_event["until_user_turn"]
    }
    idx[session_id] = rec
    INDEX_PATH.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_summary_stub(session_id: str) -> Optional[Dict[str, Any]]:
    """Get summary stub from index.json for a session."""
    try:
        idx = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
    except Exception:
        return None
    meta = idx.get(session_id)
    if not meta:
        return None
    return meta.get("summary")


def _count_user_turns(session_id: str) -> int:
    """Count user messages (turns) from jsonl file.
    
    Counts only lines with role=="user", explicitly skips summary events (type=="summary").
    Result should match: jq -s '[.[] | select(.role=="user")] | length'
    """
    f = SESS_DIR / f"{session_id}.jsonl"
    if not f.exists():
        return 0
    count = 0
    try:
        with f.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg_data = json.loads(line)
                    if not isinstance(msg_data, dict):
                        continue
                    # Explicitly skip summary events
                    if msg_data.get("type") == "summary":
                        continue
                    # Count only user messages
                    if msg_data.get("role") == "user":
                        count += 1
                except Exception:
                    continue
    except Exception:
        pass
    return count


def should_update_summary(user_turn_count: int, summary_obj: Optional[Dict[str, Any]]) -> bool:
    """
    Determine if summary should be updated.
    
    Rules:
    - N_START = 8: minimum turns before first summary
    - N_DELTA = 6: minimum turns since last summary
    
    Args:
        user_turn_count: Current number of user messages (turns)
        summary_obj: Summary stub from index.json (None if no summary exists)
    
    Returns:
        True if summary should be updated, False otherwise
    """
    N_START = 8
    N_DELTA = 6
    
    if summary_obj is None:
        return user_turn_count >= N_START
    
    until = summary_obj.get("until_user_turn", 0)
    return (user_turn_count - until) >= N_DELTA


def _get_full_summary(session_id: str) -> Optional[Dict[str, Any]]:
    """Get full summary from jsonl file (last summary event)."""
    f = SESS_DIR / f"{session_id}.jsonl"
    if not f.exists():
        return None
    summary = None
    try:
        with f.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg_data = json.loads(line)
                    if isinstance(msg_data, dict) and msg_data.get("type") == "summary":
                        summary = msg_data
                except Exception:
                    continue
    except Exception:
        pass
    return summary


def _get_recent_dialogue(session_id: str, n_user_turns: int = 12) -> List[Dict[str, str]]:
    """
    Get recent dialogue: last N user turns + their assistant replies.
    Returns list of {"role": "user"/"assistant", "content": "..."} in chronological order.
    """
    f = SESS_DIR / f"{session_id}.jsonl"
    if not f.exists():
        return []
    
    # Read all messages (excluding summary events)
    messages = []
    try:
        with f.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg_data = json.loads(line)
                    # Skip summary events
                    if isinstance(msg_data, dict) and msg_data.get("type") == "summary":
                        continue
                    # Only include user/assistant messages
                    if isinstance(msg_data, dict) and msg_data.get("role") in ("user", "assistant"):
                        content = msg_data.get("content") or msg_data.get("text") or msg_data.get("message") or ""
                        if content:
                            messages.append({
                                "role": msg_data.get("role"),
                                "content": str(content)
                            })
                except Exception:
                    continue
    except Exception:
        return []
    
    # Find indices of last N user messages (going backwards from end)
    user_indices = []
    for j in range(len(messages) - 1, -1, -1):
        if messages[j]["role"] == "user":
            user_indices.append(j)
            if len(user_indices) >= n_user_turns:
                break
    
    # Sort user_indices to get chronological order
    user_indices.sort()
    
    # Collect these user messages and their assistant replies (if exist)
    result = []
    for user_idx in user_indices:
        result.append(messages[user_idx])  # user message
        # Check if there's an assistant reply right after (next message in chronological order)
        if user_idx + 1 < len(messages) and messages[user_idx + 1]["role"] == "assistant":
            result.append(messages[user_idx + 1])  # assistant reply
    
    return result


async def _run_summary_task(session_id: str) -> None:
    """
    Wrapper task for generate_summary that catches exceptions to avoid
    "Task exception was never retrieved" warnings.
    """
    try:
        await generate_summary(session_id)
    except Exception as e:
        logger.exception(f"[summary] background task failed for session {session_id}: {e}")


# --- Session auto-summary in ChromaDB (MINIMAL) ---
async def _generate_session_summary_chroma(session_id: str) -> None:
    """
    Generate short session summary (3-5 lines) and store in ChromaDB.
    Hotfix for UX: creates long-term memory via RAG.
    
    Summary format:
    - What was discussed
    - Current state / signal
    - One conclusion (if any)
    
    Stored with:
    - namespace: "sessions"
    - kind: "summary"
    - metadata: session_id, created_at
    """
    try:
        enabled, memory = _get_memory()
        if not enabled or not memory:
            return  # Memory not enabled
        
        # Get recent dialogue (last 10 messages should be enough for short summary)
        recent_dialogue = _get_recent_dialogue(session_id, n_user_turns=10)
        if not recent_dialogue:
            return
        
        # Format dialogue for prompt (skip system messages)
        dialogue_lines = []
        for msg in recent_dialogue:
            role = msg.get("role", "")
            content = msg.get("content", "").strip()
            if content and role in ("user", "assistant"):
                dialogue_lines.append(f"{role}: {content}")
        dialogue_text = "\n".join(dialogue_lines[-10:])  # Last 10 messages max
        
        # Build prompt for SHORT summary (3-5 lines)
        prompt = (
            "Сделай ОЧЕНЬ краткий конспект диалога (3-5 строк).\n"
            "Формат:\n"
            "1. О чём говорили\n"
            "2. Текущее состояние / сигнал\n"
            "3. Один вывод (если есть)\n\n"
            "Диалог:\n" + dialogue_text
        )
        
        # Call LLM for summary generation
        summary_text = ""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream(
                    "POST",
                    "http://localhost:11434/api/chat",
                    json={
                        "model": "mistral",
                        "messages": [
                            {"role": "user", "content": prompt}
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
                    summary_text = "".join(chunks).strip()
        except Exception as e:
            logger.warning(f"[session_summary] LLM call failed: {e}")
            # Fallback: simple extractive summary
            summary_text = _extract_simple_summary(recent_dialogue)
        
        if not summary_text or len(summary_text) < 10:
            return  # Skip if summary is too short
        
        # Limit summary length (should be short anyway, but enforce max 500 chars)
        summary_text = summary_text[:500].strip()
        
        # Store in ChromaDB via ChromaMemoryManager
        user_id = "dev"  # Default user ID
        ts = int(time.time())
        summary_id = f"session_summary_{session_id}_{ts}"
        
        # Use add_texts method with proper metadata
        metadata = {
            "session_id": session_id,
            "user_id": user_id,
            "source": "summary",  # This will normalize to namespace="sessions"
            "kind": "summary",
            "created_at": ts,
        }
        
        try:
            memory.add_texts(
                texts=[summary_text],
                metadatas=[metadata],
                ids=[summary_id]
            )
            logger.info(f"[session_summary] stored in ChromaDB for session {session_id}")
        except Exception as e:
            logger.warning(f"[session_summary] failed to store in ChromaDB: {e}")
            
    except Exception as e:
        logger.error(f"[session_summary] generation failed for session {session_id}: {e}", exc_info=True)


def _extract_simple_summary(recent_dialogue: List[Dict[str, str]]) -> str:
    """Fallback: extract simple summary from dialogue without LLM."""
    if not recent_dialogue:
        return ""
    
    # Get user messages (what they asked about)
    user_messages = [msg.get("content", "").strip() for msg in recent_dialogue if msg.get("role") == "user"]
    assistant_messages = [msg.get("content", "").strip() for msg in recent_dialogue if msg.get("role") == "assistant"]
    
    if not user_messages:
        return ""
    
    # Simple extractive summary
    lines = []
    if user_messages:
        # First line: what was discussed (from last 2-3 user messages)
        last_topics = user_messages[-3:] if len(user_messages) >= 3 else user_messages
        topics = ", ".join([msg[:50] for msg in last_topics if msg])
        if topics:
            lines.append(f"Обсуждали: {topics}")
    
    if assistant_messages:
        # Second line: current state (from last assistant message)
        last_assistant = assistant_messages[-1]
        if last_assistant:
            lines.append(f"Текущий статус: {last_assistant[:100]}")
    
    # Third line: simple conclusion
    if len(user_messages) >= 2:
        lines.append("Вывод: диалог продолжается.")
    
    return "\n".join(lines[:3]) if lines else ""


async def generate_summary(session_id: str) -> None:
    """
    Generate summary for session and write it via append_summary_event.
    
    Steps:
    1. Get current user_turn_count
    2. Get previous full summary if exists
    3. Get recent dialogue (last N_RECENT_USER_TURNS user turns + assistant replies)
    4. Call LLM with prompt
    5. Write summary via append_summary_event
    """
    N_RECENT_USER_TURNS = 12
    
    try:
        # Get current user_turn_count
        user_turn_count = _count_user_turns(session_id)
        if user_turn_count == 0:
            logger.warning(f"[summary] no user turns for session {session_id}")
            return
        
        # Get previous full summary
        prev_summary = _get_full_summary(session_id)
        prev_summary_text = ""
        if prev_summary:
            prev_summary_text = prev_summary.get("text", "")
        
        # Get recent dialogue
        recent_dialogue = _get_recent_dialogue(session_id, N_RECENT_USER_TURNS)
        if not recent_dialogue:
            logger.warning(f"[summary] no recent dialogue for session {session_id}")
            return
        
        # Format dialogue for prompt
        dialogue_lines = []
        for msg in recent_dialogue:
            role = msg.get("role", "")
            content = msg.get("content", "").strip()
            if content:
                dialogue_lines.append(f"{role}: {content}")
        dialogue_text = "\n".join(dialogue_lines)
        
        # Build prompt
        system_prompt = (
            "Ты — ассистент, который делает краткий конспект диалога для \"второго мозга\".\n"
            "Правила: кратко, по делу, без домыслов, максимум 12 строк.\n"
            "Включи: ключевые цели/решения, текущий статус, открытые вопросы/следующие шаги.\n"
            "Если информации нет — не добавляй."
        )
        
        user_prompt = "PREV_SUMMARY:\n"
        if prev_summary_text:
            user_prompt += prev_summary_text
        else:
            user_prompt += "(нет предыдущего конспекта)"
        
        user_prompt += "\n\nRECENT_DIALOGUE:\n" + dialogue_text + "\n\nСделай обновлённый конспект, который покрывает всё до текущего момента."
        
        # Call LLM (using same approach as /chat endpoint)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    "http://localhost:11434/api/chat",
                    json={
                        "model": "mistral",  # Default model, same as /chat
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
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
                    result_text = "".join(chunks).strip()
        except Exception as e:
            # G3: Log error
            logger.error(
                "[ERROR] summary LLM_call_failed",
                extra={
                    "session_id": session_id,
                    "user": "dev",
                    "exception": str(e)
                }
            )
            return
        
        if not result_text:
            logger.warning(f"[summary] empty LLM response for session {session_id}")
            return
        
        # Write summary via append_summary_event
        summary_obj = {
            "v": 1,
            "updated_at": _now_iso(),
            "until_user_turn": user_turn_count,
            "text": result_text,
            "topics": []
        }
        append_summary_event(session_id, summary_obj)
        logger.info(f"[summary] generated summary for session {session_id}, until_user_turn={user_turn_count}")
        
    except Exception as e:
        logger.error(f"[summary] generate_summary failed for session {session_id}: {e}", exc_info=True)
        # G3: Log error
        logger.error(
            "[ERROR] summary generation_failed",
            extra={
                "session_id": session_id,
                "user": "dev",
                "exception": str(e)
            }
        )


# --- end helpers ---

router = APIRouter()

AGENT_PROFILE = {"priorities": ["финрезерв 10k", "форма", "AIR4/портфолио", "ясность"]}
FACTS_PROFILE = {
    "work_time": "10:00–19:00",
    "gym_time": "19:30",
    "zodiac": None,
    "dog_name": None,
    "dog_age": None,
    "location": None,
    "goals": [],
    "training_freq": None,
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

# --- PROFILE FACTS EXTRACTOR ---
def extract_profile_facts(text: str, sess_id: str) -> str | None:
    """
    Простые правила для авто-запоминания профиля из текста.
    Возвращает reply, если факт обработан здесь, иначе None.
    """
    t = text.lower()

    # 1) Локация: "я живу в ...", "живу в ...", "я из ..."
    m = re.search(
        r"\b(я живу в|живу в|я из)\s+([a-zA-Zа-яА-ЯёЁ\s]+)",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        place = m.group(2).strip().strip(".!? ")
        if place:
            FACTS_PROFILE["location"] = place
            try:
                add_fact(
                    Fact(
                        subject="Arch",
                        predicate="живёт_в",
                        object=place,
                        category="location",
                        source_session=sess_id,
                    )
                )
            except Exception as e:
                print(f"[PROFILE] failed to persist location fact: {e}")
            return f"Запомнил. Ты живёшь в {place}."

    # 2) Цели: "моя цель ...", "главная цель ...", "цель — ..."
    g = re.search(
        r"(?:моя цель|главная цель|цель)\s*[:\-–— ]+\s*(.+)",
        text,
        flags=re.IGNORECASE,
    )
    if g:
        goal = g.group(1).strip().strip(".!? ")
        if goal:
            goals = FACTS_PROFILE.get("goals") or []
            if isinstance(goals, list):
                goals.append(goal)
                FACTS_PROFILE["goals"] = goals
            try:
                add_fact(
                    Fact(
                        subject="Arch",
                        predicate="goal",
                        object=goal,
                        category="goals",
                        source_session=sess_id,
                    )
                )
            except Exception as e:
                print(f"[PROFILE] failed to persist goal fact: {e}")
            return f"Запомнил цель: {goal}."

    # 3) Тренировки: "X раза в неделю"
    freq_match = re.search(r"(\d+)\s+раза?\s+в\s+недел", t)
    if freq_match:
        freq = freq_match.group(1)
        FACTS_PROFILE["training_freq"] = freq
        desc = f"тренировки {freq} раза в неделю"
        try:
            add_fact(
                Fact(
                    subject="Arch",
                    predicate="training_freq",
                    object=freq,
                    category="habits",
                    source_session=sess_id,
                )
            )
        except Exception as e:
            print(f"[PROFILE] failed to persist training fact: {e}")
        return f"Запомнил: {desc}."

    return None

STRICT_RAG = True
RAG_SCORE_THRESHOLD = 0.60


# Pydantic models for request validation
class ChatMessage(BaseModel):
    role: str = Field(..., description="Message role")
    content: str = Field(..., description="Message content", min_length=1)


class ChatSettings(BaseModel):
    response_tone: Optional[str] = None
    output_density: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    interface_language: Optional[str] = None
    model: Optional[str] = None
    active_model: Optional[str] = None
    activeModel: Optional[str] = None
    active_model_weight: Optional[str] = None
    model_name: Optional[str] = None
    llm_model: Optional[str] = None


# --------------------------------------------------------------------
# v0.7: QB -> /chat bridge
# --------------------------------------------------------------------

class ChatRequestQBMixin(BaseModel):
    qb_session_id: Optional[str] = Field(default=None)
    qb_enabled: bool = Field(default=True)
    thinking_mode: Optional[str] = Field(default=None, description="Thinking mode: analytical, structured, wide, hard, exploratory")


def _sse_event(event: str, data: Dict[str, Any]) -> str:
    """
    Server-Sent Events format:
      event: <name>\n
      data: <json>\n
      \n
    """
    return f"event: {event}\n" + "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"


def _build_thinking_mode_directives(thinking_mode: Optional[str] = None) -> str:
    """
    Build thinking mode directives for system preamble.
    
    Args:
        thinking_mode: One of: analytical, structured, wide, hard, exploratory
        
    Returns:
        Formatted directives string or empty string if mode is unknown
    """
    mode = (thinking_mode or "structured").lower().strip()
    
    directives_map = {
        "analytical": (
            "• Ask causal/clarifying questions.\n"
            "• Provide structured hypotheses.\n"
            "• Avoid emotional language."
        ),
        "structured": (
            "• Ask step-by-step questions.\n"
            "• Provide ordered summaries or checklists.\n"
            "• Avoid expanding scope."
        ),
        "wide": (
            "• Ask broadening questions.\n"
            "• Offer alternatives and scenarios.\n"
            "• Avoid final decisions."
        ),
        "hard": (
            "• Ask direct, uncomfortable questions.\n"
            "• Use concise, firm wording.\n"
            "• Avoid empathy or reassurance."
        ),
        "exploratory": (
            "• Ask open, associative questions.\n"
            "• Share observations and patterns.\n"
            "• Avoid concrete advice."
        ),
    }
    
    # Default to structured if mode is unknown
    if mode not in directives_map:
        mode = "structured"
    
    directives = directives_map[mode]
    
    return f"\n\nTHINKING MODE: {mode.capitalize()}\nDirectives:\n{directives}\n"


def _get_qb_payload(qb_session_id: str, thinking_mode: Optional[str] = None):
    """
    Get QB payload for chat context.
    
    Args:
        qb_session_id: QB session ID
        thinking_mode: Thinking mode from request (defaults to "structured" if not provided)
    """
    session = qb_store.get(qb_session_id)
    if session is None:
        return None

    # PHASE Q5: Use thinking_mode from request, default to "structured" only if not provided
    effective_thinking_mode = thinking_mode or "structured"

    out = run_engine(
        session.answers,
        asked_ids=session.asked_ids,
        asked_at=session.asked_at,
        domain_last_asked_at=session.domain_last_asked_at,
        answered_at=session.answered_at,
        thinking_mode=effective_thinking_mode,
    )

    qb_ctx = build_qb_context(
        state_id=out.state_id,
        mode=out.mode,
        tags=out.tags,
        signals=session.answers,
        ask_budget=out.ask_budget,
        forbid_domains=out.forbid_domains,
        forbid_actions=out.forbid_actions,
        thinking_mode=effective_thinking_mode,
    )

    preamble = build_chat_preamble(qb_ctx.to_dict())

    return {
        "qb_context": qb_ctx.to_dict(),
        "chat_preamble": preamble,
        "state": {
            "id": out.state_id,
            "mode": out.mode,
            "tags": out.tags,
        },
        "constraints": {
            "ask_budget": out.ask_budget,
            "forbid_domains": out.forbid_domains,
            "forbid_actions": out.forbid_actions,
        },
        "expired": out.expired_signals,
    }


class CreateSessionRequest(BaseModel):
    title: Optional[str] = Field(None, description="Session title (optional)")


# Runtime guard limits
MAX_CHAT_INPUT_LENGTH = 10000  # Max characters for chat input text

class ChatRequest(ChatRequestQBMixin):
    q: Optional[str] = Field(None, description="Query text", max_length=MAX_CHAT_INPUT_LENGTH)
    text: Optional[str] = Field(None, description="Query text (alias)", max_length=MAX_CHAT_INPUT_LENGTH)
    input: Optional[str] = Field(None, description="Query text (alias)", max_length=MAX_CHAT_INPUT_LENGTH)
    prompt: Optional[str] = Field(None, description="Query text (alias)", max_length=MAX_CHAT_INPUT_LENGTH)
    message: Optional[str] = Field(None, description="Query text (alias)", max_length=MAX_CHAT_INPUT_LENGTH)
    messages: Optional[List[ChatMessage]] = Field(None, description="Message history", max_length=100)
    settings: Optional[ChatSettings] = Field(None, description="Chat settings")
    session_id: Optional[str] = Field(None, description="Session ID")
    session: Optional[str] = Field(None, description="Session ID (alias)")
    sid: Optional[str] = Field(None, description="Session ID (alias)")

    def get_query_text(self) -> Optional[str]:
        """Extract query text from various possible fields."""
        for field in [self.q, self.text, self.input, self.prompt, self.message]:
            if field and isinstance(field, str) and field.strip():
                if len(field) > MAX_CHAT_INPUT_LENGTH:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Input text exceeds maximum length of {MAX_CHAT_INPUT_LENGTH} characters"
                    )
                return field.strip()
        # Try to extract from messages
        if self.messages:
            for msg in reversed(self.messages):
                if isinstance(msg, ChatMessage) and msg.content and msg.content.strip():
                    content = msg.content.strip()
                    if len(content) > MAX_CHAT_INPUT_LENGTH:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Message content exceeds maximum length of {MAX_CHAT_INPUT_LENGTH} characters"
                        )
                    return content
        return None

    def get_session_id(self) -> Optional[str]:
        """Extract session_id from various possible fields."""
        for field in [self.session_id, self.session, self.sid]:
            if field and isinstance(field, str) and field.strip():
                return field.strip()
        return None

    def get_settings_dict(self) -> Dict[str, Any]:
        """Convert settings model to dict, handling None."""
        if self.settings is None:
            return {}
        return self.settings.model_dump(exclude_none=True)


@router.post("/chat")
async def chat(body: ChatRequest, request: Request = None):
    # Core Dialog: используем фиксированный ARCH_CORE_PROMPT
    # UI не может перезаписать system prompt через settings или systemPrompt
    from backend.app.chat import ARCH_CORE_PROMPT
    system_preamble = ARCH_CORE_PROMPT

    # Extract and validate session_id early to check if this is first turn
    sess_id = body.get_session_id()
    from backend.app.main import validate_session_id
    sess_id = validate_session_id(sess_id) if sess_id else None

    # --- v0.7: QB -> /chat bridge ---
    # Enable Question Bank only after first user message in session
    qb_payload = None
    qb_allowed = False
    if sess_id:
        try:
            user_turn_count = _count_user_turns(sess_id)
            qb_allowed = (user_turn_count >= 1)  # Allow QB after first user message
        except Exception:
            qb_allowed = False  # Safe fallback: disable QB if check fails
    
    # --- PHASE J2: Thinking Mode directives ---
    # Extract thinking_mode: priority: body.thinking_mode, else query param, else default "structured"
    thinking_mode = body.thinking_mode
    if not thinking_mode and request:
        # Try to get from query params as fallback
        query_params = request.query_params
        thinking_mode = query_params.get("thinking_mode")
    if not thinking_mode:
        thinking_mode = "structured"  # Default
    
    # PHASE Q5: Pass thinking_mode to QB payload generation
    if body.qb_enabled and body.qb_session_id and qb_allowed:
        qb_payload = _get_qb_payload(body.qb_session_id, thinking_mode)
        if qb_payload and qb_payload.get("chat_preamble"):
            system_preamble += "\n\n" + qb_payload["chat_preamble"] + "\n"
    
    # Add thinking mode directives AFTER ARCH_CORE_PROMPT and AFTER QB preamble
    thinking_directives = _build_thinking_mode_directives(thinking_mode)
    system_preamble += thinking_directives

    # Extract query text from validated body
    q = body.get_query_text()
    if not q:
        raise HTTPException(status_code=400, detail="Query text is required (provide 'q', 'text', 'input', 'prompt', 'message', or 'messages')")

    # Extract settings from validated body
    settings = body.get_settings_dict()
    # Debug: посмотреть, какие ключи реально приходят из UI
    try:
        print("[SETTINGS]", settings)
    except Exception:
        pass

    # UI settings игнорируются для system prompt (используем фиксированный ARCH_CORE_PROMPT)
    # Но оставляем выбор модели и другие параметры из UI
    tone = str(settings.get("response_tone", "") or "").lower()
    density = str(settings.get("output_density", "") or "").lower()
    temp = settings.get("temperature", None)
    ui_lang = str(settings.get("interface_language", "") or "").lower()

    # Выбор модели по умолчанию для Ollama
    model_name = "mistral"

    # Опциональный выбор модели из настроек UI (NEURAL ENGINE / Active model weight)
    raw_model = str(
        settings.get("model")
        or settings.get("active_model")
        or settings.get("activeModel")
        or settings.get("active_model_weight")
        or settings.get("model_name")
        or settings.get("llm_model")
        or ""
    ).strip().lower()
    if raw_model:
        # Убираем суффиксы вида "-local" / "_local" (как в UI: "mistral-7b-local")
        normalized = raw_model.replace("-local", "").replace("_local", "")

        # Mistral-7B
        if normalized in ("mistral-7b", "mistral", "mistral_7b"):
            model_name = "mistral"
        # Hermes-7B (обычно nous-hermes2:7b)
        elif normalized in (
            "hermes-7b",
            "hermes",
            "hermes:7b",
            "nous-hermes2:7b",
            "nous-hermes2-mistral-7b",
        ):
            model_name = "nous-hermes2:7b"
        # LLaMA-3.1-8B
        elif normalized in (
            "llama-3.1-8b",
            "llama3.1-8b",
            "llama3.1",
            "llama3",
            "llama3.1:8b",
        ):
            model_name = "llama3.1:8b"
        # Qwen-2.5-14B
        elif normalized in ("qwen-2.5-14b", "qwen25-14b", "qwen2.5-14b"):
            model_name = "qwen2.5:14b"
        # Mixtral-8x7B
        elif normalized in ("mixtral-8x7b", "mixtral", "mixtral-8x7b-instruct"):
            model_name = "mixtral:8x7b"
        # DeepSeek-32B
        elif normalized in (
            "deepseek-32b",
            "deepseek32b",
            "deepseek-v2:32b",
            "deepseek-v2.5:32b",
        ):
            model_name = "deepseek-v2:32b"
        # DeepSeek-14B / r1-8B
        elif normalized in ("deepseek-14b", "deepseek", "deepseek-r1", "deepseek-r1:8b"):
            model_name = "deepseek-r1:8b"
        else:
            # неизвестное имя модели — оставляем дефолт и просто логируем
            print(f"[LLM] unknown model override '{raw_model}', using default '{model_name}'")

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

    # Core Dialog: system_preamble фиксирован (ARCH_CORE_PROMPT)
    # UI не может модифицировать system prompt через settings
    # extra_parts игнорируются для system prompt

    # Extract and validate session_id from validated body
    # (Already extracted earlier for QB check, but ensure it's validated)
    if not sess_id:
        sess_id = body.get_session_id()
        sess_id = validate_session_id(sess_id) if sess_id else None
    else:
        # Re-validate to ensure consistency
        sess_id = validate_session_id(sess_id)

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

    # Общий extractor профиля (локация и др. правила)
    prof_reply = extract_profile_facts(q, sess_id)
    if prof_reply is not None:
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", prof_reply)
        except Exception:
            pass
        return {"reply": prof_reply}

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

    # Вопросы про активную модель / движок — отвечаем сами, без RAG и без фантазий LLM
    if any(
        tok in q_l
        for tok in [
            "какая модель",
            "какая у тебя модель",
            "какая сейчас модель",
            "активная модель",
            "что за модель",
            "что за движок",
            "какой движок",
            "какой вес модели",
            "нейросеть какая",
            "нейронка какая",
        ]
    ):
        # Человекочитаемое имя модели: предпочитаем то, что пришло из настроек
        human_model = settings.get("model") or model_name

        # Короткое описание отличий по типу модели
        desc = ""
        m_low = model_name.lower()
        if "hermes" in m_low:
            desc = (
                "Hermes-7B обычно даёт более развернутые и разговорные ответы, "
                "в то время как Mistral-7B более сдержанный и лаконичный."
            )
        elif "llama" in m_low:
            desc = (
                "LLaMA-3.1-8B хорошо держит контекст и логические цепочки, "
                "по сравнению с Mistral-7B чуть свободнее формулирует ответы."
            )
        elif "qwen" in m_low:
            desc = "Qwen-2.5-14B силён в фактах и коде, ответы обычно структурированные."
        elif "mixtral" in m_low:
            desc = "Mixtral-8x7B даёт более мощный и разнообразный вывод за счёт смеси экспертов."
        elif "deepseek" in m_low:
            desc = "DeepSeek часто хорош в рассуждениях и технических темах."

        reply = f"Сейчас активна модель: {human_model} (Ollama: {model_name})."
        if desc:
            reply += " " + desc

        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        return {"reply": reply}

    # Вопросы вида "что ты помнишь обо мне" — отвечаем строго из профиля, без LLM
    if any(
        tok in q_l
        for tok in [
            "что ты помнишь обо мне",
            "что помнишь обо мне",
            "что ты обо мне помнишь",
            "что знаешь обо мне",
            "что ты обо мне знаешь",
            "что помнишь про меня",
        ]
    ):
        parts: list[str] = []

        loc = FACTS_PROFILE.get("location")
        if loc:
            parts.append(f"ты живёшь в {loc}")

        zodiac = FACTS_PROFILE.get("zodiac")
        if zodiac:
            parts.append(f"твой знак зодиака — {zodiac}")

        goals = FACTS_PROFILE.get("goals") or []
        if isinstance(goals, list) and goals:
            goals_str = "; ".join(str(g) for g in goals[:3])
            if len(goals) > 3:
                goals_str += " и ещё несколько целей"
            parts.append(f"твои цели: {goals_str}")

        tfreq = FACTS_PROFILE.get("training_freq")
        if tfreq:
            parts.append(f"ты тренируешься {tfreq} раза в неделю")

        if parts:
            reply = "Вот что я о тебе помню: " + "; ".join(parts) + "."
        else:
            reply = (
                "Честно — в профиле почти нет данных именно о тебе. "
                "Расскажи мне о себе: где живёшь, какие цели и режим — я запомню."
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


    # Простое приветствие / small talk — отвечаем сами, без RAG и LLM
    if any(
        tok in q_l
        for tok in [
            "привет",
            "здравствуй",
            "здравствуйте",
            "hi",
            "hello",
            "hey",
        ]
    ) and len(q_l) <= 40:
        reply = "Привет. Я на связи, давай разбираться, что нужно сделать."
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        return {"reply": reply}

    # Small talk: "как дела" — тоже обрабатываем без RAG/LLM
    if any(
        phrase in q_l
        for phrase in [
            "как дела",
            "как у тебя дела",
            "как твои дела",
            "как поживаешь",
            "как настроение",
        ]
    ) and len(q_l) <= 60:
        reply = "Нормально, работаю над твоими задачами. Главное — твои дела, давай говорить про них."
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        return {"reply": reply}

    # Короткие подтверждения/реакции ("ок", "супер", "круто" и т.п.) — отвечаем сами
    if any(
        phrase in q_l
        for phrase in [
            "ок",
            "окей",
            "okay",
            "ладно",
            "норм",
            "супер",
            "круто",
            "огонь",
            "топ",
            "класс",
            "спасибо",
        ]
    ) and len(q_l) <= 40:
        reply = "Принял. Двигаемся дальше."
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
        # Для очень коротких вопросов (small talk / простые вопросы) RAG не используем.
        # RAG включается только для более длинных / содержательных запросов.
        use_rag = len(q_l) > 40
        rag_ok = False

        if use_rag:
            try:
                async with httpx.AsyncClient(timeout=10.0) as c:
                    r = await c.get(
                        "http://127.0.0.1:8000/memory/search",
                        params={"q": q, "session_id": sess_id, "k": 3},
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
                        # G3: Log memory hit
                        logger.info(
                            "[MEMORY_HIT]",
                            extra={
                                "session_id": sess_id,
                                "user": "dev",
                                "count": len(hits),
                                "namespace": None
                            }
                        )
            except httpx.TimeoutException:
                logger.warning(f"[RAG TIMEOUT] RAG retrieval timed out for query (session_id={sess_id})")
                # G3: Log error
                logger.error(
                    "[ERROR] RAG timeout",
                    extra={
                        "session_id": sess_id,
                        "user": "dev",
                        "exception": "RAG retrieval timed out"
                    }
                )
                rag_ctx = ""
                rag_ok = False
            except Exception as e:
                logger.warning(f"[RAG ERROR] RAG retrieval failed: {e}")
                # G3: Log error
                logger.error(
                    "[ERROR] RAG retrieval_failed",
                    extra={
                        "session_id": sess_id,
                        "user": "dev",
                        "exception": str(e)
                    }
                )
                rag_ctx = ""
                rag_ok = False

        # --- D4: Rehydration context (summary + recent dialogue) ---
        summary = _get_full_summary(sess_id)
        recent_dialogue = _get_recent_dialogue(sess_id, n_user_turns=12)
        
        # Build rehydration context
        rehydration_parts = []
        
        if summary and summary.get("text"):
            summary_text = summary.get("text", "")
            summary_until = summary.get("until_user_turn", 0)
            rehydration_parts.append("SUMMARY:")
            rehydration_parts.append(summary_text)
            rehydration_parts.append(f"SUMMARY_UNTIL_USER_TURN: {summary_until}")
            rehydration_parts.append("")
        
        if recent_dialogue:
            rehydration_parts.append("RECENT_DIALOGUE:")
            for msg in recent_dialogue:
                role = msg.get("role", "")
                content = msg.get("content", "").strip()
                if content:
                    rehydration_parts.append(f"{role}: {content}")
            rehydration_parts.append("")
        
        rehydration_parts.append("CURRENT_INPUT:")
        rehydration_parts.append(q)
        
        rehydration_ctx = "\n".join(rehydration_parts)
        
        # DEBUG log
        using_summary = bool(summary and summary.get("text"))
        summary_until = summary.get("until_user_turn") if summary else None
        recent_user_turns = sum(1 for msg in recent_dialogue if msg.get("role") == "user")
        logger.debug(f"[rehydration] using_summary={using_summary} summary_until={summary_until} recent_user_turns={recent_user_turns}")

        # user payload: combine rehydration context with RAG (if available)
        if rag_ctx:
            user_payload = f"CONTEXT:\n{rehydration_ctx}\n\n[MEMORY]\n{rag_ctx}"
        else:
            user_payload = f"CONTEXT:\n{rehydration_ctx}"

        if rag_ctx:
            system_preamble += " ВНИМАНИЕ: отвечай ТОЛЬКО на основе блока [MEMORY] ниже. Ничего не придумывай. Если пользователь просит точную фразу, верни её дословно из [MEMORY] без изменений."

        # --- call LLM via Ollama chat ---
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    "http://localhost:11434/api/chat",
                    json={
                        "model": model_name,
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
                    answer = "".join(chunks).strip()
                    
                    if not answer:
                        # Если есть RAG-контекст, в строгом режиме просто возвращаем его как ответ
                        if rag_ctx:
                            print(
                                "[LLM WARNING] пустой ответ от модели",
                                model_name,
                                "при наличии RAG-контекста; возвращаю rag_ctx",
                                repr(q),
                            )
                            answer = rag_ctx
                        else:
                            # Глобальный фолбэк: никогда не отдаём пустую строку в UI
                            print(
                                "[LLM WARNING] пустой ответ от модели",
                                model_name,
                                "на запрос без RAG:",
                                repr(q),
                            )
                            answer = (
                                "Я не получил нормальный ответ от модели на этот запрос. "
                                "Сформулируй мысль ещё раз или чуть подробнее — и попробуем снова."
                            )
        except httpx.TimeoutException:
            logger.error(f"[LLM TIMEOUT] LLM call timed out after 60s (session_id={sess_id})")
            # G3: Log error
            logger.error(
                "[ERROR] chat LLM_timeout",
                extra={
                    "session_id": sess_id,
                    "user": "dev",
                    "exception": "LLM request timed out"
                }
            )
            raise HTTPException(status_code=504, detail="LLM request timed out")
        except Exception as e:
            raise

        # PERSIST: сохраняем user и assistant сообщения
        try:
            _append_msg(sess_id, "assistant", answer)
            # Логируем сохранение для отладки
            f = SESS_DIR / f"{sess_id}.jsonl"
            print("[PERSIST]", sess_id, "jsonl:", f, "user_len:", len(q), "assistant_len:", len(answer))
        except Exception as e:
            print("[PERSIST ERROR]", sess_id, "error:", e)
            pass

        # MEMORY: сохраняем user message и assistant reply в память
        try:
            safe_memory_add(q, sess_id, "user")
            safe_memory_add(answer, sess_id, "assistant")
        except Exception as e:
            logger.debug(f"[memory] skipped: {e}")

        # Compute summary_pending
        summary_pending = False
        try:
            user_turn_count = _count_user_turns(sess_id)
            summary_obj = _get_summary_stub(sess_id)
            summary_pending = should_update_summary(user_turn_count, summary_obj)
        except Exception as e:
            logger.debug(f"[summary] failed to compute summary_pending: {e}")

        # Generate summary if pending (D3: aut-summary generation)
        # Run in background to avoid blocking /chat response
        if summary_pending:
            asyncio.create_task(_run_summary_task(sess_id))
            # summary_pending remains True (summary is being generated in background)

        # Build response
        response = {
            "reply": answer,
            "rag_ctx_head": (rag_ctx or "")[:200],
            "summary_pending": summary_pending
        }
        
        # Add QB payload if available (for debugging/UI)
        if qb_payload:
            response["qb"] = qb_payload
        
        # Add rehydration diagnostics only if DEBUG_REHYDRATION is enabled
        if DEBUG_REHYDRATION:
            response.update({
                "rehydration_used": using_summary,
                "rehydration_summary_until": summary_until,
                "rehydration_recent_user_turns": recent_user_turns
            })
        
        return response
    except Exception as e:
        # G3: Log error
        logger.error(
            "[ERROR] chat handler_failed",
            extra={
                "session_id": sess_id if 'sess_id' in locals() else None,
                "user": "dev",
                "exception": str(e)
            }
        )
        return {"reply": f"echo: {q} (ollama failed: {e})"}


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest):
    """
    G2: Streaming version of /chat endpoint.
    Uses same context building logic (rehydration + RAG) as /chat.
    Returns SSE events: meta, token, done, error.
    """
    from backend.app.chat import ARCH_CORE_PROMPT
    from typing import AsyncGenerator
    
    # G3 fix: Initialize system_preamble at the very beginning to avoid UnboundLocalError
    system_preamble = ARCH_CORE_PROMPT
    
    # Extract and validate query text
    q = body.get_query_text()
    if not q:
        async def error_gen() -> AsyncGenerator[str, None]:
            error_event = json.dumps({"type": "error", "message": "Query text is required"}, ensure_ascii=False)
            yield f"event: error\ndata: {error_event}\n\n"
        return StreamingResponse(
            error_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    
    # Extract and validate session_id
    sess_id = body.get_session_id()
    from backend.app.main import validate_session_id
    sess_id = validate_session_id(sess_id)
    
    # Extract settings (same as /chat)
    settings = body.get_settings_dict()
    tone = str(settings.get("response_tone", "") or "").lower()
    density = str(settings.get("output_density", "") or "").lower()
    ui_lang = str(settings.get("interface_language", "") or "").lower()
    
    # Model selection (same as /chat)
    model_name = "mistral"
    raw_model = str(
        settings.get("model")
        or settings.get("active_model")
        or settings.get("activeModel")
        or settings.get("active_model_weight")
        or settings.get("model_name")
        or settings.get("llm_model")
        or ""
    ).strip().lower()
    if raw_model:
        normalized = raw_model.replace("-local", "").replace("_local", "")
        if normalized in ("mistral-7b", "mistral", "mistral_7b"):
            model_name = "mistral"
        elif normalized in ("hermes-7b", "hermes", "hermes:7b", "nous-hermes2:7b", "nous-hermes2-mistral-7b"):
            model_name = "nous-hermes2:7b"
        elif normalized in ("llama-3.1-8b", "llama3.1-8b", "llama3.1", "llama3", "llama3.1:8b"):
            model_name = "llama3.1:8b"
        elif normalized in ("qwen-2.5-14b", "qwen25-14b", "qwen2.5-14b"):
            model_name = "qwen2.5:14b"
        elif normalized in ("mixtral-8x7b", "mixtral", "mixtral-8x7b-instruct"):
            model_name = "mixtral:8x7b"
        elif normalized in ("deepseek-32b", "deepseek32b", "deepseek-v2:32b", "deepseek-v2.5:32b"):
            model_name = "deepseek-v2:32b"
        elif normalized in ("deepseek-14b", "deepseek", "deepseek-r1", "deepseek-r1:8b"):
            model_name = "deepseek-r1:8b"
    
    # system_preamble already initialized at the beginning of the function
    
    # --- PHASE J2: Thinking Mode directives ---
    # Extract thinking_mode: priority: body.thinking_mode, else default "structured"
    thinking_mode = body.thinking_mode or "structured"
    
    # --- v0.7: QB -> /chat bridge ---
    # PHASE Q5: Pass thinking_mode to QB payload generation
    qb_payload = None
    if body.qb_enabled and body.qb_session_id:
        qb_payload = _get_qb_payload(body.qb_session_id, thinking_mode)
        if qb_payload and qb_payload.get("chat_preamble"):
            system_preamble += "\n\n" + qb_payload["chat_preamble"] + "\n"
    
    # Add thinking mode directives AFTER ARCH_CORE_PROMPT and AFTER QB preamble
    thinking_directives = _build_thinking_mode_directives(thinking_mode)
    system_preamble += thinking_directives
    
    # Extra parts from tone/density/lang (same as /chat)
    extra_parts: list[str] = []
    if tone == "bro":
        extra_parts.append("Стиль: токсично-доброжелательный брат. Говори честно, прямо, иногда жёстко, но с уважением и поддержкой. Без лишних извинений и подлизывания.")
    elif tone == "strict":
        extra_parts.append("Стиль: строгий, деловой, без лишних эмоций и без воды.")
    elif tone == "neutral":
        extra_parts.append("Стиль: спокойный, нейтральный, без излишней эмоциональности.")
    if density == "short":
        extra_parts.append("Отвечай максимально кратко: 2–4 коротких предложения или список из 3–5 пунктов.")
    elif density == "deep":
        extra_parts.append("Отвечай подробно и глубоко: разбирай по шагам, добавляй примеры и выводы, но без воды.")
    if ui_lang in ("ru", "ru-ru", "russian"):
        extra_parts.append("Отвечай по-русски.")
    elif ui_lang in ("en", "en-us", "en-gb", "english"):
        extra_parts.append("Answer in English.")
    
    q_l = q.lower().strip()
    
    # Quick responses (same as /chat) - return immediately via SSE
    # Zodiac date extraction
    dob_match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", q)
    if dob_match and ("дата рождения" in q_l or "родился" in q_l or "родилась" in q_l):
        try:
            day = int(dob_match.group(1))
            month = int(dob_match.group(2))
            zodiac = _zodiac_from_day_month(day, month)
            FACTS_PROFILE["zodiac"] = zodiac
            reply = f"Запомнил. Твой знак зодиака — {zodiac}."
            try:
                add_fact(Fact(subject="Arch", predicate="zodiac", object=zodiac, category="other", source_session=sess_id))
            except Exception:
                pass
            try:
                _append_msg(sess_id, "user", q)
                _append_msg(sess_id, "assistant", reply)
            except Exception:
                pass
            async def quick_reply_gen() -> AsyncGenerator[str, None]:
                meta_data = {"type": "meta", "session_id": sess_id, "model": model_name}
                if qb_payload:
                    meta_data["qb"] = qb_payload
                yield _sse_event("meta", meta_data)
                # Send reply as single token
                token_event = json.dumps({"type": "token", "delta": reply}, ensure_ascii=False)
                yield f"event: token\ndata: {token_event}\n\n"
                done_event = json.dumps({"type": "done", "finish_reason": "stop"}, ensure_ascii=False)
                yield f"event: done\ndata: {done_event}\n\n"
            return StreamingResponse(quick_reply_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
        except Exception:
            pass
    
    # Profile facts extraction
    prof_reply = extract_profile_facts(q, sess_id)
    if prof_reply is not None:
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", prof_reply)
        except Exception:
            pass
        async def quick_reply_gen() -> AsyncGenerator[str, None]:
            meta_event = json.dumps({"type": "meta", "session_id": sess_id, "model": model_name}, ensure_ascii=False)
            yield f"event: meta\ndata: {meta_event}\n\n"
            token_event = json.dumps({"type": "token", "delta": prof_reply}, ensure_ascii=False)
            yield f"event: token\ndata: {token_event}\n\n"
            done_event = json.dumps({"type": "done", "finish_reason": "stop"}, ensure_ascii=False)
            yield f"event: done\ndata: {done_event}\n\n"
        return StreamingResponse(quick_reply_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
    
    # Hard facts from profile
    if "знак зодиака" in q_l:
        zodiac = FACTS_PROFILE.get("zodiac")
        if zodiac:
            reply = f"Твой знак зодиака — {zodiac}."
        else:
            reply = "У меня нет в профиле данных о твоём знаке зодиака. Могу запомнить, если скажешь."
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        async def quick_reply_gen() -> AsyncGenerator[str, None]:
            meta_event = json.dumps({"type": "meta", "session_id": sess_id, "model": model_name}, ensure_ascii=False)
            yield f"event: meta\ndata: {meta_event}\n\n"
            token_event = json.dumps({"type": "token", "delta": reply}, ensure_ascii=False)
            yield f"event: token\ndata: {token_event}\n\n"
            done_event = json.dumps({"type": "done", "finish_reason": "stop"}, ensure_ascii=False)
            yield f"event: done\ndata: {done_event}\n\n"
        return StreamingResponse(quick_reply_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
    
    # Model questions
    if any(tok in q_l for tok in ["какая модель", "какая у тебя модель", "какая сейчас модель", "активная модель", "что за модель", "что за движок", "какой движок", "какой вес модели", "нейросеть какая", "нейронка какая"]):
        human_model = settings.get("model") or model_name
        desc = ""
        m_low = model_name.lower()
        if "hermes" in m_low:
            desc = "Hermes-7B обычно даёт более развернутые и разговорные ответы, в то время как Mistral-7B более сдержанный и лаконичный."
        elif "llama" in m_low:
            desc = "LLaMA-3.1-8B хорошо держит контекст и логические цепочки, по сравнению с Mistral-7B чуть свободнее формулирует ответы."
        elif "qwen" in m_low:
            desc = "Qwen-2.5-14B силён в фактах и коде, ответы обычно структурированные."
        elif "mixtral" in m_low:
            desc = "Mixtral-8x7B даёт более мощный и разнообразный вывод за счёт смеси экспертов."
        elif "deepseek" in m_low:
            desc = "DeepSeek часто хорош в рассуждениях и технических темах."
        reply = f"Сейчас активна модель: {human_model} (Ollama: {model_name})."
        if desc:
            reply += " " + desc
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        async def quick_reply_gen() -> AsyncGenerator[str, None]:
            meta_event = json.dumps({"type": "meta", "session_id": sess_id, "model": model_name}, ensure_ascii=False)
            yield f"event: meta\ndata: {meta_event}\n\n"
            token_event = json.dumps({"type": "token", "delta": reply}, ensure_ascii=False)
            yield f"event: token\ndata: {token_event}\n\n"
            done_event = json.dumps({"type": "done", "finish_reason": "stop"}, ensure_ascii=False)
            yield f"event: done\ndata: {done_event}\n\n"
        return StreamingResponse(quick_reply_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
    
    # Profile memory questions
    if any(tok in q_l for tok in ["что ты помнишь обо мне", "что помнишь обо мне", "что ты обо мне помнишь", "что знаешь обо мне", "что ты обо мне знаешь", "что помнишь про меня"]):
        parts: list[str] = []
        loc = FACTS_PROFILE.get("location")
        if loc:
            parts.append(f"ты живёшь в {loc}")
        zodiac = FACTS_PROFILE.get("zodiac")
        if zodiac:
            parts.append(f"твой знак зодиака — {zodiac}")
        goals = FACTS_PROFILE.get("goals") or []
        if isinstance(goals, list) and goals:
            goals_str = "; ".join(str(g) for g in goals[:3])
            if len(goals) > 3:
                goals_str += " и ещё несколько целей"
            parts.append(f"твои цели: {goals_str}")
        tfreq = FACTS_PROFILE.get("training_freq")
        if tfreq:
            parts.append(f"ты тренируешься {tfreq} раза в неделю")
        if parts:
            reply = "Вот что я о тебе помню: " + "; ".join(parts) + "."
        else:
            reply = "Честно — в профиле почти нет данных именно о тебе. Расскажи мне о себе: где живёшь, какие цели и режим — я запомню."
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        async def quick_reply_gen() -> AsyncGenerator[str, None]:
            meta_event = json.dumps({"type": "meta", "session_id": sess_id, "model": model_name}, ensure_ascii=False)
            yield f"event: meta\ndata: {meta_event}\n\n"
            token_event = json.dumps({"type": "token", "delta": reply}, ensure_ascii=False)
            yield f"event: token\ndata: {token_event}\n\n"
            done_event = json.dumps({"type": "done", "finish_reason": "stop"}, ensure_ascii=False)
            yield f"event: done\ndata: {done_event}\n\n"
        return StreamingResponse(quick_reply_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
    
    # Quick check modes
    if any(tok in q_l for tok in ["#morning_check", "план на день", "план на сегодня", "что у нас по плану", "что по плану", "утро", "morning"]):
        work = FACTS_PROFILE.get("work_time", "10:00–19:00")
        gym = FACTS_PROFILE.get("gym_time", "19:30")
        reply = f"План:\n— Работа {work}.\n— Зал {gym} (45–60 мин): базовые упражнения.\n— Вечер 20 мин: AIR4 — один микрошаг (экран/фикс), без перфекционизма.\nФинансы: резерва +600€ на неделе."
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        async def quick_reply_gen() -> AsyncGenerator[str, None]:
            meta_event = json.dumps({"type": "meta", "session_id": sess_id, "model": model_name}, ensure_ascii=False)
            yield f"event: meta\ndata: {meta_event}\n\n"
            token_event = json.dumps({"type": "token", "delta": reply}, ensure_ascii=False)
            yield f"event: token\ndata: {token_event}\n\n"
            done_event = json.dumps({"type": "done", "finish_reason": "stop"}, ensure_ascii=False)
            yield f"event: done\ndata: {done_event}\n\n"
        return StreamingResponse(quick_reply_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
    
    if any(tok in q_l for tok in ["#evening_check", "итог дня", "вечер", "вечером", "закрыть день"]):
        reply = "Итог дня:\n— Работа — закрыто, движ есть.\n— Тренировка — ✅ если был в зале.\n— AIR4 — +1 шаг, фиксанул без перфекционизма.\n— В целом — не идеально, но стабильно. Завтра дожмём."
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        async def quick_reply_gen() -> AsyncGenerator[str, None]:
            meta_event = json.dumps({"type": "meta", "session_id": sess_id, "model": model_name}, ensure_ascii=False)
            yield f"event: meta\ndata: {meta_event}\n\n"
            token_event = json.dumps({"type": "token", "delta": reply}, ensure_ascii=False)
            yield f"event: token\ndata: {token_event}\n\n"
            done_event = json.dumps({"type": "done", "finish_reason": "stop"}, ensure_ascii=False)
            yield f"event: done\ndata: {done_event}\n\n"
        return StreamingResponse(quick_reply_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
    
    if any(tok in q_l for tok in ["#week_check", "итоги недели", "неделя", "неделю закрыть"]):
        reply = "Неделя:\n— Финансы: +620€ (по плану).\n— Тренировки: 3 / 3 — стабильно.\n— AIR4: несколько шагов — идёт прогресс.\n— Общий вывод: ровно, без спешки, но в росте.\n— Следующая неделя — добавить 1 новый шаг или идею."
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        async def quick_reply_gen() -> AsyncGenerator[str, None]:
            meta_event = json.dumps({"type": "meta", "session_id": sess_id, "model": model_name}, ensure_ascii=False)
            yield f"event: meta\ndata: {meta_event}\n\n"
            token_event = json.dumps({"type": "token", "delta": reply}, ensure_ascii=False)
            yield f"event: token\ndata: {token_event}\n\n"
            done_event = json.dumps({"type": "done", "finish_reason": "stop"}, ensure_ascii=False)
            yield f"event: done\ndata: {done_event}\n\n"
        return StreamingResponse(quick_reply_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
    
    # Small talk
    if any(tok in q_l for tok in ["привет", "здравствуй", "здравствуйте", "hi", "hello", "hey"]) and len(q_l) <= 40:
        reply = "Привет. Я на связи, давай разбираться, что нужно сделать."
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        async def quick_reply_gen() -> AsyncGenerator[str, None]:
            meta_event = json.dumps({"type": "meta", "session_id": sess_id, "model": model_name}, ensure_ascii=False)
            yield f"event: meta\ndata: {meta_event}\n\n"
            token_event = json.dumps({"type": "token", "delta": reply}, ensure_ascii=False)
            yield f"event: token\ndata: {token_event}\n\n"
            done_event = json.dumps({"type": "done", "finish_reason": "stop"}, ensure_ascii=False)
            yield f"event: done\ndata: {done_event}\n\n"
        return StreamingResponse(quick_reply_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
    
    if any(phrase in q_l for phrase in ["как дела", "как у тебя дела", "как твои дела", "как поживаешь", "как настроение"]) and len(q_l) <= 60:
        reply = "Нормально, работаю над твоими задачами. Главное — твои дела, давай говорить про них."
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        async def quick_reply_gen() -> AsyncGenerator[str, None]:
            meta_event = json.dumps({"type": "meta", "session_id": sess_id, "model": model_name}, ensure_ascii=False)
            yield f"event: meta\ndata: {meta_event}\n\n"
            token_event = json.dumps({"type": "token", "delta": reply}, ensure_ascii=False)
            yield f"event: token\ndata: {token_event}\n\n"
            done_event = json.dumps({"type": "done", "finish_reason": "stop"}, ensure_ascii=False)
            yield f"event: done\ndata: {done_event}\n\n"
        return StreamingResponse(quick_reply_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
    
    if any(phrase in q_l for phrase in ["ок", "окей", "okay", "ладно", "норм", "супер", "круто", "огонь", "топ", "класс", "спасибо"]) and len(q_l) <= 40:
        reply = "Принял. Двигаемся дальше."
        try:
            _append_msg(sess_id, "user", q)
            _append_msg(sess_id, "assistant", reply)
        except Exception:
            pass
        async def quick_reply_gen() -> AsyncGenerator[str, None]:
            meta_event = json.dumps({"type": "meta", "session_id": sess_id, "model": model_name}, ensure_ascii=False)
            yield f"event: meta\ndata: {meta_event}\n\n"
            token_event = json.dumps({"type": "token", "delta": reply}, ensure_ascii=False)
            yield f"event: token\ndata: {token_event}\n\n"
            done_event = json.dumps({"type": "done", "finish_reason": "stop"}, ensure_ascii=False)
            yield f"event: done\ndata: {done_event}\n\n"
        return StreamingResponse(quick_reply_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
    
    # Main streaming logic (same context building as /chat)
    async def stream_gen() -> AsyncGenerator[str, None]:
        # G3 fix: Use local variable to avoid UnboundLocalError with += in nested scope
        from backend.app.chat import ARCH_CORE_PROMPT
        preamble = ARCH_CORE_PROMPT
        
        try:
            # Log user message
            try:
                _append_msg(sess_id, "user", q)
            except Exception:
                pass
            
            # first packet: meta (UI uses it to render mode/buttons before tokens)
            meta_data = {"type": "meta", "session_id": sess_id, "model": model_name}
            if qb_payload:
                meta_data["qb"] = qb_payload
            yield _sse_event("meta", meta_data)
            
            # RAG context (same as /chat)
            rag_ctx = ""
            use_rag = len(q_l) > 40
            rag_ok = False
            
            if use_rag:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as c:
                        r = await c.get(
                            "http://127.0.0.1:8000/memory/search",
                            params={"q": q, "session_id": sess_id, "k": 3},
                        )
                        js = r.json()
                        hits = js.get("results", [])
                        if (
                            hits
                            and isinstance(hits[0], dict)
                            and hits[0].get("text")
                            and hits[0].get("score") is not None
                            and hits[0]["score"] >= RAG_SCORE_THRESHOLD
                        ):
                            rag_ctx = hits[0]["text"][:1200]
                            rag_ok = True
                except Exception as e:
                    logger.warning(f"[RAG ERROR] RAG retrieval failed: {e}")
                    rag_ctx = ""
                    rag_ok = False
            
            # Rehydration context (same as /chat)
            summary = _get_full_summary(sess_id)
            recent_dialogue = _get_recent_dialogue(sess_id, n_user_turns=12)
            
            rehydration_parts = []
            if summary and summary.get("text"):
                summary_text = summary.get("text", "")
                summary_until = summary.get("until_user_turn", 0)
                rehydration_parts.append("SUMMARY:")
                rehydration_parts.append(summary_text)
                rehydration_parts.append(f"SUMMARY_UNTIL_USER_TURN: {summary_until}")
                rehydration_parts.append("")
            
            if recent_dialogue:
                rehydration_parts.append("RECENT_DIALOGUE:")
                for msg in recent_dialogue:
                    role = msg.get("role", "")
                    content = msg.get("content", "").strip()
                    if content:
                        rehydration_parts.append(f"{role}: {content}")
                rehydration_parts.append("")
            
            rehydration_parts.append("CURRENT_INPUT:")
            rehydration_parts.append(q)
            rehydration_ctx = "\n".join(rehydration_parts)
            
            # User payload (same as /chat)
            if rag_ctx:
                user_payload = f"CONTEXT:\n{rehydration_ctx}\n\n[MEMORY]\n{rag_ctx}"
            else:
                user_payload = f"CONTEXT:\n{rehydration_ctx}"
            
            if rag_ctx:
                preamble += " ВНИМАНИЕ: отвечай ТОЛЬКО на основе блока [MEMORY] ниже. Ничего не придумывай. Если пользователь просит точную фразу, верни её дословно из [MEMORY] без изменений."
            
            # Stream LLM response
            full_answer = ""
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    async with client.stream(
                        "POST",
                        "http://localhost:11434/api/chat",
                        json={
                            "model": model_name,
                            "messages": [
                                {"role": "system", "content": preamble},
                                {"role": "user", "content": user_payload},
                            ],
                            "stream": True,
                        },
                    ) as res:
                        res.raise_for_status()
                        async for line in res.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                json_line = json.loads(line)
                                content = json_line.get("message", {}).get("content", "")
                                if content:
                                    full_answer += content
                                    token_event = json.dumps({"type": "token", "delta": content}, ensure_ascii=False)
                                    yield f"event: token\ndata: {token_event}\n\n"
                            except Exception:
                                continue
            except httpx.TimeoutException:
                logger.error(f"[LLM TIMEOUT] LLM call timed out after 60s (session_id={sess_id})")
                error_event = json.dumps({"type": "error", "message": "LLM request timed out"}, ensure_ascii=False)
                yield f"event: error\ndata: {error_event}\n\n"
                return
            except Exception as e:
                error_event = json.dumps({"type": "error", "message": f"LLM call failed: {str(e)}"}, ensure_ascii=False)
                yield f"event: error\ndata: {error_event}\n\n"
                return
            
            answer = full_answer.strip()
            
            # Fallback if empty answer (same as /chat)
            if not answer:
                if rag_ctx:
                    answer = rag_ctx
                else:
                    answer = "Я не получил нормальный ответ от модели на этот запрос. Сформулируй мысль ещё раз или чуть подробнее — и попробуем снова."
                # Send fallback as single token
                token_event = json.dumps({"type": "token", "delta": answer}, ensure_ascii=False)
                yield f"event: token\ndata: {token_event}\n\n"
            
            # Persist messages (same as /chat)
            try:
                _append_msg(sess_id, "assistant", answer)
            except Exception as e:
                logger.debug(f"[PERSIST ERROR] {e}")
            
            # Memory (same as /chat)
            try:
                safe_memory_add(q, sess_id, "user")
                safe_memory_add(answer, sess_id, "assistant")
            except Exception as e:
                logger.debug(f"[memory] skipped: {e}")
            
            # Summary pending (same as /chat)
            summary_pending = False
            try:
                user_turn_count = _count_user_turns(sess_id)
                summary_obj = _get_summary_stub(sess_id)
                summary_pending = should_update_summary(user_turn_count, summary_obj)
                if summary_pending:
                    asyncio.create_task(_run_summary_task(sess_id))
            except Exception as e:
                logger.debug(f"[summary] failed to compute summary_pending: {e}")
            
            # Send done event
            done_event = json.dumps({"type": "done", "finish_reason": "stop"}, ensure_ascii=False)
            yield f"event: done\ndata: {done_event}\n\n"
            
        except Exception as e:
            logger.error(f"[STREAM ERROR] {e}")
            error_event = json.dumps({"type": "error", "message": f"LLM call failed: {str(e)}"}, ensure_ascii=False)
            yield f"event: error\ndata: {error_event}\n\n"
    
    return StreamingResponse(
        stream_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/sessions")
def create_session(body: Optional[CreateSessionRequest] = None):
    """
    AIR4: создать новую сессию.
    Создаёт session id (8 hex chars), записывает в index.json и создаёт jsonl файл.
    """
    # Extract optional title from request body
    title = "New session"
    if body and body.title and body.title.strip():
        title = body.title.strip()
    
    # Generate session ID (8 hex characters)
    session_id = uuid.uuid4().hex[:8]
    
    # Load index.json
    try:
        idx = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
    except Exception:
        idx = {}
    
    # Create session entry
    now = int(time.time() * 1000)  # milliseconds
    session_entry = {
        "id": session_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "turns": 0,
        "summary": None,
    }
    
    # Add opening message for new session
    opening_content = "Я здесь.\nЕсли хочешь — можем продолжить с того, что было,\nили начать с того, что сейчас важно."
    _append_msg(session_id, "assistant", opening_content)
    
    # Add to index
    idx[session_id] = session_entry
    
    # Write index.json (atomic-ish: load, update, write)
    try:
        INDEX_PATH.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to write index.json: {e}")
        raise HTTPException(status_code=500, detail="Failed to create session")
    
    # Create jsonl file if not exists (can be empty)
    jsonl_path = SESS_DIR / f"{session_id}.jsonl"
    if not jsonl_path.exists():
        try:
            jsonl_path.touch()
        except Exception as e:
            logger.warning(f"Failed to create jsonl file for session {session_id}: {e}")
            # Don't fail the request if jsonl file creation fails
    
    return session_entry


@router.get("/sessions")
def list_sessions():
    """
    AIR4: список сессий для UI.
    Читаем index.json и возвращаем отсортированный список.
    Гарантируем, что каждая сессия имеет поле "id" (миграция legacy-сессий).
    """
    try:
        idx = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
    except Exception:
        idx = {}

    # Нормализация: гарантируем наличие "id" в каждой сессии
    # Используем ключ словаря как id (самый стабильный вариант)
    idx_modified = False
    sessions = []
    for session_key, session_data in idx.items():
        if not isinstance(session_data, dict):
            continue
        # Если id отсутствует, используем ключ словаря как id
        if "id" not in session_data or not session_data.get("id"):
            session_data["id"] = session_key
            idx[session_key] = session_data
            idx_modified = True
        # Миграция: если нет поля summary, добавляем null
        if "summary" not in session_data:
            session_data["summary"] = None
            idx[session_key] = session_data
            idx_modified = True
        sessions.append(session_data)
    
    # Сохраняем миграцию обратно в index.json если были изменения
    if idx_modified:
        try:
            INDEX_PATH.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save migrated sessions to index.json: {e}")

    sessions.sort(key=lambda r: r.get("updated_at", 0), reverse=True)
    return {"ok": True, "sessions": sessions}


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    """
    AIR4: вернуть полную информацию о сессии (id, title, messages, lastMessage, timestamp).
    Берём метаданные из index.json и messages из JSONL.
    """
    # Validate session_id
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    # Читаем метаданные из index.json
    try:
        idx = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
    except Exception:
        idx = {}
    
    meta = idx.get(session_id)
    if not meta:
        return JSONResponse({"ok": False, "error": "Session not found"}, status_code=404)

    # Читаем messages и summary из JSONL
    f = SESS_DIR / f"{session_id}.jsonl"
    messages = []
    summary = None
    if f.exists():
        try:
            with f.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg_data = json.loads(line)
                        # Если это summary event, сохраняем (последний будет актуальным)
                        if isinstance(msg_data, dict) and msg_data.get("type") == "summary":
                            summary = msg_data
                            continue
                        # Нормализация: если есть text или message, добавляем content для совместимости
                        if isinstance(msg_data, dict):
                            if "text" in msg_data and "content" not in msg_data:
                                msg_data["content"] = msg_data["text"]
                            elif "message" in msg_data and "content" not in msg_data:
                                msg_data["content"] = msg_data["message"]
                        messages.append(msg_data)
                    except Exception:
                        continue
        except Exception as e:
            return {"ok": False, "error": str(e), "messages": []}
    
    # Если в index summary == null, summary должен быть null
    # (мы уже прочитали jsonl, так что summary либо найден, либо None)
    
    # Normalize summary.updated_at to ISO8601 string if needed (for response only, don't rewrite jsonl)
    if summary and isinstance(summary, dict):
        updated_at = summary.get("updated_at")
        if updated_at and not isinstance(updated_at, str):
            summary = dict(summary)  # Make a copy to avoid modifying the original
            summary["updated_at"] = _now_iso()

    # Определяем lastMessage из последнего сообщения
    last_message = ""
    if messages:
        last_msg = messages[-1]
        if isinstance(last_msg, dict):
            # Проверяем разные возможные поля для content
            last_message = (
                last_msg.get("content") or 
                last_msg.get("text") or 
                last_msg.get("message") or 
                last_msg.get("value") or 
                ""
            )
            if isinstance(last_message, str):
                pass  # уже строка
            else:
                last_message = str(last_message)

    print(
        "[GET /sessions]",
        session_id,
        "messages:",
        len(messages),
        "file_exists:",
        f.exists()
    )

    title = meta.get("title", "New session")
    created_at = meta.get("created_at", 0)
    updated_at = meta.get("updated_at", 0)
    # Compute turns as number of user messages
    turns = 0
    try:
        if isinstance(messages, list):
            turns = sum(1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "user")
    except Exception:
        turns = 0
    print(f"[GET /sessions/{session_id}] returning title={title!r}, meta={meta}")
    return {
        "ok": True,
        "id": session_id,
        "title": title,
        "messages": messages,
        "lastMessage": last_message,
        "created_at": created_at,
        "updated_at": updated_at,
        "timestamp": updated_at,
        "turns": turns,
        "summary": summary
    }


@router.post("/sessions/{session_id}/clear")
def clear_session(session_id: str):
    """
    @deprecated Not used by GoogleUI. Internal endpoint.
    AIR4: очистить историю сессии.
    Удаляет JSONL-файл и запись из index.json.
    """
    # Validate session_id
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
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


@router.post("/force_summary")
async def force_summary(session_id: str = Body(..., embed=True)):
    """
    Manual trigger for session summary generation.
    Forces generation of session summary and storage in ChromaDB.
    
    Args:
        session_id: Session ID to generate summary for
    
    Returns:
        {"ok": True, "summary_generated": bool}
    """
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    
    try:
        await _generate_session_summary_chroma(session_id)
        logger.info(f"[force_summary] manual trigger for session {session_id}")
        return {"ok": True, "summary_generated": True, "session_id": session_id}
    except Exception as e:
        logger.error(f"[force_summary] failed for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Summary generation failed: {str(e)}")
