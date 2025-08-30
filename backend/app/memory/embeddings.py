from typing import List
import torch
from sentence_transformers import SentenceTransformer

class Embeddings:
    _model = None

    @classmethod
    def load(cls):
        if cls._model is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            cls._model = SentenceTransformer("BAAI/bge-m3", device=device)
        return cls._model

    @classmethod
    def encode(cls, texts: List[str]) -> List[List[float]]:
        model = cls.load()
        emb = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return emb.tolist()

