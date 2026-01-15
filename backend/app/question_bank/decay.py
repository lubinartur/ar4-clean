from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Any, Optional

# Default decays (seconds)
DEFAULT_DECAY_SEC = 24 * 60 * 60  # 24h fallback

# Per-signal decay overrides (seconds)
SIGNAL_DECAY_SEC: Dict[str, int] = {
    # fast-changing
    "baseline_energy": 6 * 60 * 60,
    "physical_fatigue": 6 * 60 * 60,
    "mental_fatigue": 6 * 60 * 60,
    "sleep_deficit": 12 * 60 * 60,
    "overload_risk": 2 * 60 * 60,
    "emotional_overflow": 2 * 60 * 60,
    "attention_available": 4 * 60 * 60,
    "attention_fragmented": 4 * 60 * 60,
    "execution_ready": 4 * 60 * 60,
    "task_clarity": 8 * 60 * 60,
    "hunger_signal": 2 * 60 * 60,
    "thirst_signal": 2 * 60 * 60,
    "sleepiness": 2 * 60 * 60,
    # slower-changing
    "role_pressure": 7 * 24 * 60 * 60,
    "identity_conflict": 7 * 24 * 60 * 60,
    "self_trust_identity": 14 * 24 * 60 * 60,
}

@dataclass
class DecayResult:
    filtered_answers: Dict[str, str]
    expired: Dict[str, float]  # signal -> age_sec

def apply_decay(
    answers: Dict[str, str],
    answered_at: Dict[str, float],
    now: Optional[float] = None,
) -> DecayResult:
    now = now or time.time()
    out: Dict[str, str] = {}
    expired: Dict[str, float] = {}

    for sig, val in answers.items():
        t = answered_at.get(sig)
        if t is None:
            # if we don't know time, keep it (safe)
            out[sig] = val
            continue
        age = now - t
        decay = SIGNAL_DECAY_SEC.get(sig, DEFAULT_DECAY_SEC)
        if age >= decay:
            expired[sig] = age
        else:
            out[sig] = val
    return DecayResult(filtered_answers=out, expired=expired)
