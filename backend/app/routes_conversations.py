from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Body, status
from fastapi.responses import Response
from typing import Optional
from pydantic import BaseModel, field_validator

try:
    from backend.app.storage.repos.conversations import (
        list_conversations,
        get_conversation,
        create_conversation,
        rename_conversation,
        soft_delete_conversation,
    )
    from backend.app.storage.repos.messages import list_messages
except Exception:
    from .storage.repos.conversations import (
        list_conversations,
        get_conversation,
        create_conversation,
        rename_conversation,
        soft_delete_conversation,
    )
    from .storage.repos.messages import list_messages

router = APIRouter(prefix="/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    title: Optional[str] = None


class RenameConversationRequest(BaseModel):
    title: str
    
    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate that title is not empty after trim."""
        if not v or not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation_endpoint(
    body: Optional[CreateConversationRequest] = None,
):
    """Create a new conversation."""
    title = body.title if body else None
    conv = create_conversation(title=title)
    return conv


@router.get("")
async def get_conversations_list(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, description="Search query for title"),
):
    """List conversations with pagination and optional title filter."""
    items, total = list_conversations(limit=limit, offset=offset, q=q)
    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@router.get("/{conversation_id}")
async def get_conversation_messages(
    conversation_id: str,
    limit: int = Query(50, ge=1, le=200),
    before: Optional[str] = Query(None, description="ISO8601 timestamp for pagination"),
):
    """Get conversation details and messages with pagination."""
    # Get conversation
    conv = get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get messages
    messages, has_more = list_messages(
        conversation_id=conversation_id,
        limit=limit,
        before=before,
    )
    
    return {
        "conversation": {
            "id": conv["id"],
            "title": conv["title"],
            "created_at": conv["created_at"],
            "updated_at": conv["updated_at"],
            "last_message_at": conv["last_message_at"],
        },
        "messages": messages,
        "limit": limit,
        "before": before,
        "has_more": has_more,
    }


@router.patch("/{conversation_id}")
async def rename_conversation_endpoint(
    conversation_id: str,
    body: RenameConversationRequest,
):
    """Rename a conversation."""
    try:
        conv = rename_conversation(conversation_id=conversation_id, title=body.title)
        return conv
    except ValueError as e:
        error_msg = str(e)
        # Check if it's a "not found" error (contains "not found" or "deleted")
        if "not found" in error_msg.lower() or "deleted" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        # Otherwise it's a validation error (empty title) => 422
        raise HTTPException(status_code=422, detail=error_msg)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation_endpoint(conversation_id: str):
    """Soft delete a conversation and all its messages."""
    try:
        soft_delete_conversation(conversation_id=conversation_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
