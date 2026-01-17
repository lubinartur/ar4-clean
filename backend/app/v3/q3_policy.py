import logging
import os
import time
from typing import Any, Dict, Optional

log = logging.getLogger("air4.v3.q3")

def _cooldown_sec() -> int:
    # default 36h cooldown per label
    v = os.getenv("AIR4_Q3_COOLDOWN_SEC", "").strip()
    if v.isdigit():
        return int(v)
    return 36 * 3600

def _cooldown_path() -> str:
    return os.getenv("AIR4_Q3_COOLDOWN_PATH", "data/v3_q3_cooldowns.json")

def _load_cd() -> Dict[str, int]:
    import json
    p = _cooldown_path()
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return {k: int(v) for k, v in json.load(f).items()}
    except Exception:
        return {}

def _save_cd(d: Dict[str, int]) -> None:
    import json
    p = _cooldown_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def can_surface(label: str, now_ts: Optional[int] = None) -> bool:
    now = int(now_ts or time.time())
    cd = _load_cd()
    last = int(cd.get(label, 0))
    if last and (now - last) < _cooldown_sec():
        return False
    return True

def mark_surfaced(label: str, now_ts: Optional[int] = None) -> None:
    now = int(now_ts or time.time())
    cd = _load_cd()
    cd[label] = now
    _save_cd(cd)

def _cooldown_path_r3() -> str:
    return os.getenv("AIR4_R3_COOLDOWN_PATH", "data/v3_r3_cooldowns.json")

def _load_cd_r3() -> Dict[str, int]:
    import json
    p = _cooldown_path_r3()
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return {k: int(v) for k, v in json.load(f).items()}
    except Exception:
        return {}

def _save_cd_r3(d: Dict[str, int]) -> None:
    import json
    p = _cooldown_path_r3()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def can_surface_r3(label: str, now_ts: Optional[int] = None) -> bool:
    now = int(now_ts or time.time())
    cd = _load_cd_r3()
    last = int(cd.get(label, 0))
    if last and (now - last) < _cooldown_sec():
        return False
    return True

def mark_surfaced_r3(label: str, now_ts: Optional[int] = None) -> None:
    now = int(now_ts or time.time())
    cd = _load_cd_r3()
    cd[label] = now
    _save_cd_r3(cd)
