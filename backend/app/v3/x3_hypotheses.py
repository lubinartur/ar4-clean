import json
import os
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

HYP_PATH = os.getenv("AIR4_X3_HYP_PATH", "data/v3_x3_hypotheses.json")

@dataclass
class Hypothesis:
    label: str                 # к какому паттерну относится
    hid: str                   # id гипотезы
    text: str                  # краткая формулировка (НЕ вывод)
    source: str                # 'system' | 'user'
    confidence: float          # 0.0–1.0 (не истина, а вес)
    created_ts: int
    last_seen_ts: int
    active: bool = True

def _load() -> Dict[str, List[Dict[str, Any]]]:
    if not os.path.exists(HYP_PATH):
        return {}
    try:
        with open(HYP_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(HYP_PATH), exist_ok=True)
    with open(HYP_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def add_hypothesis(
    label: str,
    text: str,
    source: str = "system",
    confidence: float = 0.5,
) -> Hypothesis:
    now = int(time.time())
    hid = f"h_{now}_{abs(hash(text))%10000}"
    h = Hypothesis(
        label=label,
        hid=hid,
        text=text,
        source=source,
        confidence=float(confidence),
        created_ts=now,
        last_seen_ts=now,
        active=True,
    )
    obj = _load()
    obj.setdefault(label, [])
    obj[label].append(asdict(h))
    _save(obj)
    return h

def list_hypotheses(label: str, active_only: bool = True) -> List[Hypothesis]:
    obj = _load()
    raw = obj.get(label, [])
    out = []
    for r in raw:
        if active_only and not r.get("active", True):
            continue
        out.append(Hypothesis(**r))
    return out

def touch_hypothesis(label: str, hid: str) -> None:
    obj = _load()
    if label not in obj:
        return
    for r in obj[label]:
        if r.get("hid") == hid:
            r["last_seen_ts"] = int(time.time())
    _save(obj)

def deactivate_hypothesis(label: str, hid: str) -> None:
    obj = _load()
    if label not in obj:
        return
    for r in obj[label]:
        if r.get("hid") == hid:
            r["active"] = False
    _save(obj)

def has_competing(label: str, min_active: int = 2) -> bool:
    hs = list_hypotheses(label, active_only=True)
    return len(hs) >= int(min_active)

def top_hypotheses(label: str, k: int = 2) -> List[Hypothesis]:
    hs = list_hypotheses(label, active_only=True)
    hs.sort(key=lambda h: float(h.confidence), reverse=True)
    return hs[: int(k)]
