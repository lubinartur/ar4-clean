# backend/app/main.py — AIr4 v0.12.0 (Phase 12 — RAG Phase-12)
from __future__ import annotations

import os
import time
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Optional

from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.app.routes_memory import router as memory_router
from backend.app.routes_ingest import router as ingest_router
from backend.app.routes_profile import router as profile_router
from backend.app import chat as chat_mod
from backend.app.memory.manager_chroma import ChromaMemoryManager

# -----------------------------------------------------------------------------
# Конфиг / лог
# -----------------------------------------------------------------------------
log = logging.getLogger("uvicorn.error")
APP_VERSION = os.getenv("AIR4_VERSION", "0.12.0-phase12")
PORT = int(os.getenv("PORT", "8000"))

AIR4_OFFLINE = os.getenv("AIR4_OFFLINE", "1").strip() not in ("0", "false", "False")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL_DEFAULT = os.getenv("OLLAMA_MODEL_DEFAULT", "llama3.1:8b")
MAX_UPLOAD_BYTES = int(os.getenv("AIR4_MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))

def _require_local(url: str):
    if not AIR4_OFFLINE:
        return
    host = url.split("//")[-1].split(":")[0]
    if host not in ("127.0.0.1", "localhost"):
        raise RuntimeError(f"AIR4_OFFLINE=1: remote host blocked: {host}")

_require_local(OLLAMA_BASE_URL)

# -----------------------------------------------------------------------------
# Приложение
# -----------------------------------------------------------------------------
app = FastAPI(title="AIr4", version=APP_VERSION)
app.include_router(memory_router)
app.include_router(ingest_router)
app.include_router(profile_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Memory backend Phase-12
# -----------------------------------------------------------------------------
_app_memory_phase12: Optional[ChromaMemoryManager] = None

def get_memory_phase12() -> Optional[ChromaMemoryManager]:
    return _app_memory_phase12

@app.on_event("startup")
async def _memory_phase12_startup():
    global _app_memory_phase12
    os.makedirs("./storage/chroma_phase12", exist_ok=True)
    _app_memory_phase12 = ChromaMemoryManager(
        persist_dir="./storage/chroma_phase12",
        collection="phase12",
        model_path="./models/bge-m3",
    )
    app.state.memory_manager_phase12 = _app_memory_phase12

# -----------------------------------------------------------------------------
# Phase-12 Search
# -----------------------------------------------------------------------------
@app.get("/memory/search/phase12")
async def search_phase12(
    q: str, k: int = 3, mmr: float = 0.4, hyde: int = 1, recency_days: int = 365
):
    mem = get_memory_phase12()
    if mem is None:
        raise HTTPException(status_code=404, detail="Phase-12 memory not initialized")
    # используем add_text API через chunker для ретривала
    out = mem.search(
        user_id="dev",
        query=q,
        k=k,
        score_threshold=0.0,
    )
    return out

# -----------------------------------------------------------------------------
# Phase-12 Ingest
# -----------------------------------------------------------------------------
@app.post("/ingest/file/phase12")
async def ingest_file_phase12(file: UploadFile = File(...)):
    mem = get_memory_phase12()
    if mem is None:
        raise HTTPException(status_code=500, detail="Phase-12 memory not initialized")
    content = await file.read()
    mem.add_text(user_id="dev", text=content.decode("utf-8"))
    return {"ok": True, "file": file.filename}

# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    mem = get_memory_phase12()
    memory_info = {
        "backend": "chroma" if mem else "fallback",
        "count": -1,
        "persist_dir": "./storage/chroma_phase12",
        "collection": "phase12",
        "embed_model": "./models/bge-m3",
    }
    return {
        "ok": True,
        "status": "up",
        "version": APP_VERSION,
        "memory": memory_info,
        "memory_backend": memory_info["backend"],
        "ollama_base_url": OLLAMA_BASE_URL,
    }

# -----------------------------------------------------------------------------
# Директории проекта
# -----------------------------------------------------------------------------
def _find_dir(start: Path, name: str) -> Path:
    for base in [start, *start.parents]:
        p = base / name
        if p.exists():
            return p
    p = start / name
    p.mkdir(parents=True, exist_ok=True)
    return p

HERE = Path(__file__).resolve().parent
TEMPLATES_DIR = _find_dir(HERE, "templates")
STATIC_DIR = _find_dir(HERE, "static")
STORAGE_DIR = _find_dir(HERE, "storage")
for d in (STORAGE_DIR,):
    d.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------------
# Chat endpoint
# -----------------------------------------------------------------------------
@app.post("/chat")
async def chat_endpoint(request: Request):
    body = await request.json()
    headers = dict(request.headers)
    return await chat_mod.chat_endpoint_call(body, headers=headers)

# -----------------------------------------------------------------------------
# UI bootstrap
# -----------------------------------------------------------------------------
try:
    from ui_bootstrap import attach_ui
    attach_ui(app)
except Exception as e:
    log.warning(f"[UI] ui_bootstrap.attach_ui не подключён: {e}")

try:
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
except Exception:
    pass
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@app.get("/ui", response_class=HTMLResponse)
async def ui_index(request: Request):
    return PlainTextResponse("UI index")

@app.get("/ui/chat", response_class=HTMLResponse)
async def ui_chat(request: Request):
    return PlainTextResponse("UI chat")