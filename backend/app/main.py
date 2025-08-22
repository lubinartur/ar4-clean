# backend/app/main.py
from __future__ import annotations

import os
import secrets
import uuid
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .llm_client import LLMClient

# ─── App & CORS ────────────────────────────────────────────────────────────────
app = FastAPI(title="AIR4 API", version="0.6.0-phase6")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Env ──────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "0000")

# ─── Auth (simple token vault compatible with your smoke) ─────────────────────
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
    # Keep fields expected by previous phases/smokes
    return {
        "locked": False,
        "duress_active": False,
        "request_id": uuid.uuid4().hex[:12],
    }

@app.get("/health")
def health():
    return {"ok": True, "phase": "6", "llm_model": OLLAMA_MODEL}

# ─── /chat → LLM (Ollama) ─────────────────────────────────────────────────────
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
    # Prepare messages for Ollama chat API
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
