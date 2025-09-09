from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

todos_router = APIRouter()
templates = Jinja2Templates(directory="backend/app/templates")

@todos_router.get("/ui/todos", response_class=HTMLResponse)
def ui_todos(request: Request):
    return templates.TemplateResponse("todos.html", {"request": request})
