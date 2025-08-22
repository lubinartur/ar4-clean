# backend/app/main.py
from __future__ import annotations

import os
import secrets
import uuid
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import httpx
import json

from .llm_client import LLMClient

# ─── App & CORS ────────────────────────────────────────────────────────────────
app = FastAPI(title="AIR4 API", version="0.6.2-phase6.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # можно ужесточить позже
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Env ──────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "0000")

# ─── Auth (простой токен под smoke) ───────────────────────────────────────────
_TOKENS: set[str] = set()

class LoginBody(BaseModel):
    password: str = Field(..., min_length=1)

class LoginReply(BaseModel):
    ok: bool
    token: str

def _bearer_token(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    return authorization.split(" ", 1)[1].strip()

def require_auth(token: str = Depends(_bearer_token)) -> None:
    if token not in _TOKENS:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@app.post("/auth/login", response_model=LoginReply)
def login(body: LoginBody):
    if body.password != AUTH_PASSWORD:
        raise HTTPException(status_code=403, detail="Invalid credentials")
    token = secrets.token_hex(16)
    _TOKENS.add(token)
    return LoginReply(ok=True, token=token)

@app.get("/api/v0/secure/status")
def secure_status():
    return {
        "locked": False,
        "duress_active": False,
        "request_id": uuid.uuid4().hex[:12],
    }

@app.get("/health")
def health():
    return {"ok": True, "phase": "6.2", "llm_model": OLLAMA_MODEL}

# ─── /chat → LLM (через Ollama) ───────────────────────────────────────────────
class ChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    system: Optional[str] = Field(
        default="You are AIr4, a strict but helpful local assistant. Be concise, logical, and actionable."
    )
    temperature: float = 0.2

class ChatReply(BaseModel):
    ok: bool
    reply: str
    request_id: str

@app.post("/chat", response_model=ChatReply)
async def chat(body: ChatBody, _auth: None = Depends(require_auth)):
    messages = []
    if body.system:
        messages.append({"role": "system", "content": body.system})
    messages.append({"role": "user", "content": body.message})

    client = LLMClient(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL, timeout=180.0)
    try:
        answer = await client.chat(messages, temperature=body.temperature, stream=False)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    return ChatReply(ok=True, reply=answer, request_id=uuid.uuid4().hex[:8])

# ─── /chat/stream → SSE (стрим токенов) ───────────────────────────────────────
@app.post("/chat/stream")
async def chat_stream(body: ChatBody, _auth: None = Depends(require_auth)):
    messages = []
    if body.system:
        messages.append({"role": "system", "content": body.system})
    messages.append({"role": "user", "content": body.message})

    async def event_gen():
        url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
        payload = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": True,
            "options": {"temperature": body.temperature},
        }
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        msg = obj.get("message", {})
                        chunk = msg.get("content")
                        if chunk:
                            yield f"data: {chunk}\n\n"
                        if obj.get("done"):
                            break
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

# ─── /models → список доступных моделей Ollama ────────────────────────────────
class ModelsReply(BaseModel):
    ok: bool
    models: list[str]

@app.get("/models", response_model=ModelsReply)
async def models(_auth: None = Depends(require_auth)):
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama tags error: {e}")

    # ожидаемый формат: {"models":[{"name":"llama3.1:8b", ...}, ...]}
    names = []
    for it in (data or {}).get("models", []):
        name = (it or {}).get("name")
        if name:
            names.append(name)
    return ModelsReply(ok=True, models=names)
