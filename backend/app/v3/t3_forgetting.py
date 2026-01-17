import time
from typing import Dict, List, Any

from .s3_patterns import Pattern
from .s3_patterns import _load as _load_patterns

def _days_since(ts: int) -> float:
    return (int(time.time()) - int(ts)) / 86400.0

def archive_candidates(min_days_since_seen: int = 45, max_confidence: float = 0.2) -> List[Dict[str, Any]]:
    """
    Candidates to archive (dry-run):
    — status in ('active','paused')
    — days_since_last_seen >= min_days_since_seen
    — confidence <= max_confidence
    """
    obj = _load_patterns()
    out: List[Dict[str, Any]] = []
    for _, r in obj.items():
        p = Pattern(**r)
        ds = _days_since(p.last_seen_ts)
        if p.status not in ("active", "paused"):
            continue
        if ds < float(min_days_since_seen):
            continue
        if float(p.confidence) > float(max_confidence):
            continue
        out.append({
            "pattern_id": p.pattern_id,
            "label": p.label,
            "status": p.status,
            "confidence": round(float(p.confidence), 4),
            "days_since_seen": round(ds, 2),
            "suggest": "archived",
        })
    out.sort(key=lambda x: (x["confidence"], -x["days_since_seen"]))
    return out

def purge_candidates(min_days_archived: int = 90) -> List[Dict[str, Any]]:
    """
    Candidates to purge (dry-run):
    — status == 'archived'
    — days_since_updated >= min_days_archived
    """
    obj = _load_patterns()
    out: List[Dict[str, Any]] = []
    for _, r in obj.items():
        p = Pattern(**r)
        if p.status != "archived":
            continue
        du = _days_since(p.updated_ts)
        if du < float(min_days_archived):
            continue
        out.append({
            "pattern_id": p.pattern_id,
            "label": p.label,
            "status": p.status,
            "confidence": round(float(p.confidence), 4),
            "days_since_updated": round(du, 2),
            "suggest": "purge",
        })
    out.sort(key=lambda x: -x["days_since_updated"])
    return out
