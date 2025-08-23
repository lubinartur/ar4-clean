# backend/app/routes_memory.py — Phase 9: chroma-first, file-fallback (lazy import to avoid cycle)
from __future__ import annotations

import os, json, time, uuid, hashlib
from pathlib import Path
from typing import Optional, List, Dict

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/memory", tags=["memory"])

# -------- Lazy access to get_memory() from main (avoids circular import) --------
def _get_memory():
    try:
        from backend.app.main import get_memory  # imported at call-time
        return get_memory()
    except Exception:
        return None

# -------- Fallback (JSONL) --------
STORAGE_DIR = Path(os.getenv("AIR4_STORAGE_DIR", "backend/app/storage")).resolve()
FALLBACK_PATH = STORAGE_DIR / "memory_fallback.jsonl"
FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)

def _fb_append(rec: dict) -> None:
    with FALLBACK_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def _fb_load() -> List[dict]:
    if not FALLBACK_PATH.exists():
        return []
    out: List[dict] = []
    for line in FALLBACK_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out

def _fb_search(query: str, k: int = 4) -> List[dict]:
    items = _fb_load()
    q = query.strip().lower()
    scored: List[dict] = []
    for it in items:
        txt = str(it.get("text", ""))
        s = 0.5773502691896258 if (q and txt and q in txt.lower()) else 0.0
        scored.append({
            "id": it.get("id"),
            "text": txt,
            "meta": it.get("meta") or {},
            "score": s,
        })
    # sort by score desc, then by ts desc
    scored.sort(key=lambda x: (x["score"], x.get("meta", {}).get("ts", 0)), reverse=True)
    return scored[: max(1, int(k))]

# -------- Schemas --------
class AddBody(BaseModel):
    text: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    source: Optional[str] = "manual"

# -------- Endpoints --------
@router.post("/add")
async def memory_add(body: AddBody, x_user: Optional[str] = Header(default="dev", alias="X-User")):
    user_id = x_user or "dev"
    mm = _get_memory()

    if mm is not None:
        res = mm.add_text(
            user_id=user_id,
            text=body.text,
            session_id=body.session_id,
            source=(body.source or "user"),
        )
        return {**res, "backend": "chroma"}

    ts = int(time.time())
    rec_id = hashlib.sha1(f"{ts}|{uuid.uuid4().hex}".encode("utf-8")).hexdigest()[:32]
    rec = {
        "id": rec_id,
        "user_id": user_id,
        "text": body.text,
        "meta": {"tags": [], "source": body.source or "manual", "sid": body.session_id, "ts": ts},
    }
    _fb_append(rec)
    return {"ok": True, "id": rec_id, "meta": rec["meta"], "backend": "fallback"}

@router.get("/search")
async def memory_search(
    q: str,
    k: int = 4,
    score: float = float(os.getenv("AIR4_RAG_SCORE_THRESHOLD", "0.62")),
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    user_id = x_user or "dev"
    mm = _get_memory()

    if mm is not None:
        res = mm.search(user_id=user_id, query=q, k=int(k), score_threshold=float(score))
        return {"ok": True, "k": int(k), "score_threshold": float(score), **res, "backend": "chroma"}

    results = _fb_search(q, k=int(k))
    return {"results": results, "backend": "fallback"}
