from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List


@dataclass
class QBContext:
    state_id: str
    mode: str
    tags: List[str]
    signals: Dict[str, str]
    constraints: Dict[str, Any]
    thinking_mode: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": {"id": self.state_id, "mode": self.mode, "tags": self.tags},
            "signals": self.signals,
            "constraints": self.constraints,
            "thinking_mode": self.thinking_mode,
        }

def build_qb_context(
    *,
    state_id: str,
    mode: str,
    tags: List[str],
    signals: Dict[str, str],
    ask_budget: int,
    forbid_domains: List[str],
    forbid_actions: List[str],
    thinking_mode: str = "structured",
) -> QBContext:
    return QBContext(
        state_id=state_id,
        mode=mode,
        tags=tags,
        signals=signals,
        constraints={
            "ask_budget": ask_budget,
            "forbid_domains": forbid_domains,
            "forbid_actions": forbid_actions,
        },
        thinking_mode=thinking_mode,
    )
