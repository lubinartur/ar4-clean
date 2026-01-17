from __future__ import annotations

from typing import Dict, Any, List

"""
QB -> /chat bridge

Goal: /chat changes style & tactics based on QB mode/tags/constraints.
This is the core of "AIR4 is not chat".
"""

def _format_signals(signals: Dict[str, str]) -> str:
    if not signals:
        return "none"
    items = sorted(signals.items(), key=lambda x: x[0])
    return "\n".join([f"- {k}: {v}" for k, v in items])

def build_chat_preamble(qb_context: Dict[str, Any]) -> str:
    state = qb_context.get("state", {}) or {}
    constraints = qb_context.get("constraints", {}) or {}
    signals = qb_context.get("signals", {}) or {}
    thinking_mode = qb_context.get("thinking_mode", "structured")

    state_id = state.get("id", "UNKNOWN")
    mode = state.get("mode", "scan")
    tags = state.get("tags", []) or []

    forbid_actions: List[str] = constraints.get("forbid_actions", []) or []
    forbid_domains: List[str] = constraints.get("forbid_domains", []) or []
    ask_budget = constraints.get("ask_budget", None)

    # Mode directives (tight, tactical)
    mode_directives = {
        "execution": [
            "Do NOT ask questions. Provide next step/checklist.",
            "Be concise. Action-first output.",
        ],
        "stabilize": [
            "Keep it short. Reduce load. Offer 1 simple stabilizing action.",
            "No optimization. No persuasion. No deep reframing.",
        ],
        "contain": [
            "Do NOT rationalize. Validate state. Offer containment + grounding.",
            "No arguing, no productivity pushing.",
        ],
        "unblock": [
            "Focus on removing friction. Suggest micro-action (<=2 minutes).",
            "If avoidance/fear present: choose smallest safe step.",
        ],
        "reframe": [
            "Offer 1 reframing angle. Keep it non-philosophical.",
            "Do not expand. 1-2 short alternatives.",
        ],
        "scan": [
            "If needed ask at most 1 question. Prefer choices/yes-no.",
            "Otherwise propose a simple next move.",
        ],
    }

    lines: List[str] = []
    lines.append("QB_CONTEXT (authoritative):")
    lines.append(f"- state_id: {state_id}")
    lines.append(f"- mode: {mode}")
    lines.append(f"- tags: {tags}")
    if ask_budget is not None:
        lines.append(f"- ask_budget: {ask_budget}")
    if forbid_domains:
        lines.append(f"- forbid_domains: {forbid_domains}")
    if forbid_actions:
        lines.append(f"- forbid_actions: {forbid_actions}")
    lines.append("Signals:")
    lines.append(_format_signals(signals))

    lines.append("")
    lines.append("Mode directives:")
    for d in mode_directives.get(mode, mode_directives["scan"]):
        lines.append(f"- {d}")

    # Hard forbids
    if forbid_actions:
        lines.append("")
        lines.append("Hard forbids (must obey):")
        for a in forbid_actions:
            lines.append(f"- {a}")

    # PHASE Q4: Question style based on thinking_mode
    question_styles = {
        "analytical": "Ask 1 clarifying fact question that reduces uncertainty. Prefer measurable/ конкретный факт.",
        "structured": "Ask 1 question that chooses between 2 options. Prefer A/B.",
        "wide": "Ask 1 question that opens 2-3 possible directions. Prefer 'что из этого ближе: A/B/C'.",
        "hard": "Ask 1 blunt question that forces commitment. Prefer 'что ты выбираешь сейчас: сделать X или признать стоп'.",
        "exploratory": "Ask 1 hypothesis-testing question. Prefer 'если X верно, то... это про тебя сейчас?'",
    }
    
    style_text = question_styles.get(thinking_mode, question_styles["structured"])
    lines.append("")
    lines.append("Question style (1 question max):")
    lines.append(f"- {style_text}")

    return "\n".join(lines).strip()
