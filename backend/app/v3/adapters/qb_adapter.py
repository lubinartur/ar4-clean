from typing import Optional, Dict, Any
import logging
import os

from ..q3_longitudinal import append_event

log = logging.getLogger("air4.v3.adapter.qb")

def emit_qb_signal(
    label: str,
    session_id: Optional[str],
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Passive adapter.
    QB may call this AFTER it already decided a signal exists.
    No logic. No conditions. Fire-and-forget.
    """
    if not os.getenv("AIR4_V3_ENABLED"):
        return

    try:
        append_event(
            kind="signal",
            source="qb",
            label=label,
            meta=meta or {},
            session_id=session_id,
        )
        log.debug("QB signal emitted to V3: %s (%s)", label, session_id)
    except Exception as e:
        # V3 must never break QB
        log.warning("QB→V3 emit failed: %s", e)

    try:
        from ..s3_touch import maybe_touch_pattern
        maybe_touch_pattern(label, source="qb")
    except Exception:
        # never break QB
        pass
