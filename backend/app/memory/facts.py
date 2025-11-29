from __future__ import annotations

import json
import time
import re
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

# Файл, где храним факты (рядом с этим модулем)
FACTS_PATH = Path(__file__).with_name("facts_store.json")


class Fact(BaseModel):
    """
    Базовая единица знания: триплет subject–predicate–object.

    Примеры:
      Arch  --ужинал_с-->  ПАМЯТЬ_ТЕСТ_777
      Arch  --любит-->     Ducati Panigale V4
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    subject: str
    predicate: str
    object: str
    timestamp: float = Field(default_factory=lambda: time.time())
    category: Optional[str] = None
    source_session: Optional[str] = None
    source_message_id: Optional[str] = None


def _load_facts() -> List["Fact"]:
    """Читаем все факты из JSON. Если файла нет/битый — возвращаем пустой список."""
    if not FACTS_PATH.exists():
        return []

    try:
        raw = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
        return [Fact.parse_obj(item) for item in raw]
    except Exception as e:
        print(f"[FACTS] failed to load facts: {e}")
        return []


def _save_facts(facts: List["Fact"]) -> None:
    """Сохраняем список фактов обратно в JSON."""
    data = [f.dict() for f in facts]
    FACTS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _infer_category(predicate: str, obj: str) -> Optional[str]:
    """
    Простейшая категоризация фактов:
    - food: еда / блюда
    - country: страны / путешествия
    - vehicle: транспорт
    - location: место жительства
    """
    p = (predicate or "").lower().strip()
    o = (obj or "").lower().strip()

    # Еда / блюда
    food_markers = [
        "суши",
        "пицц",
        "паста",
        "пасту",
        "стейк",
        "стейки",
        "поке",
        "яблоко",
        "яблочко",
        "яблоки",
    ]

    # Страны / география
    country_markers = [
        "италия",
        "япония",
        "португал",
        "эстони",
        "литв",
        "латв",
        "исланд",
        "малта",
    ]

    # Транспорт / машины / байки
    vehicle_markers = [
        "bmw",
        "ducati",
        "mercedes",
        "audi",
        "porsche",
        "панигале",
        "panigale",
    ]

    if p in ("любит", "нравится"):
        if any(w in o for w in food_markers):
            return "food"
        if any(w in o for w in country_markers):
            return "country"

    if p == "живёт_в":
        return "location"

    if p == "владеет" or any(w in o for w in vehicle_markers):
        return "vehicle"

    return None


def add_fact(fact: Fact) -> None:
    """
    Добавляет факт в хранилище, избегая точных дублей.
    Дубль = совпадают subject, predicate и object (после тримминга).
    Если дубликат найден — обновляем timestamp, не создаём новую запись.
    """
    facts = _load_facts()

    subj = fact.subject.strip()
    pred = fact.predicate.strip()
    obj = fact.object.strip()

    updated = False
    for existing in facts:
        if (
            existing.subject.strip() == subj
            and existing.predicate.strip() == pred
            and existing.object.strip() == obj
        ):
            existing.timestamp = fact.timestamp
            existing.source_session = fact.source_session
            existing.source_message_id = fact.source_message_id
            updated = True
            break

    if not updated:
        facts.append(fact)

    _save_facts(facts)


def get_facts_for_subject(subject: str, limit: int = 20) -> List[Fact]:
    """Получить факты, где этот subject фигурирует как субъект."""
    facts = _load_facts()
    subj = subject.lower().strip()
    results = [f for f in facts if f.subject.lower().strip() == subj]
    results.sort(key=lambda f: f.timestamp, reverse=True)
    return results[:limit]


# ====== PRIMITIVE TEXT → FACTS EXTRACTOR (v0.1) ======


def extract_facts_from_text(
    text: str,
    *,
    subject: str = "Arch",
    source_session: str | None = None,
    source_message_id: str | None = None,
) -> list[Fact]:
    """
    Очень простой extractor (v0.1).
    Ищет базовые шаблоны типа:
      - "я люблю X"
      - "мне нравится X"
    Возвращает список Fact.
    """
    facts: list[Fact] = []

    lowered = text.lower()

    # Паттерн "я люблю X"
    m = re.search(r"\bя люблю\s+(.+)", lowered)
    if m:
        obj = m.group(1).strip().rstrip(".!")
        facts.append(
            Fact(
                subject=subject,
                predicate="любит",
                object=obj,
                category=_infer_category("любит", obj),
                source_session=source_session,
                source_message_id=source_message_id,
            )
        )

    # Паттерн "мне нравится X"
    m = re.search(r"\bмне нравится\s+(.+)", lowered)
    if m:
        obj = m.group(1).strip().rstrip(".!")
        facts.append(
            Fact(
                subject=subject,
                predicate="нравится",
                object=obj,
                category=_infer_category("нравится", obj),
                source_session=source_session,
                source_message_id=source_message_id,
            )
        )

    return facts


# NOTE: v3 extractor available: extract_facts_from_text_v3()


def extract_facts_from_text_v3(
    text: str,
    *,
    subject: str = "Arch",
    source_session: str | None = None,
    source_message_id: str | None = None,
) -> list[Fact]:
    """Расширенный extractor v3.1:
    - поддерживает несколько паттернов (живет, любит, владеет, работает)
    - нормализует предикаты
    - делит списки (я люблю X, Y, Z) без ломания слов
    - фильтрует мусор и вопросительные куски
    """
    facts: list[Fact] = []

    def make(obj: str, predicate: str) -> Fact:
        obj_clean = obj.strip()
        return Fact(
            subject=subject,
            predicate=predicate,
            object=obj_clean,
            category=_infer_category(predicate, obj_clean),
            source_session=source_session,
            source_message_id=source_message_id,
        )

    # безопасное разбиение списков
    def split_items(raw: str) -> list[str]:
        # режем только по запятым и отдельному слову "и"/"and"
        parts = re.split(r",|\s+и\s+|\s+and\s+", raw)
        out: list[str] = []
        for p in parts:
            item = p.strip().strip(".!? ").strip()
            if not item:
                continue
            if "?" in item:
                # не сохраняем куски вопросов
                continue
            if len(item) < 3:
                # отбрасываем обрывки типа "я", "ну", "ть"
                continue
            out.append(item)
        return out

    # --- Любит / нравится ---
    love_patterns = [
        r"\bя люблю\s+(.+)",
        r"\bмне нравится\s+(.+)",
        r"\bобожаю\s+(.+)",
        r"\bкайфую от\s+(.+)",
    ]
    for pat in love_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            for item in split_items(raw):
                low = item.lower()
                # Не превращаем хвосты типа "я живу в Эстонии" или "я работаю..."
                if low.startswith("я "):
                    continue
                facts.append(make(item, "любит"))

    # --- Живет ---
    m = re.search(r"\bя живу в\s+([a-zA-Zа-яА-ЯёЁ\s]+)", text, flags=re.IGNORECASE)
    if m:
        city = m.group(1).strip().strip(".!? ")
        if city and "?" not in city and len(city) > 2:
            facts.append(make(city.lower(), "живёт_в"))

    # --- Владею / у меня есть ---
    own_patterns = [
        r"\bу меня есть\s+(.+)",
        r"\bя владею\s+(.+)",
    ]
    for pat in own_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            for item in split_items(raw):
                facts.append(make(item, "владеет"))

    # --- Работа ---
    m = re.search(r"\bя работаю\s+(.+)", text, flags=re.IGNORECASE)
    if m:
        role = m.group(1).strip().strip(".!? ")
        if role and "?" not in role and len(role) > 2:
            facts.append(make(role, "работает_как"))

    # --- Тренировки ---
    m = re.search(r"\bя тренируюсь\s+(.+)", text, flags=re.IGNORECASE)
    if m:
        freq = m.group(1).strip().strip(".!? ")
        if freq and "?" not in freq and len(freq) > 2:
            facts.append(make(freq, "тренируется"))

    return facts
