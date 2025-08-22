from fastapi import FastAPI, Request, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import Optional
import os, secrets, httpx

from backend.app.memory.manager import MemoryManager
from backend.app.memory.summarizer import Summarizer
from backend.app.llm_ollama import chat_llm, DEFAULT_MODEL

app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- auth/token store ---
VALID_TOKENS = set()

# --- globals ---
MEMORY = MemoryManager()
SUM = Summarizer(llm_fn=chat_llm)

# ================== BASIC ENDPOINTS ==================

@app.get("/health")
def health():
    return {"ok": True, "status": "up"}

@app.post("/auth/login")
async def auth_login(request: Request):
    data = await request.json()
    pwd = data.get("password", "")
    expected = os.getenv("AUTH_PASSWORD", "0000")
    if pwd != expected:
        return {"ok": False, "error": "invalid_password"}
    token = secrets.token_hex(16)
    VALID_TOKENS.add(token)
    return {"ok": True, "token": token}

@app.get("/models")
async def list_models():
    """Список моделей из Ollama; если недоступно — возвращаем дефолтную."""
    try:
        base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        async with httpx.AsyncClient(base_url=base, timeout=httpx.Timeout(10, read=10)) as client:
            r = await client.get("/api/tags")
            r.raise_for_status()
            data = r.json()
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            if not models:
                models = [DEFAULT_MODEL]
            return {"ok": True, "models": models}
    except Exception:
        return {"ok": True, "models": [DEFAULT_MODEL], "warning": "ollama_unreachable"}

# ================== CHAT ==================

@app.post("/chat")
async def chat(
    request: Request,
    background: BackgroundTasks,
    x_system_prompt: Optional[str] = Header(default=None, alias="X-System-Prompt"),
    x_model: Optional[str] = Header(default=None, alias="X-Model"),
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
    x_session: Optional[str] = Header(default=None, alias="X-Session"),
):
    data = await request.json()
    user_msg = data.get("message", "")
    stream = bool(data.get("stream", False))
    model = x_model or DEFAULT_MODEL

    # 1. История для контекста
    history = MEMORY.fetch_history(user_id=x_user, session_id=x_session, k=20)

    if stream:
        async def gen():
            full = []
            async for chunk in await chat_llm(
                user_msg, history=history, system=x_system_prompt,
                model=model, stream=True
            ):
                delta = chunk.get("delta") or ""
                if delta:
                    full.append(delta)
                    yield delta
            full_text = "".join(full)
            # авто-саммари в фоне
            background.add_task(SUM.summarize_and_store,
                                user_id=x_user, session_id=x_session,
                                user_msg=user_msg, assistant_msg=full_text)
            # история
            MEMORY.append_turn(x_user, x_session, "user", user_msg)
            MEMORY.append_turn(x_user, x_session, "assistant", full_text)
        return StreamingResponse(gen(), media_type="text/plain")
    else:
        reply = await chat_llm(
            user_msg, history=history, system=x_system_prompt,
            model=model, stream=False
        )
        text = reply.get("text") if isinstance(reply, dict) else str(reply)
        background.add_task(SUM.summarize_and_store,
                            user_id=x_user, session_id=x_session,
                            user_msg=user_msg, assistant_msg=text)
        MEMORY.append_turn(x_user, x_session, "user", user_msg)
        MEMORY.append_turn(x_user, x_session, "assistant", text)
        return {"ok": True, "reply": text}

# ================== MEMORY API ==================

@app.get("/memory/summary/{session_id}")
def get_summary(session_id: str, x_user: Optional[str] = Header(default="dev", alias="X-User")):
    s = MEMORY.get_summary(user_id=x_user, session_id=session_id)
    return {"ok": True, "summary": s}

@app.post("/memory/summarize/{session_id}")
async def force_summarize(session_id: str, request: Request,
                          x_user: Optional[str] = Header(default="dev", alias="X-User")):
    body = await request.json()
    user_msg = body.get("user_msg", "")
    assistant_msg = body.get("assistant_msg", "")
    await SUM.summarize_and_store(
        user_id=x_user, session_id=session_id,
        user_msg=user_msg, assistant_msg=assistant_msg
    )
    return {"ok": True}
