import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

OVR_PATH = os.getenv("AIR4_V3_OVR_PATH", "data/v3_overrides.json")

@dataclass
class Override:
    label: str
    oid: str
    kind: str          # 'pin' | 'ban' | 'force'
    value: Any         # kind-specific payload
    source: str        # 'user'
    created_ts: int
    updated_ts: int
    active: bool = True

def _load() -> Dict[str, List[Dict[str, Any]]]:
    if not os.path.exists(OVR_PATH):
        return {}
    try:
        with open(OVR_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(OVR_PATH), exist_ok=True)
    with open(OVR_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def set_override(label: str, kind: str, value: Any, source: str = "user") -> Override:
    now = int(time.time())
    oid = f"o_{now}_{abs(hash((label, kind, str(value))))%10000}"
    o = Override(
        label=label,
        oid=oid,
        kind=kind,
        value=value,
        source=source,
        created_ts=now,
        updated_ts=now,
        active=True,
    )
    obj = _load()
    obj.setdefault(label, [])
    obj[label].append(asdict(o))
    _save(obj)
    return o

def list_overrides(label: str, active_only: bool = True) -> List[Override]:
    obj = _load()
    raw = obj.get(label, [])
    out: List[Override] = []
    for r in raw:
        if active_only and not r.get("active", True):
            continue
        out.append(Override(**r))
    return out

def get_active(label: str, kind: Optional[str] = None) -> List[Override]:
    xs = list_overrides(label, active_only=True)
    if kind:
        xs = [o for o in xs if o.kind == kind]
    return xs

def deactivate_override(label: str, oid: str) -> bool:
    obj = _load()
    if label not in obj:
        return False
    ok = False
    for r in obj[label]:
        if r.get("oid") == oid:
            r["active"] = False
            r["updated_ts"] = int(time.time())
            ok = True
    if ok:
        _save(obj)
    return ok

def clear_label(label: str) -> None:
    obj = _load()
    if label in obj:
        del obj[label]
        _save(obj)

def is_banned(label: str) -> bool:
    return len(get_active(label, kind="ban")) > 0

def is_pinned(label: str) -> bool:
    return len(get_active(label, kind="pin")) > 0

def get_force(label: str) -> list[Override]:
    return get_active(label, kind="force")

def _merge_force_rules(label: str) -> dict:
    # if multiple force overrides exist, last one wins per key
    rules: dict = {}
    xs = get_force(label)
    for o in xs:
        if isinstance(o.value, dict):
            for k, v in o.value.items():
                rules[k] = v
    return rules

def force_mode_only(label: str) -> str | None:
    rules = _merge_force_rules(label)
    v = rules.get("mode_only")
    return v if v in ("q3", "r3") else None

def force_max_per_window(label: str) -> dict | None:
    rules = _merge_force_rules(label)
    v = rules.get("max_per_window")
    if not isinstance(v, dict):
        return None
    try:
        days = int(v.get("days"))
        count = int(v.get("count"))
        if days <= 0 or count <= 0:
            return None
        return {"days": days, "count": count}
    except Exception:
        return None
