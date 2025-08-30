# backend/app/memory/manager_chroma.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
import os, time, uuid
import chromadb  # type: ignore
from chromadb.utils import embedding_functions  # type: ignore

from .chunker import chunk_text
from .embeddings_st import LocalSentenceTransformer


class _EF(embedding_functions.EmbeddingFunction):
    def __init__(self, st: LocalSentenceTransformer):
        self.st = st

    def __call__(self, texts: List[str]) -> List[List[float]]:
        return self.st.encode(texts)


class ChromaMemoryManager:
    def __init__(self, persist_dir: str, collection: str, model_path: str) -> None:
        os.makedirs(persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.st = LocalSentenceTransformer(model_path)
        self.ef = _EF(self.st)
        self.col = self.client.get_or_create_collection(
            name=collection,
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )
        # совместимость с кодом, который ожидает .collection
        self.collection = self.col

    # -------------------------
    # Bulk API для ingest_path(...)
    # -------------------------
    def add_texts(self, texts: List[str], metadatas: Optional[List[Dict[str, Any]]] = None, ids: Optional[List[str]] = None):
        if not texts:
            return
        metas = metadatas or [{} for _ in texts]
        if ids is None:
            ts = int(time.time())
            ids = [f"{ts}-{uuid.uuid4().hex}" for _ in texts]
        self.col.add(ids=ids, documents=texts, metadatas=metas)

    # -------------------------
    # Легаси API (используется фолбэком ingest_path, /chat и т.п.)
    # -------------------------
    def add_text(
        self,
        *,
        user_id: str,
        text: str,
        session_id: Optional[str] = None,
        source: str = "user",
        chunk_size: int = 800,
        chunk_overlap: int = 200,
    ) -> Dict[str, Any]:
        chunks = chunk_text(text, chunk_size, chunk_overlap)
        if not chunks:
            return {"ok": True, "added": 0}
        ids, docs, metas = [], [], []
        ts = int(time.time())
        sid = session_id or "na"
        for ch in chunks:
            cid = f"{ts}-{uuid.uuid4().hex}"
            ids.append(cid)
            docs.append(ch["text"])
            metas.append({
                "user_id": user_id,
                "session_id": sid,
                "source": source,
                "chunk_index": ch["index"],
                "created_at": ts,
            })
        self.col.add(ids=ids, documents=docs, metadatas=metas)
        return {"ok": True, "added": len(ids)}

    # -------------------------
    # Поиск для ретривера (возвращаем metadata 1:1 из стора)
    # -------------------------
def search(
    self,
    *,
    user_id: str,
    query: str,
    k: int = 4,
    score_threshold: float = 0.0,
    dedup: bool = True,
) -> Dict[str, Any]:
    qr = self.col.query(
        query_texts=[query],
        n_results=max(k * 2, k),
        # ВАЖНО: без where={"user_id": ...} — иначе ingest-доки отсекаются
        include=["documents", "metadatas", "distances", "ids"],
    )
    docs = (qr.get("documents") or [[]])[0]
    metas = (qr.get("metadatas") or [[]])[0]
    dists = (qr.get("distances") or [[]])[0]

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for doc, meta, dist in zip(docs, metas, dists):
        if not doc:
            continue
        sim = 1.0 - float(dist if dist is not None else 1.0)
        if score_threshold and sim < score_threshold:
            continue
        key = doc.strip().lower()[:160]
        if dedup and key in seen:
            continue
        seen.add(key)
        # ВАЖНО: ключ — "metadata", не "meta"
        out.append({"text": doc, "metadata": (meta or {}), "score": round(sim, 4)})
        if len(out) >= k:
            break
    return {"ok": True, "results": out}