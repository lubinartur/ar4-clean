from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

@dataclass
class StateDecision:
    state_id: str
    mode: str
    ask_budget: int
    forbid_domains: List[str]
    forbid_actions: List[str]
    tags: List[str]

def _match_requires(signals: Dict[str, str], requires: Dict[str, str]) -> bool:
    for sig, val in requires.items():
        if signals.get(sig) != val:
            return False
    return True

def _match_requires_any(signals: Dict[str, str], req_any: Dict[str, str]) -> bool:
    for sig, val in req_any.items():
        if signals.get(sig) == val:
            return True
    return False

def pick_state(signals: Dict[str, str], states_yaml: Dict[str, Any], tags: Optional[List[str]] = None) -> StateDecision:
    tags = tags or []
    candidates = states_yaml.get("states", [])
    best = None

    for st in candidates:
        ok = True
        if "requires" in st:
            ok = ok and _match_requires(signals, st["requires"])
        if ok and "requires_any" in st:
            ok = ok and _match_requires_any(signals, st["requires_any"])
        if ok and "forbids" in st:
            for sig, val in st["forbids"].items():
                if signals.get(sig) == val:
                    ok = False
                    break
        if ok:
            if best is None or st.get("priority", 0) > best.get("priority", 0):
                best = st

    if best is None:
        return StateDecision(
            state_id="DEFAULT",
            mode="scan",
            ask_budget=3,
            forbid_domains=[],
            forbid_actions=[],
            tags=tags,
        )

    beh = best.get("behavior", {})
    return StateDecision(
        state_id=best["id"],
        mode=beh.get("mode", "scan"),
        ask_budget=int(beh.get("ask_budget", 3)),
        forbid_domains=list(beh.get("forbid_domains", [])),
        forbid_actions=list(beh.get("forbid_actions", [])),
        tags=tags,
    )
