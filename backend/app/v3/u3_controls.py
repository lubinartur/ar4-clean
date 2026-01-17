import json
import os
import time
from typing import Any, Dict, Optional

RULES_PATH = os.getenv("AIR4_U3_RULES_PATH", "data/v3_u3_rules.json")

def _load() -> Dict[str, Any]:
    if not os.path.exists(RULES_PATH):
        return {"mute": [], "defer": {}, "allow_only": {}}
    try:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            obj = json.load(f)
            if "mute" not in obj: obj["mute"] = []
            if "defer" not in obj: obj["defer"] = {}
            if "allow_only" not in obj: obj["allow_only"] = {}
            return obj
    except Exception:
        return {"mute": [], "defer": {}, "allow_only": {}}

def _save(obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(RULES_PATH), exist_ok=True)
    with open(RULES_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def mute(label: str) -> None:
    obj = _load()
    if label not in obj["mute"]:
        obj["mute"].append(label)
        _save(obj)

def unmute(label: str) -> None:
    obj = _load()
    if label in obj["mute"]:
        obj["mute"].remove(label)
        _save(obj)

def defer(label: str, until_ts: int) -> None:
    obj = _load()
    obj["defer"][label] = int(until_ts)
    _save(obj)

def clear_defer(label: str) -> None:
    obj = _load()
    if label in obj["defer"]:
        del obj["defer"][label]
        _save(obj)

def allow_only(label: str, mode: Optional[str]) -> None:
    """
    mode: None (remove rule) | 'q3' | 'r3'
    """
    obj = _load()
    if mode is None:
        if label in obj["allow_only"]:
            del obj["allow_only"][label]
    else:
        obj["allow_only"][label] = mode
    _save(obj)

def is_allowed(label: str, mode: str, now_ts: Optional[int] = None) -> bool:
    """
    mode: 'q3' or 'r3'
    Returns False if muted, deferred, or mode-disallowed.
    """
    now = int(now_ts or time.time())
    obj = _load()

    if label in obj.get("mute", []):
        return False

    until = obj.get("defer", {}).get(label)
    if until is not None and now < int(until):
        return False

    only = obj.get("allow_only", {}).get(label)
    if only and only != mode:
        return False

    return True
