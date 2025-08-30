# backend/app/retrieval.py — Phase-10 Retriever (MMR / HyDE / filters / recency)
from __future__ import annotations
import json, time
from typing import Any, Dict, List, Optional

# --------- tiny utils ----------
def _now_ts() -> int:
    return int(time.time())

def _parse_where_json(s: Optional[str]) -> Optional[Dict[str, Any]]:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None

def _meta_match(meta: Dict[str, Any], where: Dict[str, Any]) -> bool:
    # простые равенства вида {"tag":"phase10","kind":"file"}
    for k, v in (where or {}).items():
        if meta.get(k) != v:
            return False
    return True

def _token_set(s: str) -> set:
    return {t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in s).split() if t}

def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / max(1, union)

def _mmr_select(cands: List[Dict[str, Any]], k: int, lamb: float = 0.5) -> List[Dict[str, Any]]:
    """MMR по токенам текста, без эмбеддингов."""
    if k <= 0 or not cands:
        return []
    k = min(k, len(cands))
    # токены
    for c in cands:
        c["_tok"] = _token_set(c.get("text", ""))
    # старт — по score
    rest = sorted(cands, key=lambda x: float(x.get("score", 0.0)), reverse=True)
    selected = [rest.pop(0)]
    while len(selected) < k and rest:
        best_i, best_val = 0, -1e9
        for i, c in enumerate(rest):
            rel = float(c.get("score", 0.0))
            div = 0.0
            for s in selected:
                a, b = c["_tok"], s["_tok"]
                if a and b:
                    inter = len(a & b)
                    union = len(a | b) or 1
                    div = max(div, inter / union)
            val = lamb * rel - (1.0 - lamb) * div
            if val > best_val:
                best_val, best_i = val, i
        selected.append(rest.pop(best_i))
    for c in cands:
        c.pop("_tok", None)
    return selected

# --------- core retriever ----------
class Retriever:
    def __init__(self, manager: Any):
        self.mgr = manager

    # низкоуровневый запрос к стору
    def _base_query(self, q: str, n: int) -> List[Dict[str, Any]]:
        # 1) если менеджер умеет .search(...) — используем его формат
        if hasattr(self.mgr, "search"):
            try:
                res = self.mgr.search(user_id="dev", query=q, k=int(n), score_threshold=0.0)
                items = res.get("results") if isinstance(res, dict) else res
                out = []
                for it in (items or []):
                    # ожидаем ключи: text / metadata / score (но поддержим старый "meta")
                    text = it.get("text")
                    meta = it.get("metadata") or it.get("meta") or {}
                    score = float(it.get("score", 0.0))
                    out.append({"text": text or "", "metadata": meta or {}, "score": score})
                if out:
                    return out
            except Exception:
                pass

        # 2) fallback напрямую в chroma collection
        coll = getattr(self.mgr, "collection", None) or getattr(self.mgr, "col", None)
        if coll and hasattr(coll, "query"):
            try:
                # (A) расширяем пул результатов, чтобы дать шанс релевантам
                n_fetch = max(int(n), int(n) * 5)
                qr = coll.query(
                    query_texts=[q],
                    n_results=n_fetch,
                    include=["documents", "metadatas", "distances"],
                )
                docs = (qr.get("documents") or [[]])[0]
                metas = (qr.get("metadatas") or [[]])[0]
                dists = (qr.get("distances") or [[]])[0]
                out = []
                seen_texts = set()
                for t, m, d in zip(docs, metas, dists):
                    text = t or ""
                    key = text.strip().lower()[:200]
                    if key in seen_texts:
                        continue
                    seen_texts.add(key)
                    score = 1.0 - float(d if d is not None else 1.0)
                    out.append({"text": text, "metadata": (m or {}), "score": score})
                return out
            except Exception:
                pass

        # 3) иначе — пусто
        return []

    def _query_hyde(self, q: str, n: int) -> List[Dict[str, Any]]:
        # HyDE опционален; если генератора нет — возвращаем пусто
        try:
            from backend.app.chat import generate_once  # опционально
        except Exception:
            return []
        try:
            hypo = (generate_once(f"Кратко ответь по существу: {q}") or "").strip()
            if not hypo:
                return []
            return self._base_query(hypo, n)
        except Exception:
            return []

    def search(
        self,
        q: str,
        k: int = 5,
        where_json: Optional[str] = None,
        mmr: Optional[float] = None,            # 0..1
        recency_days: Optional[int] = None,     # пока без реального буста — можно добавить позже
        use_hyde: bool = True,
        candidate_multiplier: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        where = _parse_where_json(where_json)
        n0 = max(1, int(k))
        n_cand = max(n0, n0 * int(candidate_multiplier or 3))

        # базовые кандидаты
        cands = self._base_query(q, n_cand)

        # HyDE‑кандидаты
        if use_hyde:
            hc = self._query_hyde(q, max(5, n0))
            if hc:
                seen = {(c.get("text") or "") for c in cands}
                for h in hc:
                    if (h.get("text") or "") not in seen:
                        cands.append(h)

        # keyword boost: усилим совпадение по токенам запроса (учитываем и метаданные)
        try:
            qtok = _token_set(q)
            if qtok:
                for c in cands:
                    meta = c.get("metadata") or {}
                    # токены текста
                    ctok = _token_set(c.get("text", "")) or set()
                    # + токены из важных полей метаданных
                    for fld in ("title", "filename", "tag", "topic"):
                        v = meta.get(fld)
                        if isinstance(v, str):
                            ctok |= _token_set(v)
                    # пересечение с запросом
                    if ctok:
                        inter = len(qtok & ctok)
                        union = len(qtok | ctok) or 1
                        j = inter / union
                    else:
                        j = 0.0
                    # базовый буст
                    boost = 0.35 * j
                    # лёгкий доп.бонус за совпадение с title
                    if meta.get("title"):
                        ttok = _token_set(str(meta["title"]))
                        if ttok and (qtok & ttok):
                            boost += 0.10
                    c["score"] = float(c.get("score", 0.0)) + boost
        except Exception:
            pass


        # where_json фильтр
        if where:
            cands = [c for c in cands if _meta_match(c.get("metadata") or {}, where)]

        # сортировка по score
        cands.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)

        # MMR (если включён)
        if mmr is not None:
            lam = min(1.0, max(0.0, float(mmr)))
            cands = _mmr_select(cands, n0, lam)

        return cands[:n0]
