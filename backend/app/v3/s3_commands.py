import re
from typing import Any, Dict, Optional

from .s3_patterns import upsert_pattern, set_status, list_patterns

_RE_PIN = re.compile(r"^\s*паттерн\s+закрепить\s+(.+?)\s*$", re.IGNORECASE)
_RE_STATUS = re.compile(r"^\s*паттерн\s+статус\s+(.+?)\s+(active|paused|archived)\s*$", re.IGNORECASE)
_RE_PROMOTE = re.compile(r"^\s*паттерн\s+продвинуть\s+(.+?)\s*$", re.IGNORECASE)
_RE_LIST = re.compile(r"^\s*паттерн\s+список(?:\s+(active|paused|archived))?\s*$", re.IGNORECASE)

def parse_s3_command(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    m = _RE_PIN.match(text)
    if m:
        return {"op": "pin", "label": m.group(1).strip()}

    m = _RE_STATUS.match(text)
    if m:
        return {"op": "status", "label": m.group(1).strip(), "status": m.group(2).lower()}

    m = _RE_PROMOTE.match(text)
    if m:
        return {"op": "promote", "label": m.group(1).strip()}

    m = _RE_LIST.match(text)
    if m:
        st = m.group(1)
        return {"op": "list", "status": st.lower() if st else None}

    return None

def apply_s3_command(cmd: Dict[str, Any]) -> Dict[str, Any]:
    op = cmd.get("op")

    if op == "pin":
        # baseline defaults for now (can be tuned later)
        p = upsert_pattern(
            cmd["label"],
            confidence=0.6,
            lifetime_days=30,
            decay=0.05,
            source="user",
            notes="pinned by user",
        )
        return {"ok": True, "op": "pin", "pattern_id": p.pattern_id, "label": p.label, "status": p.status}

    if op == "status":
        p = set_status(cmd["label"], cmd["status"])
        if not p:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "op": "status", "label": p.label, "status": p.status}

    if op == "promote":
        from .s3_promote import promote_pattern
        r = promote_pattern(cmd["label"], source="user")
        return {"ok": True, "op": "promote", **r}

    if op == "list":
        xs = list_patterns(status=cmd.get("status"))
        return {"ok": True, "op": "list", "items": [{"pattern_id": p.pattern_id, "label": p.label, "status": p.status, "confidence": p.confidence} for p in xs]}

    return {"ok": False, "error": "bad_command"}
