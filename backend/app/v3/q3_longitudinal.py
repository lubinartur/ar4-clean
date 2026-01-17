import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("air4.v3.q3")

@dataclass
class Q3Event:
    ts: int              # unix seconds
    kind: str            # e.g. "signal", "insight", "qb", "note"
    source: str          # e.g. "qb", "chat", "system"
    label: str           # short tag, e.g. "low_energy", "overwhelm"
    meta: Dict[str, Any] # optional payload
    session_id: Optional[str] = None

def _q3_path() -> str:
    # keep it simple for now: local jsonl file
    # (we'll replace with proper store later without touching v2)
    return os.getenv("AIR4_Q3_PATH", "data/v3_q3_events.jsonl")

def append_event(kind: str, source: str, label: str, meta: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None) -> Q3Event:
    ev = Q3Event(
        ts=int(time.time()),
        kind=kind,
        source=source,
        label=label,
        meta=meta or {},
        session_id=session_id,
    )
    path = _q3_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(ev), ensure_ascii=False) + "\n")

    log.info("Q3 event appended: kind=%s source=%s label=%s ts=%s", kind, source, label, ev.ts)
    return ev

def read_recent(limit: int = 50) -> List[Q3Event]:
    path = _q3_path()
    if not os.path.exists(path):
        return []

    events: List[Q3Event] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                # tolerate older lines without new fields
                sid = obj.get("session_id", None)
                obj["session_id"] = sid
                events.append(Q3Event(**obj))
            except Exception:
                # ignore bad lines (we'll add audit later in W3)
                continue

    return events[-limit:]


def repeats_summary(
    days: int = 21,
    min_count: int = 3,
    kind: Optional[str] = "signal",
    source: Optional[str] = None,
    session_id: Optional[str] = None,
    min_sessions: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Returns list of repeat stats for labels in the last N days:
    [
      {"label": "...", "count": 4, "first_ts": ..., "last_ts": ..., "span_days": 9}
    ]
    No interpretation: only numbers/time window.
    """
    path = _q3_path()
    if not os.path.exists(path):
        return []

    now = int(time.time())
    since = now - days * 24 * 3600

    stats: Dict[str, Dict[str, Any]] = {}
    counts = defaultdict(int)
    days_seen = defaultdict(set)  # label -> set(YYYY-MM-DD)
    sessions_seen = defaultdict(set)  # label -> set(session_id)

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue

            ts = int(obj.get("ts", 0))
            if ts < since:
                continue

            if kind is not None and obj.get("kind") != kind:
                continue
            if source is not None and obj.get("source") != source:
                continue
            if session_id is not None and obj.get("session_id") != session_id:
                continue

            label = obj.get("label")
            if not label:
                continue

            day_key = time.strftime("%Y-%m-%d", time.gmtime(ts))
            days_seen[label].add(day_key)

            sid = obj.get("session_id", None)
            if sid:
                sessions_seen[label].add(sid)

            counts[label] += 1
            if label not in stats:
                stats[label] = {"label": label, "count": 0, "first_ts": ts, "last_ts": ts}
            stats[label]["first_ts"] = min(stats[label]["first_ts"], ts)
            stats[label]["last_ts"] = max(stats[label]["last_ts"], ts)

    out: List[Dict[str, Any]] = []
    for label, s in stats.items():
        c = counts[label]
        ud = len(days_seen[label])
        us = len(sessions_seen[label])
        if c < min_count:
            continue
        # anti-spam: require at least 2 unique days for "over time" claims
        if ud < 2:
            continue
        if min_sessions is not None and us < int(min_sessions):
            continue
        span_days = max(0, int((s["last_ts"] - s["first_ts"]) / 86400))
        out.append(
            {
                "label": label,
                "count": c,
                "first_ts": s["first_ts"],
                "last_ts": s["last_ts"],
                "span_days": span_days,
                "unique_days": ud,
                "unique_sessions": us,
                "window_days": days,
            }
        )

    # sort: most frequent first, then most recent
    out.sort(key=lambda x: (x["count"], x["last_ts"]), reverse=True)
    return out


from .q3_policy import can_surface, mark_surfaced
from .q3_surface import format_surface_fact, format_surface_question, default_actions_hint
from .q3_trends import calc_trend
from .u3_controls import is_allowed
from .u3_last import set_last
from .v3_overrides import is_banned, is_pinned, force_mode_only, force_max_per_window
from .w3_audit import audit_decision, count_shown
from .x3_hypotheses import has_competing, top_hypotheses

def surface_candidates(days: int = 21, min_count: int = 3, source: str = "qb", limit: int = 3):
    rep = repeats_summary(days=days, min_count=min_count, source=source)
    # rep already includes unique_days >=2
    pinned_out = []
    out = []
    for r in rep:
        if not is_allowed(r["label"], mode="q3"):
            audit_decision("q3", r["label"], "suppressed", "user_rule", {"stats": r})
            continue
        if is_banned(r["label"]):
            audit_decision("q3", r["label"], "suppressed", "override_ban", {"stats": r})
            continue
        mo = force_mode_only(r["label"])
        if mo is not None and mo != "q3":
            audit_decision("q3", r["label"], "suppressed", "override_force_mode", {"stats": r, "mode_only": mo})
            continue
        mw = force_max_per_window(r["label"])
        if mw is not None:
            since_ts = int(time.time()) - int(mw["days"]) * 86400
            shown_n = count_shown(r["label"], mode="q3", since_ts=since_ts)
            if shown_n >= int(mw["count"]):
                audit_decision("q3", r["label"], "suppressed", "override_force_rate", {"stats": r, "max_per_window": mw, "shown": shown_n})
                continue
        if (not is_pinned(r["label"])) and (not can_surface(r["label"])):
            audit_decision("q3", r["label"], "suppressed", "cooldown", {"stats": r})
            continue
        if is_pinned(r["label"]):
            pinned_out.append(r)
        else:
            out.append(r)
        audit_decision("q3", r["label"], "shown", "none", {"stats": r, "pinned": is_pinned(r["label"])})
        if len(pinned_out) + len(out) >= limit:
            break
    return pinned_out + out

def surface_payload(days: int = 21, min_count: int = 3, source: str = "qb", ask: bool = True, debug: bool = False):
    cand = surface_candidates(days=days, min_count=min_count, source=source, limit=1)
    if not cand:
        return None

    r = cand[0]
    text = format_surface_fact(r)
    actions_hint = None
    if ask:
        text = text + "\n" + format_surface_question()
        actions_hint = default_actions_hint(r["label"])

    # mark cooldown immediately on surfacing
    mark_surfaced(r["label"])
    # record last surfaced label for "это" commands
    set_last("q3", r["label"])

    x3 = {"has_competing_hypotheses": has_competing(r["label"])}
    if debug and x3["has_competing_hypotheses"]:
        x3["top_hypotheses"] = [
            {"hid": h.hid, "text": h.text, "confidence": h.confidence, "source": h.source}
            for h in top_hypotheses(r["label"], k=2)
        ]

    x3_actions_hint = None
    if x3.get("has_competing_hypotheses") and (ask or debug):
        # strict, copy-pastable
        x3_actions_hint = [
            f"гипотеза список {r['label']}",
            f"гипотеза добавить {r['label']}: <текст> @0.6",
            "гипотеза убрать <hid>",
        ]

    s3_actions_hint = None
    if ask:
        s3_actions_hint = [
            f"паттерн продвинуть {r['label']}",
            f"паттерн закрепить {r['label']}",
            f"паттерн статус {r['label']} paused",
            f"паттерн статус {r['label']} archived",
        ]

    q3_trend = None
    if ask or debug:
        q3_trend = calc_trend(
            label=r["label"],
            window_curr_days=21,
            window_prev_days=21,
            source=source,
            session_id=None,
        )

    return {
        "label": r["label"],
        "text": text,
        "stats": r,
        "actions_hint": actions_hint,
        "x3": x3,
        "x3_actions_hint": x3_actions_hint,
        "s3_actions_hint": s3_actions_hint,
        "q3_trend": q3_trend,
    }


from .q3_policy import can_surface_r3, mark_surfaced_r3
from .q3_surface import format_cross_session_fact

def cross_session_candidates(
    days: int = 30,
    min_count: int = 3,
    min_sessions: int = 2,
    source: str = "qb",
    limit: int = 3,
):
    rep = repeats_summary(days=days, min_count=min_count, source=source, min_sessions=min_sessions)
    pinned_out = []
    out = []
    for r in rep:
        if not is_allowed(r["label"], mode="r3"):
            audit_decision("r3", r["label"], "suppressed", "user_rule", {"stats": r})
            continue
        if is_banned(r["label"]):
            audit_decision("r3", r["label"], "suppressed", "override_ban", {"stats": r})
            continue
        mo = force_mode_only(r["label"])
        if mo is not None and mo != "r3":
            audit_decision("r3", r["label"], "suppressed", "override_force_mode", {"stats": r, "mode_only": mo})
            continue
        mw = force_max_per_window(r["label"])
        if mw is not None:
            since_ts = int(time.time()) - int(mw["days"]) * 86400
            shown_n = count_shown(r["label"], mode="r3", since_ts=since_ts)
            if shown_n >= int(mw["count"]):
                audit_decision("r3", r["label"], "suppressed", "override_force_rate", {"stats": r, "max_per_window": mw, "shown": shown_n})
                continue
        if (not is_pinned(r["label"])) and (not can_surface_r3(r["label"])):
            audit_decision("r3", r["label"], "suppressed", "cooldown", {"stats": r})
            continue
        if is_pinned(r["label"]):
            pinned_out.append(r)
        else:
            out.append(r)
        audit_decision("r3", r["label"], "shown", "none", {"stats": r, "pinned": is_pinned(r["label"])})
        if len(pinned_out) + len(out) >= limit:
            break
    return pinned_out + out

def cross_session_payload(
    days: int = 30,
    min_count: int = 3,
    min_sessions: int = 2,
    source: str = "qb",
):
    cand = cross_session_candidates(days=days, min_count=min_count, min_sessions=min_sessions, source=source, limit=1)
    if not cand:
        return None
    r = cand[0]
    # mark cooldown for R3 surfacing
    mark_surfaced_r3(r["label"])
    return r

def cross_session_payload_text(
    days: int = 30,
    min_count: int = 3,
    min_sessions: int = 2,
    source: str = "qb",
    ask: bool = False,
    debug: bool = False,
):
    cand = cross_session_candidates(days=days, min_count=min_count, min_sessions=min_sessions, source=source, limit=1)
    if not cand:
        return None
    r = cand[0]
    text = format_cross_session_fact(r)
    actions_hint = None
    if ask:
        # без вопросника, коротко
        actions_hint = [
            f"не возвращайся к {r['label']}",
            f"пока не трогай {r['label']} до 2026-02-10",
            f"только r3 {r['label']}",
        ]
    mark_surfaced_r3(r["label"])
    # record last surfaced label for "это" commands
    set_last("r3", r["label"])

    x3 = {"has_competing_hypotheses": has_competing(r["label"])}
    if debug and x3["has_competing_hypotheses"]:
        x3["top_hypotheses"] = [
            {"hid": h.hid, "text": h.text, "confidence": h.confidence, "source": h.source}
            for h in top_hypotheses(r["label"], k=2)
        ]

    x3_actions_hint = None
    if x3.get("has_competing_hypotheses") and (ask or debug):
        # strict, copy-pastable
        x3_actions_hint = [
            f"гипотеза список {r['label']}",
            f"гипотеза добавить {r['label']}: <текст> @0.6",
            "гипотеза убрать <hid>",
        ]

    s3_actions_hint = None
    if ask:
        s3_actions_hint = [
            f"паттерн продвинуть {r['label']}",
            f"паттерн закрепить {r['label']}",
            f"паттерн статус {r['label']} paused",
            f"паттерн статус {r['label']} archived",
        ]

    r3_trend = None
    if ask or debug:
        r3_trend = calc_trend(
            label=r["label"],
            window_curr_days=30,
            window_prev_days=30,
            source=source,
            session_id=None,
        )

    return {"label": r["label"], "text": text, "stats": r, "actions_hint": actions_hint, "x3": x3, "x3_actions_hint": x3_actions_hint, "s3_actions_hint": s3_actions_hint, "r3_trend": r3_trend}
