"""
Recall v0.1: Sessions with preview + counts endpoint.

GET /recall/sessions?limit=50&offset=0&q=
Returns sessions with preview text and chat/note counts from memory bank.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Query, HTTPException
from typing import Optional, List, Dict, Any
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recall", tags=["recall"])

# Import session index path from routes_chat
try:
    from backend.app.routes_chat import INDEX_PATH, SESS_DIR
except ImportError:
    from .routes_chat import INDEX_PATH, SESS_DIR

# Import memory manager helper
try:
    from backend.app.routes_memory import _mgr
except ImportError:
    from .routes_memory import _mgr


def _get_effective_kind(item: Dict[str, Any]) -> str:
    """
    Get effective kind for an item (kind/type first; fallback namespace).
    For legacy chat messages stored as type=note but namespace=chat, returns "chat".
    """
    meta = item.get("meta") or {}
    
    # Priority 1: kind
    kind = meta.get("kind")
    if kind and isinstance(kind, str) and kind.strip():
        return kind.strip().lower()
    
    # Priority 2: type
    item_type = item.get("type") or meta.get("type")
    if item_type and isinstance(item_type, str) and item_type.strip():
        return item_type.strip().lower()
    
    # Priority 3: namespace (especially for chat)
    namespace = item.get("namespace") or meta.get("namespace")
    if namespace == "chat":
        return "chat"
    if namespace and isinstance(namespace, str) and namespace.strip():
        return namespace.strip().lower()
    
    return "item"


@router.get("/sessions")
async def recall_sessions(
    request: Request,
    limit: int = Query(50, ge=1, le=200, description="Limit sessions per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    q: Optional[str] = Query(None, description="Search query (filters by title)"),
):
    """
    Recall v0.1: Get sessions with preview text and counts.
    
    Returns:
    {
        "ok": true,
        "items": [
            {
                "session_id": str,
                "title": str,
                "updated_at": int,
                "preview": str,
                "counts": {"chat": int, "note": int}
            }
        ],
        "has_more": bool
    }
    
    Self-check:
        SID="aae30b18"
        curl -s "http://127.0.0.1:8000/recall/sessions?limit=5&offset=0" | jq '{n:(.items|length), sample:(.items[0]//null | {session_id,title,preview:(.preview[:50]),counts})}'
        curl -s "http://127.0.0.1:8000/recall/sessions?limit=5&offset=0&q=test" | jq '{n:(.items|length), filtered:(.items[]|select(.title|test("test";"i")))}'
    """
    try:
        # Get memory manager
        mgr = _mgr(request)
        coll = getattr(mgr, "collection", None) or getattr(mgr, "col", None)
        if not coll or not hasattr(coll, "get"):
            # Fallback: return sessions without preview/counts if memory unavailable
            logger.warning("[recall] Memory collection not available, returning sessions without preview")
            coll = None
        
        # Load sessions from index.json
        try:
            idx = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
        except Exception as e:
            logger.warning(f"[recall] Failed to load sessions index: {e}")
            idx = {}
        
        # Normalize sessions (ensure id field)
        sessions = []
        for session_key, session_data in idx.items():
            if not isinstance(session_data, dict):
                continue
            if "id" not in session_data or not session_data.get("id"):
                session_data["id"] = session_key
            sessions.append(session_data)
        
        # B3 lifecycle: Recall shows only CLOSED sessions; active sessions are hidden (legacy without closed_at treated as active)
        # Filter applied BEFORE search/pagination (backend authoritative)
        # Helper: is_closed(s) = (status == "closed") OR (closed_at is not None)
        closed_sessions = []
        for session in sessions:
            status = session.get("status")
            closed_at = session.get("closed_at")
            
            # If status field exists, use it
            if status == "closed":
                closed_sessions.append(session)
            elif status == "active":
                continue  # Skip active sessions
            else:
                # Legacy session: no status field
                # If closed_at exists, treat as closed (show in Recall)
                # If closed_at missing, treat as active (do NOT show in Recall)
                if closed_at is not None:
                    closed_sessions.append(session)
                # else: skip (treat as active)
        
        sessions = closed_sessions
        
        # Apply search filter if provided (only among closed sessions)
        if q:
            q_lower = q.lower().strip()
            sessions = [s for s in sessions if q_lower in (s.get("title", "") or "").lower()]
        
        # Sort by updated_at descending
        sessions.sort(key=lambda r: r.get("updated_at", 0), reverse=True)
        
        # Apply pagination
        total_sessions = len(sessions)
        paginated_sessions = sessions[offset:offset + limit]
        has_more = (offset + limit) < total_sessions
        
        # For each session, get preview and counts from memory bank
        items = []
        for session in paginated_sessions:
            session_id = session.get("id") or session.get("session_id")
            if not session_id:
                continue
            
            title = session.get("title", "New session")
            updated_at = session.get("updated_at", 0)
            
            preview = ""
            counts = {"chat": 0, "note": 0}
            
            if coll:
                try:
                    # Query memory bank for this session
                    where_filter = {"session_id": session_id}
                    chroma_result = coll.get(where=where_filter, include=["documents", "metadatas"])
                    
                    all_ids = chroma_result.get("ids", []) or []
                    all_docs = chroma_result.get("documents", []) or []
                    all_metas = chroma_result.get("metadatas", []) or []
                    
                    # Build items list
                    session_items = []
                    max_len = max(len(all_ids), len(all_docs), len(all_metas))
                    for i in range(max_len):
                        item_id = all_ids[i] if i < len(all_ids) else None
                        text = (all_docs[i] if i < len(all_docs) else None) or ""
                        meta = (all_metas[i] if i < len(all_metas) else None) or {}
                        
                        if not item_id or meta.get("session_id") != session_id:
                            continue
                        
                        # Skip archived/deleted
                        if meta.get("archived") is True or meta.get("is_deleted") is True:
                            continue
                        
                        # Build item dict
                        item = {
                            "id": item_id,
                            "text": text,
                            "content": text,
                            "meta": meta,
                            "namespace": meta.get("namespace"),
                            "type": meta.get("type") or meta.get("kind"),
                        }
                        session_items.append(item)
                        
                        # Count by effective kind
                        kind = _get_effective_kind(item)
                        if kind == "chat":
                            counts["chat"] += 1
                        elif kind == "note":
                            counts["note"] += 1
                    
                    # Select preview: prefer chat items, else latest
                    chat_items = [item for item in session_items if _get_effective_kind(item) == "chat"]
                    if chat_items:
                        # Use latest chat item
                        preview_item = max(chat_items, key=lambda x: x.get("meta", {}).get("created_at", 0) or 0)
                        preview = (preview_item.get("text") or preview_item.get("content") or "").strip()
                    elif session_items:
                        # Use latest item
                        preview_item = max(session_items, key=lambda x: x.get("meta", {}).get("created_at", 0) or 0)
                        preview = (preview_item.get("text") or preview_item.get("content") or "").strip()
                    
                    # Truncate preview to reasonable length
                    if preview:
                        preview = preview[:200].strip()
                        if len(preview) > 200:
                            preview = preview[:197] + "..."
                
                except Exception as e:
                    logger.warning(f"[recall] Failed to get memory for session {session_id}: {e}")
                    # Continue with empty preview/counts
            
            items.append({
                "session_id": session_id,
                "title": title,
                "updated_at": updated_at,
                "preview": preview,
                "counts": counts,
            })
        
        return {
            "ok": True,
            "items": items,
            "has_more": has_more,
        }
    
    except Exception as e:
        logger.error(f"[recall] Error in recall_sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get recall sessions: {str(e)}")
