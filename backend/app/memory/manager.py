# backend/app/memory/manager.py
from __future__ import annotations
import os, json, hashlib, time
from typing import List, Dict, Any, Optional

# Принцип: истории хранятся как раньше.
# Саммари/факты/туду — простым JSON + легкий дедуп. Если у тебя Chroma — оставь как есть и используй эти методы как фасад.

_STORAGE = os.getenv("STORAGE_DIR", "storage")
_SUM_DIR = os.path.join(_STORAGE, "summaries")
_FACTS_FILE = os.path.join(_STORAGE, "facts.jsonl")
_TODOS_FILE = os.path.join(_STORAGE, "todos.jsonl")
_HISTORY_DIR = os.path.join(_STORAGE, "history")

os.makedirs(_SUM_DIR, exist_ok=True)
os.makedirs(_HISTORY_DIR, exist_ok=True)
os.makedirs(_STORAGE, exist_ok=True)

def _sid_file(session_id: str, user_id: str) -> str:
    return os.path.join(_SUM_DIR, f"{user_id}__{session_id}.json")

def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

class MemoryManager:
    # ==== История ====
    def fetch_history(self, user_id: str, session_id: Optional[str], k: int = 20) -> List[Dict[str, str]]:
        if not session_id: return []
        path = os.path.join(_HISTORY_DIR, f"{user_id}__{session_id}.jsonl")
        if not os.path.exists(path): return []
        lines = open(path, "r", encoding="utf-8").read().splitlines()
        rows = [json.loads(x) for x in lines[-k:]]
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def append_turn(self, user_id: str, session_id: Optional[str], role: str, content: str) -> None:
        if not session_id: return
        path = os.path.join(_HISTORY_DIR, f"{user_id}__{session_id}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "role": role, "content": content}, ensure_ascii=False) + "\n")

    # ==== Summary ====
    def save_summary(self, user_id: str, session_id: str, summary: Dict[str, Any]) -> None:
        fp = _sid_file(session_id, user_id)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    def get_summary(self, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        fp = _sid_file(session_id, user_id)
        if not os.path.exists(fp): return None
        try:
            return json.load(open(fp, "r", encoding="utf-8"))
        except Exception:
            return None

    # ==== Facts / TODOs с дедупом по хэшу текста ====
    def _dedup_append(self, path: str, payload: Dict[str, Any], key_text: str) -> None:
        line_hash = _hash(key_text)
        payload["hash"] = line_hash
        payload["ts"] = time.time()
        payload["text"] = key_text
        # простейший дедуп: проверяем есть ли такой хэш в файле
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        if json.loads(line).get("hash") == line_hash:
                            return
                    except Exception:
                        continue
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def add_facts(self, user_id: str, session_id: str, facts: List[str], tags: List[str], dedup: bool = True) -> None:
        for fact in facts:
            self._dedup_append(_FACTS_FILE, {
                "user_id": user_id, "session_id": session_id, "tags": tags or []
            }, fact.strip())

    def add_todos(self, user_id: str, session_id: str, todos: List[str], tags: List[str], dedup: bool = True) -> None:
        for todo in todos:
            self._dedup_append(_TODOS_FILE, {
                "user_id": user_id, "session_id": session_id, "done": False, "tags": tags or []
            }, todo.strip())
