from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from backend.app.shared_templates import templates
import httpx

router = APIRouter()

@router.get("/ui/search", response_class=HTMLResponse)
async def ui_search(request: Request, q: str = ""):
    results = []
    if q:
        try:
            async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
                r = await client.get("/memory/search", params={"q": q, "k": 5})
                data = r.json()
                for item in data.get("results", []):
                    results.append({
                        "source_type": item.get("metadata", {}).get("type", "unknown"),
                        "source_name": item.get("metadata", {}).get("source", "unnamed"),
                        "text": item.get("text", "")[:500]
                    })
        except Exception as e:
            print(f"[ui_search] error: {e}")
    return templates.TemplateResponse("search.html", {"request": request, "q": q, "results": results})
