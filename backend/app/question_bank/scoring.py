from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Tuple

# Simple, deterministic scoring (0..100)
# Purpose: UI signal + routing hint. Not "truth", just a dashboard gauge.

@dataclass
class Score:
    total: int
    components: Dict[str, int]
    notes: List[str]

def _yn(signals: Dict[str, str], k: str) -> str:
    v = signals.get(k)
    return v if v in ("yes", "no") else "unknown"

def compute_score(state_id: str, mode: str, tags: List[str], signals: Dict[str, str]) -> Score:
    # Base by mode/state (fast route)
    base = 60
    notes: List[str] = []

    if mode == "execution":
        base = 75
    elif mode in ("stabilize", "contain"):
        base = 40
    elif mode in ("unblock", "reframe"):
        base = 55

    # Penalize overload / overflow strongly
    if _yn(signals, "overload_risk") == "yes":
        base -= 25
        notes.append("overload_risk")
    if _yn(signals, "emotional_overflow") == "yes":
        base -= 20
        notes.append("emotional_overflow")
    if _yn(signals, "exhaustion_threshold") == "yes":
        base -= 20
        notes.append("exhaustion_threshold")

    # Reward readiness & clarity
    if _yn(signals, "baseline_energy") == "yes":
        base += 8
    if _yn(signals, "attention_available") == "yes":
        base += 8
    if _yn(signals, "execution_ready") == "yes":
        base += 10
    if _yn(signals, "task_clarity") == "yes":
        base += 10

    # Blockers
    if _yn(signals, "avoidance_pattern") == "yes":
        base -= 8
        notes.append("avoidance")
    if _yn(signals, "fear_blocking_action") == "yes":
        base -= 8
        notes.append("fear_blocking_action")
    if _yn(signals, "time_pressure") == "yes":
        base -= 6
        notes.append("time_pressure")
    if _yn(signals, "sleep_deficit") == "yes":
        base -= 6
        notes.append("sleep_deficit")

    # Tags: small nudges
    if "want_but_avoid" in tags:
        base -= 6
        notes.append("want_but_avoid")
    if "energy_action_mismatch" in tags:
        base -= 6
        notes.append("energy_action_mismatch")
    if "emotion_blind_spot" in tags:
        base -= 4
        notes.append("emotion_blind_spot")

    # Clamp 0..100
    total = max(0, min(100, int(base)))

    # Components are intentionally coarse
    components = {
        "base": int(base),
        "mode_bonus": 0,
    }
    return Score(total=total, components=components, notes=notes)
