from typing import List, Optional
import logging

from fastapi import APIRouter, HTTPException, Query

try:
    # запуск как пакет
    from backend.app.memory.facts import (
        Fact,
        get_facts_for_subject,
        add_fact,
        _load_facts,
        _save_facts,
        SINGLE_VALUE_PREDICATES,
        delete_all_facts_for_subject,
    )
except Exception:  # запуск из корня
    from .memory.facts import (  # type: ignore
        Fact,
        get_facts_for_subject,
        add_fact,
        _load_facts,
        _save_facts,
        SINGLE_VALUE_PREDICATES,
        delete_all_facts_for_subject,
    )

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/facts", tags=["facts"])


@router.get("/", response_model=List[Fact])
def list_facts(
    subject: Optional[str] = Query("Arch", description="Subject id (user)"),
    limit: int = Query(64, ge=1, le=256),
):
    """
    Возвращает список фактов из facts.json для указанного subject.
    По умолчанию — Arch.
    """
    try:
        subj = subject or "Arch"
        return get_facts_for_subject(subj, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"facts error: {e}")

@router.get("/profile")
def facts_profile(subject: str = "Arch"):
    """
    Собирает профиль пользователя СТРОГО из Facts с category="profile".
    
    ЕДИНСТВЕННЫЙ источник данных: get_facts_for_subject().
    Показывает ТОЛЬКО факты с category="profile".
    Полностью игнорирует факты с category="other" и другими категориями.
    
    Для single-value предикатов в storage всегда только 1 факт (старые удаляются при записи).
    Если Facts пусты → profile полностью пустой (все массивы = []).
    """
    # Инициализируем пустой profile (только profile поле)
    profile = {
        "subject": subject,
        "profile": [],
    }
    
    try:
        # ЕДИНСТВЕННЫЙ источник данных - Facts
        # НЕТ других источников, НЕТ fallback значений
        facts = get_facts_for_subject(subject, limit=200)
    except Exception as e:
        # При ошибке возвращаем пустой profile
        raise HTTPException(status_code=500, detail=f"facts profile error: {e}")

    # Если Facts пусты - возвращаем пустой profile
    if not facts:
        logger.info(f"[FACTS PROFILE] No facts found for subject={subject}")
        return profile

    # Валидация: принимаем и Fact объекты, и dict'ы
    # Фильтруем ТОЛЬКО факты с category="profile"
    valid_facts: list[Fact] = []
    total_loaded = len(facts)
    
    for item in facts:
        # Нормализуем: если dict - конвертируем в Fact, если Fact - используем как есть
        if isinstance(item, dict):
            # Извлекаем поля из dict
            subject_val = (item.get("subject") or "").strip()
            predicate_val = (item.get("predicate") or "").strip()
            object_val = (item.get("object") or "").strip()
            timestamp_val = float(item.get("timestamp") or 0)
            category_val = (item.get("category") or "").strip()
            
            # Пропускаем неполные факты
            if not subject_val or not predicate_val or not object_val:
                continue
            
            # Фильтруем: показываем ТОЛЬКО category="profile"
            if category_val.lower() != "profile":
                continue
            
            # Создаём Fact объект
            try:
                fact = Fact(
                    subject=subject_val,
                    predicate=predicate_val,
                    object=object_val,
                    timestamp=timestamp_val,
                    category=category_val if category_val else None,
                    source_session=item.get("source_session"),
                    source_message_id=item.get("source_message_id"),
                )
                valid_facts.append(fact)
            except Exception as e:
                logger.warning(f"[FACTS PROFILE] Failed to create Fact from dict: {e}")
                continue
        elif isinstance(item, Fact):
            # Уже Fact объект - проверяем полноту и category
            if not item.subject or not item.predicate or not item.object:
                continue
            # Фильтруем: показываем ТОЛЬКО category="profile"
            if not item.category or item.category.lower() != "profile":
                continue
            valid_facts.append(item)
        else:
            # Неизвестный тип - пропускаем
            logger.warning(f"[FACTS PROFILE] Unknown fact type: {type(item)}")
            continue
    
    facts_kept = len(valid_facts)
    logger.info(f"[FACTS PROFILE] Loaded {total_loaded} facts, kept {facts_kept} profile facts for subject={subject}")
    
    # Если после валидации нет фактов - возвращаем пустой profile
    if not valid_facts:
        return profile

    # Форматируем факты как "predicate — object" для отображения
    profile_items = []
    for fact in valid_facts:
        obj = fact.object.strip()
        if not obj:  # Пропускаем пустые объекты
            continue
        # Форматируем как "predicate — object"
        formatted = f"{fact.predicate.replace('_', ' ')} — {obj}"
        profile_items.append(formatted)

    # Сортируем и сохраняем
    profile["profile"] = sorted(profile_items)

    logger.info(f"[FACTS PROFILE] Profile items for subject={subject}: {len(profile['profile'])} items")

    return profile


# Reindex endpoint
@router.post("/reindex")
def reindex_facts(
    session_id: str = Query(..., description="Session ID (required)"),
    subject: str = "Arch"
) -> dict:
    """
    @deprecated Not used by GoogleUI. Internal endpoint.
    Переиндексирует все факты из локального хранилища в векторную память (MEMORY).
    По сути повторно прогоняет их через add_fact, который сам вызывает MEMORY.add_text().
    """
    # Validate session_id
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    try:
        facts = _load_facts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"facts load error: {e}")

    if not facts:
        raise HTTPException(status_code=404, detail="no facts to reindex")

    count = 0
    for f in facts:
        # если задан subject — можем переопределить его на лету
        if subject:
            f.subject = subject
        try:
            add_fact(f)
            count += 1
        except Exception as e:
            # не валим весь процесс из-за одного факта
            print(
                "[FACTS REINDEX] error:",
                f.subject,
                f.predicate,
                f.object,
                "->",
                e,
            )

    return {"status": "ok", "count": count}


@router.delete("/wipe")
def wipe_facts(
    session_id: str = Query(..., description="Session ID (required)"),
    subject: str = Query("Arch", description="Subject to wipe all facts for (case-insensitive)")
) -> dict:
    """
    @deprecated Not used by GoogleUI. Dev-only endpoint.
    Удаляет ВСЕ факты для указанного subject (case-insensitive).
    
    Использует delete_all_facts_for_subject() для удаления всех фактов, где subject совпадает.
    Сохраняет изменения в persisted store (facts_store.json) немедленно.
    
    Returns:
        JSON с количеством удалённых фактов и subject:
        {"deleted": <count>, "subject": "<subject>"}
    
    Example:
        DELETE /facts/wipe?subject=Arch
        → {"deleted": 42, "subject": "Arch"}
    """
    # Validate session_id
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    try:
        deleted_count = delete_all_facts_for_subject(subject)
        logger.info(f"[FACTS WIPE] Deleted {deleted_count} fact(s) for subject={subject}")
        return {"deleted": deleted_count, "subject": subject}
    except Exception as e:
        logger.error(f"[FACTS WIPE] Error: {e}")
        raise HTTPException(status_code=500, detail=f"facts wipe error: {e}")


@router.delete("/purge")
def purge_facts(
    session_id: str = Query(..., description="Session ID (required)"),
    subject: str = Query("Arch", description="Subject to filter (required)"),
    predicate: Optional[str] = Query(None, description="Optional predicate to filter (case-insensitive)"),
    object_contains: Optional[str] = Query(None, description="Optional substring to search in object (case-insensitive)"),
) -> dict:
    """
    @deprecated Not used by GoogleUI. Internal endpoint.
    Удаляет legacy-факты по критериям фильтрации.
    
    Загружает все факты, фильтрует по:
    - subject (обязательно, case-insensitive)
    - predicate (опционально, case-insensitive)
    - object_contains (опционально, case-insensitive substring search)
    
    Удаляет отфильтрованные факты из хранилища.
    
    Примеры:
    - DELETE /facts/purge?subject=Arch&predicate=запомнил&object_contains=мой любимый цвет
      → удалит все legacy записи про цвет
    - DELETE /facts/purge?subject=Arch&predicate=запомнил
      → удалит все факты с predicate="запомнил" для Arch
    """
    # Validate session_id
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    try:
        # Загружаем все факты
        all_facts = _load_facts()
        
        if not all_facts:
            return {"deleted": 0}
        
        # Фильтруем факты по критериям
        subject_lower = subject.strip().lower()
        predicate_lower = predicate.strip().lower() if predicate else None
        object_contains_lower = object_contains.strip().lower() if object_contains else None
        
        original_count = len(all_facts)
        filtered_facts = []
        
        for fact in all_facts:
            # Проверяем subject (обязательно)
            if fact.subject.strip().lower() != subject_lower:
                filtered_facts.append(fact)  # Оставляем факт
                continue
            
            # Проверяем predicate (если задан)
            if predicate_lower is not None:
                if fact.predicate.strip().lower() != predicate_lower:
                    filtered_facts.append(fact)  # Оставляем факт
                    continue
            
            # Проверяем object_contains (если задан)
            if object_contains_lower is not None:
                if object_contains_lower not in fact.object.strip().lower():
                    filtered_facts.append(fact)  # Оставляем факт
                    continue
            
            # Факт соответствует всем критериям - удаляем (не добавляем в filtered_facts)
        
        deleted_count = original_count - len(filtered_facts)
        
        # Сохраняем отфильтрованные факты
        if deleted_count > 0:
            _save_facts(filtered_facts)
            logger.info(f"[FACTS PURGE] Deleted {deleted_count} fact(s): subject={subject}, predicate={predicate}, object_contains={object_contains}")
        
        return {"deleted": deleted_count}
        
    except Exception as e:
        logger.error(f"[FACTS PURGE] Error: {e}")
        raise HTTPException(status_code=500, detail=f"facts purge error: {e}")
