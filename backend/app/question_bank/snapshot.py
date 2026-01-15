from __future__ import annotations

from typing import Dict, Any, List

# UI-friendly compact snapshot.

def build_snapshot(mode: str, state_id: str, tags: List[str], signals: Dict[str, str]) -> Dict[str, Any]:
    def yn(sig: str) -> str:
        v = signals.get(sig)
        return v if v in ("yes", "no") else "unknown"

    # Minimal readable set (don't bloat UI)
    return {
        "state": {"id": state_id, "mode": mode, "tags": tags},
        "chips": [
            {"k": "energy", "v": yn("baseline_energy")},
            {"k": "overload", "v": yn("overload_risk")},
            {"k": "focus", "v": yn("attention_available")},
            {"k": "emotion_load", "v": yn("emotional_load_present")},
            {"k": "overflow", "v": yn("emotional_overflow")},
            {"k": "ready", "v": yn("execution_ready")},
            {"k": "clarity", "v": yn("task_clarity")},
        ],
        "signals_count": len(signals),
    }
