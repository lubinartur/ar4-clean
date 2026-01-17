import time
from typing import Dict, List, Any

from .s3_patterns import list_patterns, get_pattern_by_id, Pattern
from .s3_patterns import _load as _load_patterns, _save as _save_patterns  # internal
from .w3_audit import write_audit

def _days_since(ts: int) -> float:
    return (int(time.time()) - int(ts)) / 86400.0

def apply_aging(p: Pattern) -> Dict[str, Any]:
    """
    Aging rule v1:
    — base decay per day: confidence *= (1 - decay)^(days_since_last_seen)
    — floor at 0.0
    — if confidence < 0.15 and days_since_last_seen > lifetime_days: archive
    """
    ds = _days_since(p.last_seen_ts)
    old_c = float(p.confidence)
    # exponential-ish decay
    factor = (1.0 - float(p.decay)) ** max(ds, 0.0)
    new_c = max(0.0, min(1.0, old_c * factor))

    new_status = p.status
    if (new_c < 0.15) and (ds > float(p.lifetime_days)) and (p.status == "active"):
        new_status = "archived"

    return {
        "pattern_id": p.pattern_id,
        "label": p.label,
        "days_since_seen": round(ds, 2),
        "old_confidence": round(old_c, 4),
        "new_confidence": round(new_c, 4),
        "old_status": p.status,
        "new_status": new_status,
        "changed": (abs(new_c - old_c) > 1e-6) or (new_status != p.status),
    }

def age_all(dry_run: bool = True) -> List[Dict[str, Any]]:
    obj = _load_patterns()
    out: List[Dict[str, Any]] = []
    changed_any = False

    for pid, r in obj.items():
        p = Pattern(**r)
        calc = apply_aging(p)
        if not calc["changed"]:
            continue

        out.append(calc)
        changed_any = True

        if not dry_run:
            r["confidence"] = float(calc["new_confidence"])
            r["status"] = calc["new_status"]
            r["updated_ts"] = int(time.time())
            obj[pid] = r

            write_audit({
                "ts": int(time.time()),
                "mode": "t3",
                "label": p.label,
                "decision": "meta",
                "reason": "pattern_aged",
                "details": calc,
            })

    if (not dry_run) and changed_any:
        _save_patterns(obj)

    # sort by biggest confidence drop
    out.sort(key=lambda x: (x["old_confidence"] - x["new_confidence"]), reverse=True)
    return out
