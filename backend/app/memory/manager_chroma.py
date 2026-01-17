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
        self.collection = self.col  # совместимость с legacy-кодом

    def get_collection(self) -> Any:
        """
        Phase E: Get the active Chroma collection instance.
        Returns the live collection object used for add/search operations.
        """
        return self.col

    @staticmethod
    def _normalize_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase E: Normalize metadata to ensure namespace and tag are always present.
        
        Namespace derivation (stable, minimal):
        - source == "facts" -> namespace="facts"
        - source == "note" -> namespace="notes"
        - source == "summary" -> namespace="sessions"
        - source in ["ingest","file","url"] -> namespace="ingest"
        - source in ["user","assistant"] -> namespace="chat"
        - else -> namespace="general"
        
        Tag: default to "general" if missing/empty.
        """
        normalized = dict(meta)  # Copy to avoid mutating input
        
        # Derive namespace from source field
        source = normalized.get("source", "").lower()
        if source == "facts":
            normalized["namespace"] = "facts"
        elif source == "note":
            normalized["namespace"] = "notes"
        elif source == "summary":
            normalized["namespace"] = "sessions"
        elif source in ("ingest", "file", "url"):
            normalized["namespace"] = "ingest"
        elif source in ("user", "assistant"):
            normalized["namespace"] = "chat"
        else:
            normalized["namespace"] = "general"
        
        # Ensure tag is always present
        if not normalized.get("tag") or not normalized.get("tag").strip():
            normalized["tag"] = "general"
        
        return normalized

    # -------------------------
    # Bulk API для ingest_path(...)
    # -------------------------
    def add_texts(self, texts: List[str], metadatas: Optional[List[Dict[str, Any]]] = None, ids: Optional[List[str]] = None):
        if not texts:
            return
        
        metas = metadatas or [{} for _ in texts]
        # Enforce session_id in metadata for all records
        for i, meta in enumerate(metas):
            if "session_id" not in meta or not meta.get("session_id"):
                raise ValueError(f"session_id is required in metadata at index {i} for all memory records")
            # Phase E: Normalize metadata (add namespace, ensure tag)
            metas[i] = self._normalize_metadata(meta)
        
        # Write guards: validate all texts
        for i, text in enumerate(texts):
            if not text or not isinstance(text, str):
                raise ValueError(f"text at index {i} is required and must be a non-empty string")
            text_stripped = text.strip()
            if not text_stripped:
                raise ValueError(f"text at index {i} cannot be empty or whitespace-only")
            if len(text_stripped) < 5:
                raise ValueError(f"text at index {i} must be at least 5 characters long")
        
        # Check for duplicates within the same session
        # Group by session_id to check duplicates per session
        session_to_items: Dict[str, List[tuple]] = {}
        for idx, (text, meta) in enumerate(zip(texts, metas)):
            sid = meta.get("session_id")
            if sid not in session_to_items:
                session_to_items[sid] = []
            session_to_items[sid].append((idx, text, meta))
        
        # Filter out duplicates per session
        final_texts = []
        final_metas = []
        final_indices = []
        for sid, group in session_to_items.items():
            # Get existing documents for this session
            existing = self.col.get(
                where={"session_id": sid},
                include=["documents"]
            )
            existing_docs = existing.get("documents") or []
            existing_normalized = {doc.strip().lower() for doc in existing_docs if doc}
            
            for orig_idx, text, meta in group:
                text_normalized = text.strip().lower()
                if text_normalized not in existing_normalized:
                    final_texts.append(text)
                    final_metas.append(meta)
                    final_indices.append(orig_idx)
                    existing_normalized.add(text_normalized)  # Prevent duplicates in this batch
        
        if not final_texts:
            return  # All were duplicates
        
        if ids is None:
            ts = int(time.time())
            final_ids = [f"{ts}-{uuid.uuid4().hex}" for _ in final_texts]
        else:
            # Use IDs for non-duplicate texts
            final_ids = [ids[i] for i in final_indices]
        
        # Ensure metadata is always a dict (defensive check)
        final_metas_clean = [m if isinstance(m, dict) else {} for m in final_metas]
        
        # Ensure all lists have the same length
        assert len(final_ids) == len(final_texts) == len(final_metas_clean), "List length mismatch in add_texts"
        
        self.col.add(ids=final_ids, documents=final_texts, metadatas=final_metas_clean)

    # -------------------------
    # Легаси API (используется фолбэком ingest_path, /chat и т.п.)
    # -------------------------
    def add_text(
        self,
        *,
        user_id: str,
        text: str,
        session_id: str,  # Required: no default, no Optional
        source: str = "user",
        chunk_size: int = 6000,       # увеличено для Phase-12
        chunk_overlap: int = 800,     # увеличено
    ) -> Dict[str, Any]:
        if not session_id:
            raise ValueError("session_id is required and cannot be empty")
        
        # Write guards: validate text input
        if not text or not isinstance(text, str):
            raise ValueError("text is required and must be a non-empty string")
        text_stripped = text.strip()
        if not text_stripped:
            raise ValueError("text cannot be empty or whitespace-only")
        if len(text_stripped) < 5:
            raise ValueError("text must be at least 5 characters long")
        
        # Check for duplicates within the same session
        # Normalize text for comparison (strip and lowercase)
        text_normalized = text_stripped.lower()
        # Search for exact matches in this session
        existing = self.col.get(
            where={"session_id": session_id},
            include=["documents"]
        )
        existing_docs = existing.get("documents") or []
        # Check if normalized text already exists
        for existing_doc in existing_docs:
            if existing_doc and existing_doc.strip().lower() == text_normalized:
                return {"ok": True, "added": 0, "skipped": True}
        
        chunks = chunk_text(text, chunk_size, chunk_overlap)
        if not chunks:
            return {"ok": True, "added": 0}
        ids, docs, metas = [], [], []
        ts = int(time.time())
        sid = session_id
        for ch in chunks:
            cid = f"{ts}-{uuid.uuid4().hex}"
            ids.append(cid)
            docs.append(ch["text"])
            raw_meta = {
                "user_id": user_id,
                "session_id": sid,
                "source": source,
                "chunk_index": ch["index"],
                "created_at": ts,
            }
            # Phase E: Normalize metadata (add namespace, ensure tag)
            normalized_meta = self._normalize_metadata(raw_meta)
            metas.append(normalized_meta if isinstance(normalized_meta, dict) else {})
        
        # Ensure all lists have the same length
        assert len(ids) == len(docs) == len(metas), "List length mismatch in add_text"
        
        self.col.add(ids=ids, documents=docs, metadatas=metas)
        return {"ok": True, "added": len(ids)}

    # -------------------------
    # Поиск Phase-12
    # -------------------------
    def search(
        self,
        *,
        user_id: str,
        query: str,
        session_id: str,  # Required for session isolation
        k: int = 5,
        score_threshold: float = 0.0,
        dedup: bool = True,
    ) -> Dict[str, Any]:
        if not session_id:
            raise ValueError("session_id is required for memory search")
        # Query with session_id filter in where clause
        qr = self.col.query(
            query_texts=[query],
            n_results=max(k * 2, k),
            where={"session_id": session_id},  # Filter by session_id
            include=["documents", "metadatas", "distances"],
        )
        ids = (qr.get("ids") or [[]])[0]
        docs = (qr.get("documents") or [[]])[0]
        metas = (qr.get("metadatas") or [[]])[0]
        dists = (qr.get("distances") or [[]])[0]

        out: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item_id, doc, meta, dist in zip(ids, docs, metas, dists):
            if not doc:
                continue
            # Additional safety check: ensure metadata matches session_id
            meta_dict = meta or {}
            if meta_dict.get("session_id") != session_id:
                continue  # Skip records from other sessions (defense in depth)
            sim = 1.0 - float(dist if dist is not None else 1.0)
            if score_threshold and sim < score_threshold:
                continue
            key = doc.strip().lower()[:160]
            if dedup and key in seen:
                continue
            seen.add(key)
            out.append({
                "id": item_id,
                "text": doc,
                "meta": meta_dict,
                "metadata": meta_dict,
                "score": round(sim, 4),
            })
            if len(out) >= k:
                break
        return {"ok": True, "results": out}