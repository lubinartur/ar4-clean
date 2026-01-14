from __future__ import annotations

import json
import time
import re
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from . import manager_chroma

# Файл, где храним факты (рядом с этим модулем)
FACTS_PATH = Path(__file__).with_name("facts_store.json")

# Single-value predicates: предикаты, где новое значение перезаписывает старое
SINGLE_VALUE_PREDICATES = {
    "любимый цвет",
    "favorite color",
    "место жительства",
    "страна",
    "location",
    "country",
    "живёт_в",
    "lives_in",
    "работает_как",
    "job",
    "профессия",
}


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
    - sport: спорт / тренировки
    - health: здоровье / травмы / курс
    - work: работа / профессия / проекты
    - goals: цели / долгосрочные задачи
    - hobby: хобби / интересы
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
        "бургер",
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
        "ламборгини",
        "lamborghini",
    ]

    # Спорт / тренировки
    sport_markers = [
        "зал",
        "тренируюсь",
        "тренировка",
        "тренировки",
        "жим",
        "присед",
        "становая",
        "сплит",
        "бицепс",
        "грудь",
        "плечи",
        "ноги",
        "кикбоксинг",
    ]

    # Здоровье / курс / травмы
    health_markers = [
        "спина",
        "поясница",
        "боль",
        "травма",
        "восстановление",
        "здоровье",
        "сустанон",
        "курс",
    ]

    # Работа / проекты
    work_markers = [
        "работаю",
        "работа",
        "дизайнер",
        "дизайн",
        "ux",
        "ui",
        "проект",
        "проекты",
        "air4",
        "ai",
        "финансы",
        "кредиты",
    ]

    # Цели
    goals_markers = [
        "цель",
        "цели",
        "соната",
        "лунная соната",
        "bench",
        "жим",
        "кг",
        "евро",
        "доход",
    ]

    # Хобби / интересы
    hobby_markers = [
        "музыка",
        "фортепиано",
        "пианино",
        "мото",
        "байк",
        "мотоцикл",
        "аниме",
        "3d",
        "рендер",
        "рисовать",
        "рисование",
        "фото",
        "фотография",
    ]

    # Вариант B: цели только для "серьёзных" хотелок, не еды
    if p in ("хочет", "хочу", "мечтает", "мечтаю"):
        # если это еда — считаем как еду, а не цель
        if any(w in o for w in food_markers):
            return "food"
        # если явно про авто / технику — считаем как цель (хочу машину/бренд)
        if any(w in o for w in vehicle_markers):
            return "goals"
        # если упоминается доход / деньги / результат — тоже цель
        serious_goal_markers = [
            "евро",
            "€",
            "доход",
            "зарплат",
            "зарабатывать",
            "заработок",
            "цель",
            "соната",
            "лунная соната",
            "курс",
            "форму",
            "дом",
            "квартир",
        ]
        if any(w in o for w in serious_goal_markers):
            return "goals"
        # остальное по умолчанию не считаем отдельной категорией целей

    if p in ("любит", "нравится"):
        if any(w in o for w in food_markers):
            return "food"
        if any(w in o for w in country_markers):
            return "country"
        if any(w in o for w in sport_markers):
            return "sport"
        if any(w in o for w in health_markers):
            return "health"
        if any(w in o for w in hobby_markers):
            return "hobby"

    if p == "живёт_в":
        return "location"

    if p in ("тренируется",):
        return "sport"

    if p == "владеет" or any(w in o for w in vehicle_markers):
        return "vehicle"

    if p in ("работает_как", "работает") or any(w in o for w in work_markers):
        return "work"

    if any(w in o for w in goals_markers):
        return "goals"

    return None


def add_fact(fact: Fact) -> None:
    """
    Добавляет факт в хранилище, избегая точных дублей.
    
    Для single-value предикатов:
    - Удаляет все старые факты с тем же (subject, predicate) перед сохранением
    - В storage всегда только 1 актуальный факт
    
    Для multi-value предикатов:
    - Дубль = совпадают subject, predicate и object (после тримминга)
    - Если дубликат найден — обновляем timestamp, не создаём новую запись
    """
    facts = _load_facts()

    subj = fact.subject.strip()
    pred = fact.predicate.strip()
    obj = fact.object.strip()
    pred_key = pred.lower()

    # Для single-value предикатов: удаляем все старые факты с тем же predicate
    if pred_key in SINGLE_VALUE_PREDICATES:
        facts = [f for f in facts 
                if not (f.subject.strip().lower() == subj.lower() 
                       and f.predicate.strip().lower() == pred_key)]
        # Добавляем новый факт
        facts.append(fact)
        _save_facts(facts)
    else:
        # Для multi-value: проверяем на дубликаты (полный триплет)
        updated = False
        for existing in facts:
            if (
                existing.subject.strip().lower() == subj.lower()
                and existing.predicate.strip().lower() == pred_key
                and existing.object.strip().lower() == obj.lower()
            ):
                existing.timestamp = fact.timestamp
                existing.source_session = fact.source_session
                existing.source_message_id = fact.source_message_id
                existing.category = fact.category  # Обновляем категорию тоже
                updated = True
                break

        if not updated:
            facts.append(fact)

        _save_facts(facts)

    # Дополнительно сохраним факт в векторную память (Memory Bank → All)
    try:
        mm = getattr(manager_chroma, "MEMORY", None)
        if mm is not None and hasattr(mm, "add_text"):
            text = f"{fact.subject} {fact.predicate.replace('_', ' ')} {fact.object}"
            mm.add_text(
                user_id="dev",
                text=text,
                session_id=fact.source_session or "facts",
                source="facts",
            )
    except Exception as e:
        print(f"[FACTS] failed to index fact in memory: {e}")


def get_facts_for_subject(subject: str, limit: int = 20) -> List[Fact]:
    """Получить факты, где этот subject фигурирует как субъект."""
    facts = _load_facts()
    subj = subject.lower().strip()
    results = [f for f in facts if f.subject.lower().strip() == subj]
    results.sort(key=lambda f: f.timestamp, reverse=True)
    return results[:limit]


def delete_facts(subject: str, predicate: str, object_value: str | None = None) -> int:
    """
    Удаляет факты по критериям (case-insensitive).
    
    Args:
        subject: Subject для фильтрации (case-insensitive)
        predicate: Predicate для фильтрации (case-insensitive)
        object_value: Optional object для фильтрации (case-insensitive)
    
    Returns:
        Количество удалённых фактов
    """
    facts = _load_facts()
    subject_lower = subject.lower().strip()
    predicate_lower = predicate.lower().strip()
    object_lower = object_value.lower().strip() if object_value else None
    
    original_count = len(facts)
    
    # Фильтруем факты: оставляем только те, которые НЕ соответствуют критериям удаления
    filtered_facts = []
    for fact in facts:
        fact_subj = fact.subject.lower().strip()
        fact_pred = fact.predicate.lower().strip()
        fact_obj = fact.object.lower().strip()
        
        # Проверяем совпадение subject и predicate
        if fact_subj != subject_lower or fact_pred != predicate_lower:
            filtered_facts.append(fact)
            continue
        
        # Если object_value указан, проверяем и его
        if object_lower is not None:
            if fact_obj != object_lower:
                filtered_facts.append(fact)
            # Иначе пропускаем (удаляем)
        else:
            # object_value не указан - удаляем все факты с таким subject+predicate
            # (не добавляем в filtered_facts)
            pass
    
    deleted_count = original_count - len(filtered_facts)
    
    if deleted_count > 0:
        _save_facts(filtered_facts)
    
    return deleted_count


def get_profile_completeness(subject: str = "Arch") -> dict[str, bool]:
    """
    Проверяет полноту профиля: какие ключевые поля заполнены.
    
    Returns:
        dict с ключами: "location", "job", "favorite_color"
        Значение True = поле заполнено, False = не заполнено
    """
    facts = get_facts_for_subject(subject, limit=200)
    
    # Предикаты для каждого поля
    location_predicates = {"живёт_в", "lives_in", "location", "место жительства"}
    job_predicates = {"работает_как", "job", "профессия"}
    favorite_color_predicates = {"любимый цвет", "favorite color"}
    
    completeness = {
        "location": False,
        "job": False,
        "favorite_color": False,
    }
    
    for fact in facts:
        pred_key = fact.predicate.strip().lower()
        
        if pred_key in location_predicates:
            completeness["location"] = True
        elif pred_key in job_predicates:
            completeness["job"] = True
        elif pred_key in favorite_color_predicates:
            completeness["favorite_color"] = True
    
    return completeness


def choose_next_profile_question(completeness: dict[str, bool]) -> tuple[str, str] | None:
    """
    Выбирает следующий вопрос для заполнения профиля.
    
    Args:
        completeness: результат get_profile_completeness()
    
    Returns:
        tuple (key, question) или None если все поля заполнены
        Приоритет: location -> job -> favorite_color
    """
    if not completeness.get("location"):
        return ("location", "Где ты сейчас живёшь (страна/город)?")
    
    if not completeness.get("job"):
        return ("job", "Кем работаешь?")
    
    if not completeness.get("favorite_color"):
        return ("favorite_color", "Какой твой любимый цвет?")
    
    return None


def delete_all_facts_for_subject(subject: str) -> int:
    """
    Удаляет ВСЕ факты для указанного subject (case-insensitive).
    
    Args:
        subject: Subject для фильтрации (case-insensitive)
    
    Returns:
        Количество удалённых фактов
    """
    facts = _load_facts()
    subject_lower = subject.lower().strip()
    
    original_count = len(facts)
    
    # Фильтруем факты: оставляем только те, которые НЕ соответствуют subject
    filtered_facts = [
        fact for fact in facts 
        if fact.subject.lower().strip() != subject_lower
    ]
    
    deleted_count = original_count - len(filtered_facts)
    
    if deleted_count > 0:
        _save_facts(filtered_facts)
    
    return deleted_count


def extract_profile_facts_auto(
    text: str,
    *,
    subject: str = "Arch",
    source_session: str | None = None,
    source_message_id: str | None = None,
) -> list[Fact]:
    """
    Легковесный экстрактор для автосохранения профильных фактов.
    
    Сохраняет ТОЛЬКО стабильные свойства (profile facts):
    - location (живёт_в)
    - job (работает_как)
    - favorite color (любимый цвет)
    - country (страна)
    
    НЕ сохраняет:
    - желания ("хочу", "планирую")
    - временные состояния
    - вопросы
    - эмоции
    - еду, транспорт, цели (это не profile)
    
    Требования:
    - Утверждение от первого лица ("я живу", "мой", "мне", "я работаю")
    - Стабильное свойство (не желание, не вопрос)
    """
    facts: list[Fact] = []
    
    # Фильтруем вопросы и временные/желательные формулировки
    text_lower = text.lower().strip()
    
    # Пропускаем вопросы
    question_starters = ("какой", "какая", "какие", "как", "что", "где", "когда", "почему", "зачем", "сколько", "чей", "чья", "чьё")
    if "?" in text or text_lower.startswith(question_starters):
        return facts
    
    # Пропускаем желания, планы и временные формулировки
    temporal_patterns = [
        r"\bхочу\b",
        r"\bхотел\b",
        r"\bхотела\b",
        r"\bпланирую\b",
        r"\bпланирую\b",
        r"\bмечтаю\b",
        r"\bдумаю\b",
        r"\bможет\b",
        r"\bможет быть\b",
        r"\bнаверное\b",
        r"\bнаверно\b",
        r"\bсейчас\b",
        r"\bсегодня\b",
        r"\bнужно\b",
        r"\bнадо\b",
    ]
    for pattern in temporal_patterns:
        if re.search(pattern, text_lower):
            return facts
    
    # --- Любимый цвет ---
    color_patterns = [
        r'(мой|моя)\s+любим(ый|ая)\s+цвет\s*(—|-|:)?\s*([a-zA-Zа-яА-ЯёЁ]+)',
        r'любимый\s+цвет\s*(—|-|:)?\s*([a-zA-Zа-яА-ЯёЁ]+)',
        r'favorite\s+color\s*(—|-|:)?\s*([a-zA-Zа-яА-ЯёЁ]+)',
    ]
    for pattern in color_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            color = (m.group(4) if len(m.groups()) >= 4 else m.group(2)).strip().lower()
            if color and len(color) > 2 and "?" not in color:
                facts.append(Fact(
                    subject=subject,
                    predicate="любимый цвет",
                    object=color,
                    category="profile",
                    source_session=source_session,
                    source_message_id=source_message_id,
                ))
                return facts  # Single-value, возвращаем сразу
    
    # --- Место жительства ---
    location_patterns = [
        r"\bя живу в\s+([a-zA-Zа-яА-ЯёЁ\s\-]+)",
        r"\bживу в\s+([a-zA-Zа-яА-ЯёЁ\s\-]+)",
        r"\blives?\s+in\s+([a-zA-Zа-яА-ЯёЁ\s\-]+)",
    ]
    for pattern in location_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            location = m.group(1).strip().strip(".!? ")
            if location and len(location) > 2 and "?" not in location:
                # Проверяем, что это не вопрос
                location_words = location.split()
                if len(location_words) <= 5:  # Не слишком длинные фразы
                    facts.append(Fact(
                        subject=subject,
                        predicate="живёт_в",
                        object=location.lower(),
                        category="profile",
                        source_session=source_session,
                        source_message_id=source_message_id,
                    ))
                    return facts  # Single-value
    
    # --- Работа / профессия ---
    job_patterns = [
        r"\bя работаю\s+(.+?)(?:\.|$|,|\s+и\s+)",
        r"\bработаю\s+(.+?)(?:\.|$|,|\s+и\s+)",
        r"\bработаю\s+веб[\s\-]?дизайнером",
        r"\bработаю\s+программистом",
        r"\bпрофессия\s*[:—\-]\s*(.+?)(?:\.|$|,)",
    ]
    for pattern in job_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            job = m.group(1).strip().strip(".!? ")
            if job and len(job) > 2 and "?" not in job:
                # Очищаем от лишних слов
                job = re.sub(r'^(как|веб|senior|junior)\s+', '', job, flags=re.IGNORECASE).strip()
                if job and len(job.split()) <= 5:  # Не слишком длинные фразы
                    facts.append(Fact(
                        subject=subject,
                        predicate="работает_как",
                        object=job.lower(),
                        category="profile",
                        source_session=source_session,
                        source_message_id=source_message_id,
                    ))
                    return facts  # Single-value
    
    # --- Страна (если явно указана) ---
    country_patterns = [
        r"\b(из|родом из|родом с)\s+([А-ЯЁ][а-яё]+(?:ии|ии|ии)?)",
        r"\b(country|страна)\s*[:—\-]\s*([А-ЯЁ][а-яё]+(?:ии|ии|ии)?)",
    ]
    for pattern in country_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            country = m.group(2).strip().strip(".!? ")
            if country and len(country) > 2 and "?" not in country:
                facts.append(Fact(
                    subject=subject,
                    predicate="страна",
                    object=country.lower(),
                    category="profile",
                    source_session=source_session,
                    source_message_id=source_message_id,
                ))
                return facts  # Single-value
    
    return facts


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

    # --- FAVORITE COLOR (robust) ---
    # Железобетонный паттерн, не зависит от тире/пунктуации
    m = re.search(
        r'(мой|моя)\s+любим(ый|ая)\s+цвет\s*(—|-|:)?\s*([a-zA-Zа-яА-ЯёЁ]+)',
        text,
        re.IGNORECASE
    )
    if m:
        color = m.group(4).strip().lower()
        if color and len(color) > 2:
            facts.append(Fact(
                subject=subject,
                predicate="любимый цвет",
                object=color,
                category="profile",
                source_session=source_session,
                source_message_id=source_message_id,
            ))
            return facts

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

    # --- Хочет / цели ---
    goal_patterns = [
        r"\bя хочу\s+(.+)",
        r"\bхочу\s+(.+)",
    ]
    for pat in goal_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            for item in split_items(raw):
                low = item.lower()
                # Не сохраняем хвосты типа "я живу", "я работаю" и т.п.
                if low.startswith("я "):
                    continue
                facts.append(make(item, "хочет"))

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

    # --- Любимый цвет (single-value) ---
    color_patterns = [
        r"\b(мой|моя|мое)\s+любимый\s+цвет\s*[:\-–—]\s*(.+)",
        r"\b(мой|моя|мое)\s+любимый\s+цвет\s+это\s+(.+)",
        r"\bлюбимый\s+цвет\s*[:\-–—]\s*(.+)",
        r"\bfavorite\s+color\s*[:\-–—]\s*(.+)",
    ]
    for pat in color_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            color = m.group(-1).strip().strip(".!? ")  # Берём последнюю группу (цвет)
            if color and "?" not in color and len(color) > 2:
                facts.append(
                    Fact(
                        subject=subject,
                        predicate="любимый цвет",
                        object=color,
                        category="profile",
                        source_session=source_session,
                        source_message_id=source_message_id,
                    )
                )

    return facts
