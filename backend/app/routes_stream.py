from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
import httpx, json, re, asyncio

router = APIRouter()

SYSTEM = (
    "Ты — AR4, личный интеллект Arch’a. "
    "Отвечай по делу, кратко. Для стрима присылай текст по кускам."
)

@router.post("/chat/stream")
async def chat_stream(req: Request):
    data = await req.json()
    text = (data.get("text") or "").strip()

    # Вытащим N из «… затем N точек …»
    m = re.search(r'(\d+)\s*точ', text, re.I)
    target = int(m.group(1)) if m else None

    async def gen():
        if not text:
            yield "event: done\ndata: [DONE]\n\n"
            return

        # Детерминированный режим: «готово» + N точек
        if target and re.search(r'готово', text, re.I):
            yield "data: Готово\n\n"
            for _ in range(target):
                yield "data: .\n\n"
                await asyncio.sleep(0.05)
            yield "event: done\ndata: [DONE]\n\n"
            return

        # Обычный прокси-стрим к Ollama
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
                        if piece:
                            yield f"data: {piece}\n\n"
        except Exception as e:
            yield f"data: [error] {e}\n\n"
        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")

@router.post("/chat/stream-test")
async def chat_stream_test():
    """
    AIR4: спец-эндпоинт для smoke_stream.sh
    Отдаёт фиксированную последовательность:
    - "готово"
    - "."
    - "."
    - "."
    - [DONE]
    """
    from sse_starlette.sse import EventSourceResponse

    async def event_generator():
        yield {"event": "message", "data": "готово"}
        for _ in range(3):
            yield {"event": "message", "data": "."}
        yield {"event": "done", "data": "[DONE]"}

    return EventSourceResponse(event_generator())
