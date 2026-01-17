from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import hashlib

from .loader import load_bank, load_meta
from .signal_resolver import resolve
from .state_engine import pick_state
from .policy import select_next_questions, apply_personal_calibration
from .decay import apply_decay, DecayResult

@dataclass
class EngineOutput:
    mode: str
    state_id: str
    tags: List[str]
    ask_budget: int
    forbid_domains: List[str]
    forbid_actions: List[str]
    next_questions: List[dict]
    expired_signals: List[dict]
    calibration_profile: str = "base"  # PHASE L2: Profile string for debugging


# PHASE R v0.2 Step 1: Signal-specific insight interpretations
SIGNAL_INSIGHT_COPY: Dict[str, str] = {
    "baseline_energy": "уровень базовой энергии",
    "attention_available": "доступность внимания",
    "physical_fatigue": "физическая усталость",
    "mental_fatigue": "ментальная усталость",
    "sleep_deficit": "недосып",
    "recovery_state": "состояние восстановления",
    "attention_fragmented": "фрагментированное внимание",
    "focus_depth": "глубина фокуса",
    "rumination": "застревание в мыслях",
    "cognitive_noise": "когнитивный шум",
    "clarity": "ощущение ясности",
    "emotional_load_present": "эмоциональная нагрузка",
    "sense_of_control": "ощущение контроля",
    "overload_risk": "риск перегрузки",
    "nervous_system_load": "нагрузка на нервную систему",
    "alertness_level": "уровень бодрости",
    "energy_fluctuation": "колебания энергии",
    "exhaustion_threshold": "близость к истощению",
    "attention_fatigue": "усталость внимания",
    "emotional_overflow": "эмоциональное переполнение",
}


# PHASE Q3: Get angle text for signal insights based on thinking_mode
def _get_signal_insight_angle(thinking_mode: Optional[str]) -> str:
    """
    PHASE Q3: Get angle text for signal insights based on thinking_mode.
    
    Args:
        thinking_mode: Thinking mode (analytical, structured, wide, hard, exploratory, or None)
    
    Returns:
        Angle text string for the given thinking_mode
    """
    thinking_mode = thinking_mode or "structured"  # Default to structured if None
    
    angles = {
        "analytical": "Связь: это может влиять на способность держать задачу.",
        "structured": "Структура: фиксируем как факт текущего состояния.",
        "wide": "Варианты: это может быть временно или связано с контекстом.",
        "hard": "Прямо: если сигнал есть — действуй исходя из него.",
        "exploratory": "Проверим: это стабильно или ситуативно?",
    }
    
    return angles.get(thinking_mode, angles["structured"])


def generate_insight_text(signal: str, thinking_mode: Optional[str] = None) -> str:
    """
    PHASE R v0.2 Step 1: Generate signal-specific insight text.
    PHASE Q3: Now supports thinking_mode to add angle text before CTA.
    
    Args:
        signal: Signal string (e.g., "baseline_energy")
        thinking_mode: Thinking mode (analytical, structured, wide, hard, exploratory) to add angle text
    
    Returns:
        Insight text string in format: "Фиксирую сигнал: <signal>. Сейчас это означает: <interpretation>. <angle>. Дальше: продолжить / зафиксировать / копать."
    """
    # Get signal interpretation or use signal name as fallback
    interpretation = SIGNAL_INSIGHT_COPY.get(signal, signal)
    
    # PHASE Q3: Get angle text based on thinking_mode
    angle = _get_signal_insight_angle(thinking_mode)
    
    # Format: "Фиксирую сигнал: <signal>. Сейчас это означает: <interpretation>. <angle>. Дальше: продолжить / зафиксировать / копать."
    return f"Фиксирую сигнал: {signal}. Сейчас это означает: {interpretation}. {angle} Дальше: продолжить / зафиксировать / копать."


# PHASE R v0.2 Step 2: Chip key to Russian label mapping
CHIP_LABELS: Dict[str, str] = {
    "energy": "энергия",
    "overload": "перегрузка",
    "focus": "фокус",
    "emotion_load": "эмоциональная нагрузка",
    "overflow": "переполнение",
    "ready": "готовность",
    "clarity": "ясность",
    "fatigue": "усталость",
}

# PHASE R v0.2 Step 2: Value to readable form mapping
CHIP_VALUE_LABELS: Dict[str, str] = {
    "yes": "да",
    "no": "нет",
    "low": "низкий",
    "mid": "средний",
    "high": "высокий",
}

# PHASE R v0.2 Step 2: Hypothesis templates based on patterns
def _generate_hypothesis(chips_summary: List[str]) -> str:
    """Generate a short hypothesis based on chip patterns."""
    summary_lower = " ".join(chips_summary).lower()
    
    # Energy + fatigue patterns
    if "энергия: нет" in summary_lower or "усталость: да" in summary_lower:
        return "возможно, нужен отдых"
    if "энергия: да" in summary_lower and "фокус: да" in summary_lower:
        return "хорошее состояние для работы"
    
    # Overload patterns
    if "перегрузка: да" in summary_lower:
        return "риск перегрузки, стоит снизить темп"
    if "переполнение: да" in summary_lower:
        return "много информации, нужна пауза"
    
    # Focus patterns
    if "фокус: нет" in summary_lower:
        return "внимание рассеяно, нужна концентрация"
    if "фокус: да" in summary_lower and "ясность: да" in summary_lower:
        return "ясность и фокус — можно действовать"
    
    # Emotion patterns
    if "эмоциональная нагрузка: да" in summary_lower:
        return "эмоциональное напряжение требует внимания"
    
    # Default
    return "паттерн требует наблюдения"


# PHASE Q2: Sanitize insight text - remove double dots and normalize punctuation
def sanitize_insight_text(text: str) -> str:
    """
    PHASE Q2: Clean up insight text formatting.
    
    Args:
        text: Text to sanitize
    
    Returns:
        Cleaned text with normalized punctuation
    """
    if not text:
        return text
    
    # Replace double dots with single dot
    text = text.replace("..", ".")
    # Replace " ." and ". ." with "."
    text = text.replace(" .", ".")
    text = text.replace(". .", ".")
    # Trim spaces
    text = text.strip()
    
    return text


# PHASE Q1: Format hypothesis based on thinking_mode
def format_hypothesis(base_hypothesis: str, thinking_mode: Optional[str], chips: List[str]) -> str:
    """
    PHASE Q1: Format hypothesis text based on thinking_mode.
    
    Args:
        base_hypothesis: Base hypothesis text (e.g., "возможно, нужен отдых")
        thinking_mode: Thinking mode (analytical, structured, wide, hard, exploratory, or None)
        chips: List of chip summaries (for potential future use)
    
    Returns:
        Formatted hypothesis text according to thinking_mode style
    """
    thinking_mode = thinking_mode or "structured"  # Default to structured if None
    
    if thinking_mode == "analytical":
        return f"Наблюдается: {base_hypothesis}. Вероятное следствие: требует анализа."
    elif thinking_mode == "structured":
        return f"Сейчас: {base_hypothesis}. Следующий шаг: упорядочить/выбрать."
    elif thinking_mode == "wide":
        return f"Возможны варианты: {base_hypothesis}. Можно рассмотреть 2–3 направления."
    elif thinking_mode == "hard":
        return f"Факт: {base_hypothesis}. Если нет движения — причина не в состоянии."
    elif thinking_mode == "exploratory":
        return f"Гипотеза: {base_hypothesis}. Проверим?"
    else:
        # Fallback for unknown thinking_mode
        return base_hypothesis


def generate_short_pattern_insight(snapshot: Dict[str, Any], signals: Dict[str, str], thinking_mode: Optional[str] = None) -> str:
    """
    PHASE R v0.2 Step 2: Generate pattern insight with summary and hypothesis.
    PHASE Q1: Now supports thinking_mode to format hypothesis text.
    
    Args:
        snapshot: Snapshot dict with chips and signals_count
        signals: Current signals dict
        thinking_mode: Optional thinking mode (analytical, structured, wide, hard, exploratory) to format hypothesis
    
    Returns:
        Insight text string in format: "Сводка сейчас: [chips]. Гипотеза: [hypothesis]. Дальше: продолжить / зафиксировать / копать."
        Or fallback "Пока мало сигналов, продолжаем 1–2 вопроса. Дальше: продолжить / зафиксировать / копать." if all chips are unknown.
    """
    chips = snapshot.get("chips", [])
    if not chips:
        return "Пока мало сигналов, продолжаем 1–2 вопроса. Дальше: продолжить / зафиксировать / копать."
    
    # Extract 2-3 key chips (not unknown), prioritize energy, focus, overload
    priority_order = ["energy", "focus", "overload", "ready", "clarity", "fatigue", "emotion_load", "overflow"]
    selected_chips = []
    seen_keys = set()
    
    # First pass: priority chips
    for priority_key in priority_order:
        if len(selected_chips) >= 3:
            break
        for chip in chips:
            k = chip.get("k", "")
            v = chip.get("v", "unknown")
            if k == priority_key and v != "unknown" and k not in seen_keys:
                label = CHIP_LABELS.get(k, k)
                value_label = CHIP_VALUE_LABELS.get(v, v)
                selected_chips.append(f"{label}: {value_label}")
                seen_keys.add(k)
                break
    
    # Second pass: other chips if we have space
    if len(selected_chips) < 3:
        for chip in chips:
            if len(selected_chips) >= 3:
                break
            k = chip.get("k", "")
            v = chip.get("v", "unknown")
            if v != "unknown" and k not in seen_keys:
                label = CHIP_LABELS.get(k, k)
                value_label = CHIP_VALUE_LABELS.get(v, v)
                selected_chips.append(f"{label}: {value_label}")
                seen_keys.add(k)
    
    # If no valid chips found
    if not selected_chips:
        return "Пока мало сигналов, продолжаем 1–2 вопроса. Дальше: продолжить / зафиксировать / копать."
    
    # Build summary
    summary = ", ".join(selected_chips)
    
    # Generate base hypothesis
    base_hypothesis = _generate_hypothesis(selected_chips)
    
    # PHASE Q1: Format hypothesis based on thinking_mode
    hypothesis = format_hypothesis(base_hypothesis, thinking_mode, selected_chips)
    
    # PHASE Q2: Sanitize hypothesis text before assembly
    hypothesis = sanitize_insight_text(hypothesis)
    
    # PHASE Q2: Ensure single dot before "Дальше:"
    # Remove trailing punctuation from hypothesis (we add dot ourselves before "Дальше:")
    hypothesis = hypothesis.rstrip(".!?,")
    hypothesis = hypothesis.strip()
    
    # Format: "Сводка сейчас: [summary]. Гипотеза: [hypothesis]. Дальше: продолжить / зафиксировать / копать."
    return f"Сводка сейчас: {summary}. Гипотеза: {hypothesis}. Дальше: продолжить / зафиксировать / копать."

def run_engine(
    current_answers: Dict[str, str],
    asked_ids: Optional[List[str]] = None,
    asked_at: Optional[Dict[str, float]] = None,
    domain_last_asked_at: Optional[Dict[str, float]] = None,
    answered_at: Optional[Dict[str, float]] = None,
    depth_mode: Optional[str] = None,
    calibration: Optional[Dict[str, int]] = None,
    thinking_mode: Optional[str] = None,
) -> EngineOutput:
    bank = load_bank()
    meta = load_meta()

    # Apply decay first (expired signals are treated as unknown)
    answered_at = answered_at or {}
    decay_res: DecayResult = apply_decay(current_answers, answered_at)
    rr = resolve(decay_res.filtered_answers, meta["collisions"])
    decision = pick_state(rr.signals, meta["states"], tags=rr.tags)
    
    # PHASE L2: Get base budget from depth_mode only
    # thinking_mode does NOT override ask_budget (only affects initiative/insight thresholds)
    depth_mode = depth_mode or "normal"
    if depth_mode == "silent":
        base_budget = 0
    elif depth_mode == "normal":
        base_budget = 1
    elif depth_mode == "deep":
        base_budget = 2
    elif depth_mode == "giga":
        base_budget = 3
    else:
        base_budget = 1
    
    # PHASE L2: Apply personal calibration if provided
    effective_budget = base_budget
    calibration_profile = "base"
    if calibration is not None:
        effective_budget, calibration_profile = apply_personal_calibration(base_budget, calibration)
    
    # Use effective_budget for question selection
    # Note: select_next_questions will also apply depth_mode internally, but we pass the calibrated budget
    # We need to modify select_next_questions to accept an already-calibrated budget, or we need to
    # pass calibration to it. For now, let's pass the effective budget and have select_next_questions
    # use it if calibration is provided, otherwise apply depth_mode as before.
    
    selection = select_next_questions(
        bank=bank,
        flow_rules_yaml=meta["flow_rules"],
        decision_mode=decision.mode,
        ask_budget=effective_budget,
        forbid_domains=decision.forbid_domains,
        current_answers=rr.signals,
        asked_ids=asked_ids or [],
        asked_at=asked_at or {},
        domain_last_asked_at=domain_last_asked_at or {},
        tags=decision.tags,
        depth_mode=depth_mode,
        calibration_applied=calibration is not None,  # Flag to skip depth_mode adjustment if calibration was applied
    )

    return EngineOutput(
        mode=decision.mode,
        state_id=decision.state_id,
        tags=decision.tags,
        ask_budget=effective_budget,  # Return effective budget after calibration
        forbid_domains=decision.forbid_domains,
        forbid_actions=decision.forbid_actions,
        next_questions=[
            {"id": q.id, "signal": q.signal, "domain": q.domain, "question": q.question, "answers": list(q.answers)}
            for q in selection.questions
        ],
        expired_signals=[
            {"signal": sig, "age_sec": age}
            for sig, age in decay_res.expired.items()
        ],
        calibration_profile=calibration_profile,
    )
