from __future__ import annotations

from typing import List, Dict, Any

# Minimal onboarding packs (fast scan)
# Goal: determine safe state & whether to execute or stabilize.

ONBOARDING_PACKS: List[Dict[str, Any]] = [
    {
        "id": "OB-1-core_state",
        "name": "Core state scan",
        "signals": [
            "baseline_energy",
            "attention_available",
            "emotional_load_present",
            "emotional_overflow",
            "overload_risk",
            "execution_ready",
            "task_clarity",
        ],
    },
    {
        "id": "OB-2-blockers",
        "name": "Blockers scan",
        "signals": [
            "avoidance_pattern",
            "fear_blocking_action",
            "internal_pressure",
            "external_pressure",
            "time_pressure",
            "sleep_deficit",
            "rest_need",
        ],
    },
    {
        "id": "OB-3-environment_body",
        "name": "Environment & body",
        "signals": [
            "environment_distracting",
            "digital_overload",
            "interruption_risk",
            "tension_body",
            "pain_presence",
            "hunger_signal",
            "thirst_signal",
        ],
    },
]
