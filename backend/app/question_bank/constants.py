from __future__ import annotations

# Canonical answers used across QB.
YES = "yes"
NO = "no"
LOW = "low"
MID = "mid"
HIGH = "high"

YES_NO = {YES, NO}
TRI_LEVEL = {LOW, MID, HIGH}

ALL_ALLOWED = YES_NO | TRI_LEVEL

# Default cooldowns (seconds)
DEFAULT_Q_COOLDOWN_SEC = 6 * 60 * 60      # 6 hours per question
DEFAULT_DOMAIN_COOLDOWN_SEC = 30 * 60     # 30 minutes per domain

# Modes that should not ask too much
MODE_SAFE_DOMAINS = {
    "stabilize": {"energy_state", "body_physiology", "environment_context", "time_temporal"},
    "contain": {"energy_state", "body_physiology", "environment_context", "time_temporal"},
    "unblock": {"energy_state", "focus_attention", "action_execution", "motivation_drive", "risk_defense", "control_agency_pressure", "time_temporal", "environment_context"},
}
