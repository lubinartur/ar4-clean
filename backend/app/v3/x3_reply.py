from typing import Optional

from .x3_commands import parse_x3_command, apply_x3_command

def handle_x3_reply(text: str) -> Optional[str]:
    cmd = parse_x3_command(text or "")
    if not cmd:
        return None

    res = apply_x3_command(cmd)
    if not res.get("ok"):
        if res.get("error") == "not_found":
            return "Не нашёл такую гипотезу (hid)."
        return None

    op = res["op"]
    if op == "add":
        return f"Ок. Гипотеза добавлена: {res['hid']} (label=**{res['label']}**)."
    if op == "remove":
        return f"Ок. Гипотеза отключена: {res['hid']} (label=**{res['label']}**)."
    if op == "list":
        items = res.get("items", [])
        if not items:
            return f"Для **{res['label']}** активных гипотез нет."
        lines = [f"- {it['hid']} ({it['confidence']:.2f}): {it['text']}" for it in items]
        return f"Гипотезы для **{res['label']}**:\n" + "\n".join(lines)

    return "Ок."
