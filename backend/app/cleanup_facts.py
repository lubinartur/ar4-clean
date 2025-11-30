from pathlib import Path
import json

PATH = Path("memory/facts_store.json")

TECH_MARKERS = (
    "phase",
    "фаза",
    "air4",
    "аир4",
    "profile",
    "профиль",
    "pipeline",
    "пайплайн",
    "тест",
    "test",
)

def is_tech_fact(obj: str) -> bool:
    t = (obj or "").lower()
    return any(m in t for m in TECH_MARKERS)

def main():
    if not PATH.exists():
        print(f"[CLEANUP] файл не найден: {PATH}")
        return

    raw = PATH.read_text(encoding="utf-8")
    data = json.loads(raw)

    # поддержим оба варианта: список или {"facts": [...]}
    if isinstance(data, dict) and "facts" in data:
        facts = data["facts"]
        wrap_dict = True
    elif isinstance(data, list):
        facts = data
        wrap_dict = False
    else:
        print("[CLEANUP] неизвестный формат facts_store.json")
        return

    before = len(facts)
    kept = []
    removed = []

    for f in facts:
        obj = ""
        try:
            obj = (f.get("object") or "").strip()
        except Exception:
            pass

        if obj and is_tech_fact(obj):
            removed.append(obj)
        else:
            kept.append(f)

    print(f"Всего фактов до чистки: {before}")
    print(f"Удаляем мусорных фактов: {before - len(kept)}")
    for o in removed:
        print("TRASH:", o)

    if wrap_dict:
        data["facts"] = kept
        PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        PATH.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Фактов после чистки: {len(kept)}")

if __name__ == "__main__":
    main()
