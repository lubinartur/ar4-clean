import re
import time
from typing import Any, Dict, Optional

from .u3_controls import mute, unmute, defer, clear_defer, allow_only
from .u3_last import get_last

_RE_MUTE_THIS = re.compile(r"^\s*не\s+возвращайся\s+к\s+этому\s*$", re.IGNORECASE)
_RE_DEFER_THIS = re.compile(r"^\s*пока\s+не\s+трогай\s+это\s+до\s+(\d{4}-\d{2}-\d{2})\s*$", re.IGNORECASE)

_RE_MUTE = re.compile(r"^\s*не\s+возвращайся\s+к\s+(.+?)\s*$", re.IGNORECASE)
_RE_UNMUTE = re.compile(r"^\s*можно\s+снова\s+(.+?)\s*$", re.IGNORECASE)

# "пока не трогай <label> до 2026-02-10"
_RE_DEFER = re.compile(r"^\s*пока\s+не\s+трогай\s+(.+?)\s+до\s+(\d{4}-\d{2}-\d{2})\s*$", re.IGNORECASE)
_RE_CLEAR_DEFER = re.compile(r"^\s*убери\s+отсрочку\s+(.+?)\s*$", re.IGNORECASE)

# "только q3 <label>" / "только r3 <label>" / "снять ограничение <label>"
_RE_ONLY = re.compile(r"^\s*только\s+(q3|r3)\s+(.+?)\s*$", re.IGNORECASE)
_RE_ONLY_CLEAR = re.compile(r"^\s*снять\s+ограничение\s+(.+?)\s*$", re.IGNORECASE)

def _parse_date_yyyy_mm_dd(s: str) -> Optional[int]:
    try:
        # local midnight
        t = time.strptime(s, "%Y-%m-%d")
        return int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1)))
    except Exception:
        return None

def parse_u3_command(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    m = _RE_MUTE_THIS.match(text)
    if m:
        label = get_last("q3") or get_last("r3")
        if not label:
            return None
        return {"op": "mute", "label": label}

    m = _RE_DEFER_THIS.match(text)
    if m:
        label = get_last("q3") or get_last("r3")
        if not label:
            return None
        ts = _parse_date_yyyy_mm_dd(m.group(1))
        if ts is None:
            return None
        return {"op": "defer", "label": label, "until_ts": ts}

    m = _RE_MUTE.match(text)
    if m:
        return {"op": "mute", "label": m.group(1).strip()}

    m = _RE_UNMUTE.match(text)
    if m:
        return {"op": "unmute", "label": m.group(1).strip()}

    m = _RE_DEFER.match(text)
    if m:
        label = m.group(1).strip()
        ts = _parse_date_yyyy_mm_dd(m.group(2))
        if ts is None:
            return None
        return {"op": "defer", "label": label, "until_ts": ts}

    m = _RE_CLEAR_DEFER.match(text)
    if m:
        return {"op": "clear_defer", "label": m.group(1).strip()}

    m = _RE_ONLY.match(text)
    if m:
        mode = m.group(1).lower()
        label = m.group(2).strip()
        return {"op": "allow_only", "label": label, "mode": mode}

    m = _RE_ONLY_CLEAR.match(text)
    if m:
        return {"op": "allow_only", "label": m.group(1).strip(), "mode": None}

    return None

def apply_u3_command(cmd: Dict[str, Any]) -> bool:
    op = cmd.get("op")
    label = cmd.get("label")
    if not op or not label:
        return False

    if op == "mute":
        mute(label); return True
    if op == "unmute":
        unmute(label); return True
    if op == "defer":
        defer(label, int(cmd["until_ts"])); return True
    if op == "clear_defer":
        clear_defer(label); return True
    if op == "allow_only":
        allow_only(label, cmd.get("mode")); return True

    return False
