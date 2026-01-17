import json
import os
import time
from typing import Dict, Optional

TOUCH_PATH = os.getenv("AIR4_S3_TOUCH_PATH", "data/v3_s3_touch.json")

def _load() -> Dict[str, int]:
    if not os.path.exists(TOUCH_PATH):
        return {}
    try:
        with open(TOUCH_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(obj: Dict[str, int]) -> None:
    os.makedirs(os.path.dirname(TOUCH_PATH), exist_ok=True)
    with open(TOUCH_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def can_touch(label: str, cooldown_sec: int = 86400) -> bool:
    obj = _load()
    last = int(obj.get(label, 0))
    return (int(time.time()) - last) >= int(cooldown_sec)

def mark_touched(label: str) -> None:
    obj = _load()
    obj[label] = int(time.time())
    _save(obj)
