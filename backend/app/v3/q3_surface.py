import time
from typing import Any, Dict, Optional

def _fmt_date(ts: int) -> str:
    # ISO-like date only, user-safe
    return time.strftime("%Y-%m-%d", time.localtime(ts))

def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    n10 = n % 10
    n100 = n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not (12 <= n100 <= 14):
        return few
    return many

def _fmt_n(n: int, one: str, few: str, many: str) -> str:
    return f"{n} {_ru_plural(n, one, few, many)}"

def format_surface_fact(r: Dict[str, Any]) -> str:
    """
    r is a dict from repeats_summary/surface_candidates:
    label, count, unique_days, window_days, first_ts, last_ts
    Output: 1–2 lines. No advice. No interpretation.
    """
    label = r.get("label", "unknown")
    count = int(r.get("count", 0))
    ud = int(r.get("unique_days", 0))
    win = int(r.get("window_days", 0))
    first_ts = int(r.get("first_ts", 0))
    last_ts = int(r.get("last_ts", 0))

    # Minimal, factual, time-bounded
    count_txt = _fmt_n(count, "раз", "раза", "раз")
    # Для "в ..." нужен предложный падеж ("днях"), не винительный
    ud_text = f"{ud} {_ru_plural(ud, 'дне', 'днях', 'днях')}"
    win_txt = _fmt_n(win, "день", "дня", "дней")

    line1 = f"Повтор за {win_txt}: **{label}** — {count_txt} (в {ud_text})."
    if first_ts and last_ts:
        line2 = f"Диапазон: {_fmt_date(first_ts)} → {_fmt_date(last_ts)}."
        return f"{line1}\n{line2}"
    return line1

def format_cross_session_fact(r: Dict[str, Any]) -> str:
    label = r.get("label", "unknown")
    count = int(r.get("count", 0))
    ud = int(r.get("unique_days", 0))
    us = int(r.get("unique_sessions", 0))
    win = int(r.get("window_days", 0))
    first_ts = int(r.get("first_ts", 0))
    last_ts = int(r.get("last_ts", 0))

    count_txt = _fmt_n(count, "раз", "раза", "раз")
    # prepositional case for "в ..."
    days_txt = _fmt_n(ud, "дне", "днях", "днях")
    sess_txt = _fmt_n(us, "сессии", "сессиях", "сессиях")
    win_txt = _fmt_n(win, "день", "дня", "дней")

    line1 = f"Межсессионный повтор за {win_txt}: **{label}** — {count_txt} (в {days_txt}, в {sess_txt})."
    if first_ts and last_ts:
        line2 = f"Диапазон: {_fmt_date(first_ts)} → {_fmt_date(last_ts)}."
        return f"{line1}\n{line2}"
    return line1

def format_surface_question() -> str:
    # keep it optional and neutral
    return "Хочешь: (a) закрепить как паттерн, (b) игнорировать, (c) не трогать?"

def default_actions_hint(label: str) -> list[str]:
    # strict, copy-pastable commands
    return [
        f"не возвращайся к {label}",
        f"пока не трогай {label} до 2026-02-10",
        f"снять ограничение {label}",
    ]
