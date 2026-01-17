from typing import Optional
from .s3_commands import parse_s3_command, apply_s3_command

def handle_s3_reply(text: str) -> Optional[str]:
    cmd = parse_s3_command(text or "")
    if not cmd:
        return None

    res = apply_s3_command(cmd)
    if not res.get("ok"):
        if res.get("error") == "not_found":
            return "Не нашёл паттерн по label (сначала закрепи)."
        return None

    op = res["op"]
    if op == "pin":
        return f"Ок. Закрепил паттерн **{res['label']}** (id={res['pattern_id']})."
    if op == "status":
        return f"Ок. Статус **{res['label']}** → {res['status']}."
    if op == "promote":
        return f"Ок. Продвинул паттерн **{res['label']}** (id={res['pattern_id']}, c={res['confidence']:.2f})."
    if op == "list":
        items = res.get("items", [])
        if not items:
            return "Паттернов нет."
        lines = [f"- {it['pattern_id']} [{it['status']}] {it['label']} (c={it['confidence']:.2f})" for it in items]
        return "Паттерны:\n" + "\n".join(lines)

    return "Ок."
