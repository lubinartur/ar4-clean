from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from backend.app.shared_templates import templates
from backend.app.main import _SESSIONS

router = APIRouter()

@router.get("/ui/chat/{session_id}/messages", response_class=HTMLResponse)
async def chat_messages_fragment(request: Request, session_id: str):
    session = _SESSIONS.get(session_id)
    return templates.TemplateResponse("fragments/messages.html", {
        "request": request,
        "session": session,
        "messages": session.messages if session else []
    })
