import time
from typing import Optional

from .s3_patterns import get_pattern_by_label, touch, is_user_pinned
from .s3_touch_policy import can_touch, mark_touched
from .w3_audit import write_audit

def maybe_touch_pattern(label: str, source: str) -> bool:
    # only QB signals are allowed to auto-touch
    if (source or "").lower() != "qb":
        return False

    p = get_pattern_by_label(label)
    if not p:
        return False
    if p.status != "active":
        return False
    if not is_user_pinned(p):
        return False

    if not can_touch(label):
        return False

    touch(label)
    mark_touched(label)

    # audit meta event
    write_audit({
        "ts": int(time.time()),
        "mode": "s3",
        "label": label,
        "decision": "meta",
        "reason": "pattern_touch",
        "details": {"source": source, "pattern_id": p.pattern_id},
    })
    return True
