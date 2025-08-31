from __future__ import annotations
import os
from functools import lru_cache
from typing import List
import numpy as np
from FlagEmbedding import BGEM3FlagModel

MODEL_PATH = os.getenv("EMBEDDING_MODEL_PATH", "models/bge-m3")

@lru_cache(maxsize=1)
def _model() -> BGEM3FlagModel:
    # fp16 ок на Mac (CPU/MPS). Если будут варнинги — снимем.
    return BGEM3FlagModel(MODEL_PATH, use_fp16=True)

def embed(texts: List[str]) -> list[list[float]]:
    out = _model().encode(texts, batch_size=min(32, len(texts)))
    vecs = out["dense_vecs"]
    # L2-нормировка для косинусной близости / inner product
    vecs = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-12)
    return vecs.tolist()
