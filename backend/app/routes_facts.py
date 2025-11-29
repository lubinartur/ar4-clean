from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

try:
    # запуск как пакет
    from backend.app.memory.facts import Fact, get_facts_for_subject
except Exception:  # запуск из корня
    from .memory.facts import Fact, get_facts_for_subject  # type: ignore


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
