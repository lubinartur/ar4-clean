from memory.facts import _load_facts, add_fact, Fact


def reindex():
    facts = _load_facts()
    print(f"[REINDEX] Loaded {len(facts)} facts")

    for f in facts:
        # add_fact сам:
        #  - проверит дубликаты
        #  - перезапишет timestamp
        #  - и самое главное: отправит текст в MEMORY.add_text(...)
        try:
            add_fact(f)
            print("[OK]", f"{f.subject} {f.predicate.replace('_', ' ')} {f.object}")
        except Exception as e:
            print("[ERR]", f"{f.subject} {f.predicate} {f.object}", "->", e)

    print("\n[REINDEX] Completed")


if __name__ == "__main__":
    reindex()