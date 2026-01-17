from __future__ import annotations
from typing import Optional, Any

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

# PHASE O: Initiative trigger threshold
INIT_THRESHOLD = 5  # answers_count must be < this for initiative to trigger

# PHASE K/R v0.2: Insight cooldown (seconds)
INSIGHT_COOLDOWN_SEC = 60  # Cooldown between signal-based insights (global)
INSIGHT_SIGNAL_COOLDOWN_SEC = 300  # Cooldown per signal (5 minutes)
# PHASE K/R v0.2 Step 4: Minimum interval for AUTO INSIGHT (anti-spam)
AUTO_INSIGHT_MIN_INTERVAL = 3  # Minimum answers_count interval for AUTO insight

# PHASE R v0.3: Historical pattern trigger constants
# Note: Set to small values (10 seconds) for local testing
HISTORICAL_MIN_GAP_SEC = 86400  # 24h - minimum time between first and second occurrence
HISTORICAL_COOLDOWN_SEC = 86400  # 24h - cooldown between historical insights

# PHASE O: Canonical first question (used when initiative triggers)
# Uses existing signal from bank to avoid adding new signals
CANONICAL_FIRST_QUESTION_SIGNAL = "baseline_energy"  # Q-ES-001 from core.yaml
CANONICAL_FIRST_QUESTION_TEXT = "Ты сейчас больше уставший, чем собранный?"

# PHASE J: Thinking mode policy mapping
# Maps thinking_mode to behavioral parameters: initiative_level, insight_threshold
# Note: ask_budget is NOT used from thinking_mode (depth_mode controls ask_budget instead)
# ask_budget values are kept in the table for potential future use
THINKING_MODE_POLICY: dict[str, dict[str, Any]] = {
    "analytical": {
        "ask_budget": 1,
        "initiative_level": "low",
        "insight_threshold": "high",
    },
    "structured": {
        "ask_budget": 2,
        "initiative_level": "medium",
        "insight_threshold": "medium",
    },
    "wide": {
        "ask_budget": 3,
        "initiative_level": "medium",
        "insight_threshold": "low",
    },
    "hard": {
        "ask_budget": 2,
        "initiative_level": "high",
        "insight_threshold": "low",
    },
    "exploratory": {
        "ask_budget": 1,
        "initiative_level": "low",
        "insight_threshold": "medium",
    },
}

def get_thinking_mode_policy(thinking_mode: Optional[str] = None) -> dict[str, Any]:
    """
    Get policy parameters for a thinking_mode.
    
    Args:
        thinking_mode: One of: analytical, structured, wide, hard, exploratory
        
    Returns:
        dict with keys: ask_budget (int), initiative_level (str), insight_threshold (str)
        Defaults to "structured" if mode is unknown or None.
    """
    mode = (thinking_mode or "structured").lower().strip()
    if mode not in THINKING_MODE_POLICY:
        mode = "structured"
    return THINKING_MODE_POLICY[mode].copy()

def get_initiative_threshold(initiative_level: str, base_threshold: int = INIT_THRESHOLD, profile: Optional[str] = None) -> int:
    """
    Get initiative threshold based on initiative_level and profile.
    
    Args:
        initiative_level: "low", "medium", or "high" (from thinking_mode)
        base_threshold: Base threshold (default: INIT_THRESHOLD = 5)
        profile: Personal calibration profile "push"|"balanced"|"gentle"|"base" (optional)
        
    Returns:
        Adjusted threshold:
        - thinking_mode low: base_threshold * 2 (less frequent initiative)
        - thinking_mode medium: base_threshold (default)
        - thinking_mode high: base_threshold // 2 (more frequent initiative)
        - profile gentle: additional * 1.5 (even less frequent)
        - profile push: additional * 0.7 (even more frequent)
    """
    # First apply thinking_mode modifier
    if initiative_level == "low":
        threshold = base_threshold * 2
    elif initiative_level == "high":
        threshold = max(1, base_threshold // 2)
    else:  # medium
        threshold = base_threshold
    
    # PHASE L: Apply profile modifier
    if profile == "gentle":
        threshold = int(threshold * 1.5)  # Less frequent initiative
    elif profile == "push":
        threshold = max(1, int(threshold * 0.7))  # More frequent initiative
    
    return threshold

def get_insight_signal_threshold(insight_threshold: str) -> int:
    """
    Get signal count threshold for insight generation.
    
    Args:
        insight_threshold: "low", "medium", or "high"
        
    Returns:
        Signal count threshold:
        - low: 1 (insights appear more frequently)
        - medium: 2 (default)
        - high: 3 (insights appear less frequently)
    """
    if insight_threshold == "low":
        return 1
    elif insight_threshold == "high":
        return 3
    else:  # medium
        return 2

def get_insight_interval_multiplier(insight_threshold: str) -> float:
    """
    Get multiplier for insight interval (used in AUTO INSIGHT logic).
    
    Args:
        insight_threshold: "low", "medium", or "high"
        
    Returns:
        Multiplier:
        - low: 0.5 (insights appear more frequently)
        - medium: 1.0 (default)
        - high: 2.0 (insights appear less frequently)
    """
    if insight_threshold == "low":
        return 0.5
    elif insight_threshold == "high":
        return 2.0
    else:  # medium
        return 1.0
