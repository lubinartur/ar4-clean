from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse
import httpx, json

router = APIRouter()

SYSTEM_PREAMBLE = (
    'Ты — AR4. Выполняй инструкции ДОСЛОВНО. '
    'Если просят точки — выводи только символ "." (ASCII 46).'
)

def _need_five_dots(text: str) -> bool:
    t = text.lower()
    return ('5 точ' in t) or ('пять точ' in t)

async def _gen(text: str):
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": "mistral",
        "stream": True,
        "options": {"temperature": 0, "top_p": 0, "repeat_penalty": 1.1},
        "messages": [
            {"role": "system", "content": SYSTEM_PREAMBLE},
            {"role": "user", "content": text},
        ],
    }

    dots_limit = 5 if _need_five_dots(text) else None
    emitted_dots = 0
    sent_any = False

    async with httpx.AsyncClient(timeout=None) as c:
        async with c.stream("POST", url, json=payload) as r:
            async for line in r.aiter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                chunk = (obj.get("message") or {}).get("content", "")
                if not chunk:
                    continue

                # Нормализация
                chunk = chunk.replace("•", ".")
                if not sent_any:
                    chunk = chunk.lstrip()
                    if chunk:
                        sent_any = True

                if dots_limit is not None:
                    out = []
                    for ch in chunk:
                        if ch == '.':
                            if emitted_dots < dots_limit:
                                out.append('.')
                                emitted_dots += 1
                                if emitted_dots == dots_limit:
                                    # Отдали последнюю точку — завершаем стрим
                                    if out:
                                        yield f"data: {''.join(out)}\n\n"
                                    yield "event: done\n"
                                    yield "data: [DONE]\n\n"
                                    return
                            else:
                                continue
                        else:
                            out.append(ch)
                    if out:
                        yield f"data: {''.join(out)}\n\n"
                else:
                    yield f"data: {chunk}\n\n"

                if obj.get("done"):
                    break

    yield "event: done\n"
    yield "data: [DONE]\n\n"

@router.post("/chat/stream")
async def chat_stream(text: str = Body(..., embed=True)):
    return StreamingResponse(_gen(text), media_type="text/event-stream")
