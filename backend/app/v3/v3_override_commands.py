import re
from typing import Any, Dict, Optional

from .v3_overrides import set_override, list_overrides, deactivate_override, clear_label

_RE_BAN = re.compile(r"^\s*оверрайд\s+бан\s+(.+?)\s*$", re.IGNORECASE)
_RE_PIN = re.compile(r"^\s*оверрайд\s+пин\s+(.+?)\s*$", re.IGNORECASE)

_RE_FORCE_MODE = re.compile(r"^\s*оверрайд\s+форс\s+режим\s+(.+?)\s+(q3|r3)\s*$", re.IGNORECASE)
_RE_FORCE_RATE = re.compile(r"^\s*оверрайд\s+форс\s+лимит\s+(.+?)\s+(\d+)\s+за\s+(\d+)\s*д\s*$", re.IGNORECASE)

_RE_LIST = re.compile(r"^\s*оверрайд\s+список\s+(.+?)\s*$", re.IGNORECASE)
_RE_REMOVE = re.compile(r"^\s*оверрайд\s+снять\s+(o_\S+)\s*$", re.IGNORECASE)
_RE_CLEAR = re.compile(r"^\s*оверрайд\s+очистить\s+(.+?)\s*$", re.IGNORECASE)

def parse_override_command(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    m = _RE_BAN.match(text)
    if m:
        return {"op": "set", "label": m.group(1).strip(), "kind": "ban", "value": {"note": "manual"}}

    m = _RE_PIN.match(text)
    if m:
        return {"op": "set", "label": m.group(1).strip(), "kind": "pin", "value": {"note": "manual"}}

    m = _RE_FORCE_MODE.match(text)
    if m:
        return {"op": "set", "label": m.group(1).strip(), "kind": "force", "value": {"mode_only": m.group(2).lower()}}

    m = _RE_FORCE_RATE.match(text)
    if m:
        label = m.group(1).strip()
        count = int(m.group(2))
        days = int(m.group(3))
        return {"op": "set", "label": label, "kind": "force", "value": {"max_per_window": {"days": days, "count": count}}}

    m = _RE_LIST.match(text)
    if m:
        return {"op": "list", "label": m.group(1).strip()}

    m = _RE_REMOVE.match(text)
    if m:
        return {"op": "remove", "oid": m.group(1).strip()}

    m = _RE_CLEAR.match(text)
    if m:
        return {"op": "clear", "label": m.group(1).strip()}

    return None

def apply_override_command(cmd: Dict[str, Any]) -> Dict[str, Any]:
    op = cmd.get("op")

    if op == "set":
        o = set_override(cmd["label"], cmd["kind"], cmd["value"], source="user")
        return {"ok": True, "op": "set", "oid": o.oid, "label": o.label, "kind": o.kind, "value": o.value}

    if op == "list":
        xs = list_overrides(cmd["label"], active_only=False)
        return {
            "ok": True,
            "op": "list",
            "label": cmd["label"],
            "items": [
                {"oid": o.oid, "kind": o.kind, "active": o.active, "value": o.value, "updated_ts": o.updated_ts}
                for o in xs
            ],
        }

    if op == "remove":
        oid = cmd["oid"]
        # need label: brute force small store
        from .v3_overrides import _load, _save  # internal use
        import time
        obj = _load()
        for label, arr in obj.items():
            for r in arr:
                if r.get("oid") == oid:
                    r["active"] = False
                    r["updated_ts"] = int(time.time())
                    _save(obj)
                    return {"ok": True, "op": "remove", "oid": oid, "label": label}
        return {"ok": False, "op": "remove", "oid": oid, "error": "not_found"}

    if op == "clear":
        clear_label(cmd["label"])
        return {"ok": True, "op": "clear", "label": cmd["label"]}

    return {"ok": False, "error": "bad_command"}
