import os, json, time
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
import httpx

try:
    from dotenv import load_dotenv; load_dotenv()
except Exception:
    pass

# ---- Config
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:latest")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.4"))
LLM_MAX_CTX = int(os.getenv("LLM_MAX_CTX", "4096"))
HTTP_TIMEOUT = httpx.Timeout(60.0, read=60.0, connect=10.0)

# ---- App
app = FastAPI(title="AIR4 API", version="0.4.0-phase4")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# ---- Schemas
class ChatIn(BaseModel):
    message: str = Field(..., description="Пользовательский ввод")
    session_id: str = Field("default", description="ID сессии")
    system: Optional[str] = Field(None, description="Доп. системный промт")
    stream: bool = Field(False, description="Стримить ответ?")
    k_memory: int = Field(4, description="Сколько фрагментов памяти подмешать")

class ChatOut(BaseModel):
    reply: str
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    memory_used: Optional[List[str]] = None

# ---- Memory hooks (подключи свои реализации)
def retrieve_relevant(session_id: str, query: str, k: int = 4) -> List[str]:
    """
    Верни k релевантных кусочков памяти (Phase 3). Если нет — пусто.
    """
    try:
        # from memory import retrieve_relevant as rr
        # return rr(session_id=session_id, query=query, k=k)
        return []  # заглушка, если свой модуль уже есть — замени
    except Exception:
        return []

def store_chat_summary(session_id: str, user_text: str, assistant_text: str) -> None:
    """
    Сохрани автосаммари/контекст (Phase 3). Заглушка — замени своей.
    """
    try:
        # from memory import store_summary
        # store_summary(session_id=session_id, user=user_text, assistant=assistant_text)
        pass
    except Exception:
        pass

# ---- Builders
def build_messages(system: Optional[str], memory_blocks: List[str], user_text: str) -> List[dict]:
    messages: List[dict] = []
    base_system = (
        "Ты — локальный ассистент AIR4. Отвечай кратко, по шагам. "
        "Если не уверен — скажи. Соблюдай приватность."
    )
    messages.append({"role": "system", "content": base_system})
    if system:
        messages.append({"role": "system", "content": system})
    if memory_blocks:
        mem = "\n\n".join(memory_blocks)
        messages.append({"role": "system", "content": f"Релевантная память:\n{mem}"})
    messages.append({"role": "user", "content": user_text})
    return messages

# ---- Health
@app.get("/health")
async def health():
    return {"ok": True, "model": OLLAMA_MODEL}

# ---- Chat
@app.post("/chat", response_model=ChatOut, summary="Chat via Ollama (Phase 4)")
async def chat(body: ChatIn):
    memory_blocks = retrieve_relevant(body.session_id, body.message, body.k_memory)
    messages = build_messages(body.system, memory_blocks, body.message)

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": body.stream,
        "options": {
            "temperature": LLM_TEMPERATURE,
            "num_ctx": LLM_MAX_CTX,
        },
    }

    if body.stream:
        async def gen():
            start = time.perf_counter()
            buf: List[str] = []
            prompt_tokens = None
            completion_tokens = None
            url = f"{OLLAMA_BASE_URL}/api/chat"
            try:
                async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                    async with client.stream("POST", url, json=payload) as r:
                        if r.status_code != 200:
                            text = await r.aread()
                            raise HTTPException(status_code=502, detail=text.decode("utf-8", "ignore"))
                        async for line in r.aiter_lines():
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            msg = data.get("message", {})
                            chunk = msg.get("content")
                            if chunk:
                                buf.append(chunk)
                                yield chunk
                            if data.get("done"):
                                meta = data.get("metrics") or {}
                                prompt_tokens = meta.get("prompt_eval_count")
                                completion_tokens = meta.get("eval_count")
                                break
            finally:
                # попытка сохранить контекст
                try:
                    store_chat_summary(body.session_id, body.message, "".join(buf))
                except Exception:
                    pass
            # финальный мета-хвост (не ломает plain-stream)
            latency_ms = int((time.perf_counter() - start) * 1000)
            tail = json.dumps({
                "meta": {
                    "model": OLLAMA_MODEL,
                    "latency_ms": latency_ms,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }
            }, ensure_ascii=False)
            yield f"\n\n[[META]] {tail}\n"

        return StreamingResponse(gen(), media_type="text/plain")

    # non-stream
    start = time.perf_counter()
    url = f"{OLLAMA_BASE_URL}/api/chat"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        r = await client.post(url, json=payload)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=r.text)
        data = r.json()
        text = (data.get("message") or {}).get("content", "").strip()
        meta = data.get("metrics") or {}
        try:
            store_chat_summary(body.session_id, body.message, text)
        except Exception:
            pass
    latency_ms = int((time.perf_counter() - start) * 1000)
    return ChatOut(
        reply=text,
        model=OLLAMA_MODEL,
        prompt_tokens=meta.get("prompt_eval_count"),
        completion_tokens=meta.get("eval_count"),
        latency_ms=latency_ms,
        memory_used=memory_blocks or None,
    )
