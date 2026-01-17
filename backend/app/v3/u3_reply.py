import time
from typing import Optional

from .u3_commands import parse_u3_command, apply_u3_command

def _fmt_date(ts: int) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(int(ts)))

def handle_u3_reply(text: str) -> Optional[str]:
    """
    Returns short confirmation string if a U3 command was applied, else None.
    """
    cmd = parse_u3_command(text or "")
    if not cmd:
        return None

    ok = apply_u3_command(cmd)
    if not ok:
        return None

    op = cmd["op"]
    label = cmd["label"]

    if op == "mute":
        return f"Ок. Не возвращаюсь к **{label}**."
    if op == "unmute":
        return f"Ок. **{label}** снова можно поднимать."
    if op == "defer":
        return f"Ок. **{label}** не трогаю до {_fmt_date(cmd['until_ts'])}."
    if op == "clear_defer":
        return f"Ок. Отсрочка для **{label}** снята."
    if op == "allow_only":
        mode = cmd.get("mode")
        if mode is None:
            return f"Ок. Ограничение режима для **{label}** снято."
        if mode == "q3":
            return f"Ок. **{label}** поднимаю только внутри-сессионно (Q3)."
        if mode == "r3":
            return f"Ок. **{label}** поднимаю только межсессионно (R3)."
    return "Ок."
