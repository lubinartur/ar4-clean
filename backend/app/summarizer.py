# backend/app/summarizer.py
from __future__ import annotations
from typing import List, Dict, Optional, Tuple
import time, hashlib, re

import chromadb

try:
    from FlagEmbedding import BGEM3FlagModel  # если есть из Фазы 2 — используем
    _HAS_BGE = True
except Exception:
    _HAS_BGE = False


def _now() -> float:
    return time.time()

def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

def _clean(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


class AutoSummarizer:
    """
    Короткие конспекты сессий -> Chroma (коллекция 'air4_summaries').
    Если LLM нет — делаем простую экстракцию.
    """

    def __init__(
        self,
        chroma_dir: str = ".chroma",
        collection: str = "air4_summaries",
        llm_call=None,
        bge_device: str = "cpu"
    ):
        self.client = chromadb.PersistentClient(path=chroma_dir)
        # Без явной embedding_function Chroma использует дефолтную (ок для старта)
        self.col = self.client.get_or_create_collection(collection)
        self.llm_call = llm_call
        self._embedder = (
            BGEM3FlagModel("BAAI/bge-m3", use_fp16=False, device=bge_device) if _HAS_BGE else None
        )

    # ---- публичное ----
    def summarize_session(
        self,
        messages: List[Dict],
        user_id: str = "default",
        session_id: Optional[str] = None,
        max_bullets: int = 6,
        max_chars_src: int = 2000
    ) -> Dict:
        """
        Создаёт саммари и сохраняет. Возвращает dict с id, summary, metadata.
        """
        session_id = session_id or _derive_session_id(messages)
        src = _tail_text(messages, max_chars=max_chars_src)
        summary = self._llm_summary(src, max_bullets=max_bullets)

        ts = int(_now())
        doc_id = f"sum_{user_id}_{session_id}_{ts}_{_hash(summary)}"
        meta = {"user_id": user_id, "session_id": session_id, "created_at": ts, "type": "summary"}

        if self._embedder:
            emb = self._embedder.encode([summary], batch_size=1, max_length=512, return_dense=True)["dense_vecs"][0]
            self.col.add(ids=[doc_id], documents=[summary], metadatas=[meta], embeddings=[emb])
        else:
            # положим без эмбеддингов — коллекция сама сделает по умолчанию (достаточно для MVP)
            self.col.add(ids=[doc_id], documents=[summary], metadatas=[meta])

        return {"id": doc_id, "summary": summary, "metadata": meta}

    def recent(self, user_id: str = "default", limit: int = 3) -> List[Tuple[str, Dict]]:
        """
        Возвращает последние N саммари как [(text, metadata), ...], сортируя по created_at.
        """
        res = self.col.get(where={"user_id": user_id})
        rows = []
        for i, text in enumerate(res.get("documents", [])):
            md = res["metadatas"][i]
            rows.append((text, md))
        rows.sort(key=lambda x: x[1].get("created_at", 0), reverse=True)
        return rows[:limit]

    # ---- внутреннее ----
    def _llm_summary(self, text: str, max_bullets: int = 6) -> str:
        text = _clean(text)
        if not text:
            return "• (пусто)"

        # 1) если есть llm_call — пробуем им
        if self.llm_call:
            prompt = (
                "Сделай краткий конспект из 5–"
                f"{max_bullets} буллетов. Только факты, решения, статусы, TODO. Без воды.\n\nТекст:\n" + text
            )
            try:
                s = (self.llm_call(prompt) or "").strip()
                if s:
                    return s
            except Exception:
                pass

        # 2) fallback — простая экстракция предложений
        return _extractive_bullets(text, max_bullets=max_bullets)


def _derive_session_id(messages: List[Dict]) -> str:
    for m in messages:
        md = m.get("metadata") or {}
        if md.get("session_id"):
            return str(md["session_id"])
    if messages:
        base = (messages[0].get("content", "") + messages[-1].get("content", "")) or str(_now())
        return _hash(base)
    return _hash(str(_now()))

def _tail_text(messages: List[Dict], max_chars: int = 2000) -> str:
    """
    Берём хвост беседы, НО пропускаем system-сообщения,
    чтобы в саммари не попадала “Короткая память ...”.
    """
    buf: List[str] = []
    total = 0
    for m in reversed(messages):
        if (m.get('role') or '').lower() == 'system':
            continue
        line = f"{m.get('role','user')}: {m.get('content','')}\n"
        if total + len(line) > max_chars:
            break
        buf.insert(0, line)
        total += len(line)
    return "".join(buf).strip()

def _extractive_bullets(text: str, max_bullets: int = 6) -> str:
    # очень простая эвристика: берём “содержательные” предложения
    sents = re.split(r"(?<=[\.\!\?])\s+", text)
    scored = []
    kws = ("сделать","этап","итог","важно","дальше","план","шаг","ошибка","решение","статус","todo")
    for s in sents:
        if not s.strip():
            continue
        score = len(s) ** 0.4
        low = s.lower()
        score += sum(1 for k in kws if k in low) * 1.8
        scored.append((score, s.strip()))
    top = [s for _, s in sorted(scored, key=lambda x: x[0], reverse=True)[:max_bullets]]
    return "\n".join(f"• {t}" for t in top) or f"• {text[:200]}"

