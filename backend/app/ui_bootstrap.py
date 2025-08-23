# ui_bootstrap.py — безопасное подключение UI (templates/static + /ui)
from pathlib import Path
import logging
from fastapi import Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

log = logging.getLogger("uvicorn.error")

def _find_dir(start: Path, name: str) -> Path:
    """
    Ищет папку name от start вверх по дереву.
    Если не найдена — создаёт рядом с start.
    """
    for base in [start, *start.parents]:
        p = base / name
        if p.exists():
            return p
    p = start / name
    p.mkdir(parents=True, exist_ok=True)
    return p

def attach_ui(app):
    """
    Подключает:
      • /static → StaticFiles
      • /ui → отдаёт templates/index.html (с понятной ошибкой, если файла нет)
      • /__routes → список маршрутов (для отладки)
    Пишет пути до templates/static в лог uvicorn.
    """
    here = Path(__file__).resolve().parent
    templates_dir = _find_dir(here, "templates")
    static_dir = _find_dir(here, "static")

    log.info(f"[UI] templates dir: {templates_dir}")
    log.info(f"[UI] static dir:    {static_dir}")

    templates = Jinja2Templates(directory=str(templates_dir))

    # Монтируем статику (если уже смонтировано — молча пропускаем)
    try:
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    except Exception:
        pass

    @app.get("/ui", response_class=HTMLResponse)
    async def ui_index(request: Request):
        index_html = templates_dir / "index.html"
        if not index_html.exists():
            # Дружелюбная ошибка вместо «Internal Server Error»
            return PlainTextResponse(
                f"Ожидался шаблон: {index_html}\n"
                f"Создай templates/index.html (мы уже готовили его на прошлых шагах).",
                status_code=500,
            )
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/__routes")
    def list_routes():
        return [getattr(r, "path", None) for r in app.router.routes]
