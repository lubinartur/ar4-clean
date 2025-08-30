from typing import List, Optional
import os

class LocalSentenceTransformer:
    """Локальная обёртка над SentenceTransformers без онлайн-скачивания."""
    def __init__(self, model_path: str, device: Optional[str] = None):
        if not model_path or not os.path.isdir(model_path):
            raise RuntimeError(
                f"AIR4: локальная модель не найдена: {model_path}. "
                "Скопируй веса ST в локальную папку и укажи AIR4_EMBED_MODEL_PATH."
            )
        from sentence_transformers import SentenceTransformer  # type: ignore
        self.model = SentenceTransformer(model_path, device=device or "cpu")

    def encode(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        vecs = self.model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return vecs.tolist()
