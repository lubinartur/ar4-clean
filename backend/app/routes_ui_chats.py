from __future__ import annotations

from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
from typing import Optional

try:
    from backend.app.storage.repos.conversations import list_conversations, get_conversation
    from backend.app.storage.repos.messages import list_messages
except Exception:
    from .storage.repos.conversations import list_conversations, get_conversation
    from .storage.repos.messages import list_messages

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

router = APIRouter()


@router.get("/ui/chats", response_class=HTMLResponse)
async def ui_chats(request: Request, cid: Optional[str] = Query(None)):
    """
    Main chats UI page with sidebar and chat view.
    """
    # Get conversations list for sidebar
    conversations, total = list_conversations(limit=50, offset=0, q=None)
    
    # Get current conversation and messages if cid provided
    current_conv = None
    messages = []
    if cid:
        current_conv = get_conversation(cid)
        if current_conv:
            msgs, has_more = list_messages(conversation_id=cid, limit=200, before=None)
            messages = msgs
        # If cid provided but conversation not found, current_conv will be None
        # We'll show "Chat not found" in template
    
    return templates.TemplateResponse(
        "chats.html",
        {
            "request": request,
            "conversations": conversations,
            "current_conv": current_conv,
            "current_cid": cid,
            "messages": messages,
        }
    )
