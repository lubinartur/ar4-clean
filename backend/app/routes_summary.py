from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="backend/app/templates")
summary_router = APIRouter()

@summary_router.get("/ui/summary", response_class=HTMLResponse)
async def ui_summary(request: Request):
    return templates.TemplateResponse("partials/summary_content.html", {"request": request})

