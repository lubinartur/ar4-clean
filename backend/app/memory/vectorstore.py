import os
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings

CHROMA_DIR = os.getenv("CHROMA_DIR", os.path.join(os.getcwd(), "storage", "chroma"))
COLLECTION = os.getenv("CHROMA_COLLECTION", "longterm_v1")

class VectorStore:
    def __init__(self):
        os.makedirs(CHROMA_DIR, exist_ok=True)
        self.client = chromadb.PersistentClient(path=CHROMA_DIR, settings=Settings(allow_reset=False))
        self.col = self.client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    def add(self, ids: List[str], texts: List[str], embeddings: List[List[float]], meta: List[Dict[str, Any]]):
        self.col.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=meta)

    def query(self, text_embedding: List[float], k: int = 5):
        return self.col.query(query_embeddings=[text_embedding], n_results=k)

