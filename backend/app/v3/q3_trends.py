import time
from typing import Optional

from .q3_longitudinal import read_recent


def calc_trend(
    label: str,
    window_curr_days: int,
    window_prev_days: int,
    source: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """
    Calculate trend between two time windows for a given label.
    Pure calculation, no side effects.
    """
    now = int(time.time())
    events = read_recent(limit=10000)

    # Time boundaries
    curr_window_start = now - (window_curr_days * 86400)
    prev_window_start = now - (window_prev_days * 86400)

    # Filter events by label and optional filters
    prev_count = 0
    curr_count = 0

    for ev in events:
        # Filter by label
        if ev.label != label:
            continue

        # Filter by source if specified
        if source is not None and ev.source != source:
            continue

        # Filter by session_id if specified
        if session_id is not None and ev.session_id != session_id:
            continue

        # Count in windows
        if prev_window_start <= ev.ts < curr_window_start:
            prev_count += 1
        elif ev.ts >= curr_window_start:
            curr_count += 1

    # Calculate delta and percentage
    delta = curr_count - prev_count

    if prev_count == 0:
        if curr_count > 0:
            delta_pct = 100.0
        else:
            delta_pct = 0.0
    else:
        delta_pct = round((delta / prev_count) * 100, 2)

    # Determine trend
    if delta > 0:
        trend = "up"
    elif delta < 0:
        trend = "down"
    else:
        trend = "flat"

    return {
        "label": label,
        "window_curr_days": window_curr_days,
        "window_prev_days": window_prev_days,
        "prev": prev_count,
        "curr": curr_count,
        "delta": delta,
        "delta_pct": delta_pct,
        "trend": trend,
    }
