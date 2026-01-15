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


# Insight text options by thinking_mode
INSIGHT_OPTIONS_BY_MODE: Dict[str, List[str]] = {
    "analytical": [
        "Замечаю повтор.",
        "Повторяющийся сигнал.",
        "Это уже встречалось.",
    ],
    "structured": [
        "Есть повтор.",
        "Фиксирую повтор.",
        "Повторилось снова.",
    ],
    "wide": [
        "Это всплывает снова.",
        "Похоже, возвращается.",
        "Опять появилось.",
    ],
    "hard": [
        "Повтор.",
        "Снова то же.",
        "Это не в первый раз.",
    ],
    "exploratory": [
        "Любопытно: снова всплыло.",
        "Интересно, это повторяется.",
        "Похоже, возвращается.",
    ],
}


def generate_insight_text(signal: str, thinking_mode: Optional[str] = None) -> str:
    """
    Generate insight text based on thinking_mode and signal hash.
    
    Args:
        signal: Signal string to generate deterministic hash from
        thinking_mode: Thinking mode (analytical, structured, wide, hard, exploratory)
                      If unknown or None, defaults to "structured"
    
    Returns:
        Insight text string
    """
    # Default to structured if thinking_mode is unknown
    mode = thinking_mode or "structured"
    if mode not in INSIGHT_OPTIONS_BY_MODE:
        mode = "structured"
    
    insight_options = INSIGHT_OPTIONS_BY_MODE[mode]
    
    # Use hash of signal for deterministic selection
    signal_hash = int(hashlib.md5(signal.encode()).hexdigest(), 16)
    return insight_options[signal_hash % len(insight_options)]


def generate_short_pattern_insight(snapshot: Dict[str, Any], signals: Dict[str, str]) -> str:
    """
    Generate a short (<= 1 line) pattern insight based on snapshot chips.
    No философия, just concise observation.
    Format: "Снова повтор: [pattern1] при [pattern2]."
    
    Args:
        snapshot: Snapshot dict with chips and signals_count
        signals: Current signals dict
    
    Returns:
        Short insight text string
    """
    chips = snapshot.get("chips", [])
    if not chips:
        return "Снова повтор: паттерн виден."
    
    # Extract key patterns from chips (prioritize energy and ready)
    energy_pattern = None
    ready_pattern = None
    other_patterns = []
    
    for chip in chips:
        k = chip.get("k", "")
        v = chip.get("v", "unknown")
        if v == "yes":
            if k == "energy":
                energy_pattern = "энергия высокая"
            elif k == "ready":
                ready_pattern = "готовность высокая"
            elif k == "overload":
                other_patterns.append("перегрузка")
            elif k == "focus":
                other_patterns.append("фокус есть")
            elif k == "emotion_load":
                other_patterns.append("эмоциональная нагрузка")
            elif k == "overflow":
                other_patterns.append("переполнение")
            elif k == "clarity":
                other_patterns.append("ясность")
        elif v == "no":
            if k == "energy":
                energy_pattern = "энергия низкая"
            elif k == "ready":
                ready_pattern = "готовность низкая"
            elif k == "overload":
                other_patterns.append("нет перегрузки")
            elif k == "focus":
                other_patterns.append("фокус слабый")
            elif k == "emotion_load":
                other_patterns.append("нет эмоциональной нагрузки")
            elif k == "overflow":
                other_patterns.append("нет переполнения")
            elif k == "clarity":
                other_patterns.append("нет ясности")
    
    # Build insight: prioritize energy + ready combination
    parts = []
    if energy_pattern:
        parts.append(energy_pattern)
    if ready_pattern:
        parts.append(ready_pattern)
    
    # Add one more pattern if we have space
    if len(parts) < 2 and other_patterns:
        parts.append(other_patterns[0])
    
    if not parts:
        return "Снова повтор: паттерн виден."
    
    # Format: "Снова повтор: [first] при [second]." or just "[first]." if only one
    if len(parts) >= 2:
        return f"Снова повтор: {parts[0]} при {parts[1]}."
    else:
        return f"Снова повтор: {parts[0]}."

def run_engine(
    current_answers: Dict[str, str],
    asked_ids: Optional[List[str]] = None,
    asked_at: Optional[Dict[str, float]] = None,
    domain_last_asked_at: Optional[Dict[str, float]] = None,
    answered_at: Optional[Dict[str, float]] = None,
    depth_mode: Optional[str] = None,
    calibration: Optional[Dict[str, int]] = None,
) -> EngineOutput:
    bank = load_bank()
    meta = load_meta()

    # Apply decay first (expired signals are treated as unknown)
    answered_at = answered_at or {}
    decay_res: DecayResult = apply_decay(current_answers, answered_at)
    rr = resolve(decay_res.filtered_answers, meta["collisions"])
    decision = pick_state(rr.signals, meta["states"], tags=rr.tags)
    
    # PHASE L2: Get base budget from depth_mode
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
