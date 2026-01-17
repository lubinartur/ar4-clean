import re
import time
from typing import Any, Dict, Optional

from .s3_patterns import set_status, get_pattern_by_id
from .s3_patterns import _load as _load_patterns, _save as _save_patterns  # internal
from .t3_forgetting import archive_candidates, purge_candidates
from .w3_audit import write_audit

_RE_LIST = re.compile(r"^\s*забыть\s+список\s*$", re.IGNORECASE)
_RE_ARCHIVE = re.compile(r"^\s*забыть\s+архивировать\s+(.+?)\s*$", re.IGNORECASE)
_RE_PURGE = re.compile(r"^\s*забыть\s+удалить\s+(p_\d+)\s*$", re.IGNORECASE)

def parse_t3_command(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    if _RE_LIST.match(text):
        return {"op": "list"}
    m = _RE_ARCHIVE.match(text)
    if m:
        return {"op": "archive", "label": m.group(1).strip()}
    m = _RE_PURGE.match(text)
    if m:
        return {"op": "purge", "pattern_id": m.group(1).strip()}
    return None

def apply_t3_command(cmd: Dict[str, Any]) -> Dict[str, Any]:
    op = cmd.get("op")

    if op == "list":
        return {
            "ok": True,
            "op": "list",
            "archive": archive_candidates(),
            "purge": purge_candidates(),
        }

    if op == "archive":
        label = cmd["label"]
        p = set_status(label, "archived")
        if not p:
            return {"ok": False, "error": "not_found"}
        write_audit({
            "ts": int(time.time()),
            "mode": "t3",
            "label": label,
            "decision": "meta",
            "reason": "forget_archive",
            "details": {"pattern_id": p.pattern_id, "status": p.status},
        })
        return {"ok": True, "op": "archive", "label": label, "pattern_id": p.pattern_id}

    if op == "purge":
        pid = cmd["pattern_id"]
        obj = _load_patterns()
        if pid not in obj:
            return {"ok": False, "error": "not_found"}
        label = obj[pid].get("label", "")
        del obj[pid]
        _save_patterns(obj)
        write_audit({
            "ts": int(time.time()),
            "mode": "t3",
            "label": label or pid,
            "decision": "meta",
            "reason": "forget_purge",
            "details": {"pattern_id": pid},
        })
        return {"ok": True, "op": "purge", "pattern_id": pid, "label": label}

    return {"ok": False, "error": "bad_command"}
