from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
import httpx, json

router = APIRouter()

SYSTEM = "Ты — AR4, личный интеллект Arch’a. Отвечай по делу, кратко."

@router.post("/chat/stream")
async def chat_stream(req: Request):
    data = await req.json()
    text = (data.get("text") or "").strip()

    async def gen():
        if not text:
            yield "event: done\ndata: [DONE]\n\n"; return

        dot_cap = 3
        dot_seen = 0

        try:
            async with httpx.AsyncClient(timeout=60.0) as c:
                payload = {
                    "model": "mistral",
                    "stream": True,
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": text},
                    ],
                }
                async with c.stream("POST", "http://localhost:11434/api/chat", json=payload) as res:
                    async for line in res.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            piece = json.loads(line).get("message", {}).get("content", "")
                        except Exception:
                            piece = ""
                        if not piece:
                            continue

                        buf = []
                        for ch in piece:
                            if ch == ".":
                                if dot_seen < dot_cap:
                                    buf.append(".")
                                    dot_seen += 1
                                    if dot_seen == dot_cap:
                                        if buf:
                                            yield f"data: {''.join(buf)}\n\n"
                                        yield "event: done\ndata: [DONE]\n\n"
                                        return
                                else:
                                    continue
                            else:
                                buf.append(ch)
                        if buf:
                            yield f"data: {''.join(buf)}\n\n"
        except Exception as e:
            yield f"data: [error] {e}\n\n"

        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
