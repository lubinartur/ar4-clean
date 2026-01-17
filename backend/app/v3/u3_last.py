import json
import os
from typing import Any, Dict, Optional

LAST_PATH = os.getenv("AIR4_U3_LAST_PATH", "data/v3_u3_last.json")

def _load() -> Dict[str, Any]:
    if not os.path.exists(LAST_PATH):
        return {"q3": None, "r3": None}
    try:
        with open(LAST_PATH, "r", encoding="utf-8") as f:
            obj = json.load(f)
            if "q3" not in obj: obj["q3"] = None
            if "r3" not in obj: obj["r3"] = None
            return obj
    except Exception:
        return {"q3": None, "r3": None}

def _save(obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(LAST_PATH), exist_ok=True)
    with open(LAST_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def set_last(mode: str, label: str) -> None:
    obj = _load()
    if mode not in ("q3", "r3"):
        return
    obj[mode] = label
    _save(obj)

def get_last(mode: str) -> Optional[str]:
    obj = _load()
    if mode not in ("q3", "r3"):
        return None
    v = obj.get(mode)
    return v if isinstance(v, str) and v else None
