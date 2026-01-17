from typing import Optional

from .v3_override_commands import parse_override_command, apply_override_command

def handle_override_reply(text: str) -> Optional[str]:
    cmd = parse_override_command(text or "")
    if not cmd:
        return None

    res = apply_override_command(cmd)
    if not res.get("ok"):
        if res.get("error") == "not_found":
            return "Не нашёл такой override (oid)."
        return None

    op = res["op"]
    if op == "set":
        return f"Ок. Override создан: {res['oid']} (kind={res['kind']}, label=**{res['label']}**)."
    if op == "remove":
        return f"Ок. Override снят: {res['oid']} (label=**{res['label']}**)."
    if op == "clear":
        return f"Ок. Overrides для **{res['label']}** очищены."
    if op == "list":
        items = res.get("items", [])
        if not items:
            return f"Для **{res['label']}** overrides нет."
        lines = []
        for it in items:
            st = "ON" if it["active"] else "off"
            lines.append(f"- {it['oid']} [{st}] {it['kind']}: {it['value']}")
        return f"Overrides для **{res['label']}**:\n{chr(10).join(lines)}"

    return "Ок."
