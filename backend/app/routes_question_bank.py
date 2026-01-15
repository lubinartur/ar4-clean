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

router = APIRouter(prefix="/qb", tags=["question_bank"])

_bank = load_bank()
_signal_set = set([q.signal for q in _bank.questions])

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
    out = run_engine(req.answers, asked_ids=[], asked_at={}, domain_last_asked_at={}, answered_at={}, calibration=None)
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
def qb_answer(req: QBAnswerRequest):
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
        # Re-fetch to get updated counter
        s = store.get(req.session_id)
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
        # Re-fetch to get updated counter
        s = store.get(req.session_id)
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

    depth_mode = req.depth_mode or "normal"
    thinking_mode_val = req.thinking_mode or "structured"
    
    # PHASE L2: Re-fetch session after capture/go_deeper to get updated counters
    if is_capture or is_go_deeper:
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
        s.signal_counts[req.signal] = s.signal_counts.get(req.signal, 0) + 1
        s.touch()  # Update session timestamp
        
        # Generate insight if: signal appears >= 2 times AND no insight shown yet in this session
        if s.signal_counts[req.signal] >= 2 and s.last_insight_at is None:
            # Generate insight text based on thinking_mode
            insight_text = generate_insight_text(req.signal, thinking_mode_val)
            suggest_actions = ["continue", "capture", "go_deeper"]
            s.last_insight_at = time.time()
            # PHASE L2: Store last_insight for capture
            s.last_insight = insight_text
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

    # AUTO INSIGHT: Deterministic insight based on depth_mode and answers_count
    # Only for normal answers (not calibration_action, force_insight, capture, go_deeper)
    if not is_calibration_action and not is_force_insight and not is_capture and not is_go_deeper:
        # Define intervals by depth_mode
        intervals = {
            "silent": 999999,  # Never
            "normal": 10,
            "deep": 5,
            "giga": 3,
        }
        interval = intervals.get(depth_mode, 10)
        
        # Check if we should emit insight
        n = s.answers_count
        signals_count = snap.get("signals_count", 0)
        
        if interval > 0 and n > 0 and n % interval == 0 and signals_count > 0:
            # Generate short pattern insight
            if not insight_text:  # Don't override existing insight
                insight_text = generate_short_pattern_insight(snap, s.answers)
                suggest_actions = ["continue", "capture", "go_deeper"]
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
        # Store last_insight for capture
        s.last_insight = insight_text
        s.touch()
    
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
            "profile": out.calibration_profile,  # PHASE L2: Calibration profile for debugging
        },
    }
    
    # Add insight if generated (always for calibration actions, force_insight, and capture)
    if insight_text:
        result["insight"] = insight_text
        result["suggest"] = suggest_actions or ["continue", "capture", "go_deeper"]
    
    # PHASE L2: Add captured item if this was a capture action
    if captured_item is not None:
        result["captured"] = captured_item
    
    return result


@router.get("/state")
def qb_state(session_id: str, depth_mode: Optional[str] = None, thinking_mode: Optional[str] = None, force_insight: Optional[int] = None):
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
            "profile": out.calibration_profile,  # PHASE L2: Calibration profile for debugging
        },
    }
    
    # PHASE L2.2: Support force_insight query param
    if force_insight and force_insight != 0:
        result["insight"] = "Тестовый инсайт: вижу текущий паттерн. Выбирай действие."
        result["suggest"] = ["continue", "capture", "go_deeper"]
    
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
    # Re-fetch to get updated counters
    s = store.get(req.session_id)
    
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
            "profile": out.calibration_profile,  # PHASE L2: Calibration profile for debugging
        },
    }

@router.get("/snapshot")
def qb_snapshot(session_id: str, depth_mode: Optional[str] = None):
    s = store.get(session_id)
    if s is None:
        return {"error": "session_not_found", "session_id": session_id}
    # Snapshot endpoint doesn't need calibration, pass None
    out = run_engine(
        s.answers,
        asked_ids=s.asked_ids,
        asked_at=s.asked_at,
        domain_last_asked_at=s.domain_last_asked_at,
        answered_at=s.answered_at,
        depth_mode=depth_mode,
        calibration=None,
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
