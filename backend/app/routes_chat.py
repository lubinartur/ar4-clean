from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import httpx
import json

router = APIRouter()

@router.post("/chat")
async def chat(request: Request):
    data = await request.json()
    q = data.get("q") or data.get("msg") or ""
    if not q.strip():
        return JSONResponse({"reply": "empty"}, status_code=200)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", "http://localhost:11434/api/chat", json={
                "model": "mistral",
                "messages": [{"role": "user", "content": q}]
            }) as res:
                chunks = []
                async for line in res.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        json_line = json.loads(line)
                        content = json_line.get("message", {}).get("content", "")
                        chunks.append(content)
                    except Exception:
                        continue
                answer = "".join(chunks)
                return {"reply": answer}
    except Exception as e:
        return {"reply": f"echo: {q} (ollama failed: {e})"}