# backend/app/routes_memory.py — Phase 10: memory routes (preserve metadata + debug)
from __future__ import annotations

from typing import Any, Optional
import json
import time
from uuid import uuid4

from fastapi import APIRouter, Request, Query, Header, HTTPException
from pydantic import BaseModel, Field

from backend.app.retrieval import Retriever

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
    # B1.11: Generate unique ID with milliseconds + UUID to prevent collisions
    now_ts = int(time.time())
    now_ms = int(time.time() * 1000)
    _id = f"note-{now_ms}-{uuid4().hex[:8]}"
    raw_meta = {
        "tag": body.tag or "note",
        "kind": "note",
        "user_id": x_user or "dev",
        "session_id": session_id,
        "source": "note",
        "created_at": now_ts  # B1.11: Set created_at for deterministic sorting
    }
    # Phase E: Metadata normalization happens in manager methods
    
    # Prefer add_texts to ensure full metadata (tag, kind, etc.) is stored
    try:
        if hasattr(mgr, "add_texts"):
            # B1.11: Self-check verification commands:
            #   SID="aae30b18"
            #   for i in $(seq 1 12); do curl -s -X POST "http://127.0.0.1:8000/memory/add?session_id=$SID" -H "Content-Type: application/json" -d "{\"text\":\"mem item $i\",\"tags\":[\"test\"],\"type\":\"note\"}" >/dev/null; done
            #   curl -s "http://127.0.0.1:8000/memory/search?q=mem%20item&session_id=$SID&limit=5&offset=0" | jq '{n:(.results|length), has_more}'
            #   curl -s "http://127.0.0.1:8000/memory/search?q=mem%20item&session_id=$SID&limit=5&offset=5" | jq '{n:(.results|length), has_more}'
            #   curl -s "http://127.0.0.1:8000/memory/search?q=mem%20item&session_id=$SID&limit=5&offset=10" | jq '{n:(.results|length), has_more}'
            #   curl -s "http://127.0.0.1:8000/memory/search?q=mem%20item&session_id=$SID&limit=50&offset=0" | jq -r '.results[].id' | sort | uniq -c | head
            # Expected: offset=0=>n=5 has_more=true, offset=5=>n=5 has_more=true, offset=10=>n=2 has_more=false, all IDs unique (count=1 each)
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
# 
# Contract (B0.1):
#   Query params:
#     - q: str (required) - search query
#     - session_id: str (required) - session ID filter
#     - k: int (optional, default=3) - number of results
#     - mmr: float (optional) - MMR lambda 0..1
#     - hyde: int (optional, default=1) - HyDE on/off
#     - recency_days: int (optional) - recency boost
#     - where_json: str (optional) - JSON filter e.g. {"tag":"phase10"}
#     - candidate_multiplier: int (optional) - multiplier for candidates
#     - limit: int (optional) - list mode limit (overrides k if set)
#     - offset: int (optional, default=0) - list mode offset
#   Response shape:
#     - {"ok": True, "results": [...]} - always
#     - {"has_more": bool} - only if limit is provided
#   Result item shape:
#     - id: str
#     - text: str
#     - metadata or meta: dict (with session_id, tag, namespace, etc.)
#     - score: float
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
    limit: Optional[int] = Query(None, ge=1, le=200, description="Limit for list mode (overrides k if set)"),
    offset: Optional[int] = Query(0, ge=0, description="Offset for list mode pagination"),
):
    # Validate session_id
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    mgr = _mgr(request)
    retr = Retriever(mgr)
    try:
        is_list_mode = limit is not None
        
        if is_list_mode:
            # B1.10: Deterministic list-mode (bypass semantic search, scoped by session_id)
            # Self-check examples (after adding 12 notes "mem item X"):
            #   SID="aae30b18"
            #   curl "http://127.0.0.1:8000/memory/search?q=mem%20item&session_id=$SID&limit=5&offset=0" | jq '{n:(.results|length), has_more}'
            #   curl "http://127.0.0.1:8000/memory/search?q=mem%20item&session_id=$SID&limit=5&offset=5" | jq '{n:(.results|length), has_more}'
            #   curl "http://127.0.0.1:8000/memory/search?q=mem%20item&session_id=$SID&limit=5&offset=10" | jq '{n:(.results|length), has_more}'
            limit_i = int(limit)
            offset_i = int(offset or 0)
            q_norm = (q or "").strip().lower()
            
            # Build effective where filter: session_id is always enforced
            effective_where = {"session_id": session_id}
            if where_json:
                where_dict = json.loads(where_json) if isinstance(where_json, str) else where_json
                if isinstance(where_dict, dict):
                    effective_where.update(where_dict)  # AND-merge (where_json overrides on conflict)
            
            # Get collection and fetch items scoped by session_id (not full DB scan)
            coll = getattr(mgr, "collection", None) or getattr(mgr, "col", None)
            if not coll or not hasattr(coll, "get"):
                raise RuntimeError("memory manager collection does not support .get()")
            
            # Fetch only items matching where filter (scoped to session_id)
            chroma_result = coll.get(where=effective_where, include=["documents", "metadatas", "ids"])
            all_ids = chroma_result.get("ids", []) or []
            all_docs = chroma_result.get("documents", []) or []
            all_metas = chroma_result.get("metadatas", []) or []
            
            # Helper: extract created_at from metadata or id (defensive)
            def extract_created_at(item_id: str, meta: dict) -> float:
                # Try metadata fields (prefer created_at, fallback to ts/time)
                created_at = meta.get("created_at")
                if created_at is not None:
                    if isinstance(created_at, (int, float)):
                        return float(created_at)
                    if isinstance(created_at, str):
                        try:
                            return float(created_at)
                        except (ValueError, TypeError):
                            pass
                # Fallback: ts or time
                for key in ["ts", "time", "timestamp"]:
                    val = meta.get(key)
                    if val is not None:
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            continue
                # Fallback: extract from id (format: "note-{timestamp}-{uuid}")
                try:
                    parts = item_id.split("-")
                    if len(parts) >= 2:
                        return float(parts[1])
                except (ValueError, TypeError, IndexError):
                    pass
                return 0.0  # Final fallback
            
            # Build items list with id, text, meta, created_at
            all_items = []
            max_len = max(len(all_ids), len(all_docs), len(all_metas))
            for i in range(max_len):
                item_id = all_ids[i] if i < len(all_ids) else None
                text = (all_docs[i] if i < len(all_docs) else None) or ""
                meta = (all_metas[i] if i < len(all_metas) else None) or {}
                
                # Defensive: skip if missing id
                if not item_id:
                    continue
                
                # Ensure session_id match (double-check)
                if meta.get("session_id") != session_id:
                    continue
                
                created_at_val = extract_created_at(item_id, meta)
                all_items.append({
                    "id": item_id,
                    "text": text,
                    "meta": meta,
                    "_created_at": created_at_val,  # Internal sort key
                    "score": 1.0  # No relevance score in list-mode
                })
            
            # Filter by q (substring match, case-insensitive) BEFORE pagination
            if q_norm:
                all_items = [item for item in all_items if q_norm in item.get("text", "").lower()]
            
            # Sort deterministically: created_at DESC, then id DESC (for tie-breaking)
            # Use tuple (created_at, id) with reverse=True for DESC on both
            all_items.sort(key=lambda x: (x["_created_at"], x["id"]), reverse=True)
            # Remove internal sort key
            for item in all_items:
                item.pop("_created_at", None)
            
            # Paginate
            window = all_items[offset_i:offset_i + limit_i + 1]
            has_more = bool(len(window) > limit_i)
            page = window[:limit_i]
            
            # Convert to response format (same shape as search-mode)
            results = [{"id": item["id"], "text": item["text"], "score": item["score"], "meta": item["meta"]} for item in page]
        else:
            # B1: Search mode (semantic search with k/mmr/hyde)
            results = retr.search(
                q=q,
                session_id=session_id,
                k=int(k),
                where_json=where_json,
                mmr=mmr,
                recency_days=int(recency_days or 0) or None,
                use_hyde=bool(hyde),
                candidate_multiplier=candidate_multiplier,
            )
            has_more = None
        
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
        
        # B1.7: Build response with guaranteed boolean has_more in list-mode only
        response = {"ok": True, "results": results}
        if is_list_mode:
            response["has_more"] = bool(has_more)  # guaranteed bool
        return response
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
# C1: Memory suggest endpoint (rule-based heuristics, no autosave)
# C1-FIX: Consider user intent from user->assistant pair
# --------------------------
class SuggestBody(BaseModel):
    user_text: str = Field(..., description="User message text (preceding the assistant response)")
    assistant_text: str = Field(..., description="Assistant message text to analyze")


@router.post("/suggest")
async def memory_suggest(
    body: SuggestBody,
    request: Request,
    session_id: str = Query(..., description="Session ID (required)"),
):
    """
    C1-FIX: Suggest saving based on user intent (user->assistant pair).
    No database writes, returns suggestion metadata only.
    
    Response:
    {
        "ok": True,
        "suggest": bool,
        "confidence": float (0.2..0.9),
        "reason": str,
        "proposed_tag": str ("important"|"profile"|"manual")
    }
    """
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    
    user_text = (body.user_text or "").strip().lower()
    assistant_text = (body.assistant_text or "").strip().lower()
    
    # C1: Rule-based heuristics (check user intent first, then assistant response)
    suggest = False
    confidence = 0.0
    reason = ""
    proposed_tag = "manual"
    
    # User intent markers (case-insensitive check)
    user_markers = ["важно", "запомни", "сохрани", "сохранить", "зафиксируй", "фиксируем", "итог", "решили", "делаем так", "подведем итог"]
    
    # Check user_text for markers (primary trigger)
    for marker in user_markers:
        if marker in user_text:
            suggest = True
            confidence = 0.85
            reason = "user_intent"
            # proposed_tag="important" if contains ("итог" or "решили" or "делаем так" or "фиксируем") else "manual"
            if any(m in user_text for m in ["итог", "решили", "делаем так", "фиксируем"]):
                proposed_tag = "important"
            else:
                proposed_tag = "manual"
            break
    
    # Fallback: Check assistant_text for summary markers
    if not suggest:
        assistant_markers = ["итог", "решение", "договорились", "фиксируем", "план:", "важно:"]
        for marker in assistant_markers:
            if marker in assistant_text:
                suggest = True
                confidence = 0.75
                reason = "assistant_summary"
                proposed_tag = "manual"
                break
    
    # Default: no signal
    if not suggest:
        confidence = 0.2
        reason = "no_signal"
        proposed_tag = "manual"
    
    return {
        "ok": True,
        "suggest": suggest,
        "confidence": confidence,
        "reason": reason,
        "proposed_tag": proposed_tag
    }


# --------------------------
# B2.1: Memory Bank endpoints (v3.1 Read + Control UI)
# --------------------------

# B2.1.x namespace-fix: Map target_type to namespace for promote and filtering
def _type_to_namespace(target_type: str) -> Optional[str]:
    """Map target_type to namespace. Returns None if unknown."""
    t = (target_type or "").strip().lower()
    mapping = {
        "note": "notes",
        "notes": "notes",
        "chat": "chat",
        "capture": "captures",
        "summary": "summaries",
        "fact": "facts",
        "pattern": "patterns",
    }
    return mapping.get(t)


@router.get("/bank")
async def memory_bank(
    request: Request,
    session_id: str = Query(..., description="Session ID (required)"),
    type: Optional[str] = Query(None, description="Filter by type (facts/summaries/captures/patterns/notes)"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    from_ts: Optional[int] = Query(None, ge=0, description="Filter from timestamp (epoch)"),
    to_ts: Optional[int] = Query(None, ge=0, description="Filter to timestamp (epoch)"),
    limit: int = Query(50, ge=1, le=200, description="Limit items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    include_archived: int = Query(0, ge=0, le=1, description="C3.0: Include archived items (0=no, 1=yes)"),
):
    """
    B2.1: Memory Bank deterministic listing (no semantic scoring).
    Returns filtered, paginated memory items.
    
    B2.1.1 Verification:
      SID="aae30b18"
      curl -s "http://127.0.0.1:8000/memory/search?q=&session_id=$SID&limit=5&offset=0" | jq '{n:(.results|length)}'
      curl -s "http://127.0.0.1:8000/memory/bank?session_id=$SID&limit=5&offset=0" | jq '{dbg:.__dbg, raw:.__count_raw, n:(.items|length), sample:(.items[0]//null | {id,namespace:(.meta.namespace//null),kind:(.meta.kind//null),session:(.meta.session_id//null)})}'
      Expected: raw>0 and n>0, sample.meta.session_id == SID.
    """
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    mgr = _mgr(request)
    
    try:
        limit_i = int(limit)
        offset_i = int(offset or 0)
        
        # Build where filter (session_id always enforced)
        # B2.1.1: Fetch with session_id only, apply tag/type filters post-fetch (ChromaDB requires $and for multiple conditions)
        effective_where = {"session_id": session_id}
        
        # Get collection (same as /memory/search uses)
        coll = getattr(mgr, "collection", None) or getattr(mgr, "col", None)
        if not coll or not hasattr(coll, "get"):
            raise RuntimeError("memory manager collection does not support .get()")
        
        # B2.1.1: TEMP debug - raw count with session_id only (before tag filter)
        # B2.1.3: ids returned by default; do NOT use include=["ids"]
        raw_where = {"session_id": session_id}
        raw_result = coll.get(where=raw_where)  # ids returned by default
        count_raw = len(raw_result.get("ids") or [])
        
        # Fetch all items for session_id (type filter applied later)
        # B2.1.3: ids returned by default; only include documents and metadatas
        chroma_result = coll.get(where=effective_where, include=["documents", "metadatas"])
        all_ids = chroma_result.get("ids", []) or []
        all_docs = chroma_result.get("documents", []) or []
        all_metas = chroma_result.get("metadatas", []) or []
        
        # Helper: extract created_at
        def extract_created_at(item_id: str, meta: dict) -> float:
            created_at = meta.get("created_at")
            if created_at is not None:
                if isinstance(created_at, (int, float)):
                    return float(created_at)
                if isinstance(created_at, str):
                    try:
                        return float(created_at)
                    except (ValueError, TypeError):
                        pass
            for key in ["ts", "time", "timestamp"]:
                val = meta.get(key)
                if val is not None:
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        continue
            try:
                parts = item_id.split("-")
                if len(parts) >= 2:
                    return float(parts[1])
            except (ValueError, TypeError, IndexError):
                pass
            return 0.0
        
        # Build items list
        all_items = []
        max_len = max(len(all_ids), len(all_docs), len(all_metas))
        for i in range(max_len):
            item_id = all_ids[i] if i < len(all_ids) else None
            text = (all_docs[i] if i < len(all_docs) else None) or ""
            meta = (all_metas[i] if i < len(all_metas) else None) or {}
            
            if not item_id or meta.get("session_id") != session_id:
                continue
            
            # B2.1.1: Filter archived/deleted (treat missing as False)
            # C3.0: Only filter archived if include_archived=0 (default behavior)
            if include_archived == 0:
                if meta.get("archived") is True or meta.get("is_deleted") is True:
                    continue
            else:
                # C3.0: When include_archived=1, still filter deleted items but keep archived
                if meta.get("is_deleted") is True:
                    continue
            
            # B2.1.1: Apply tag filter (post-fetch, ChromaDB where doesn't support multiple keys without $and)
            if tag:
                item_tag = meta.get("tag") or "general"
                if item_tag != tag:
                    continue
            
            # B2.1.x namespace-fix: Apply strict type filter (prefer kind/type over namespace; namespace is legacy fallback)
            # HOTFIX: For type=note, ONLY use kind/type, never namespace (to allow promote to work)
            if type:
                req_type = (type or "").strip().lower()
                # Normalize "notes" -> "note" for comparison
                if req_type == "notes":
                    req_type = "note"
                
                kind = (meta.get("kind") or meta.get("type") or "").strip().lower()
                ns = (meta.get("namespace") or "").strip().lower()
                
                # HOTFIX: For "note" type, ONLY check kind/type, ignore namespace completely
                if req_type == "note":
                    # Item passes ONLY if kind/type == "note"
                    if kind != "note":
                        continue
                else:
                    # For other types: prefer kind/type, fallback to namespace if kind/type missing
                    if kind:
                        # If item has kind/type, use it for filtering
                        if kind != req_type:
                            continue
                    else:
                        # Legacy fallback: use namespace mapping only if kind/type is missing
                        expected_ns = _type_to_namespace(req_type)
                        if expected_ns and ns != expected_ns:
                            continue
            
            # Filter by date range
            created_at_val = extract_created_at(item_id, meta)
            if from_ts is not None and created_at_val < float(from_ts):
                continue
            if to_ts is not None and created_at_val > float(to_ts):
                continue
            
            # Extract type/tag from metadata
            item_type = meta.get("kind") or meta.get("type") or "note"
            item_tag = meta.get("tag") or "general"
            # HOTFIX: Compute namespace from kind/type as fallback (namespace can be "sticky" after promote)
            # namespace = meta.namespace ?? meta.kind ?? meta.type ?? fallback
            namespace = meta.get("namespace")
            if not namespace:
                # Compute from kind/type if namespace missing
                kind_or_type = meta.get("kind") or meta.get("type")
                if kind_or_type:
                    computed_ns = _type_to_namespace(kind_or_type)
                    if computed_ns:
                        namespace = computed_ns
            # Final fallback
            if not namespace:
                namespace = "general"
            
            all_items.append({
                "id": item_id,
                "text": text,
                "meta": meta,
                "created_at": created_at_val,
                "type": item_type,
                "tag": item_tag,
                "session_id": session_id,
                "namespace": namespace,
                "_sort_key": created_at_val
            })
        
        # Sort: created_at DESC, id DESC
        all_items.sort(key=lambda x: (x["_sort_key"], x["id"]), reverse=True)
        for item in all_items:
            item.pop("_sort_key", None)
        
        # Paginate
        window = all_items[offset_i:offset_i + limit_i + 1]
        has_more = bool(len(window) > limit_i)
        page = window[:limit_i]
        
        # B2.1.4: Clean response (debug fields removed)
        return {
            "ok": True,
            "items": page,
            "has_more": has_more
        }
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[ERROR] memory_bank failed: {e}")
        raise HTTPException(status_code=500, detail=f"Memory bank query failed: {str(e)}")


class PromoteBody(BaseModel):
    id: str = Field(..., description="Memory item ID")
    target_type: str = Field(..., description="Target type/kind")
    target_tag: Optional[str] = Field(None, description="Target tag (optional)")


@router.post("/promote")
async def memory_promote(
    body: PromoteBody,
    request: Request,
    session_id: str = Query(..., description="Session ID (required)"),
):
    """
    B2.1: Explicit promote - updates item classification (kind/type/tag/namespace).
    B2.1.x namespace-fix: Updates namespace based on target_type mapping.
    
    Test: SID="aae30b18"; ITEM_ID="note-..."
      curl -s -X POST "http://127.0.0.1:8000/memory/promote?session_id=$SID" \
        -H "Content-Type: application/json" \
        -d "{\"id\":\"$ITEM_ID\",\"target_type\":\"capture\",\"target_tag\":\"important\"}" | jq
    
    Self-check: SID="86b1b1a7"
      # create note
      curl -s -X POST "http://127.0.0.1:8000/memory/add?session_id=$SID" -H "Content-Type: application/json" -d '{"text":"PROMOTE NS TEST","tag":"manual"}'
      # get top note id
      ITEM_ID=$(curl -s "http://127.0.0.1:8000/memory/bank?session_id=$SID&type=note&limit=1" | jq -r '.items[0].id')
      # promote to chat
      curl -s -X POST "http://127.0.0.1:8000/memory/promote?session_id=$SID" -H "Content-Type: application/json" -d "{\"id\":\"$ITEM_ID\",\"target_type\":\"chat\",\"target_tag\":\"general\"}"
      # verify meta.namespace=chat in ALL
      curl -s "http://127.0.0.1:8000/memory/bank?session_id=$SID&limit=200" | jq --arg id "$ITEM_ID" '.items[]|select(.id==$id)|{id,type,namespace,meta_ns:(.meta.namespace//null), meta_kind:(.meta.kind//null)}'
      # verify NOT in NOTES anymore
      curl -s "http://127.0.0.1:8000/memory/bank?session_id=$SID&type=note&limit=200" | jq --arg id "$ITEM_ID" '{has:(.items|map(.id)|index($id)!=null)}'
    """
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    mgr = _mgr(request)
    
    try:
        coll = getattr(mgr, "collection", None) or getattr(mgr, "col", None)
        if not coll:
            raise RuntimeError("memory manager collection not available")
        
        # Get existing item
        result = coll.get(ids=[body.id], include=["metadatas"])
        if not result.get("ids") or body.id not in result["ids"]:
            raise HTTPException(status_code=404, detail=f"Memory item {body.id} not found")
        
        meta_list = result.get("metadatas", [])
        if not meta_list:
            raise HTTPException(status_code=404, detail=f"Metadata not found for {body.id}")
        
        existing_meta = meta_list[0] or {}
        
        # Verify session_id matches
        if existing_meta.get("session_id") != session_id:
            raise HTTPException(status_code=403, detail="Session ID mismatch")
        
        # B2.1.x namespace-fix: Update metadata with namespace mapping
        # HOTFIX: Store before state for debug
        before_ns = existing_meta.get("namespace")
        before_kind = existing_meta.get("kind")
        before_type = existing_meta.get("type")
        
        updated_meta = dict(existing_meta)  # Preserve all existing fields
        updated_meta["kind"] = body.target_type
        updated_meta["type"] = body.target_type
        if body.target_tag:
            updated_meta["tag"] = body.target_tag
        updated_meta["updated_at"] = int(time.time())
        
        # B2.1.x namespace-fix: Map target_type to namespace (best-effort)
        mapped_namespace = _type_to_namespace(body.target_type)
        if mapped_namespace:
            updated_meta["namespace"] = mapped_namespace
        # If mapping returns None (unknown type), keep existing namespace
        
        # Normalize namespace based on type if manager has normalization
        if hasattr(mgr, "_normalize_metadata"):
            normalized = mgr._normalize_metadata(updated_meta)
            updated_meta.update(normalized)
        
        # Update via ChromaDB update
        coll.update(ids=[body.id], metadatas=[updated_meta])
        
        # HOTFIX: Self-check - verify what actually got written to ChromaDB
        after_result = coll.get(ids=[body.id], include=["metadatas"])
        after_meta = None
        if after_result.get("metadatas") and len(after_result["metadatas"]) > 0:
            after_meta = after_result["metadatas"][0] or {}
        
        # Return with debug fields
        response = {"ok": True}
        if after_meta:
            response["__dbg"] = "promote-v2"
            response["__before_ns"] = before_ns
            response["__before_kind"] = before_kind
            response["__before_type"] = before_type
            response["__after_ns"] = after_meta.get("namespace")
            response["__after_kind"] = after_meta.get("kind")
            response["__after_type"] = after_meta.get("type")
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[ERROR] memory_promote failed: {e}")
        raise HTTPException(status_code=500, detail=f"Promote failed: {str(e)}")


class ArchiveBody(BaseModel):
    id: str = Field(..., description="Memory item ID")


@router.post("/archive")
async def memory_archive(
    body: ArchiveBody,
    request: Request,
    session_id: str = Query(..., description="Session ID (required)"),
):
    """
    B2.1: Soft archive - sets meta.archived=true and archived_at timestamp.
    
    Test: SID="aae30b18"; ITEM_ID="note-..."
      curl -s -X POST "http://127.0.0.1:8000/memory/archive?session_id=$SID" \
        -H "Content-Type: application/json" \
        -d "{\"id\":\"$ITEM_ID\"}" | jq
    """
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    mgr = _mgr(request)
    
    try:
        coll = getattr(mgr, "collection", None) or getattr(mgr, "col", None)
        if not coll:
            raise RuntimeError("memory manager collection not available")
        
        # Get existing item
        result = coll.get(ids=[body.id], include=["metadatas"])
        if not result.get("ids") or body.id not in result["ids"]:
            raise HTTPException(status_code=404, detail=f"Memory item {body.id} not found")
        
        meta_list = result.get("metadatas", [])
        if not meta_list:
            raise HTTPException(status_code=404, detail=f"Metadata not found for {body.id}")
        
        existing_meta = meta_list[0] or {}
        
        # Verify session_id matches
        if existing_meta.get("session_id") != session_id:
            raise HTTPException(status_code=403, detail="Session ID mismatch")
        
        # Update metadata: archive
        updated_meta = dict(existing_meta)
        updated_meta["archived"] = True
        updated_meta["archived_at"] = int(time.time())
        updated_meta["updated_at"] = int(time.time())
        
        # Update via ChromaDB update
        coll.update(ids=[body.id], metadatas=[updated_meta])
        
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[ERROR] memory_archive failed: {e}")
        raise HTTPException(status_code=500, detail=f"Archive failed: {str(e)}")


@router.post("/unarchive")
async def memory_unarchive(
    body: ArchiveBody,
    request: Request,
    session_id: str = Query(..., description="Session ID (required)"),
):
    """
    C3.0: Unarchive - sets meta.archived=False and clears archived_at.
    
    Test: SID="aae30b18"; ITEM_ID="note-..."
      curl -s -X POST "http://127.0.0.1:8000/memory/unarchive?session_id=$SID" \
        -H "Content-Type: application/json" \
        -d "{\"id\":\"$ITEM_ID\"}" | jq
    """
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    mgr = _mgr(request)
    
    try:
        coll = getattr(mgr, "collection", None) or getattr(mgr, "col", None)
        if not coll:
            raise RuntimeError("memory manager collection not available")
        
        # Get existing item
        result = coll.get(ids=[body.id], include=["metadatas"])
        if not result.get("ids") or body.id not in result["ids"]:
            raise HTTPException(status_code=404, detail=f"Memory item {body.id} not found")
        
        meta_list = result.get("metadatas", [])
        if not meta_list:
            raise HTTPException(status_code=404, detail=f"Metadata not found for {body.id}")
        
        existing_meta = meta_list[0] or {}
        
        # Verify session_id matches
        if existing_meta.get("session_id") != session_id:
            raise HTTPException(status_code=403, detail="Session ID mismatch")
        
        # Update metadata: unarchive
        updated_meta = dict(existing_meta)
        updated_meta["archived"] = False
        if "archived_at" in updated_meta:
            del updated_meta["archived_at"]
        updated_meta["updated_at"] = int(time.time())
        
        # Update via ChromaDB update
        coll.update(ids=[body.id], metadatas=[updated_meta])
        
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[C3.0] memory_unarchive failed: {e}")
        raise HTTPException(status_code=500, detail=f"Unarchive failed: {str(e)}")


@router.delete("/bank/{item_id}")
async def memory_bank_delete(
    item_id: str,
    request: Request,
    session_id: str = Query(..., description="Session ID (required)"),
):
    """
    B2.1: Soft delete - sets meta.is_deleted=true and deleted_at timestamp.
    
    Test: SID="aae30b18"; ITEM_ID="note-..."
      curl -s -X DELETE "http://127.0.0.1:8000/memory/bank/$ITEM_ID?session_id=$SID" | jq
    """
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    mgr = _mgr(request)
    
    try:
        coll = getattr(mgr, "collection", None) or getattr(mgr, "col", None)
        if not coll:
            raise RuntimeError("memory manager collection not available")
        
        # Get existing item
        result = coll.get(ids=[item_id], include=["metadatas"])
        if not result.get("ids") or item_id not in result["ids"]:
            raise HTTPException(status_code=404, detail=f"Memory item {item_id} not found")
        
        meta_list = result.get("metadatas", [])
        if not meta_list:
            raise HTTPException(status_code=404, detail=f"Metadata not found for {item_id}")
        
        existing_meta = meta_list[0] or {}
        
        # Verify session_id matches
        if existing_meta.get("session_id") != session_id:
            raise HTTPException(status_code=403, detail="Session ID mismatch")
        
        # Update metadata: soft delete
        updated_meta = dict(existing_meta)
        updated_meta["is_deleted"] = True
        updated_meta["deleted_at"] = int(time.time())
        updated_meta["updated_at"] = int(time.time())
        
        # Update via ChromaDB update
        coll.update(ids=[item_id], metadatas=[updated_meta])
        
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[ERROR] memory_bank_delete failed: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


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
