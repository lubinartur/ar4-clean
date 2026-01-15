from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List, Set, Optional
import time

from .schema import Bank, Question
from .constants import DEFAULT_Q_COOLDOWN_SEC, DEFAULT_DOMAIN_COOLDOWN_SEC, MODE_SAFE_DOMAINS

@dataclass
class Selection:
    questions: List[Question]
    reason: str

def apply_personal_calibration(base_budget: int, calib: Dict[str, int]) -> tuple[int, str]:
    """
    PHASE L2 v0.1: Adjust ask_budget based on user behavior.
    
    Args:
        base_budget: Base ask_budget from depth_mode (silent:0, normal:1, deep:2, giga:3)
        calib: Calibration dict with keys: continue_count, capture_count, go_deeper_count, answers_count
    
    Returns:
        tuple of (adjusted_budget, calibration_profile)
        where calibration_profile is "push"|"balanced"|"gentle"|"base" for debugging
    """
    continue_count = calib.get("continue_count", 0)
    capture_count = calib.get("capture_count", 0)
    go_deeper_count = calib.get("go_deeper_count", 0)
    
    total_actions = continue_count + capture_count + go_deeper_count
    
    # Force push profile if go_deeper_count >= 3 and continue_count == 0
    force_push = go_deeper_count >= 3 and continue_count == 0
    
    # If total_actions < 3 and not forcing push: do nothing (keep base ask_budget)
    if total_actions < 3 and not force_push:
        return (base_budget, "base")
    
    # Calculate ratios
    go_deeper_ratio = go_deeper_count / total_actions if total_actions > 0 else 0.0
    capture_ratio = capture_count / total_actions if total_actions > 0 else 0.0
    continue_ratio = continue_count / total_actions if total_actions > 0 else 0.0
    
    # Determine profile
    if force_push or go_deeper_ratio >= 0.45:
        profile = "push"
    elif capture_ratio >= 0.45:
        profile = "balanced"
    elif continue_ratio >= 0.60:
        profile = "gentle"
    else:
        profile = "base"
    
    # Apply profile multiplier
    if profile == "push":
        adjusted = min(base_budget + 1, 3)
        # Additional rule: if in deep/giga mode with push profile, ensure at least 2 questions
        if base_budget >= 2:  # deep=2 or giga=3
            adjusted = max(adjusted, 2)
    elif profile == "balanced":
        adjusted = base_budget
    elif profile == "gentle":
        adjusted = max(base_budget - 1, 0)
    else:  # base
        adjusted = base_budget
    
    return (adjusted, profile)

def _domain_priority(flow_rules_yaml: Dict[str, Any]) -> List[str]:
    for r in flow_rules_yaml.get("rules", []):
        if r.get("id") == "FLOW-007" and r.get("type") == "priority":
            return list(r.get("order", []))
    return []

def _signals_known(answers: Dict[str, str]) -> Set[str]:
    return set(answers.keys())

def _filter_candidates(
    bank: Bank,
    forbid_domains: Set[str],
    known_signals: Set[str],
    asked_ids: Set[str],
) -> List[Question]:
    out: List[Question] = []
    for q in bank.questions:
        if q.domain in forbid_domains:
            continue
        if q.signal in known_signals:
            continue
        if q.id in asked_ids:
            continue
        out.append(q)
    return out

def _cooldown_ok_for_question(q: Question, asked_at: Dict[str, float], q_cd: int) -> bool:
    t = asked_at.get(q.id)
    if t is None:
        return True
    return (time.time() - t) >= q_cd

def _cooldown_ok_for_domain(q: Question, domain_last_asked_at: Dict[str, float], d_cd: int) -> bool:
    t = domain_last_asked_at.get(q.domain)
    if t is None:
        return True
    return (time.time() - t) >= d_cd

def select_next_questions(
    bank: Bank,
    flow_rules_yaml: Dict[str, Any],
    decision_mode: str,
    ask_budget: int,
    forbid_domains: Optional[List[str]],
    current_answers: Dict[str, str],
    asked_ids: Optional[List[str]] = None,
    asked_at: Optional[Dict[str, float]] = None,
    domain_last_asked_at: Optional[Dict[str, float]] = None,
    q_cooldown_sec: int = DEFAULT_Q_COOLDOWN_SEC,
    domain_cooldown_sec: int = DEFAULT_DOMAIN_COOLDOWN_SEC,
    tags: Optional[List[str]] = None,
    depth_mode: Optional[str] = None,
    calibration_applied: bool = False,
    prefer_domain: Optional[str] = None,
) -> Selection:
    """
    Minimal selection policy:
    - If ask_budget <= 0: return []
    - Pick questions by domain priority
    - In stabilize/contain modes: restrict to safest domains only
    - In execution mode: return []
    """
    tags = tags or []
    
    # PHASE L2: Apply depth_mode to set base ask_budget only if calibration hasn't been applied
    # If calibration was applied in engine.py, the ask_budget parameter already includes the adjustment
    if not calibration_applied:
        depth_mode = depth_mode or "normal"
        if depth_mode == "silent":
            ask_budget = 0
        elif depth_mode == "normal":
            ask_budget = 1
        elif depth_mode == "deep":
            ask_budget = 2
        elif depth_mode == "giga":
            ask_budget = 3
        else:
            # Unknown depth_mode, use normal behavior
            ask_budget = 1
    
    if ask_budget <= 0 or decision_mode == "execution":
        return Selection(questions=[], reason="no_questions_allowed")

    forbid_domains_set = set(forbid_domains or [])
    known = _signals_known(current_answers)
    asked_set = set(asked_ids or [])
    asked_at = asked_at or {}
    domain_last_asked_at = domain_last_asked_at or {}

    # Mode-based safety clamp
    safe_domains = MODE_SAFE_DOMAINS.get(decision_mode)
    # reframe/scan: no clamp beyond forbids

    candidates = _filter_candidates(bank, forbid_domains_set, known, asked_set)
    if safe_domains is not None:
        candidates = [q for q in candidates if q.domain in safe_domains]

    # Apply cooldowns (even if question not in asked_ids list; asked_at is the source of truth)
    candidates = [
        q for q in candidates
        if _cooldown_ok_for_question(q, asked_at, q_cooldown_sec)
        and _cooldown_ok_for_domain(q, domain_last_asked_at, domain_cooldown_sec)
    ]

    # Domain priority order
    order = _domain_priority(flow_rules_yaml)
    order_index = {d: i for i, d in enumerate(order)}
    
    # PHASE L2: Domain preference for go_deeper
    def domain_pref_score(q: Question) -> int:
        if prefer_domain and q.domain == prefer_domain:
            return -100  # Strong preference for preferred domain
        return 0

    candidates.sort(key=lambda q: (
        domain_pref_score(q),  # Prefer domain first if specified
        order_index.get(q.domain, 999)  # Then by domain priority
    ))

    # Tag-sensitive nudges (tiny but effective)
    def tag_score(q: Question) -> int:
        s = 0
        if "energy_action_mismatch" in tags and q.domain in ("motivation_drive", "risk_defense", "action_execution"):
            s -= 5
        if "want_but_avoid" in tags and q.domain in ("action_execution", "risk_defense"):
            s -= 5
        if "emotion_blind_spot" in tags and q.domain == "emotion_regulation":
            s -= 5
        if "control_illusion" in tags and q.domain == "control_agency_pressure":
            s -= 5
        return s

    # Re-sort with tag scores (keeping domain preference)
    candidates.sort(key=lambda q: (
        domain_pref_score(q),
        order_index.get(q.domain, 999),
        tag_score(q)
    ))

    chosen = candidates[:ask_budget]
    return Selection(
        questions=chosen,
        reason=f"mode={decision_mode},budget={ask_budget},tags={tags}",
    )
