from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

@router.post("/chat")
async def chat(request: Request):
    data = await request.json()
    q = data.get("q") or data.get("msg") or ""
    if not q.strip():
        return JSONResponse({"reply": "empty"}, status_code=200)
    # временный sanity-check ответ
    if q.lower().strip() == "ping":
        return {"reply": "pong"}
    return {"reply": f"echo: {q}"}