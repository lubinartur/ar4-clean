from pathlib import Path
import re
CHAT = Path("backend/app/chat.py")
t = CHAT.read_text(encoding="utf-8")
changed = False

imp = "from backend.app.routes_profile import load_profile as _load_user_profile"
if imp not in t:
    lines = t.splitlines(True)
    import_end = 0
    for i, L in enumerate(lines[:200]):
        if L.startswith("import ") or L.startswith("from "):
            import_end = i
    lines.insert(import_end+1, imp + "\\n")
    t = "".join(lines)
    changed = True

if "def _profile_block_from_request(" not in t:
    helper = [
        "",
        "def _profile_block_from_request(headers)->str:",
        "    try:",
        "        user_id = headers.get(\\"X-User\\", \\"dev\\")",
        "    except Exception:",
        "        user_id = \\"dev\\"",
        "    try:",
        "        prof = _load_user_profile(user_id)",
        "    except Exception:",
        "        return \\"\\"",
        "    prefs = getattr(prof, \\"preferences\\", {}) or {}",
        "    facts = getattr(prof, \\"facts\\", {}) or {}",
        "    goals = getattr(prof, \\"goals\\", []) or []",
        "    parts = []",
        "    if getattr(prof, \\"name\\", None): parts.append(f\\"name={prof.name}\\")",
        "    if prefs: parts.append(\\"prefs=\\" + \\",\\".join([f\\"{k}:{v}\\" for k,v in list(prefs.items())[:5]]))",
        "    if facts: parts.append(\\"facts=\\" + \\",\\".join([f\\"{k}:{v}\\" for k,v in list(facts.items())[:6]]))",
        "    if goals: parts.append(\\"goals=\\" + \\"; \\".join([getattr(g, \\"title\\", getattr(g, \\"id\\", \\"\\")) for g in goals][:3]))",
        "    return (\\"USER_PROFILE: \\" + \\" | \\".join(parts)) if parts else \\"\\"",
    ]
    t += "\\n".join(helper) + "\\n"
    changed = True

sig_old = "def build_messages(system: Optional[str], memory_blocks: List[str], user_text: str) -> List[dict]:"
sig_new = "def build_messages(system: Optional[str], memory_blocks: List[str], user_text: str, _headers: dict | None = None) -> List[dict]:"
if sig_old in t and sig_new not in t:
    t = t.replace(sig_old, sig_new)
    anchor = sig_new
    idx = t.index(anchor) + len(anchor)
    inject = "\\n    profile_block = _profile_block_from_request(_headers or {})\\n    if profile_block:\\n        system = (system + \\"\\\\n\\" + profile_block) if system else profile_block\\n"
    t = t[:idx] + inject + t[idx:]
    changed = True

if "_headers=dict(request.headers)" not in t:
    t2, n = re.subn(r"messages\\s*=\\s*build_messages\\(([^\\n]+)\\)", r"messages = build_messages(\\1, _headers=dict(request.headers))", t, count=1)
    if n:
        t = t2
        changed = True

if changed:
    CHAT.write_text(t, encoding="utf-8")
    print("chat.py patched")
else:
    print("chat.py unchanged")
