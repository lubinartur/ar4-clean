import re
from typing import Any, Dict, Optional

from .x3_hypotheses import add_hypothesis, list_hypotheses, deactivate_hypothesis

# "гипотеза добавить low_energy: Может быть сон @0.6"
_RE_ADD = re.compile(r"^\s*гипотеза\s+добавить\s+(.+?)\s*:\s*(.+?)(?:\s+@([01](?:\.\d+)?))?\s*$", re.IGNORECASE)
# "гипотеза убрать h_...."
_RE_REMOVE = re.compile(r"^\s*гипотеза\s+убрать\s+(h_\S+)\s*$", re.IGNORECASE)
# "гипотеза список low_energy"
_RE_LIST = re.compile(r"^\s*гипотеза\s+список\s+(.+?)\s*$", re.IGNORECASE)

def parse_x3_command(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    m = _RE_ADD.match(text)
    if m:
        label = m.group(1).strip()
        htext = m.group(2).strip()
        conf = m.group(3)
        c = float(conf) if conf is not None else 0.5
        # clamp
        c = 0.0 if c < 0 else 1.0 if c > 1 else c
        return {"op": "add", "label": label, "text": htext, "confidence": c}

    m = _RE_REMOVE.match(text)
    if m:
        return {"op": "remove", "hid": m.group(1).strip()}

    m = _RE_LIST.match(text)
    if m:
        return {"op": "list", "label": m.group(1).strip()}

    return None

def apply_x3_command(cmd: Dict[str, Any]) -> Dict[str, Any]:
    op = cmd.get("op")

    if op == "add":
        h = add_hypothesis(
            label=cmd["label"],
            text=cmd["text"],
            source="user",
            confidence=float(cmd.get("confidence", 0.5)),
        )
        return {"ok": True, "op": "add", "hid": h.hid, "label": h.label}

    if op == "remove":
        hid = cmd["hid"]
        # we don't know label directly; search small storage by listing keys
        # (acceptable for v3 alpha; can index later)
        # Best-effort: try all labels
        from .x3_hypotheses import _load, _save  # internal use
        obj = _load()
        for label, arr in obj.items():
            for r in arr:
                if r.get("hid") == hid:
                    r["active"] = False
                    _save(obj)
                    return {"ok": True, "op": "remove", "hid": hid, "label": label}
        return {"ok": False, "op": "remove", "hid": hid, "error": "not_found"}

    if op == "list":
        hs = list_hypotheses(cmd["label"], active_only=True)
        return {
            "ok": True,
            "op": "list",
            "label": cmd["label"],
            "items": [{"hid": h.hid, "text": h.text, "confidence": h.confidence, "source": h.source} for h in hs],
        }

    return {"ok": False, "error": "bad_command"}
