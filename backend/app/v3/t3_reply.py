from typing import Optional
from .t3_commands import parse_t3_command, apply_t3_command

def handle_t3_reply(text: str) -> Optional[str]:
    cmd = parse_t3_command(text or "")
    if not cmd:
        return None

    res = apply_t3_command(cmd)
    if not res.get("ok"):
        return "Не нашёл (label/pattern_id)."

    op = res["op"]
    if op == "list":
        a = res.get("archive", [])
        p = res.get("purge", [])
        lines = []
        lines.append(f"Кандидаты на архивирование: {len(a)}")
        for it in a[:5]:
            lines.append(f"- {it['label']} ({it['confidence']}, {it['days_since_seen']}d)")
        lines.append(f"\nКандидаты на удаление: {len(p)}")
        for it in p[:5]:
            lines.append(f"- {it['pattern_id']} {it['label']} ({it['days_since_updated']}d)")
        return "\n".join(lines)

    if op == "archive":
        return f"Ок. Архивировал **{res['label']}** (id={res['pattern_id']})."

    if op == "purge":
        return f"Ок. Удалил паттерн {res['pattern_id']} (label=**{res.get('label','')}**)."

    return "Ок."
