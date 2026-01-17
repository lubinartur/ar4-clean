import json
import os
import time
from collections import Counter
from typing import Any, Dict, List, Optional

AUDIT_PATH = os.getenv("AIR4_W3_AUDIT_PATH", "data/v3_w3_audit.jsonl")

def write_audit(event: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

def audit_decision(
    mode: str,                # 'q3' | 'r3'
    label: str,
    decision: str,            # 'shown' | 'suppressed'
    reason: str,              # 'cooldown' | 'user_rule' | 'threshold' | 'none'
    details: Optional[Dict[str, Any]] = None,
) -> None:
    ev = {
        "ts": int(time.time()),
        "mode": mode,
        "label": label,
        "decision": decision,
        "reason": reason,
        "details": details or {},
    }
    write_audit(ev)

def read_audit_recent(limit: int = 2000) -> List[Dict[str, Any]]:
    if not os.path.exists(AUDIT_PATH):
        return []
    # small file assumption for v3 alpha; later we index
    with open(AUDIT_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()[-limit:]
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out

def audit_summary(label: str, mode: str | None = None, limit: int = 2000) -> Dict[str, Any]:
    events = read_audit_recent(limit=limit)
    filtered = []
    for e in events:
        if e.get("label") != label:
            continue
        if mode and e.get("mode") != mode:
            continue
        filtered.append(e)

    if not filtered:
        return {"label": label, "mode": mode, "total": 0}

    decisions = Counter(e.get("decision") for e in filtered)
    reasons = Counter(e.get("reason") for e in filtered if e.get("decision") == "suppressed")

    last = filtered[-1]

    return {
        "label": label,
        "mode": mode,
        "total": len(filtered),
        "shown": int(decisions.get("shown", 0)),
        "suppressed": int(decisions.get("suppressed", 0)),
        "top_suppressed_reasons": reasons.most_common(3),
        "last": {
            "ts": last.get("ts"),
            "mode": last.get("mode"),
            "decision": last.get("decision"),
            "reason": last.get("reason"),
            "details": last.get("details", {}),
        },
    }

def _fmt_reason(reason: str) -> str:
    if reason == "cooldown":
        return "сработал cooldown (чтобы не спамить)"
    if reason == "user_rule":
        return "сработало правило пользователя (mute/defer/режим)"
    if reason == "threshold":
        return "не выполнены пороги (частота/дни/сессии)"
    if reason == "none":
        return "все проверки пройдены"
    return reason

def audit_explain(label: str, mode: str | None = None) -> str:
    s = audit_summary(label, mode=mode)
    if s.get("total", 0) == 0:
        return f"По **{label}** нет аудита решений."

    last = s["last"]
    decision = last.get("decision")
    reason = last.get("reason", "unknown")

    if decision == "shown":
        line1 = f"Я поднял **{label}**: {_fmt_reason('none')}."
        return line1

    # suppressed
    line1 = f"Я НЕ поднял **{label}**: {_fmt_reason(reason)}."
    top = s.get("top_suppressed_reasons", [])
    if top:
        # show 1 top reason only to keep it short
        r0, c0 = top[0]
        line2 = f"Чаще всего подавлялось так: {_fmt_reason(r0)} ({c0}×)."
        return f"{line1}\n{line2}"
    return line1

def count_shown(label: str, mode: str | None, since_ts: int, limit: int = 5000) -> int:
    events = read_audit_recent(limit=limit)
    n = 0
    for e in events:
        if e.get("label") != label:
            continue
        if mode and e.get("mode") != mode:
            continue
        if int(e.get("ts", 0)) < int(since_ts):
            continue
        if e.get("decision") == "shown":
            n += 1
    return n
