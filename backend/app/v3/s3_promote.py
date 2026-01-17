import time
from typing import Dict, Any

from .s3_patterns import get_pattern_by_label, upsert_pattern, touch
from .w3_audit import write_audit

def promote_pattern(label: str, source: str = "user") -> Dict[str, Any]:
    """
    User-confirmed promotion:
    — if pattern exists: touch + gentle confidence boost (+0.10, capped at 1.0)
    — if not exists: create with stronger baseline
    — audit: reason=pattern_promoted, mode=r3, decision=meta
    """
    now = int(time.time())
    p = get_pattern_by_label(label)

    if p:
        new_conf = min(1.0, float(p.confidence) + 0.10)
        p2 = upsert_pattern(
            label,
            confidence=new_conf,
            lifetime_days=int(p.lifetime_days),
            decay=float(p.decay),
            source=source,
            notes=((p.notes or "") + " | promoted").strip(" |"),
        )
        touch(label)
        action = "updated"
    else:
        p2 = upsert_pattern(
            label,
            confidence=0.70,
            lifetime_days=45,
            decay=0.04,
            source=source,
            notes="promoted by user",
        )
        action = "created"

    write_audit({
        "ts": now,
        "mode": "r3",
        "label": label,
        "decision": "meta",
        "reason": "pattern_promoted",
        "details": {
            "pattern_id": p2.pattern_id,
            "action": action,
            "confidence": float(p2.confidence),
        },
    })

    return {
        "pattern_id": p2.pattern_id,
        "label": label,
        "action": action,
        "confidence": float(p2.confidence),
    }
