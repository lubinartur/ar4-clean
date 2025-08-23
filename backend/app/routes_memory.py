# backend/app/routes_memory.py
# Memory API: /memory/add, /memory/search
# Работает в двух режимах:
# 1) "chroma" — если доступны backend.app.memory.embeddings/vectorstore
# 2) "fallback" — простой локальный индекс (JSONL + мешок слов + косинус)
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/memory", tags=["memory"])

# ------------------------------ режимы ---------------------------------------
# Принудительный фоллбек (без внешних зависимостей):
_FORCE_FALLBACK = os.getenv("AIR4_MEMORY_FORCE_FALLBACK", "0") == "1"

_USE_REAL_STACK = not _FORCE_FALLBACK
_real_emb = None
_real_store = None
if _USE_REAL_STACK:
    try:
        # Эти модули уже есть у тебя в проекте (ты их нашёл grep-ом)
        from backend.app.memory.embeddings import Embeddings as _RealEmb
        from backend.app.memory.vectorstore import VectorStore as _RealStore

        _real_emb = _RealEmb()
        _real_store = _RealStore()
    except Exception:
        _USE_REAL_STACK = False
        _real_emb = None
        _real_store = None

# -------------------------- файловый фоллбек ---------------------------------
_FALLBACK_DIM = 512
# Храним JSONL рядом со storage/
_PROJECT_ROOT = os.path.abspath(os.getcwd())
_FALLBACK_PATH = os.path.join(_PROJECT_ROOT, "storage", "memory_fallback.jsonl")
os.makedirs(os.path.dirname(_FALLBACK_PATH), exist_ok=True)

_word_re = re.compile(r"[^\W_]+", flags=re.UNICODE)


def _stable_hash(text: str) -> int:
    h = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "little", signed=False)


def _embed_fallback(texts: List[str]) -> List[List[float]]:
    vecs: List[List[float]] = []
    for t in texts:
        v = [0.0] * _FALLBACK_DIM
        toks = [w.lower() for w in _word_re.findall(t)]
        for w in toks:
            i = _stable_hash(w) % _FALLBACK_DIM
            v[i] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        vecs.append([x / n for x in v])
    return vecs


def _cosine(a: List[float], b: List[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b)))


def _store_append(doc_id: str, text: str, meta: Dict[str, Any], emb: List[float]) -> None:
    with open(_FALLBACK_PATH, "a", encoding="utf-8") as f:
        f.write(
            json.dumps({"id": doc_id, "text": text, "meta": meta, "emb": emb}, ensure_ascii=False)
            + "\n"
        )


def _store_load_all() -> List[Dict[str, Any]]:
    if not os.path.exists(_FALLBACK_PATH):
        return []
    out: List[Dict[str, Any]] = []
    with open(_FALLBACK_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


# ------------------------------ схемы ----------------------------------------
class AddIn(BaseModel):
    text: str
    tags: List[str] = []
    source: Optional[str] = None
    sid: Optional[str] = None  # привязка к сессии (необязательна)


# ------------------------------ ручки ----------------------------------------
@router.post("/add")
def mem_add(item: AddIn):
    text = (item.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty text")

    doc_id = uuid.uuid4().hex
    meta: Dict[str, Any] = {
        "tags": item.tags,
        "source": item.source or "manual",
        "sid": item.sid,
        "ts": int(time.time()),
    }

    # Сначала пробуем реальный стек, если он активен
    if _USE_REAL_STACK:
        try:
            emb = _real_emb.encode([text])[0]  # type: ignore[attr-defined]
            _real_store.add([doc_id], [text], [emb], [meta])  # type: ignore[attr-defined]
            return {"ok": True, "id": doc_id, "meta": meta, "backend": "chroma"}
        except Exception:
            # упали — мягкий фоллбек
            pass

    # Фоллбек
    emb = _embed_fallback([text])[0]
    _store_append(doc_id, text, meta, emb)
    return {"ok": True, "id": doc_id, "meta": meta, "backend": "fallback"}


@router.get("/search")
def mem_search(q: str = Query(..., min_length=1), k: int = Query(5, ge=1, le=50)):
    q = q.strip()
    if not q:
        raise HTTPException(status_code=400, detail="empty query")

    if _USE_REAL_STACK:
        try:
            emb = _real_emb.encode([q])[0]  # type: ignore[attr-defined]
            res = _real_store.query(emb, k=k)  # type: ignore[attr-defined]

            ids = (res.get("ids") or [[]])[0]
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]
            out: List[Dict[str, Any]] = []
            n = min(len(ids), len(docs), len(metas), len(dists))
            for i in range(n):
                score = None
                try:
                    score = 1.0 - float(dists[i])
                except Exception:
                    pass
                out.append({"id": ids[i], "text": docs[i], "meta": metas[i], "score": score})
            return {"results": out, "backend": "chroma"}
        except Exception:
            # мягкий фоллбек
            pass

    # Фоллбек-поиск
    qv = _embed_fallback([q])[0]
    items = _store_load_all()
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for it in items:
        emb = it.get("emb") or []
        score = _cosine(qv, emb) if isinstance(emb, list) and emb else 0.0
        scored.append((score, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = [{"id": it["id"], "text": it["text"], "meta": it["meta"], "score": float(score)} for score, it in scored[:k]]
    return {"results": out, "backend": "fallback"}
