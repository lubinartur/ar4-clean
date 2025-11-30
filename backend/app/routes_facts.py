from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

try:
    # запуск как пакет
    from backend.app.memory.facts import (
        Fact,
        get_facts_for_subject,
        add_fact,
        _load_facts,
    )
except Exception:  # запуск из корня
    from .memory.facts import (  # type: ignore
        Fact,
        get_facts_for_subject,
        add_fact,
        _load_facts,
    )


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
    Собирает профиль пользователя: еда, страны, транспорт, локация, прочее.
    """
    try:
        facts = get_facts_for_subject(subject, limit=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"facts profile error: {e}")

    profile = {
        "food": set(),
        "country": set(),
        "vehicle": set(),
        "goals": set(),
        "location": set(),
        "other": set(),
    }

    for f in facts:
        cat = f.category or "other"
        obj = f.object.strip()
        if cat not in profile:
            profile["other"].add(obj)
        else:
            profile[cat].add(obj)

    return {
        "subject": subject,
        "food": sorted(profile["food"]),
        "country": sorted(profile["country"]),
        "vehicle": sorted(profile["vehicle"]),
        "goals": sorted(profile["goals"]),
        "location": sorted(profile["location"]),
        "other": sorted(profile["other"]),
    }


# Reindex endpoint
@router.post("/reindex")
def reindex_facts(subject: str = "Arch") -> dict:
    """
    Переиндексирует все факты из локального хранилища в векторную память (MEMORY).
    По сути повторно прогоняет их через add_fact, который сам вызывает MEMORY.add_text().
    """
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
