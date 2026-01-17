from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Optional, List, Any
import time
import os

from .question_bank.engine import run_engine, generate_insight_text, generate_short_pattern_insight
from .question_bank.store_singleton import store
from .question_bank.validation import validate_answer_value, validate_signal_exists
from .question_bank.loader import load_bank, load_meta
from .question_bank.context import build_qb_context
from .question_bank.onboarding import ONBOARDING_PACKS
from .question_bank.snapshot import build_snapshot
from .question_bank.scoring import compute_score
from .question_bank.chat_bridge import build_chat_preamble
from .question_bank.policy import select_next_questions
from .question_bank.signal_resolver import resolve
from .question_bank.decay import apply_decay
from .question_bank.state_engine import pick_state
from .question_bank.constants import (
    INIT_THRESHOLD,
    INSIGHT_COOLDOWN_SEC,
    INSIGHT_SIGNAL_COOLDOWN_SEC,
    AUTO_INSIGHT_MIN_INTERVAL,
    HISTORICAL_MIN_GAP_SEC,
    HISTORICAL_COOLDOWN_SEC,
    get_thinking_mode_policy,
    get_initiative_threshold,
    get_insight_signal_threshold,
    get_insight_interval_multiplier,
)

router = APIRouter(prefix="/qb", tags=["question_bank"])

_bank = load_bank()
_signal_set = set([q.signal for q in _bank.questions])

# PHASE R v0.3 Step 1.2: Compute pattern_key from signals (stable), not from snapshot.chips
def _compute_pattern_key_from_signals(signals: Dict[str, str]) -> Optional[str]:
    """
    Compute pattern_key from signals dict (stable mapping).
    Maps: energy <- baseline_energy, focus <- attention_available, overload <- overload_risk
    Returns None if no valid signals found.
    """
    if not signals:
        return None
    
    pattern_parts = []
    
    # energy <- baseline_energy (yes/no)
    energy_val = signals.get("baseline_energy", "")
    if energy_val in ("yes", "no"):
        pattern_parts.append(f"energy:{energy_val}")
    
    # focus <- attention_available (yes/no)
    focus_val = signals.get("attention_available", "")
    if focus_val in ("yes", "no"):
        pattern_parts.append(f"focus:{focus_val}")
    
    # overload <- overload_risk (yes/no)
    overload_val = signals.get("overload_risk", "")
    if overload_val in ("yes", "no"):
        pattern_parts.append(f"overload:{overload_val}")
    
    if not pattern_parts:
        return None
    
    # Sort to ensure consistent ordering
    pattern_parts.sort()
    return "|".join(pattern_parts)


def get_cooldown_sec(depth_mode: Optional[str], calibration_profile: Optional[str] = None) -> int:
    """Get cooldown in seconds based on depth_mode and calibration profile."""
    depth_mode = depth_mode or "normal"
    if depth_mode == "silent":
        return 60
    elif depth_mode == "normal":
        base_cooldown = 20
    elif depth_mode == "deep":
        base_cooldown = 10
    elif depth_mode == "giga":
        base_cooldown = 5
    else:
        base_cooldown = 20  # Default to normal
    
    # Apply profile-based adjustment (push mode reduces cooldown further)
    if calibration_profile == "push" and depth_mode in ("deep", "giga"):
        # Reduce cooldown by 50% for push mode in deep/giga
        return max(1, base_cooldown // 2)
    
    return base_cooldown

class QBRequest(BaseModel):
    # signal -> answer (e.g. {"baseline_energy":"yes"})
    answers: Dict[str, str] = Field(default_factory=dict)

@router.post("/next")
def qb_next(req: QBRequest):
    # Stateless mode: validate inputs
    for sig, ans in req.answers.items():
        validate_signal_exists(sig, _signal_set)
        validate_answer_value(ans)
    # Stateless mode doesn't have calibration data, so pass None
    # Default to "structured" thinking_mode for stateless mode
    out = run_engine(req.answers, asked_ids=[], asked_at={}, domain_last_asked_at={}, answered_at={}, calibration=None, thinking_mode="structured")
    return {
        "state": {"id": out.state_id, "mode": out.mode, "tags": out.tags},
        "constraints": {"ask_budget": out.ask_budget, "forbid_domains": out.forbid_domains, "forbid_actions": out.forbid_actions},
        "questions": out.next_questions,
        "expired": out.expired_signals,
    }


class QBCreateSessionResponse(BaseModel):
    session_id: str


@router.post("/sessions", response_model=QBCreateSessionResponse)
def qb_create_session():
    s = store.create()
    return {"session_id": s.id}

@router.get("/onboarding")
def qb_onboarding():
    """
    Returns canonical onboarding packs (signal lists).
    UI can request pack -> ask those signals quickly.
    """
    return {"packs": ONBOARDING_PACKS}

class QBOnboardingPackRequest(BaseModel):
    session_id: str
    pack_id: str

@router.post("/onboarding/start")
def qb_onboarding_start(req: QBOnboardingPackRequest):
    s = store.get(req.session_id)
    if s is None:
        return {"error": "session_not_found", "session_id": req.session_id}
    pack = next((p for p in ONBOARDING_PACKS if p["id"] == req.pack_id), None)
    if pack is None:
        raise HTTPException(status_code=400, detail="unknown_pack_id")
    # Return questions matching pack signals, excluding already answered
    sigs = [x for x in pack["signals"] if x not in s.answers]
    qs = [q for q in _bank.questions if q.signal in sigs]
    return {
        "session": {"id": s.id, "answered": len(s.answers)},
        "pack": {"id": pack["id"], "name": pack["name"]},
        "questions": [{"id": q.id, "signal": q.signal, "domain": q.domain, "question": q.question, "answers": list(q.answers)} for q in qs],
    }

class QBAnswerRequest(BaseModel):
    session_id: str
    signal: str
    answer: str
    depth_mode: Optional[str] = None
    thinking_mode: Optional[str] = None
    action: Optional[str] = Field(None, description="PHASE L1: Optional suggest action (continue/capture/go_deeper)")

class QBActionRequest(BaseModel):
    session_id: str
    action: str  # "continue" | "capture" | "go_deeper"


@router.post("/answer")
def qb_answer(req: QBAnswerRequest, debug: Optional[int] = None):
    """
    Stateful mode: client sends one answer at a time.
    Server stores answers and asked_ids.
    """
    # PHASE L2: Handle reserved signals (calibration actions, force insight, capture, go_deeper)
    is_calibration_action = req.signal == "qb_calibration_action"
    is_force_insight = req.signal == "qb_force_insight"
    is_capture = req.signal == "qb_capture"
    is_go_deeper = req.signal == "qb_go_deeper"
    
    if is_calibration_action:
        # Validate calibration action value
        if req.answer not in ["continue", "capture", "go_deeper"]:
            raise HTTPException(status_code=400, detail=f"invalid_calibration_action: {req.answer}")
        # Increment calibration counter (do NOT increment answers_count or store as answer)
        s = store.increment_action_count(req.session_id, req.answer)
        # PHASE L: Update profile after action counter changed
        s = store.update_profile(req.session_id)
        # Do NOT store this signal in s.answers to avoid polluting signals
    elif is_force_insight:
        # PHASE L2: Force insight for testing - accept any answer, do not mutate signals
        # Accept any answer value (typically "test")
        s = store.get(req.session_id)
        if s is None:
            # Auto-create session if missing
            s = store.create()
        # Do NOT store this signal in s.answers to avoid polluting signals
        # Do NOT increment any counters
    elif is_capture:
        # PHASE L2: Capture insight/snapshot - accept any answer, do not mutate signals
        # Require answer to be present
        if not req.answer:
            raise HTTPException(status_code=400, detail="answer required for qb_capture")
        s = store.get(req.session_id)
        if s is None:
            # Auto-create session if missing
            s = store.create()
        # Ensure captures list exists
        if not hasattr(s, 'captures') or s.captures is None:
            s.captures = []
        # Do NOT store this signal in s.answers to avoid polluting signals
        # Increment capture_count for calibration
        store.increment_action_count(req.session_id, "capture")
        # PHASE L: Update profile after action counter changed
        s = store.update_profile(req.session_id)
    elif is_go_deeper:
        # PHASE L2: Go deeper - force one question from same domain if possible
        if not req.answer:
            raise HTTPException(status_code=400, detail="answer required for qb_go_deeper")
        s = store.get(req.session_id)
        if s is None:
            # Auto-create session if missing
            s = store.create()
        # Increment go_deeper_count for calibration
        store.increment_action_count(req.session_id, "go_deeper")
        # PHASE L: Update profile after action counter changed
        s = store.update_profile(req.session_id)
        # Do NOT store this signal in s.answers to avoid polluting signals
    else:
        # Normal signal validation
        try:
            validate_signal_exists(req.signal, _signal_set)
            validate_answer_value(req.answer)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        s = store.upsert_answer(req.session_id, req.signal, req.answer)
        
        # PHASE L1: Increment answers_count on successful answer (not for calibration actions or force insight)
        store.increment_answers_count(req.session_id)
        
        # PHASE L1: Increment action counter if action is provided (legacy support)
        if req.action and req.action in ["continue", "capture", "go_deeper"]:
            store.increment_action_count(req.session_id, req.action)
        
        # PHASE L: Update profile after counters changed
        store.update_profile(req.session_id)

    depth_mode = req.depth_mode or "normal"
    thinking_mode_val = req.thinking_mode or "structured"
    
    # PHASE J: Get thinking mode policy parameters
    thinking_policy = get_thinking_mode_policy(thinking_mode_val)
    insight_threshold_level = thinking_policy["insight_threshold"]
    insight_signal_threshold = get_insight_signal_threshold(insight_threshold_level)
    insight_interval_multiplier = get_insight_interval_multiplier(insight_threshold_level)
    
    # PHASE K/R v0.2: Re-fetch session to ensure we have latest state (including last_insight_at)
    s = store.get(req.session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    
    calibration = {
        "continue_count": s.continue_count,
        "capture_count": s.capture_count,
        "go_deeper_count": s.go_deeper_count,
        "answers_count": s.answers_count,
    }
    
    # Insight Loop v0.1: track signal counts and generate insight (skip calibration actions, force insight, and capture)
    insight_text: Optional[str] = None
    suggest_actions: Optional[List[str]] = None
    # PHASE K/R v0.2 Step 5: Track if signal-based insight was shown (to prevent double insight)
    did_signal_insight = False
    # PHASE R v0.2 Step 4: Debug explanation for insight reason
    insight_debug: Optional[str] = None
    is_debug = debug and debug != 0
    
    if is_calibration_action:
        # PHASE L2: Always return insight and suggest for calibration actions
        insight_text = "Ок. Калибровка принята."
        suggest_actions = ["continue", "capture", "go_deeper"]
        # Store last_insight for capture
        s.last_insight = insight_text
        s.touch()
    elif is_force_insight:
        # PHASE L2: Always return insight and suggest for force insight (testing)
        # Set placeholder, will be filled after we get engine output
        suggest_actions = ["continue", "capture", "go_deeper"]
    elif is_capture:
        # PHASE L2: Capture will set insight after snapshot is built
        # Skip signal count tracking
        pass
    elif is_go_deeper:
        # PHASE L2: Go deeper will set insight and force question after engine output
        # Skip signal count tracking
        pass
    else:
        # PHASE K/R v0.2: Update signal counts through store method to ensure persistence
        s = store.update_signal_counts(req.session_id, req.signal)
        
        # PHASE K/R v0.2: Generate insight if signal count >= threshold AND both cooldowns expired AND not first answer
        now = time.time()
        # Global cooldown check
        global_cooldown_ok = (
            s.last_insight_at is None or 
            (now - s.last_insight_at) >= INSIGHT_COOLDOWN_SEC
        )
        # Per-signal cooldown check
        last_signal_insight = s.last_insight_by_signal.get(req.signal)
        signal_cooldown_ok = (
            last_signal_insight is None or
            (now - last_signal_insight) >= INSIGHT_SIGNAL_COOLDOWN_SEC
        )
        # PHASE K/R v0.2 Step 3: Anti-reactive - require at least 2 answers before showing signal-based insight
        has_enough_answers = s.answers_count >= 2
        
        if s.signal_counts[req.signal] >= insight_signal_threshold and global_cooldown_ok and signal_cooldown_ok and has_enough_answers:
            # Generate insight text based on thinking_mode
            insight_text = generate_insight_text(req.signal, thinking_mode_val)
            suggest_actions = ["continue", "capture", "go_deeper"]
            did_signal_insight = True  # PHASE K/R v0.2 Step 5: Mark that signal-based insight was shown
            # PHASE R v0.2 Step 4: Set debug explanation
            if is_debug:
                insight_debug = f"signal:{req.signal}"
            # PHASE K/R v0.2: Update both global and per-signal cooldown timestamps
            s = store.set_last_insight_at(req.session_id, now)
            s = store.set_last_insight_by_signal(req.session_id, req.signal, now)
            s = store.set_last_insight(req.session_id, insight_text)
    
    # Silent mode: return empty questions immediately
    if depth_mode == "silent":
        out = run_engine(
            s.answers,
            asked_ids=s.asked_ids,
            asked_at=s.asked_at,
            domain_last_asked_at=s.domain_last_asked_at,
            answered_at=s.answered_at,
            depth_mode=depth_mode,
            calibration=calibration,
        )
        out.next_questions = []
    else:
        out = run_engine(
            s.answers,
            asked_ids=s.asked_ids,
            asked_at=s.asked_at,
            domain_last_asked_at=s.domain_last_asked_at,
            answered_at=s.answered_at,
            depth_mode=depth_mode,
            calibration=calibration,
        )
        
        # PHASE L2: Special handling for go_deeper - force one question immediately
        if is_go_deeper:
            # Force ask_budget to 1 and skip cooldown
            bank = load_bank()
            meta = load_meta()
            decay_res = apply_decay(s.answers, s.answered_at)
            rr = resolve(decay_res.filtered_answers, meta["collisions"])
            decision = pick_state(rr.signals, meta["states"], tags=rr.tags)
            
            # Get preferred domain from last question
            prefer_domain = s.last_domain if hasattr(s, 'last_domain') and s.last_domain else None
            
            # Force select exactly one question with domain preference
            selection = select_next_questions(
                bank=bank,
                flow_rules_yaml=meta["flow_rules"],
                decision_mode=decision.mode,
                ask_budget=1,  # Force exactly 1
                forbid_domains=decision.forbid_domains,
                current_answers=rr.signals,
                asked_ids=s.asked_ids,
                asked_at=s.asked_at,
                domain_last_asked_at=s.domain_last_asked_at,
                tags=decision.tags,
                depth_mode=depth_mode,
                calibration_applied=True,  # Skip depth_mode adjustment
                prefer_domain=prefer_domain,
            )
            
            # Override questions
            out.next_questions = [
                {"id": q.id, "signal": q.signal, "domain": q.domain, "question": q.question, "answers": list(q.answers)}
                for q in selection.questions
            ]
            
            # Set insight and suggest
            insight_text = "Ок, копаем."
            suggest_actions = ["continue", "capture"]
        else:
            # Cooldown check: apply depth_mode and profile-based cooldown (skip for go_deeper)
            cooldown_sec = get_cooldown_sec(depth_mode, out.calibration_profile)
            now = time.time()
            if s.last_asked_at is not None and (now - s.last_asked_at) < cooldown_sec:
                out.next_questions = []
            else:
                # Update last_asked_at when actually showing questions
                if out.next_questions:
                    store.set_last_asked_at(req.session_id, now)
    
    asked_now = [q["id"] for q in out.next_questions]
    asked_domains_now = [q["domain"] for q in out.next_questions]
    store.mark_asked(req.session_id, asked_now)
    store.mark_domain_asked(req.session_id, asked_domains_now)
    
    # PHASE L2: Update last_domain and last_question_id when questions are served
    if out.next_questions:
        # Update session's last_domain and last_question_id
        last_q = out.next_questions[0]
        s.last_domain = last_q.get("domain")
        s.last_question_id = last_q.get("id")
        s.touch()

    qb_ctx = build_qb_context(
        state_id=out.state_id,
        mode=out.mode,
        tags=out.tags,
        signals=s.answers,
        ask_budget=out.ask_budget,
        forbid_domains=out.forbid_domains,
        forbid_actions=out.forbid_actions,
        thinking_mode=thinking_mode_val,
    )
    snap = build_snapshot(out.mode, out.state_id, out.tags, s.answers)
    score = compute_score(out.state_id, out.mode, out.tags, s.answers)
    preamble = build_chat_preamble(qb_ctx.to_dict())

    # PHASE R v0.3 Step 1.1: Log pattern occurrences independent of insight cooldowns
    # PHASE R v0.3 Step 1.2: Compute pattern_key from signals (stable), not from snapshot.chips
    # This happens ALWAYS when we have signals, not dependent on insight_text
    now = time.time()
    pattern_key = _compute_pattern_key_from_signals(s.answers)
    if pattern_key:
        s = store.add_pattern_occurrence(req.session_id, pattern_key, now)

    # AUTO INSIGHT: Deterministic insight based on depth_mode, answers_count, and insight_threshold
    # Only for normal answers (not calibration_action, force_insight, capture, go_deeper)
    # PHASE K/R v0.2 Step 5: Skip AUTO insight if signal-based insight was already shown
    if not is_calibration_action and not is_force_insight and not is_capture and not is_go_deeper and not did_signal_insight:
        # Define intervals by depth_mode
        intervals = {
            "silent": 999999,  # Never
            "normal": 10,
            "deep": 5,
            "giga": 3,
        }
        base_interval = intervals.get(depth_mode, 10)
        
        # PHASE J: Apply insight_threshold multiplier to interval
        interval = int(base_interval * insight_interval_multiplier)
        if interval < 1:
            interval = 1
        # PHASE K/R v0.2 Step 4: Enforce minimum interval to prevent spam
        interval = max(interval, AUTO_INSIGHT_MIN_INTERVAL)
        
        # Check if we should emit insight
        n = s.answers_count
        signals_count = snap.get("signals_count", 0)
        
        if interval > 0 and n > 0 and n % interval == 0 and signals_count > 0:
            # Generate short pattern insight
            if not insight_text:  # Don't override existing insight
                insight_text = generate_short_pattern_insight(snap, s.answers, thinking_mode_val)
                suggest_actions = ["continue", "capture", "go_deeper"]
                # PHASE R v0.2 Step 4: Set debug explanation for AUTO insight
                if is_debug:
                    insight_debug = f"auto:interval={interval},answers_count={n}"
                # Store last_insight for capture
                s.last_insight = insight_text
                s.touch()

    # PHASE L2: Build insight text for force_insight after we have engine output
    if is_force_insight and not insight_text:
        # Build insight with optional debug info in DEV mode
        is_dev = os.getenv("ENV") == "dev" or os.getenv("DEBUG") == "1"
        if is_dev:
            signals_count = len(s.answers)
            insight_text = f"Тестовый инсайт: вижу текущий паттерн (state_id={out.state_id}, signals={signals_count}, profile={out.calibration_profile}). Выбирай действие."
        else:
            insight_text = "Тестовый инсайт: вижу текущий паттерн. Выбирай действие."
        # PHASE R v0.2 Step 4: Set debug explanation for force_insight
        if is_debug:
            insight_debug = "forced"
        # Store last_insight for capture
        s.last_insight = insight_text
        s.touch()
    
    # PHASE R v0.3 Step 1.1: Historical Pattern Trigger
    # Check historical insight AFTER signal/auto insight is determined, but BEFORE capture logic
    # Historical insight has priority and replaces existing insight_text (or sets it if None)
    # Pattern occurrence was already logged above, now check if historical condition is met
    did_historical = False
    gap_ok = False
    cooldown_ok = False
    occurrences = []
    if pattern_key:  # Check if we have a valid pattern_key (already logged above)
        # Re-fetch session to get updated pattern_history
        s = store.get(req.session_id)
        if s is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        
        occurrences = s.pattern_history.get(pattern_key, [])
        if len(occurrences) >= 2:
            # PHASE R v0.3 Step 1.4: Historical gap should ignore same-cycle duplicates
            # Find previous occurrence that is at least HISTORICAL_MIN_GAP_SEC before last_ts
            last_ts = max(occurrences)
            prev_ts = max((ts for ts in occurrences if ts <= last_ts - HISTORICAL_MIN_GAP_SEC), default=None)
            gap_ok = prev_ts is not None
        
        # Check cooldown (last historical insight) - compute always for debug
        cooldown_ok = (
            s.last_historical_insight_at is None or
            (now - s.last_historical_insight_at) >= HISTORICAL_COOLDOWN_SEC
        )
        
        if len(occurrences) >= 2 and gap_ok and cooldown_ok:
            # Historical insight has priority: replace existing insight_text (or set if None)
            insight_text = "Этот паттерн уже возникал раньше. Похоже, это повторяющееся состояние. Дальше: продолжить / зафиксировать / копать."
            suggest_actions = ["continue", "capture", "go_deeper"]
            did_historical = True
            # Update cooldown timestamp and last_insight
            s = store.set_last_historical_insight_at(req.session_id, now)
            s = store.set_last_insight(req.session_id, insight_text)
            if is_debug:
                insight_debug = f"historical:pattern={pattern_key},occurrences={len(occurrences)}"
    
    # PHASE L2: Handle capture logic after we have snapshot
    captured_item: Optional[Dict[str, Any]] = None
    if is_capture:
        # Ensure captures list exists
        if not hasattr(s, 'captures') or s.captures is None:
            s.captures = []
        
        # Get current timestamp in ISO format
        from datetime import datetime
        now_iso = datetime.utcnow().isoformat() + "Z"
        
        # Build capture item
        captured_item = {
            "ts": now_iso,
            "insight": s.last_insight if s.last_insight else req.answer or "captured",
            "snapshot": snap,
            "signals": dict(s.answers),  # Copy current signals
        }
        
        # Append to captures
        s.captures.append(captured_item)
        s.touch()
        
        # Set confirmation insight
        insight_text = "Сохранено ✓"
        suggest_actions = ["continue", "go_deeper"]
    
    result = {
        "session": {"id": s.id, "answered": len(s.answers), "asked_total": len(s.asked_ids)},
        "state": {"id": out.state_id, "mode": out.mode, "tags": out.tags},
        "constraints": {"ask_budget": out.ask_budget, "forbid_domains": out.forbid_domains, "forbid_actions": out.forbid_actions},
        "questions": out.next_questions,
        "qb_context": qb_ctx.to_dict(),
        "snapshot": snap,
        "expired": out.expired_signals,
        "score": {"total": score.total, "notes": score.notes},
        "chat_preamble": preamble,
        # PHASE L1: Behavioral metrics
        "calibration": {
            "continue_count": s.continue_count,
            "capture_count": s.capture_count,
            "go_deeper_count": s.go_deeper_count,
            "answers_count": s.answers_count,
            "profile": s.profile,  # PHASE L: Profile from session (auto-updated)
        },
    }
    
    # Add insight if generated (always for calibration actions, force_insight, and capture)
    if insight_text:
        result["insight"] = insight_text
        result["suggest"] = suggest_actions or ["continue", "capture", "go_deeper"]
        # PHASE R v0.2 Step 4: Add debug explanation if debug mode enabled
        if is_debug and insight_debug:
            result["insight_debug"] = insight_debug
    
    # PHASE L2: Add captured item if this was a capture action
    if captured_item is not None:
        result["captured"] = captured_item
    
    # Add debug fields for historical patterns (only when debug is enabled)
    if is_debug:
        result["pattern_key"] = pattern_key
        result["pattern_occurrences_count"] = len(occurrences)
        result["historical_gap_ok"] = gap_ok
        result["historical_cooldown_ok"] = cooldown_ok
        result["historical_eligible"] = (len(occurrences) >= 2) and gap_ok and cooldown_ok
        result["historical_last_at"] = getattr(s, 'last_historical_insight_at', None) if pattern_key else None
    
    return result


@router.get("/state")
def qb_state(session_id: str, depth_mode: Optional[str] = None, thinking_mode: Optional[str] = None, force_insight: Optional[int] = None, debug: Optional[int] = None):
    s = store.get(session_id)
    if s is None:
        return {"error": "session_not_found", "session_id": session_id}
    
    depth_mode = depth_mode or "normal"
    
    # PHASE L2: Prepare calibration data
    calibration = {
        "continue_count": s.continue_count,
        "capture_count": s.capture_count,
        "go_deeper_count": s.go_deeper_count,
        "answers_count": s.answers_count,
    }
    
    # PHASE J: Get thinking mode policy for initiative threshold
    thinking_mode_val = thinking_mode or "structured"
    thinking_policy = get_thinking_mode_policy(thinking_mode_val)
    initiative_level = thinking_policy["initiative_level"]
    # PHASE L: Apply profile modifier to initiative threshold
    effective_init_threshold = get_initiative_threshold(initiative_level, INIT_THRESHOLD, s.profile)
    
    # PHASE O: Session-based initiative trigger (now uses thinking_mode policy)
    # Check if initiative should trigger: depth_mode != "silent", answers_count < threshold, not already asked
    initiative_triggered = False
    if depth_mode != "silent" and s.answers_count < effective_init_threshold and not s.initiative_asked:
        initiative_triggered = True
        s.initiative_asked = True
        s.touch()
    
    # Silent mode: return empty questions immediately
    if depth_mode == "silent":
        out = run_engine(
            s.answers,
            asked_ids=s.asked_ids,
            asked_at=s.asked_at,
            domain_last_asked_at=s.domain_last_asked_at,
            answered_at=s.answered_at,
            depth_mode=depth_mode,
            calibration=calibration,
            thinking_mode=thinking_mode_val,
        )
        out.next_questions = []
    else:
        out = run_engine(
            s.answers,
            asked_ids=s.asked_ids,
            asked_at=s.asked_at,
            domain_last_asked_at=s.domain_last_asked_at,
            answered_at=s.answered_at,
            depth_mode=depth_mode,
            calibration=calibration,
            thinking_mode=thinking_mode_val,
        )
        
        # PHASE O: If initiative triggered, override with canonical first question
        if initiative_triggered:
            # Find question from bank using canonical signal, or use fallback
            from .question_bank.constants import CANONICAL_FIRST_QUESTION_SIGNAL, CANONICAL_FIRST_QUESTION_TEXT
            canonical_q = None
            for q in _bank.questions:
                if q.signal == CANONICAL_FIRST_QUESTION_SIGNAL:
                    canonical_q = {
                        "id": q.id,
                        "signal": q.signal,
                        "domain": q.domain,
                        "question": CANONICAL_FIRST_QUESTION_TEXT,  # Override with canonical text
                        "answers": list(q.answers)
                    }
                    break
            
            # Fallback: if question not found, create minimal question structure
            if not canonical_q:
                canonical_q = {
                    "id": "Q-INIT-001",
                    "signal": CANONICAL_FIRST_QUESTION_SIGNAL,
                    "domain": "energy_state",
                    "question": CANONICAL_FIRST_QUESTION_TEXT,
                    "answers": ["yes", "no"]
                }
            
            # Use canonical first question
            out.next_questions = [canonical_q]
            # Mark as asked
            store.mark_asked(session_id, [canonical_q["id"]])
            store.set_last_asked_at(session_id, time.time())
        else:
            # Cooldown check: apply depth_mode and profile-based cooldown
            cooldown_sec = get_cooldown_sec(depth_mode, out.calibration_profile)
            now = time.time()
            if s.last_asked_at is not None and (now - s.last_asked_at) < cooldown_sec:
                out.next_questions = []
            else:
                # Update last_asked_at when actually showing questions
                if out.next_questions:
                    store.set_last_asked_at(session_id, now)
    
    thinking_mode_val = thinking_mode or "structured"
    qb_ctx = build_qb_context(
        state_id=out.state_id,
        mode=out.mode,
        tags=out.tags,
        signals=s.answers,
        ask_budget=out.ask_budget,
        forbid_domains=out.forbid_domains,
        forbid_actions=out.forbid_actions,
        thinking_mode=thinking_mode_val,
    )
    snap = build_snapshot(out.mode, out.state_id, out.tags, s.answers)
    score = compute_score(out.state_id, out.mode, out.tags, s.answers)
    preamble = build_chat_preamble(qb_ctx.to_dict())
    result = {
        "session": {"id": s.id, "answered": len(s.answers), "asked_total": len(s.asked_ids)},
        "state": {"id": out.state_id, "mode": out.mode, "tags": out.tags},
        "constraints": {"ask_budget": out.ask_budget, "forbid_domains": out.forbid_domains, "forbid_actions": out.forbid_actions},
        "questions": out.next_questions,
        "answers": s.answers,
        "qb_context": qb_ctx.to_dict(),
        "snapshot": snap,
        "expired": out.expired_signals,
        "score": {"total": score.total, "notes": score.notes},
        "chat_preamble": preamble,
        # PHASE L1: Behavioral metrics
        "calibration": {
            "continue_count": s.continue_count,
            "capture_count": s.capture_count,
            "go_deeper_count": s.go_deeper_count,
            "answers_count": s.answers_count,
            "profile": s.profile,  # PHASE L: Profile from session (auto-updated)
        },
    }
    
    # PHASE R v0.2 FIX: Support force_insight query param - use real AUTO/pattern insight
    is_debug = debug and debug != 0
    if force_insight and force_insight != 0:
        # Generate real pattern insight instead of test stub
        result["insight"] = generate_short_pattern_insight(snap, s.answers, thinking_mode_val)
        result["suggest"] = ["continue", "capture", "go_deeper"]
        # PHASE R v0.2 Step 4: Add debug explanation for force_insight
        if is_debug:
            result["insight_debug"] = "forced"
    
    return result


@router.post("/action")
def qb_action(req: QBActionRequest):
    """
    PHASE L2.4: Handle calibration actions (continue/capture/go_deeper).
    Returns same response shape as /qb/answer.
    - continue: close insight, go idle (questions=[])
    - capture: store capture, close insight, go idle (questions=[])
    - go_deeper: close insight AND immediately return 1 next question
    """
    # Validate action
    if req.action not in ["continue", "capture", "go_deeper"]:
        raise HTTPException(status_code=400, detail=f"invalid_action: {req.action}")
    
    s = store.get(req.session_id)
    if s is None:
        return {"error": "session_not_found", "session_id": req.session_id}
    
    # Increment calibration counter
    store.increment_action_count(req.session_id, req.action)
    # PHASE L: Update profile after action counter changed
    s = store.update_profile(req.session_id)
    
    depth_mode = "normal"  # Default, could be made configurable
    thinking_mode_val = "structured"
    
    calibration = {
        "continue_count": s.continue_count,
        "capture_count": s.capture_count,
        "go_deeper_count": s.go_deeper_count,
        "answers_count": s.answers_count,
    }
    
    # Run engine to get current state
    out = run_engine(
        s.answers,
        asked_ids=s.asked_ids,
        asked_at=s.asked_at,
        domain_last_asked_at=s.domain_last_asked_at,
        answered_at=s.answered_at,
        depth_mode=depth_mode,
        calibration=calibration,
        thinking_mode=thinking_mode_val,
    )
    
    # PHASE L2.4: Handle go_deeper - select exactly 1 question immediately
    if req.action == "go_deeper":
        # Force ask_budget to 1 and skip cooldown
        bank = load_bank()
        meta = load_meta()
        decay_res = apply_decay(s.answers, s.answered_at)
        rr = resolve(decay_res.filtered_answers, meta["collisions"])
        decision = pick_state(rr.signals, meta["states"], tags=rr.tags)
        
        # Get preferred domain from last question
        prefer_domain = s.last_domain if hasattr(s, 'last_domain') and s.last_domain else None
        
        # Force select exactly one question with domain preference
        selection = select_next_questions(
            bank=bank,
            flow_rules_yaml=meta["flow_rules"],
            decision_mode=decision.mode,
            ask_budget=1,  # Force exactly 1
            forbid_domains=decision.forbid_domains,
            current_answers=rr.signals,
            asked_ids=s.asked_ids,
            asked_at=s.asked_at,
            domain_last_asked_at=s.domain_last_asked_at,
            tags=decision.tags,
            depth_mode=depth_mode,
            calibration_applied=True,  # Skip depth_mode adjustment
            prefer_domain=prefer_domain,
        )
        
        # Override questions with exactly 1 question
        out.next_questions = [
            {"id": q.id, "signal": q.signal, "domain": q.domain, "question": q.question, "answers": list(q.answers)}
            for q in selection.questions
        ]
        
        # Mark as asked
        asked_now = [q["id"] for q in out.next_questions]
        asked_domains_now = [q["domain"] for q in out.next_questions]
        store.mark_asked(req.session_id, asked_now)
        store.mark_domain_asked(req.session_id, asked_domains_now)
        
        # Update last_domain and last_question_id
        if out.next_questions:
            last_q = out.next_questions[0]
            s.last_domain = last_q.get("domain")
            s.last_question_id = last_q.get("id")
            s.touch()
        
        # Set insight and suggest
        insight_text = "Ок, копаем."
        suggest_actions = ["continue", "capture"]
    elif req.action == "capture":
        # PHASE L2.4: Handle capture - store capture, then go idle
        # Ensure captures list exists
        if not hasattr(s, 'captures') or s.captures is None:
            s.captures = []
        
        # Return empty questions and confirmation
        out.next_questions = []
        insight_text = "Сохранено ✓"
        suggest_actions = ["continue", "go_deeper"]
    else:  # continue
        # PHASE L2.4: Handle continue - close insight, go idle
        out.next_questions = []
        insight_text = None  # No insight, just close
        suggest_actions = []
    
    # Build response
    qb_ctx = build_qb_context(
        state_id=out.state_id,
        mode=out.mode,
        tags=out.tags,
        signals=s.answers,
        ask_budget=out.ask_budget,
        forbid_domains=out.forbid_domains,
        forbid_actions=out.forbid_actions,
        thinking_mode=thinking_mode_val,
    )
    snap = build_snapshot(out.mode, out.state_id, out.tags, s.answers)
    score = compute_score(out.state_id, out.mode, out.tags, s.answers)
    preamble = build_chat_preamble(qb_ctx.to_dict())
    
    result = {
        "session": {"id": s.id, "answered": len(s.answers), "asked_total": len(s.asked_ids)},
        "state": {"id": out.state_id, "mode": out.mode, "tags": out.tags},
        "constraints": {"ask_budget": out.ask_budget, "forbid_domains": out.forbid_domains, "forbid_actions": out.forbid_actions},
        "questions": out.next_questions,
        "qb_context": qb_ctx.to_dict(),
        "snapshot": snap,
        "expired": out.expired_signals,
        "score": {"total": score.total, "notes": score.notes},
        "chat_preamble": preamble,
        "calibration": {
            "continue_count": s.continue_count,
            "capture_count": s.capture_count,
            "go_deeper_count": s.go_deeper_count,
            "answers_count": s.answers_count,
            "profile": out.calibration_profile,
        },
    }
    
    # PHASE L2.4: Add insight and suggest only if set
    if insight_text:
        result["insight"] = insight_text
        result["suggest"] = suggest_actions
    
    # PHASE L2.4: Add captured item if this was a capture action
    if req.action == "capture":
        from datetime import datetime
        now_iso = datetime.utcnow().isoformat() + "Z"
        captured_item = {
            "ts": now_iso,
            "insight": s.last_insight if s.last_insight else "captured",
            "snapshot": snap,
            "signals": dict(s.answers),
        }
        # Append to captures
        if not hasattr(s, 'captures') or s.captures is None:
            s.captures = []
        s.captures.append(captured_item)
        s.touch()
        result["captured"] = captured_item
    
    return result


@router.post("/reset")
def qb_reset(session_id: str, depth_mode: Optional[str] = None, thinking_mode: Optional[str] = None):
    s = store.reset(session_id)
    if s is None:
        return {"error": "session_not_found", "session_id": session_id}
    depth_mode = depth_mode or "normal"
    thinking_mode_val = thinking_mode or "structured"
    
    # PHASE L2: Prepare calibration data (should be zeros after reset)
    calibration = {
        "continue_count": s.continue_count,
        "capture_count": s.capture_count,
        "go_deeper_count": s.go_deeper_count,
        "answers_count": s.answers_count,
    }
    
    out = run_engine(
        s.answers,
        asked_ids=s.asked_ids,
        asked_at=s.asked_at,
        domain_last_asked_at=s.domain_last_asked_at,
        answered_at=s.answered_at,
        depth_mode=depth_mode,
        calibration=calibration,
        thinking_mode=thinking_mode_val,
    )
    
    # Cooldown check: apply depth_mode and profile-based cooldown
    cooldown_sec = get_cooldown_sec(depth_mode, out.calibration_profile)
    now = time.time()
    if s.last_asked_at is not None and (now - s.last_asked_at) < cooldown_sec:
        out.next_questions = []
    else:
        # Update last_asked_at when actually showing questions
        if out.next_questions:
            store.set_last_asked_at(session_id, now)
    
    asked_now = [q["id"] for q in out.next_questions]
    asked_domains_now = [q["domain"] for q in out.next_questions]
    store.mark_asked(session_id, asked_now)
    store.mark_domain_asked(session_id, asked_domains_now)
    qb_ctx = build_qb_context(
        state_id=out.state_id,
        mode=out.mode,
        tags=out.tags,
        signals=s.answers,
        ask_budget=out.ask_budget,
        forbid_domains=out.forbid_domains,
        forbid_actions=out.forbid_actions,
        thinking_mode=thinking_mode_val,
    )
    snap = build_snapshot(out.mode, out.state_id, out.tags, s.answers)
    score = compute_score(out.state_id, out.mode, out.tags, s.answers)
    preamble = build_chat_preamble(qb_ctx.to_dict())
    return {
        "session": {"id": s.id, "answered": 0, "asked_total": len(s.asked_ids)},
        "state": {"id": out.state_id, "mode": out.mode, "tags": out.tags},
        "constraints": {"ask_budget": out.ask_budget, "forbid_domains": out.forbid_domains, "forbid_actions": out.forbid_actions},
        "questions": out.next_questions,
        "qb_context": qb_ctx.to_dict(),
        "snapshot": snap,
        "expired": out.expired_signals,
        "score": {"total": score.total, "notes": score.notes},
        "chat_preamble": preamble,
        # PHASE L1: Behavioral metrics
        "calibration": {
            "continue_count": s.continue_count,
            "capture_count": s.capture_count,
            "go_deeper_count": s.go_deeper_count,
            "answers_count": s.answers_count,
            "profile": s.profile,  # PHASE L: Profile from session (auto-updated)
        },
    }

@router.get("/snapshot")
def qb_snapshot(session_id: str, depth_mode: Optional[str] = None):
    s = store.get(session_id)
    if s is None:
        return {"error": "session_not_found", "session_id": session_id}
    # Snapshot endpoint doesn't need calibration, pass None
    # Default to "structured" thinking_mode for snapshot
    out = run_engine(
        s.answers,
        asked_ids=s.asked_ids,
        asked_at=s.asked_at,
        domain_last_asked_at=s.domain_last_asked_at,
        answered_at=s.answered_at,
        depth_mode=depth_mode,
        calibration=None,
        thinking_mode="structured",
    )
    return build_snapshot(out.mode, out.state_id, out.tags, s.answers)


class QBCheckinRequest(BaseModel):
    session_id: str
    date: str  # "YYYY-MM-DD" from UI in user's timezone

@router.post("/checkin")
def qb_checkin(req: QBCheckinRequest):
    s = store.get(req.session_id)
    if s is None:
        return {"error": "session_not_found", "session_id": req.session_id}
    store.set_checkin_date(req.session_id, req.date)
    return {"session_id": req.session_id, "last_checkin_date": req.date}

@router.get("/checkin/status")
def qb_checkin_status(session_id: str, today: str):
    s = store.get(session_id)
    if s is None:
        return {"error": "session_not_found", "session_id": session_id}
    done = (s.last_checkin_date == today)
    return {"session_id": session_id, "today": today, "last_checkin_date": s.last_checkin_date, "done": done}
