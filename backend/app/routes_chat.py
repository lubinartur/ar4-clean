from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

@router.post("")
async def chat(request: Request):
    data = await request.json()
    query = data.get("query", "")
    return JSONResponse({"echo": query})
