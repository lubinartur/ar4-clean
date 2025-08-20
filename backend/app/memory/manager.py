# backend/app/memory/manager.py
from __future__ import annotations

import time, hashlib
from typing import List, Dict, Any, Optional

from .embeddings import Embeddings
from .vectorstore import VectorStore
from .summarizer import summarize_turns


class MemoryManager:
    """
    Единая точка работы с памятью:
    - краткосрочный буфер (short_buffer)
    - долгосрочная память (Chroma через VectorStore)
    - профиль пользователя (goals/facts)
    """

    def __init__(self):
        self.vs = VectorStore()
        self.short_buffer: List[Dict[str, str]] = []
        self.profile: Dict[str, Any] = {"goals": [], "facts": {}}

    # ---------- Short-term ----------
    def push_short(self, role: str, content: str, max_len: int = 12):
        self.short_buffer.append({"role": role, "content": content})
        if len(self.short_buffer) > max_len:
            self.short_buffer.pop(0)

    def short_context(self) -> str:
        return "\n".join(f"{m['role']}: {m['content']}" for m in self.short_buffer)

    def short_summary(self) -> str:
        return summarize_turns([m["content"] for m in self.short_buffer])

    # ---------- Long-term: ingest ----------
    def _gen_id(self, text: str) -> str:
        return hashlib.sha256(f"{time.time()}::{text[:64]}".encode()).hexdigest()[:16]

    def ingest(self, text: str, meta: Dict[str, Any]) -> str:
        """
        Добавить одиночный кусок текста в память.
        """
        emb = Embeddings.encode([text])[0]
        doc_id = self._gen_id(text)
        self.vs.add([doc_id], [text], [emb], [meta])
        return doc_id

    def ingest_many(self, texts: List[str], metas: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        """
        Добавить батч текстов. metas по длине = texts или None (тогда пустые dict).
        """
        if not texts:
            return []
        metas = metas or [{} for _ in texts]
        embs = Embeddings.encode(texts)
        ids = [self._gen_id(t) for t in texts]
        self.vs.add(ids, texts, embs, metas)
        return ids

    # ---------- Long-term: retrieve ----------
    def retrieve(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Базовый поиск по близости. Возвращает подробные записи.
        """
        q_emb = Embeddings.encode([query])[0]
        res = self.vs.query(q_emb, k)
        out: List[Dict[str, Any]] = []
        for doc, meta, dist, _id in zip(
            res.get("documents", [[]])[0],
            res.get("metadatas",  [[]])[0],
            res.get("distances",  [[]])[0],
            res.get("ids",        [[]])[0],
        ):
            out.append({"id": _id, "text": doc, "meta": meta, "score": 1 - dist})
        return out

    def retrieve_relevant(self, user_id: str, query: str, k: int = 6) -> List[str]:
        """
        Упрощённый интерфейс для чата: только тексты, с фильтром по user_id (если он в метаданных).
        """
        try:
            items = self.retrieve(query=query, k=max(1, k))
            # если в метаданных есть user_id — фильтруем
            filtered = [
                it for it in items
                if not isinstance(it.get("meta"), dict) or it["meta"].get("user_id") in (None, user_id)
            ]
            texts = [it["text"] for it in filtered] or [it["text"] for it in items]
            return texts[:k]
        except Exception:
            return []

    # ---------- Profile ----------
    def upsert_profile(self, patch: Dict[str, Any]):
        for k, v in patch.items():
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


# --------- Глобальный синглтон + удобные функции для main.py ---------
_MM = MemoryManager()

def add_memory(user_id: str, texts: List[str], metas: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    """
    Утилита для массового добавления с проставлением user_id в метаданные.
    """
    metas = metas or [{} for _ in texts]
    for m in metas:
        m.setdefault("user_id", user_id)
    return _MM.ingest_many(texts, metas)

def retrieve_relevant(user_id: str, query: str, k: int = 6) -> List[str]:
    """
    То, что ожидает /chat: список подходящих текстов.
    """
    return _MM.retrieve_relevant(user_id=user_id, query=query, k=k)
