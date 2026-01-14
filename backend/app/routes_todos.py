# ============================================================================
# DEPRECATED: Legacy HTMX Todos UI Router
# ============================================================================
# This router is kept for reference but is NOT registered in main.py.
# GoogleUI (React) at /ui/google is the only active UI.
# ============================================================================

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

todos_router = APIRouter()
templates = Jinja2Templates(directory="backend/app/templates")

# @todos_router.get("/ui/todos", response_class=HTMLResponse)
# def ui_todos(request: Request):
#     """DEPRECATED: Legacy HTMX todos UI - Use GoogleUI instead."""
#     return templates.TemplateResponse("todos.html", {"request": request})
