import time, hashlib
from typing import List, Dict, Any
from .embeddings import Embeddings
from .vectorstore import VectorStore
from .summarizer import summarize_turns

class MemoryManager:
    def __init__(self):
        self.vs = VectorStore()
        self.short_buffer: List[Dict[str, str]] = []
        self.profile: Dict[str, Any] = {"goals": [], "facts": {}}

    # ---- Short-term ----
    def push_short(self, role: str, content: str, max_len: int = 12):
        self.short_buffer.append({"role": role, "content": content})
        if len(self.short_buffer) > max_len:
            self.short_buffer.pop(0)

    def short_context(self) -> str:
        return "\n".join([f"{m['role']}: {m['content']}" for m in self.short_buffer])

    def short_summary(self) -> str:
        return summarize_turns([m["content"] for m in self.short_buffer])

    # ---- Long-term ----
    def ingest(self, text: str, meta: Dict[str, Any]) -> str:
        emb = Embeddings.encode([text])[0]
        doc_id = hashlib.sha256(f"{time.time()}::{text[:64]}".encode()).hexdigest()[:16]
        self.vs.add([doc_id], [text], [emb], [meta])
        return doc_id

    def retrieve(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        q_emb = Embeddings.encode([query])[0]
        res = self.vs.query(q_emb, k)
        out = []
        for doc, meta, dist, _id in zip(res["documents"][0], res["metadatas"][0], res["distances"][0], res["ids"][0]):
            out.append({"id": _id, "text": doc, "meta": meta, "score": 1 - dist})
        return out

    # ---- Profile ----
    def upsert_profile(self, patch: Dict[str, Any]):
        for k,v in patch.items():
            if isinstance(v, dict):
                self.profile.setdefault(k, {}).update(v)
            elif isinstance(v, list):
                self.profile.setdefault(k, [])
                self.profile[k].extend(v)
            else:
                self.profile[k] = v
        return self.profile

    def profile_text(self) -> str:
        return f"Goals: {self.profile.get('goals', [])}\nFacts: {self.profile.get('facts', {})}"

