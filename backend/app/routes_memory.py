# backend/app/routes_memory.py — Phase 10: memory routes (preserve metadata + debug)
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Request, Query, Header
from pydantic import BaseModel, Field

from backend.app.retrieval import Retriever

router = APIRouter(prefix="/memory", tags=["memory"])


def _mgr(req: Request) -> Any:
    mgr = getattr(req.app.state, "memory_manager", None)
    if mgr is None:
        raise RuntimeError("memory_manager not initialized in app.state")
    return mgr


# --------------------------
# /memory/add — простой add для заметок (bulk API, затем фолбэк)
# --------------------------
class AddBody(BaseModel):
    text: str = Field(..., description="Plain text to store")
    tag: Optional[str] = Field("note", description="Custom tag")


@router.post("/add")
async def memory_add(
    body: AddBody,
    request: Request,
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    mgr = _mgr(request)
    meta = {"tag": body.tag or "note", "kind": "note", "user_id": x_user or "dev"}
    # пробуем современные пути
    if hasattr(mgr, "add_texts"):
        mgr.add_texts([body.text], [meta])
    elif hasattr(mgr, "collection"):
        mgr.collection.add(documents=[body.text], metadatas=[meta])
    elif hasattr(mgr, "add_text"):
        try:
            mgr.add_text(user_id=x_user or "dev", text=body.text, session_id=None, source=meta.get("kind"))
        except TypeError:
            mgr.add_text(x_user or "dev", body.text, None, meta.get("kind"))
    else:
        raise RuntimeError("No supported add method on memory manager")
    return {"ok": True}


# --------------------------
# /memory/search — Phase‑10 retriever (MMR / HyDE / recency / filters)
# --------------------------
@router.get("/search")
async def memory_search(
    request: Request,
    q: str = Query(..., description="User query"),
    k: int = Query(3, ge=1, le=50),
    mmr: Optional[float] = Query(None, ge=0.0, le=1.0, description="MMR λ (0..1); None disables MMR"),
    hyde: int = Query(1, description="1 to use HyDE, 0 to disable"),
    recency_days: Optional[int] = Query(0, ge=0, description="Recency half-life in days (0=off)"),
    where_json: Optional[str] = Query(None, description='JSON filter, e.g. {"tag":"phase10"}'),
    candidate_multiplier: Optional[int] = Query(3, ge=1, le=10),
):
    mgr = _mgr(request)
    retr = Retriever(mgr)
    results = retr.search(
        q=q,
        k=int(k),
        where_json=where_json,
        mmr=mmr,
        recency_days=int(recency_days or 0) or None,
        use_hyde=bool(hyde),
        candidate_multiplier=candidate_multiplier,
    )
    # НИЧЕГО не обрезаем: отдаём text / metadata / score как вернул retriever
    return {"ok": True, "results": results}


# --------------------------
# /memory/debug/query_raw — прямой просмотр того, что лежит в Chroma
# Возвращает JSON даже при ошибке (ok=False + error)
# --------------------------
@router.get("/debug/query_raw")
async def memory_debug_query_raw(
    request: Request,
    q: str = Query(...),
    k: int = Query(3, ge=1, le=50),
):
    try:
        mgr = _mgr(request)
        coll = getattr(mgr, "collection", None) or getattr(mgr, "col", None)
        if not coll:
            return {
                "ok": False,
                "error": "no collection on manager",
                "has_col": hasattr(mgr, "col"),
                "has_collection": hasattr(mgr, "collection"),
                "mgr_type": type(mgr).__name__,
            }
        if not hasattr(coll, "query"):
            return {"ok": False, "error": "collection has no .query()", "type": str(type(coll))}

        qr = coll.query(
            query_texts=[q],
            n_results=int(k),
            include=["documents", "metadatas", "distances"],
        )

        docs = (qr.get("documents") or [[]])[0]
        metas = (qr.get("metadatas") or [[]])[0]
        ids = (qr.get("ids") or [[]])[0]
        dists = (qr.get("distances") or [[]])[0]

        rows = []
        for d, m, i, dist in zip(docs, metas, ids, dists):
            rows.append({
                "id": i,
                "score": 1.0 - float(dist if dist is not None else 1.0),
                "metadata": m,
                "text_head": (d or "")[:120],
            })
        return {"ok": True, "rows": rows}
    except Exception as e:
        return {"ok": False, "error": repr(e), "type": e.__class__.__name__}
