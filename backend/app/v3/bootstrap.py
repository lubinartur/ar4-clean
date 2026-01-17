import logging
import os

log = logging.getLogger("air4.v3")

def _is_enabled() -> bool:
    # Default OFF. Enable only when explicitly set.
    v = os.getenv("AIR4_V3_ENABLED", "").strip().lower()
    return v in ("1", "true", "yes", "on")

def init_v3(app=None) -> None:
    if not _is_enabled():
        log.info("V3 disabled (flag off)")
        return

    log.info("V3 enabled (flag on) — no-op")
    from .q3_longitudinal import read_recent, repeats_summary, surface_candidates, surface_payload
    n = len(read_recent(5))
    log.info("Q3 ready: recent_events=%s", n)
    rep = repeats_summary(days=21, min_count=3)
    log.info("Q3 repeats: %s", rep[:5])
    cand = surface_candidates(days=21, min_count=3, source='qb', limit=3)
    log.info("Q3 surface_candidates: %s", cand)
    payload = surface_payload(days=21, min_count=3, source='qb', ask=False)
    log.info("Q3 surface_payload: %s", payload)