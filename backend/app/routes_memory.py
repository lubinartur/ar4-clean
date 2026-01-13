# backend/app/routes_memory.py — Phase 10: memory routes (preserve metadata + debug)
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Request, Query, Header, HTTPException
from pydantic import BaseModel, Field

from backend.app.retrieval import Retriever
import time

# Импорт функции удаления фактов
try:
    from backend.app.memory.facts import delete_facts
except ImportError:
    from .memory.facts import delete_facts

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
    session_id: str = Query(..., description="Session ID (required)"),
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    # Validate session_id
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    
    # Write guards: validate text input at route level
    if not body.text or not isinstance(body.text, str):
        raise HTTPException(status_code=400, detail="text is required and must be a non-empty string")
    text_stripped = body.text.strip()
    if not text_stripped:
        raise HTTPException(status_code=400, detail="text cannot be empty or whitespace-only")
    if len(text_stripped) < 5:
        raise HTTPException(status_code=400, detail="text must be at least 5 characters long")
    
    mgr = _mgr(request)
    meta = {"tag": body.tag or "note", "kind": "note", "user_id": x_user or "dev", "session_id": session_id}
    
    # пробуем современные пути
    if hasattr(mgr, "collection"):
        # Check for duplicates before adding
        existing = mgr.collection.get(
            where={"session_id": session_id},
            include=["documents"]
        )
        existing_docs = existing.get("documents") or []
        text_normalized = text_stripped.lower()
        for existing_doc in existing_docs:
            if existing_doc and existing_doc.strip().lower() == text_normalized:
                return {"ok": True, "skipped": True}
        
        mgr.collection.add(
            ids=[f"note-{int(time.time())}"],
            documents=[body.text],
            metadatas=[meta]
        )
        return {"ok": True, "via": "collection.add", "meta": meta}
    elif hasattr(mgr, "add_text"):
        try:
            result = mgr.add_text(user_id=x_user or "dev", text=body.text, session_id=session_id, source=meta.get("kind"))
            # Handle skipped duplicates
            if isinstance(result, dict) and result.get("skipped"):
                return {"ok": True, "skipped": True}
            return {"ok": True}
        except ValueError as e:
            # Re-raise validation errors as HTTP 400
            raise HTTPException(status_code=400, detail=str(e))
        except TypeError:
            try:
                result = mgr.add_text(x_user or "dev", body.text, session_id, meta.get("kind"))
                if isinstance(result, dict) and result.get("skipped"):
                    return {"ok": True, "skipped": True}
                return {"ok": True}
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
    else:
        raise RuntimeError("No supported add method on memory manager")


# --------------------------
# /memory/delete — Delete memory item by ID
# --------------------------
class DeleteBody(BaseModel):
    id: str = Field(..., description="ID of the memory item to delete", min_length=1)


@router.post("/delete")
async def memory_delete(
    body: DeleteBody,
    request: Request,
    session_id: str = Query(..., description="Session ID (required)"),
):
    """
    Delete a memory item by ID.
    Used by GoogleUI.
    """
    # Validate session_id
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    
    # Validate input (check for whitespace-only)
    id_value = body.id.strip()
    if not id_value:
        raise HTTPException(status_code=400, detail="id cannot be empty or whitespace-only")
    
    mgr = _mgr(request)
    
    # Get collection (ChromaDB)
    coll = getattr(mgr, "collection", None) or getattr(mgr, "col", None)
    if not coll:
        raise HTTPException(status_code=500, detail="Memory collection not available")
    
    if not hasattr(coll, "delete"):
        raise HTTPException(status_code=500, detail="Collection does not support delete operation")
    
    try:
        # First verify the record belongs to this session (prevent cross-session deletion)
        # Get the record to check its metadata
        get_result = coll.get(ids=[id_value], include=["metadatas"])
        if not get_result.get("ids") or len(get_result["ids"]) == 0:
            # Record doesn't exist - return success (idempotent)
            return {"ok": True, "deleted": 0}
        
        # Check if the record's session_id matches
        metas = get_result.get("metadatas") or [[]]
        if metas and len(metas) > 0:
            record_meta = metas[0] or {}
            record_session_id = record_meta.get("session_id")
            if record_session_id != session_id:
                # Record belongs to different session - prevent deletion
                raise HTTPException(status_code=403, detail="Cannot delete memory from another session")
        
        # Delete by ID (ChromaDB delete() doesn't raise if ID doesn't exist)
        coll.delete(ids=[id_value])
        return {"ok": True, "deleted": 1}
    except HTTPException:
        raise
    except Exception as e:
        # Handle any unexpected exceptions
        raise HTTPException(status_code=500, detail=f"Failed to delete memory: {str(e)}")


# --------------------------
# /memory/search — Phase‑10 retriever (MMR / HyDE / recency / filters)
# --------------------------
@router.get("/search")
async def memory_search(
    request: Request,
    q: str = Query(..., description="User query"),
    session_id: str = Query(..., description="Session ID (required)"),
    k: int = Query(3, ge=1, le=50),
    mmr: Optional[float] = Query(None, ge=0.0, le=1.0, description="MMR λ (0..1); None disables MMR"),
    hyde: int = Query(1, description="1 to use HyDE, 0 to disable"),
    recency_days: Optional[int] = Query(0, ge=0, description="Recency half-life in days (0=off)"),
    where_json: Optional[str] = Query(None, description='JSON filter, e.g. {"tag":"phase10"}'),
    candidate_multiplier: Optional[int] = Query(3, ge=1, le=10),
):
    # Validate session_id
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    mgr = _mgr(request)
    retr = Retriever(mgr)
    results = retr.search(
        q=q,
        session_id=session_id,  # Pass session_id for filtering
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
    """
    @deprecated Not used by GoogleUI. Internal debug endpoint.
    Прямой просмотр того, что лежит в Chroma.
    """
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


# --------------------------
# /memory/facts — DELETE endpoint для удаления фактов
# --------------------------
@router.delete("/facts")
async def memory_delete_facts(
    predicate: str = Query(..., description="Predicate to match (case-insensitive)"),
    subject: str = Query("Arch", description="Subject to match (case-insensitive, default: Arch)"),
    object: Optional[str] = Query(None, description="Optional object to match (case-insensitive)"),
):
    """
    @deprecated Not used by GoogleUI. Internal endpoint.
    Удаляет факты по критериям.
    
    Удаляет все факты, где:
    - subject совпадает (case-insensitive)
    - predicate совпадает (case-insensitive)
    - object совпадает (case-insensitive), если указан
    
    Returns:
        {"deleted": <int>} - количество удалённых фактов
    """
    try:
        deleted_count = delete_facts(subject=subject, predicate=predicate, object_value=object)
        return {"deleted": deleted_count}
    except Exception as e:
        return {"deleted": 0, "error": str(e)}
