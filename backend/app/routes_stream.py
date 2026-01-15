from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import json
import time
import asyncio
import re
import tempfile
import os
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional, Dict, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

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


# --- Model Mode Router ---
# Mapping режимов к моделям
MODEL_MODE_MAP = {
    "fast": "mistral",  # Самая быстрая разговорная
    "normal": "qwen2.5:14b",  # Дефолтная разговорная (не R1)
    "smart": "deepseek-r1:8b",  # Reasoning модель для логики/аналитики
    "think": "deepseek-r1:8b",  # Alias для smart
}

# Ключевые слова для определения типа запроса
SMART_KEYWORDS = [
    # Аналитика/сравнение
    "сравни", "сравнение", "сравнить", "compare",
    "проанализируй", "проанализировать", "анализ", "analyze", "analysis",
    "выведи", "вывести", "вывод", "выведи формулу", "derive",
    "рассчитай", "рассчитать", "расчёт", "calculate", "calculation",
    "докажи", "доказать", "доказательство", "prove", "proof",
    # Планирование с ограничениями
    "план с ограничениями", "ограничения", "constraints", "constraint",
    # Поиск ошибок/оптимизация
    "найди ошибки", "найди ошибку", "ошибки", "find errors", "bug",
    "оптимизируй", "оптимизировать", "оптимизация", "optimize", "optimization",
    "улучши", "улучшить", "improve", "improvement",
]

NORMAL_KEYWORDS = [
    # Оффер/лендинг/копирайт
    "оффер", "offer", "лендинг", "landing", "копирайт", "copywriting",
    "реклама", "advertising", "рекламный", "текст",
    # UX/дизайн
    "ux", "ui", "дизайн", "design", "интерфейс", "interface",
    "usability", "юзабилити", "прототип", "prototype",
    # Общение/советы/коучинг
    "совет", "советы", "advice", "коучинг", "coaching", "помоги",
    "help", "как", "how", "что делать", "what should",
    # Small talk
    "привет", "hi", "hello", "как дела", "how are you",
]


def route_model_mode(query: str, explicit_mode: str | None = None) -> tuple[str, str, str]:
    """
    Определяет режим модели на основе запроса.
    
    Args:
        query: Текст запроса пользователя
        explicit_mode: Явно указанный режим ("fast", "normal", "smart", "think", "auto")
    
    Returns:
        tuple (mode, model, reason)
        - mode: выбранный режим ("fast", "normal", "smart")
        - model: имя модели Ollama
        - reason: причина выбора ("manual", "keyword", "len", "default")
    """
    # Если режим указан явно и не "auto" - используем его
    if explicit_mode and explicit_mode.lower() != "auto":
        mode = explicit_mode.lower()
        if mode in MODEL_MODE_MAP:
            model = MODEL_MODE_MAP[mode]
            return (mode, model, "manual")
        # Если невалидный режим - fallback на normal
        return ("normal", MODEL_MODE_MAP["normal"], "manual_invalid")
    
    # Auto-router: определяем на основе ключевых слов
    query_lower = query.lower().strip()
    
    # Проверяем SMART ключевые слова (приоритет выше)
    for keyword in SMART_KEYWORDS:
        if keyword in query_lower:
            model = MODEL_MODE_MAP["smart"]
            return ("smart", model, f"keyword:{keyword}")
    
    # Проверяем NORMAL ключевые слова
    for keyword in NORMAL_KEYWORDS:
        if keyword in query_lower:
            model = MODEL_MODE_MAP["normal"]
            return ("normal", model, f"keyword:{keyword}")
    
    # Эвристика по длине: короткие запросы -> fast, длинные -> normal
    query_len = len(query.strip())
    if query_len < 30:
        model = MODEL_MODE_MAP["fast"]
        return ("fast", model, "len_short")
    elif query_len > 200:
        # Длинные запросы могут требовать аналитики - используем normal (не smart, т.к. нет явных ключевых слов)
        model = MODEL_MODE_MAP["normal"]
        return ("normal", model, "len_long")
    else:
        # Дефолт для средних запросов
        model = MODEL_MODE_MAP["normal"]
        return ("normal", model, "default")


# Импортируем необходимые функции и константы из routes_chat
try:
    from backend.app.routes_chat import (
        _zodiac_from_day_month,
        extract_profile_facts,
        FACTS_PROFILE,
        RAG_SCORE_THRESHOLD,
    )
    from backend.app.memory.facts import Fact, add_fact, extract_facts_from_text_v3, extract_profile_facts_auto, get_facts_for_subject, delete_facts, SINGLE_VALUE_PREDICATES
except ImportError:
    from .routes_chat import (
        _zodiac_from_day_month,
        extract_profile_facts,
        FACTS_PROFILE,
        RAG_SCORE_THRESHOLD,
    )
    from .memory.facts import Fact, add_fact, extract_facts_from_text_v3, extract_profile_facts_auto, get_facts_for_subject, delete_facts, SINGLE_VALUE_PREDICATES

router = APIRouter()

# --- Session state для recall (в памяти, не в БД) ---
# Хранит последний успешный recall для каждой сессии
session_state: dict[str, dict[str, str]] = {}

# --- Session policy state для profile follow-up questions ---
# Хранит время последнего вопроса и ключ для каждой сессии
session_policy_state: dict[str, dict[str, float | str]] = {}

# --- Helper: определение follow-up вопросов ---
def is_followup_question(q: str) -> bool:
    """
    Определяет, является ли вопрос уточняющим (follow-up).
    Follow-up вопросы обычно короткие или содержат подтверждения/уточнения.
    """
    q_clean = q.strip()
    if not q_clean:
        return False
    
    words = q_clean.split()
    word_count = len(words)
    
    # Короткие вопросы (<= 3 слов)
    if word_count <= 3:
        return True
    
    # Вопросы, начинающиеся с определённых слов
    q_lower = q_clean.lower()
    followup_starters = [
        "а ", "и ", "он ", "она ", "оно ", "они ",
        "да", "нет", "точно", "правда", "верно",
    ]
    
    for starter in followup_starters:
        if q_lower.startswith(starter):
            return True
    
    # Проверка на цвета и подтверждения в тексте (не только в начале)
    followup_keywords = [
        "синий", "зелёный", "красный", "жёлтый", "чёрный", "белый",
        "оранжевый", "фиолетовый", "розовый", "серый",
        "точно", "верно", "правильно", "да", "нет",
    ]
    
    for keyword in followup_keywords:
        if keyword in q_lower:
            return True
    
    return False

# --- Helper: фильтрация мусорных фактов ---
def _is_valid_fact_object(obj: str) -> bool:
    """
    Проверяет, является ли object факта валидным (не мусором).
    Возвращает True, если факт стоит сохранять.
    """
    obj_clean = obj.strip().lower()
    if not obj_clean:
        return False
    
    # Если это число → мусор
    try:
        float(obj_clean.replace(',', '.'))
        return False
    except ValueError:
        pass
    
    # Разбиваем на слова
    words = obj_clean.split()
    word_count = len(words)
    
    # Если одно слово → мусор
    if word_count == 1:
        return False
    
    # Если < 3 слов, проверяем наличие ключевых слов
    if word_count < 3:
        key_words = ["мой", "моя", "я", "люблю", "хочу", "живу", "цель"]
        if not any(key_word in obj_clean for key_word in key_words):
            return False
    
    return True

# --- Session storage helpers (локальные, без импортов из routes_chat) ---
SESS_DIR = Path("data/sessions")
SESS_DIR.mkdir(parents=True, exist_ok=True)
INDEX_PATH = SESS_DIR / "index.json"


def _bump_session(session_id: str, title: str | None = None) -> None:
    try:
        idx = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
    except Exception:
        idx = {}
    now = int(time.time() * 1000)  # milliseconds
    
    # Если session_id нет в index -> создать запись
    if session_id not in idx:
        idx[session_id] = {
            "title": "",
            "created_at": now,
            "updated_at": now,
        }
    
    rec = idx[session_id]
    
    # Всегда обновлять updated_at
    rec["updated_at"] = now
    
    # Если title передан/вычислен -> писать title (только если title не пустой)
    if title:
        rec["title"] = title
        print(f"[SESSIONS] set title for session={session_id} title={title!r}")
    
    # Atomic write: записываем во временный файл, затем переименовываем
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=SESS_DIR, delete=False, suffix='.tmp') as tmp:
            tmp.write(json.dumps(idx, ensure_ascii=False))
            tmp_path = tmp.name
        # Atomic rename
        os.replace(tmp_path, INDEX_PATH)
        print(f"[SESSIONS] upsert index session={session_id}")
    except Exception as e:
        # Fallback to direct write if atomic write fails
        try:
            INDEX_PATH.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
            print(f"[SESSIONS] upsert index session={session_id}")
        except Exception as fallback_err:
            # Не падаем, если не удалось записать index.json - просто логируем
            print(f"[SESSIONS] WARNING: Failed to write index.json for session={session_id} (atomic and fallback both failed): {e}, {fallback_err}")
            return


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
            print(f"[SESSIONS] _append_msg user message, extracted title={title!r} for session={session_id}")
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


# --- Helper: отправка готового ответа через SSE ---
async def _send_reply_via_sse(reply: str, session_id: str) -> AsyncGenerator[str, None]:
    """Отправляет готовый текст как один токен или посимвольно через SSE."""
    if reply:
        # Отправляем весь текст одним токеном (быстрее для готовых ответов)
        event = json.dumps({"type": "token", "delta": reply}, ensure_ascii=False)
        yield f"data: {event}\n\n"
    yield f'data: {json.dumps({"type": "done"})}\n\n'
    _append_msg(str(session_id), "assistant", reply)


# Pydantic models for request validation
class ChatStreamSettings(BaseModel):
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
    model_mode: Optional[str] = None
    mode: Optional[str] = None


# Runtime guard limits (shared with routes_chat)
MAX_CHAT_INPUT_LENGTH = 10000  # Max characters for chat input text

class ChatStreamRequest(BaseModel):
    text: Optional[str] = Field(None, description="Query text", max_length=MAX_CHAT_INPUT_LENGTH)
    q: Optional[str] = Field(None, description="Query text (alias)", max_length=MAX_CHAT_INPUT_LENGTH)
    session_id: Optional[str] = Field(None, description="Session ID")
    session: Optional[str] = Field(None, description="Session ID (alias)")
    sid: Optional[str] = Field(None, description="Session ID (alias)")
    settings: Optional[ChatStreamSettings] = Field(None, description="Chat settings")
    thinking_mode: Optional[str] = Field(default=None, description="Thinking mode: analytical, structured, wide, hard, exploratory")

    def get_query_text(self) -> str:
        """Extract query text from various possible fields."""
        for field in [self.text, self.q]:
            if field and isinstance(field, str) and field.strip():
                if len(field) > MAX_CHAT_INPUT_LENGTH:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Input text exceeds maximum length of {MAX_CHAT_INPUT_LENGTH} characters"
                    )
                return field.strip()
        return ""

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


# --- Основной SSE-стрим ---
@router.post("/chat/stream")
async def chat_stream(body: ChatStreamRequest, request: Request = None):
    """
    SSE endpoint для стриминга чата.
    Использует тот же пайплайн, что и /chat (RAG/память/модель).
    Формат событий:
      data: {"type":"token","delta":"..."}\n\n
      data: {"type":"done"}\n\n
      data: {"type":"error","message":"..."}\n\n
    """
    # Extract and validate query text
    q = body.get_query_text()
    if not q:
        async def error_gen() -> AsyncGenerator[str, None]:
            error_event = json.dumps({"type": "error", "message": "Query text is required (provide 'text' or 'q')"}, ensure_ascii=False)
            yield f"data: {error_event}\n\n"
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
    session_id = body.get_session_id()
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)

    async def stream_gen() -> AsyncGenerator[str, None]:
        # G3 fix: Use local variable to avoid UnboundLocalError with += in nested scope
        from backend.app.chat import ARCH_CORE_PROMPT
        from backend.app.routes_chat import _build_thinking_mode_directives
        preamble = ARCH_CORE_PROMPT
        
        # --- PHASE J2: Thinking Mode directives ---
        # Extract thinking_mode: priority: body.thinking_mode, else query param, else default "structured"
        thinking_mode = body.thinking_mode
        if not thinking_mode and request:
            # Try to get from query params as fallback
            query_params = request.query_params
            thinking_mode = query_params.get("thinking_mode")
        if not thinking_mode:
            thinking_mode = "structured"  # Default
        
        # Add thinking mode directives AFTER ARCH_CORE_PROMPT
        thinking_directives = _build_thinking_mode_directives(thinking_mode)
        preamble += thinking_directives
        
        try:
            if not q:
                yield f'data: {json.dumps({"type": "error", "message": "empty query"})}\n\n'
                return

            sess_id = str(session_id)
            q_l = q.lower().strip()
            
            # Флаг для отслеживания memory_intent (используется ниже для follow-up question)
            is_memory_intent_processed = False

            # --- Auto-save profile facts (до обработки Memory Intent) ---
            # Автосохранение профильных фактов без слова "Запомни"
            try:
                auto_facts = extract_profile_facts_auto(
                    q,
                    subject="Arch",
                    source_session=sess_id,
                )
                if auto_facts:
                    logger.debug(f"[AUTO-FACTS] Extracted {len(auto_facts)} profile fact(s)")
                    for fact in auto_facts:
                        # Для single-value: add_fact() уже удаляет старые факты
                        # Логируем количество удаленных фактов перед сохранением
                        pred_key = fact.predicate.strip().lower()
                        is_single_value = pred_key in SINGLE_VALUE_PREDICATES
                        deleted_count = 0
                        
                        if is_single_value:
                            # Проверяем сколько будет удалено
                            existing = get_facts_for_subject("Arch", limit=1000)
                            deleted_count = len([
                                f for f in existing
                                if f.subject.strip().lower() == "arch"
                                and f.predicate.strip().lower() == pred_key
                            ])
                        
                        add_fact(fact)
                        
                        # Логируем INFO уровень
                        logger.info(
                            f"[AUTO-FACTS] Saved fact: predicate={fact.predicate!r}, "
                            f"object={fact.object!r}, category={fact.category!r}, "
                            f"deleted_old={deleted_count}"
                        )
            except Exception as e:
                logger.warning(f"[AUTO-FACTS] Error extracting/saving profile facts: {e}")

            # --- Memory Intent: обработка "Запомни:" / "Remember:" (обычный и silent) ---
            # Перехватываем сообщения вида "Запомни: ..." / "Remember: ..." / "Запомни тихо: ..." / "Remember silently: ..."
            # Сначала проверяем silent intent
            silent_memory_pattern = re.compile(r'^\s*(запомни\s+тихо[:,]?|remember\s+silently[:,]?)\s*(.+)', re.IGNORECASE)
            silent_match = silent_memory_pattern.match(q)
            is_silent = False
            fact_text = None
            
            if silent_match:
                is_silent = True
                fact_text = silent_match.group(2).strip()
            else:
                # Проверяем обычный memory intent
                memory_intent_pattern = re.compile(r'^\s*(запомни[:,]?|remember[:,]?)\s*(.+)', re.IGNORECASE)
                memory_match = memory_intent_pattern.match(q)
                if memory_match:
                    fact_text = memory_match.group(2).strip()
            
            if fact_text is not None:
                is_memory_intent_processed = True  # Отмечаем что это memory_intent
                if not fact_text:
                    # Пустой текст после "Запомни:" - возвращаем ошибку (только если не silent)
                    if not is_silent:
                        reply = "Что именно нужно запомнить?"
                        async for event in _send_reply_via_sse(reply, sess_id):
                            yield event
                    return
                
                # Извлекаем факты из текста
                # Memory intent = ИМПЕРАТИВ. Модель не имеет права решать, сохранять или нет.
                extracted_facts = extract_facts_from_text_v3(
                    fact_text,
                    subject="Arch",
                    source_session=sess_id,
                )
                
                if extracted_facts:
                    # Если extractor вернул факты - сохраняем их БЕЗ проверок полезности
                    # Проверяем существующие факты для определения дубликатов (только для multi-value)
                    existing_facts = get_facts_for_subject("Arch", limit=1000)
                    existing_triplets = {
                        (f.subject.strip().lower(), f.predicate.strip().lower(), f.object.strip().lower())
                        for f in existing_facts
                    }
                    
                    new_facts = []
                    for fact in extracted_facts:
                        pred_key = fact.predicate.strip().lower()
                        is_single_value = pred_key in SINGLE_VALUE_PREDICATES
                        
                        if is_single_value:
                            # Для single-value: УДАЛЯЕМ все старые факты с тем же (subject, predicate)
                            deleted_count = delete_facts(
                                subject=fact.subject,
                                predicate=fact.predicate,
                                object_value=None  # Удаляем все, независимо от object
                            )
                            if deleted_count > 0:
                                logger.debug(f"[MEMORY INTENT] Deleted {deleted_count} old single-value fact(s) for predicate={fact.predicate}")
                            # Затем добавляем новый факт (дубликатов больше нет)
                            new_facts.append(fact)
                            add_fact(fact)
                        else:
                            # Для multi-value: проверяем полный триплет на дубликаты
                            triplet_key = (
                                fact.subject.strip().lower(),
                                pred_key,
                                fact.object.strip().lower()
                            )
                            is_duplicate = triplet_key in existing_triplets
                            
                            # Сохраняем и добавляем в список только НЕ дубликаты
                            if not is_duplicate:
                                new_facts.append(fact)
                                add_fact(fact)
                    
                    # Формируем ответ (только если не silent)
                    reply = None
                    if not is_silent:
                        if new_facts:
                            # Есть новые факты
                            fact_descriptions = []
                            for fact in new_facts:
                                pred_clean = fact.predicate.replace('_', ' ').strip()
                                # Для single-value предикатов используем формат "predicate — object"
                                if fact.predicate.strip().lower() in SINGLE_VALUE_PREDICATES:
                                    desc = f"{pred_clean} — {fact.object}"
                                else:
                                    desc = f"{fact.subject} {pred_clean} {fact.object}"
                                fact_descriptions.append(desc)
                            reply = f"Запомнил: {', '.join(fact_descriptions)}."
                        else:
                            # Все факты уже были сохранены (дубликаты)
                            reply = "Уже сохранено."
                else:
                    # Extractor не вернул факты
                    if not is_silent:
                        reply = "Не понял, что именно запомнить."
                        async for event in _send_reply_via_sse(reply, sess_id):
                            yield event
                    return
                
                # Отправляем ответ через SSE и завершаем (НЕ вызываем LLM)
                # Сообщение пользователя НЕ записывается в диалог (return до _append_msg)
                # В silent режиме ответ не отправляется
                if not is_silent and reply:
                    async for event in _send_reply_via_sse(reply, sess_id):
                        yield event
                return

            # Гарантируем, что сессия есть в index.json (перед записью сообщения)
            try:
                _bump_session(sess_id, None)
            except Exception as e:
                print(f"[SESSIONS] Failed to upsert index for {sess_id}: {e}")
                # Не прерываем выполнение - продолжаем даже если index.json не обновился

            # Логируем запрос пользователя
            try:
                _append_msg(sess_id, "user", q)
            except Exception:
                pass

            # --- Подготовка system_preamble (Core Dialog) ---
            # Core Dialog: используем фиксированный ARCH_CORE_PROMPT
            # UI не может перезаписать system prompt через settings или systemPrompt
            # system_preamble уже инициализирован в начале stream_gen()

            # Настройки из validated body
            settings = body.get_settings_dict()

            logger.info("[STREAM REQ] model=%r active_model=%r", settings.get("model"), settings.get("active_model"))

            tone = str(settings.get("response_tone", "") or "").lower()
            density = str(settings.get("output_density", "") or "").lower()
            temp = settings.get("temperature", None)
            ui_lang = str(settings.get("interface_language", "") or "").lower()

            # Выбор модели через Model Mode Router
            # Проверяем явно указанную модель (override)
            raw_model = str(
                settings.get("model")
                or settings.get("active_model")
                or settings.get("activeModel")
                or settings.get("active_model_weight")
                or settings.get("model_name")
                or settings.get("llm_model")
                or ""
            ).strip().lower()
            
            # Если модель указана явно - используем её (override router)
            if raw_model:
                normalized = raw_model.replace("-local", "").replace("_local", "")
                if normalized in ("mistral-7b", "mistral", "mistral_7b"):
                    model_name = "mistral"
                    logger.info(f"[ROUTER] mode=manual chosen={model_name} reason=override")
                elif normalized in ("hermes-7b", "hermes", "hermes:7b", "nous-hermes2:7b", "nous-hermes2-mistral-7b"):
                    model_name = "nous-hermes2:7b"
                    logger.info(f"[ROUTER] mode=manual chosen={model_name} reason=override")
                elif normalized in ("llama-3.1-8b", "llama3.1-8b", "llama3.1", "llama3", "llama3.1:8b"):
                    model_name = "llama3.1:8b"
                    logger.info(f"[ROUTER] mode=manual chosen={model_name} reason=override")
                elif normalized in ("qwen-2.5-14b", "qwen25-14b", "qwen2.5-14b"):
                    model_name = "qwen2.5:14b"
                    logger.info(f"[ROUTER] mode=manual chosen={model_name} reason=override")
                elif normalized in ("mixtral-8x7b", "mixtral", "mixtral-8x7b-instruct"):
                    model_name = "mixtral:8x7b"
                    logger.info(f"[ROUTER] mode=manual chosen={model_name} reason=override")
                elif normalized in ("deepseek-32b", "deepseek32b", "deepseek-v2:32b", "deepseek-v2.5:32b"):
                    model_name = "deepseek-v2:32b"
                    logger.info(f"[ROUTER] mode=manual chosen={model_name} reason=override")
                elif normalized in ("deepseek-14b", "deepseek", "deepseek-r1", "deepseek-r1:8b"):
                    model_name = "deepseek-r1:8b"
                    logger.info(f"[ROUTER] mode=manual chosen={model_name} reason=override")
                else:
                    # Неизвестная модель - используем router
                    explicit_mode = settings.get("model_mode") or settings.get("mode")
                    router_mode, model_name, router_reason = route_model_mode(q, explicit_mode)
                    logger.info(f"[ROUTER] mode={router_mode} chosen={model_name} reason=unknown_model_fallback_to_{router_reason}")
            else:
                # Используем Model Mode Router
                explicit_mode = settings.get("model_mode") or settings.get("mode")
                router_mode, model_name, router_reason = route_model_mode(q, explicit_mode)
                logger.info(f"[ROUTER] mode={router_mode} chosen={model_name} reason={router_reason}")

            # Core Dialog: system_preamble фиксирован (ARCH_CORE_PROMPT)
            # UI не может модифицировать system prompt через settings
            # extra_parts игнорируются для system prompt

            # --- Специальные случаи (как в /chat) ---
            
            # Дата рождения -> знак зодиака
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
                    async for event in _send_reply_via_sse(reply, sess_id):
                        yield event
                    return
                except Exception:
                    reply = "Принял дату рождения, но не смог корректно определить знак зодиака."
                    async for event in _send_reply_via_sse(reply, sess_id):
                        yield event
                    return

            # Профиль факты
            prof_reply = extract_profile_facts(q, sess_id)
            if prof_reply is not None:
                async for event in _send_reply_via_sse(prof_reply, sess_id):
                    yield event
                return

            # Знак зодиака
            if "знак зодиака" in q_l:
                zodiac = FACTS_PROFILE.get("zodiac")
                if zodiac:
                    reply = f"Твой знак зодиака — {zodiac}."
                else:
                    reply = "У меня нет в профиле данных о твоём знаке зодиака. Могу запомнить, если скажешь."
                async for event in _send_reply_via_sse(reply, sess_id):
                    yield event
                return

            # Активная модель
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
                async for event in _send_reply_via_sse(reply, sess_id):
                    yield event
                return

            # Что помнишь обо мне
            if any(tok in q_l for tok in ["что ты помнишь обо мне", "что помнишь обо мне", "что ты обо мне помнишь", "что знаешь обо мне", "что ты обо мне знаешь", "что помнишь про меня"]):
                parts: list[str] = []
                if FACTS_PROFILE.get("location"):
                    parts.append(f"ты живёшь в {FACTS_PROFILE['location']}")
                if FACTS_PROFILE.get("zodiac"):
                    parts.append(f"твой знак зодиака — {FACTS_PROFILE['zodiac']}")
                goals = FACTS_PROFILE.get("goals") or []
                if isinstance(goals, list) and goals:
                    goals_str = "; ".join(str(g) for g in goals[:3])
                    if len(goals) > 3:
                        goals_str += " и ещё несколько целей"
                    parts.append(f"твои цели: {goals_str}")
                if FACTS_PROFILE.get("training_freq"):
                    parts.append(f"ты тренируешься {FACTS_PROFILE['training_freq']} раза в неделю")
                if parts:
                    reply = "Вот что я о тебе помню: " + "; ".join(parts) + "."
                else:
                    reply = "Честно — в профиле почти нет данных именно о тебе. Расскажи мне о себе: где живёшь, какие цели и режим — я запомню."
                async for event in _send_reply_via_sse(reply, sess_id):
                    yield event
                return

            # Быстрые режимы
            if any(tok in q_l for tok in ["#morning_check", "план на день", "план на сегодня", "что у нас по плану", "что по плану", "утро", "morning"]):
                work = FACTS_PROFILE.get("work_time", "10:00–19:00")
                gym = FACTS_PROFILE.get("gym_time", "19:30")
                reply = f"План:\n— Работа {work}.\n— Зал {gym} (45–60 мин): базовые упражнения.\n— Вечер 20 мин: AIR4 — один микрошаг (экран/фикс), без перфекционизма.\nФинансы: резерва +600€ на неделе."
                async for event in _send_reply_via_sse(reply, sess_id):
                    yield event
                return

            if any(tok in q_l for tok in ["#evening_check", "итог дня", "вечер", "вечером", "закрыть день"]):
                reply = "Итог дня:\n— Работа — закрыто, движ есть.\n— Тренировка — ✅ если был в зале.\n— AIR4 — +1 шаг, фиксанул без перфекционизма.\n— В целом — не идеально, но стабильно. Завтра дожмём."
                async for event in _send_reply_via_sse(reply, sess_id):
                    yield event
                return

            if any(tok in q_l for tok in ["#week_check", "итоги недели", "неделя", "неделю закрыть"]):
                reply = "Неделя:\n— Финансы: +620€ (по плану).\n— Тренировки: 3 / 3 — стабильно.\n— AIR4: несколько шагов — идёт прогресс.\n— Общий вывод: ровно, без спешки, но в росте.\n— Следующая неделя — добавить 1 новый шаг или идею."
                async for event in _send_reply_via_sse(reply, sess_id):
                    yield event
                return

            # Small talk
            if any(tok in q_l for tok in ["привет", "здравствуй", "здравствуйте", "hi", "hello", "hey"]) and len(q_l) <= 40:
                reply = "Привет. Я на связи, давай разбираться, что нужно сделать."
                async for event in _send_reply_via_sse(reply, sess_id):
                    yield event
                return

            if any(phrase in q_l for phrase in ["как дела", "как у тебя дела", "как твои дела", "как поживаешь", "как настроение"]) and len(q_l) <= 60:
                reply = "Нормально, работаю над твоими задачами. Главное — твои дела, давай говорить про них."
                async for event in _send_reply_via_sse(reply, sess_id):
                    yield event
                return

            if any(phrase in q_l for phrase in ["ок", "окей", "okay", "ладно", "норм", "супер", "круто", "огонь", "топ", "класс", "спасибо"]) and len(q_l) <= 40:
                reply = "Принял. Двигаемся дальше."
                async for event in _send_reply_via_sse(reply, sess_id):
                    yield event
                return

            # --- Recall: загрузка фактов о пользователе для вопросов про него ---
            memory_context = ""
            
            # Проверяем, является ли это follow-up вопросом
            is_followup = is_followup_question(q)
            last_recall = session_state.get(sess_id, {})
            last_recall_predicate = last_recall.get("last_recall_predicate")
            last_recall_subject = last_recall.get("last_recall_subject", "Arch")
            
            # Если это follow-up и есть сохранённый predicate, принудительно запускаем recall
            force_recall = is_followup and last_recall_predicate is not None
            
            # Определяем, является ли запрос вопросом о пользователе
            # Паттерны для русских вопросов
            ru_patterns = [
                r'\b(мой|мне|я|у меня|моя|мое|мои)\b',
                r'\b(какой мой|где я|что я|мой любимый|моя любимая|мое любимое|что я люблю|что мне нравится)\b',
                r'\b(как я|когда я|почему я|зачем я)\b',
            ]
            # Паттерны для английских вопросов
            en_patterns = [
                r'\b(my|me|do I|what is my|where do I|what do I|what I like|what I love)\b',
                r'\b(how do I|when do I|why do I)\b',
            ]
            is_user_question = (
                any(re.search(pattern, q_l, re.IGNORECASE) for pattern in ru_patterns) or
                any(re.search(pattern, q_l, re.IGNORECASE) for pattern in en_patterns)
            )
            
            # Запускаем recall если это явный вопрос о пользователе ИЛИ follow-up с сохранённым predicate
            if is_user_question or force_recall:
                try:
                    # Для follow-up используем сохранённый subject, иначе "Arch"
                    recall_subject = last_recall_subject if force_recall else "Arch"
                    facts = get_facts_for_subject(recall_subject, limit=20)
                    
                    if facts:
                        # Для single-value предикатов в storage всегда только 1 факт (старые удаляются при записи)
                        # Фильтруем факты по predicate для follow-up вопросов
                        filtered_facts = facts
                        if force_recall:
                            target_pred_key = last_recall_predicate.strip().lower()
                            filtered_facts = [
                                f for f in facts
                                if f.predicate.strip().lower() == target_pred_key
                            ]
                        
                        resolved_facts = filtered_facts
                        resolved_facts.sort(key=lambda f: f.timestamp, reverse=True)
                        
                        if resolved_facts:
                            fact_lines = []
                            for fact in resolved_facts:
                                # Форматируем факт в читаемый вид
                                predicate_clean = fact.predicate.replace('_', ' ').strip()
                                fact_text = f"{predicate_clean} — {fact.object}"
                                fact_lines.append(f"  - {fact_text}")
                            
                            if fact_lines:
                                # Сохраняем контекст последнего успешного recall (ТОЛЬКО после успешного recall)
                                # Для follow-up используем сохранённый predicate, иначе берём из самого нового факта
                                if force_recall:
                                    predicate_to_save = last_recall_predicate
                                else:
                                    # Для обычных вопросов сохраняем predicate из самого нового факта (первого в отсортированном списке)
                                    predicate_to_save = resolved_facts[0].predicate if resolved_facts else None
                                
                                if predicate_to_save:
                                    if sess_id not in session_state:
                                        session_state[sess_id] = {}
                                    session_state[sess_id]["last_recall_predicate"] = predicate_to_save
                                    session_state[sess_id]["last_recall_subject"] = recall_subject
                                    logger.debug("[RECALL] Saved recall context: predicate=%r subject=%r", predicate_to_save, recall_subject)
                                
                                # Строгие инструкции для LLM: запрет на неопределённость
                                memory_context = (
                                    "Известные факты о пользователе:\n" + "\n".join(fact_lines) +
                                    "\n\nКРИТИЧЕСКИ ВАЖНО:\n"
                                    "- Отвечай СТРОГО на основе этих фактов.\n"
                                    "- ЗАПРЕЩЕНО использовать слова: 'возможно', 'кажется', 'вероятно', 'не уверен', 'не знаю', 'может быть'.\n"
                                    "- Если факт есть в списке — отвечай УТВЕРДИТЕЛЬНО и ТОЧНО.\n"
                                    "- Не добавляй свои предположения или домыслы."
                                )
                                logger.debug("[RECALL] Loaded %d facts for %s question", len(resolved_facts), "follow-up" if force_recall else "user")
                        else:
                            # Для follow-up: если фактов с нужным predicate нет, строго запрещаем фантазировать
                            if force_recall:
                                memory_context = (
                                    f"КРИТИЧЕСКИ ВАЖНО: Пользователь задаёт уточняющий вопрос про '{last_recall_predicate}', "
                                    f"но в сохранённых фактах НЕТ информации об этом.\n"
                                    f"Ответь СТРОГО: 'Я не находил сохранённой информации об этом.'\n"
                                    f"ЗАПРЕЩЕНО фантазировать, предполагать или использовать слова 'возможно', 'кажется'."
                                )
                                logger.debug("[RECALL] No facts found for follow-up question with predicate=%r", last_recall_predicate)
                            else:
                                # Fallback для обычных вопросов
                                memory_context = (
                                    "КРИТИЧЕСКИ ВАЖНО: Пользователь спрашивает о себе, но в сохранённых фактах нет информации об этом.\n"
                                    "Ответь СТРОГО: 'Я не находил сохранённой информации об этом.'\n"
                                    "ЗАПРЕЩЕНО фантазировать или использовать слова 'возможно', 'кажется'."
                                )
                                logger.debug("[RECALL] No facts found for user question")
                    else:
                        # Fallback: если фактов нет с самого начала
                        memory_context = (
                            "КРИТИЧЕСКИ ВАЖНО: Пользователь спрашивает о себе, но в сохранённых фактах нет информации об этом.\n"
                            "Ответь СТРОГО: 'Я не находил сохранённой информации об этом.'\n"
                            "ЗАПРЕЩЕНО фантазировать или использовать слова 'возможно', 'кажется'."
                        )
                        logger.debug("[RECALL] No facts found for user question")
                except Exception as e:
                    logger.error("[RECALL] Failed to load facts: %s", e)
            
            # --- Основной LLM вызов (RAG + Ollama streaming) ---
            
            # RAG контекст
            rag_ctx = ""
            use_rag = len(q_l) > 40
            if use_rag:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as c:
                        r = await c.get("http://127.0.0.1:8000/memory/search", params={"q": q, "session_id": sess_id, "k": 3})
                        js = r.json()
                        hits = js.get("results", [])
                        if hits and isinstance(hits[0], dict) and hits[0].get("text") and hits[0].get("score") is not None and hits[0]["score"] >= RAG_SCORE_THRESHOLD:
                            rag_ctx = hits[0]["text"][:1200]
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

            user_payload = f"{q}\n\n[MEMORY]\n{rag_ctx}" if rag_ctx else q

            # Build preamble for LLM call (preamble already initialized at start of stream_gen())
            if rag_ctx:
                preamble += " ВНИМАНИЕ: отвечай ТОЛЬКО на основе блока [MEMORY] ниже. Ничего не придумывай. Если пользователь просит точную фразу, верни её дословно из [MEMORY] без изменений."
            
            # Добавляем memory_context (факты о пользователе) в preamble
            if memory_context:
                preamble += "\n\n" + memory_context

            # Отправляем meta событие с resolved_model ДО начала стриминга
            meta_event = json.dumps({"type": "meta", "resolved_model": model_name}, ensure_ascii=False)
            yield f"data: {meta_event}\n\n"

            # Вызов Ollama с streaming
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
                        },
                    ) as res:
                        full_answer = ""
                        first_chunk_logged = False
                        first_parsed_logged = False
                        async for line in res.aiter_lines():
                            line = line.strip()
                            if not line:
                                continue
                            
                            # Диагностика: логируем первый chunk
                            if not first_chunk_logged:
                                logger.debug("[STREAM DBG] first_chunk raw=%r", line[:200])
                                first_chunk_logged = True
                            
                            # JSON case
                            if line.startswith("{"):
                                try:
                                    obj = json.loads(line)
                                except json.JSONDecodeError:
                                    obj = None
                                
                                if obj is not None:
                                    # Проверяем ошибку от Ollama
                                    if isinstance(obj, dict) and "error" in obj:
                                        error_str = str(obj["error"])
                                        logger.error("[OLLAMA ERROR] %s", error_str)
                                        error_data = json.dumps({"message": "ollama_error", "detail": error_str}, ensure_ascii=False)
                                        yield f'event: error\ndata: {error_data}\n\n'
                                        return
                                    
                                    # Проверяем done=true — завершаем стрим
                                    if obj.get("done") is True:
                                        break
                                    
                                    # Извлекаем delta из разных возможных форматов
                                    delta = None
                                    if isinstance(obj.get("response"), str) and obj.get("response"):
                                        delta = obj["response"]
                                    else:
                                        msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
                                        content = msg.get("content") if msg else None
                                        if isinstance(content, str) and content:
                                            delta = content
                                    
                                    # Диагностика: логируем первый распарсенный token
                                    if not first_parsed_logged:
                                        logger.debug("[STREAM DBG] parsed_token=%r keys=%s", delta, list(obj.keys()) if isinstance(obj, dict) else None)
                                        first_parsed_logged = True
                                    
                                    # Если нашли delta — аккумулируем и стримим его
                                    if delta is not None:
                                        full_answer += delta
                                        event = json.dumps({"type": "token", "delta": delta}, ensure_ascii=False)
                                        yield f"data: {event}\n\n"
                                    continue
                            
                            # Non-JSON case (plain text)
                            full_answer += line
                            event = json.dumps({"type": "token", "delta": line}, ensure_ascii=False)
                            yield f"data: {event}\n\n"

                        if not full_answer.strip():
                            # Если streaming не вернул ответ, отправляем error через SSE и завершаем
                            logger.error(f"[STREAM ERROR] Empty model response for session={sess_id}, query_len={len(q)}")
                            error_data = json.dumps({"message": "empty_model_response"}, ensure_ascii=False)
                            yield f"event: error\ndata: {error_data}\n\n"
                            return  # Прерываем выполнение, не сохраняем пустой ответ

                        # --- Profile Completeness + Follow-up Question (после ответа LLM) ---
                        # Проверяем полноту профиля и добавляем 1 вопрос если нужно
                        # НЕ добавляем вопрос если:
                        # - это был memory_intent (is_memory_intent_processed = True)
                        # - ответ короткий сервисный (уже проверено выше)
                        # - пользователь спросил системный вопрос ("кто ты", "что ты умеешь")
                        
                        # Проверяем системные вопросы пользователя
                        system_question_patterns = [
                            r'\b(кто ты|что ты умеешь|что ты|кто такая|что такое)\b',
                            r'\b(who are you|what are you|what can you)\b',
                        ]
                        is_system_question = any(re.search(pattern, q_l, re.IGNORECASE) for pattern in system_question_patterns)
                        
                        # Добавляем follow-up вопрос только если это НЕ memory_intent и НЕ системный вопрос
                        # is_memory_intent_processed доступен через замыкание из внешней области видимости
                        if not is_memory_intent_processed and not is_system_question:
                            try:
                                completeness = get_profile_completeness("Arch")
                                question_info = choose_next_profile_question(completeness)
                                
                                if question_info:
                                    question_key, question_text = question_info
                                    
                                    # Получаем или инициализируем состояние для сессии
                                    if sess_id not in session_policy_state:
                                        session_policy_state[sess_id] = {"last_profile_q_ts": 0.0, "last_profile_q_key": ""}
                                    
                                    policy_state = session_policy_state[sess_id]
                                    now_ts = time.time()
                                    last_q_ts = policy_state.get("last_profile_q_ts", 0.0)
                                    last_q_key = policy_state.get("last_profile_q_key", "")
                                    
                                    # Проверяем cooldown (600 секунд = 10 минут)
                                    cooldown_passed = (now_ts - last_q_ts) >= 600
                                    # Если задавали тот же вопрос недавно, не повторяем
                                    different_key = question_key != last_q_key
                                    
                                    if cooldown_passed or different_key:
                                        # Добавляем вопрос в конец ответа
                                        full_answer += f"\n\nВопрос: {question_text}"
                                        
                                        # Обновляем состояние
                                        session_policy_state[sess_id] = {
                                            "last_profile_q_ts": now_ts,
                                            "last_profile_q_key": question_key,
                                        }
                                        
                                        logger.debug(
                                            f"[PROFILE-Q] Added question: key={question_key!r}, "
                                            f"cooldown_passed={cooldown_passed}, different_key={different_key}"
                                        )
                                    else:
                                        logger.debug(
                                            f"[PROFILE-Q] Skipped (cooldown): key={question_key!r}, "
                                            f"last_ts={last_q_ts}, elapsed={now_ts - last_q_ts:.1f}s"
                                        )
                            except Exception as e:
                                logger.warning(f"[PROFILE-Q] Error checking completeness/adding question: {e}")

                        # Завершаем стрим
                        yield f'data: {json.dumps({"type": "done"})}\n\n'
                        
                        # Логируем полный ответ (только если он не пустой)
                        try:
                            _append_msg(sess_id, "assistant", full_answer.strip())
                            # Убеждаемся, что JSONL файл реально создался
                            jsonl_file = SESS_DIR / f"{sess_id}.jsonl"
                            if jsonl_file.exists():
                                print(f"[SESSIONS] JSONL file exists: {jsonl_file}")
                            else:
                                print(f"[SESSIONS] WARNING: JSONL file missing: {jsonl_file}")
                        except Exception as e:
                            print(f"[SESSIONS] Failed to append assistant message: {e}")
                            pass
                        
                        # MEMORY: сохраняем user message и assistant reply в память
                        try:
                            safe_memory_add(q, sess_id, "user")
                            safe_memory_add(full_answer.strip(), sess_id, "assistant")
                        except Exception as e:
                            logger.debug(f"[memory] skipped: {e}")

            except httpx.TimeoutException:
                logger.error(f"[LLM TIMEOUT] LLM streaming timed out after 60s (session_id={sess_id})")
                # G3: Log error
                logger.error(
                    "[ERROR] chat/stream LLM_timeout",
                    extra={
                        "session_id": sess_id,
                        "user": "dev",
                        "exception": "LLM request timed out"
                    }
                )
                error_event = json.dumps({"type": "error", "message": "LLM request timed out"}, ensure_ascii=False)
                yield f"data: {error_event}\n\n"
            except Exception as e:
                # G3: Log error
                logger.error(
                    "[ERROR] chat/stream LLM_call_failed",
                    extra={
                        "session_id": sess_id,
                        "user": "dev",
                        "exception": str(e)
                    }
                )
                error_event = json.dumps({"type": "error", "message": f"LLM call failed: {str(e)}"}, ensure_ascii=False)
                yield f"data: {error_event}\n\n"

        except Exception as e:
            logger.error(f"[STREAM ERROR] Stream handler failed: {e}")
            # G3: Log error
            logger.error(
                "[ERROR] chat/stream handler_failed",
                extra={
                    "session_id": sess_id if 'sess_id' in locals() else None,
                    "user": "dev",
                    "exception": str(e)
                }
            )
            error_event = json.dumps({"type": "error", "message": f"LLM call failed: {str(e)}"}, ensure_ascii=False)
            yield f"data: {error_event}\n\n"

    return StreamingResponse(
        stream_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# --- Тестовый эндпоинт для scripts/smoke_stream.sh ---
@router.post("/chat/stream-test")
async def chat_stream_test():
    """
    @deprecated Not used by GoogleUI. Test endpoint.
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

    return StreamingResponse(gen(), media_type="text/event-stream")
