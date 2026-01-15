from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Any

@dataclass
class ResolveResult:
    signals: Dict[str, str]  # signal -> answer
    tags: List[str]          # collision tags

def apply_collisions(signals: Dict[str, str], collisions_yaml: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    for col in collisions_yaml.get("collisions", []):
        when = col.get("when", {})
        all_req = when.get("all", {})
        ok = True
        for sig, val in all_req.items():
            if signals.get(sig) != val:
                ok = False
                break
        if ok:
            tags.append(col["output"]["tag"])
    return tags

def resolve(signals: Dict[str, str], collisions_yaml: Dict[str, Any]) -> ResolveResult:
    tags = apply_collisions(signals, collisions_yaml)
    return ResolveResult(signals=signals, tags=tags)
