import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

PAT_PATH = os.getenv("AIR4_S3_PAT_PATH", "data/v3_s3_patterns.json")

@dataclass
class Pattern:
    pattern_id: str
    label: str
    created_ts: int
    updated_ts: int
    last_seen_ts: int

    confidence: float          # 0..1, текущий вес паттерна
    lifetime_days: int         # ожидаемый горизонт
    decay: float               # скорость угасания 0..1

    status: str = "active"     # active|paused|archived
    notes: str = ""            # краткая заметка (manual)
    source: str = "system"     # system|user

def _load() -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(PAT_PATH):
        return {}
    try:
        with open(PAT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(PAT_PATH), exist_ok=True)
    with open(PAT_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _pid(label: str) -> str:
    # stable-ish id per label
    return f"p_{abs(hash(label))%10_000_000:07d}"

def upsert_pattern(
    label: str,
    confidence: float = 0.5,
    lifetime_days: int = 30,
    decay: float = 0.05,
    source: str = "system",
    notes: str = "",
) -> Pattern:
    now = int(time.time())
    obj = _load()
    pid = _pid(label)

    if pid in obj:
        r = obj[pid]
        r["updated_ts"] = now
        r["last_seen_ts"] = now
        # update fields if provided
        r["confidence"] = float(confidence)
        r["lifetime_days"] = int(lifetime_days)
        r["decay"] = float(decay)
        if notes:
            r["notes"] = notes
        r["source"] = source or r.get("source", "system")
        obj[pid] = r
    else:
        p = Pattern(
            pattern_id=pid,
            label=label,
            created_ts=now,
            updated_ts=now,
            last_seen_ts=now,
            confidence=float(confidence),
            lifetime_days=int(lifetime_days),
            decay=float(decay),
            status="active",
            notes=notes or "",
            source=source or "system",
        )
        obj[pid] = asdict(p)

    _save(obj)
    return Pattern(**obj[pid])

def get_pattern_by_id(pattern_id: str) -> Optional[Pattern]:
    obj = _load()
    r = obj.get(pattern_id)
    return Pattern(**r) if r else None

def get_pattern_by_label(label: str) -> Optional[Pattern]:
    pid = _pid(label)
    return get_pattern_by_id(pid)

def list_patterns(status: Optional[str] = None) -> List[Pattern]:
    obj = _load()
    out: List[Pattern] = []
    for _, r in obj.items():
        if status and r.get("status") != status:
            continue
        out.append(Pattern(**r))
    # newest first
    out.sort(key=lambda p: int(p.updated_ts), reverse=True)
    return out

def set_status(label: str, status: str) -> Optional[Pattern]:
    if status not in ("active", "paused", "archived"):
        return None
    p = get_pattern_by_label(label)
    if not p:
        return None
    obj = _load()
    r = obj[p.pattern_id]
    r["status"] = status
    r["updated_ts"] = int(time.time())
    obj[p.pattern_id] = r
    _save(obj)
    return Pattern(**r)

def touch(label: str) -> Optional[Pattern]:
    p = get_pattern_by_label(label)
    if not p:
        return None
    obj = _load()
    r = obj[p.pattern_id]
    r["last_seen_ts"] = int(time.time())
    r["updated_ts"] = int(time.time())
    obj[p.pattern_id] = r
    _save(obj)
    return Pattern(**r)

def is_user_pinned(p: Pattern) -> bool:
    # simple heuristic for v3:
    if (p.source or "").lower() == "user":
        return True
    if "pinned by user" in (p.notes or "").lower():
        return True
    return False
