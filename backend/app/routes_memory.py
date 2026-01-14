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
    raw_meta = {"tag": body.tag or "note", "kind": "note", "user_id": x_user or "dev", "session_id": session_id, "source": "note"}
    # Phase E: Metadata normalization happens in manager methods
    
    # Prefer add_texts to ensure full metadata (tag, kind, etc.) is stored
    try:
        if hasattr(mgr, "add_texts"):
            _id = f"note-{int(time.time())}"
            try:
                mgr.add_texts([body.text], [raw_meta], ids=[_id])
                return {"ok": True}
            except ValueError as e:
                # Re-raise validation errors as HTTP 400
                raise HTTPException(status_code=400, detail=str(e))
        elif hasattr(mgr, "add_text"):
            # Fallback: use add_text if add_texts not available
            try:
                result = mgr.add_text(user_id=x_user or "dev", text=body.text, session_id=session_id, source=raw_meta.get("kind", "note"))
                # Handle skipped duplicates
                if isinstance(result, dict) and result.get("skipped"):
                    return {"ok": True, "skipped": True}
                return {"ok": True}
            except ValueError as e:
                # Re-raise validation errors as HTTP 400
                raise HTTPException(status_code=400, detail=str(e))
            except TypeError:
                try:
                    result = mgr.add_text(x_user or "dev", body.text, session_id, raw_meta.get("kind", "note"))
                    if isinstance(result, dict) and result.get("skipped"):
                        return {"ok": True, "skipped": True}
                    return {"ok": True}
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
        else:
            raise RuntimeError("No supported add method on memory manager")
    except HTTPException:
        raise
    except Exception as e:
        # G3: Log error
        import logging
        logger = logging.getLogger(__name__)
        logger.error(
            "[ERROR] memory write_failed",
            extra={
                "session_id": session_id,
                "user": x_user or "dev",
                "exception": str(e)
            }
        )
        raise HTTPException(status_code=500, detail=f"Memory write failed: {str(e)}")


# --------------------------
# /memory/delete — Delete memory by id, namespace, or tag (Phase E)
# --------------------------
class DeleteBody(BaseModel):
    by: str = Field(..., description="Delete criterion: 'id', 'namespace', or 'tag'", pattern="^(id|namespace|tag)$")
    value: str = Field(..., description="Value to match", min_length=1)


@router.delete("/delete")
async def memory_delete(
    body: DeleteBody,
    request: Request,
    session_id: Optional[str] = Query(None, description="Session ID (optional)"),
):
    """
    Phase E: Delete memory items by id, namespace, or tag.
    
    - by="id": Delete single item by ID (404 if not found). session_id is optional.
    - by="namespace": Delete all items with matching namespace (returns deleted count, 200 even if 0).
      If session_id provided, scope to that session; otherwise delete globally.
    - by="tag": Delete all items with matching tag (returns deleted count, 200 even if 0).
      If session_id provided, scope to that session; otherwise delete globally.
    """
    # Validate session_id if provided (but it's optional)
    if session_id:
        from backend.app.main import validate_session_id
        session_id = validate_session_id(session_id)
    
    # Validate input
    by_value = body.by.strip().lower()
    value = body.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="value cannot be empty or whitespace-only")
    
    if by_value not in ("id", "namespace", "tag"):
        raise HTTPException(status_code=400, detail="by must be one of: id, namespace, tag")
    
    # Get memory manager from app.state
    try:
        mgr = _mgr(request)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail="Memory manager not initialized in app.state")
    
    # Get collection (ChromaDB)
    # Prefer get_collection() method if available, fallback to attributes
    if hasattr(mgr, "get_collection") and callable(getattr(mgr, "get_collection")):
        try:
            coll = mgr.get_collection()
        except Exception:
            coll = None
    else:
        coll = getattr(mgr, "collection", None) or getattr(mgr, "col", None)
    
    # Check if collection is truly unavailable (e.g., InMemoryAdapter)
    if not coll:
        # Check manager type to provide appropriate error
        mgr_type = type(mgr).__name__
        if "InMemory" in mgr_type or "MemoryAdapter" in mgr_type:
            raise HTTPException(status_code=503, detail="Memory collection not available (using in-memory adapter)")
        raise HTTPException(status_code=503, detail="Memory collection not available")
    
    # Verify collection has delete method
    if not hasattr(coll, "delete"):
        raise HTTPException(status_code=500, detail="Collection does not support delete operation")
    
    try:
        if by_value == "id":
            # Delete by ID: verify existence (session_id is optional, no ownership check)
            get_result = coll.get(ids=[value], include=["metadatas"])
            if not get_result.get("ids") or len(get_result["ids"]) == 0:
                raise HTTPException(status_code=404, detail=f"Memory item with id '{value}' not found")
            
            # Delete by ID (no session_id filtering)
            coll.delete(ids=[value])
            return {"status": "ok", "deleted": 1, "by": "id", "value": value}
        
        elif by_value == "namespace":
            # Delete by namespace: add session_id to where clause only if provided
            where_clause = {"namespace": value}
            if session_id:
                where_clause["session_id"] = session_id
            # Get count before deletion
            get_result = coll.get(where=where_clause)
            count_before = len(get_result.get("ids") or [])
            # Delete
            coll.delete(where=where_clause)
            return {"status": "ok", "deleted": count_before, "by": "namespace", "value": value}
        
        elif by_value == "tag":
            # Delete by tag: add session_id to where clause only if provided
            where_clause = {"tag": value}
            if session_id:
                where_clause["session_id"] = session_id
            # Get count before deletion
            get_result = coll.get(where=where_clause)
            count_before = len(get_result.get("ids") or [])
            # Delete
            coll.delete(where=where_clause)
            return {"status": "ok", "deleted": count_before, "by": "tag", "value": value}
        
    except HTTPException:
        raise
    except Exception as e:
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
    try:
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
        # G3: Log memory hit if results found
        if results and len(results) > 0:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                "[MEMORY_HIT]",
                extra={
                    "session_id": session_id,
                    "user": "dev",
                    "count": len(results),
                    "namespace": None
                }
            )
        # НИЧЕГО не обрезаем: отдаём text / metadata / score как вернул retriever
        return {"ok": True, "results": results}
    except Exception as e:
        # G3: Log error
        import logging
        logger = logging.getLogger(__name__)
        logger.error(
            "[ERROR] memory search_failed",
            extra={
                "session_id": session_id,
                "user": "dev",
                "exception": str(e)
            }
        )
        raise


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
