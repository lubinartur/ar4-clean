# backend/app/main.py — AIr4 v0.11.1 (Phase 11 — Profile + RAG fixed)
from __future__ import annotations

import os
import re
import time
import json
import uuid
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from urllib.parse import urlparse

from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
)
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
APP_VERSION = os.getenv("AIR4_VERSION", "0.11.1-phase11")
PORT = int(os.getenv("PORT", "8000"))

AIR4_OFFLINE = os.getenv("AIR4_OFFLINE", "1").strip() not in ("0", "false", "False")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL_DEFAULT = os.getenv("OLLAMA_MODEL_DEFAULT", "llama3.1:8b")
MAX_UPLOAD_BYTES = int(os.getenv("AIR4_MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))


def _require_local(url: str):
    if not AIR4_OFFLINE:
        return
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
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
# Memory backend
# -----------------------------------------------------------------------------
_app_memory = None


def get_memory():
    return _app_memory


@app.on_event("startup")
async def _memory_startup():
    """Инициализация backend памяти"""
    global _app_memory
    backend = os.getenv("AIR4_MEMORY_BACKEND", "fallback")
    force_fb = os.getenv("AIR4_MEMORY_FORCE_FALLBACK", "1") == "1"
    if backend == "chroma" and not force_fb:
        persist_dir = os.getenv("AIR4_CHROMA_DIR", "./storage/chroma")
        collection = os.getenv("AIR4_CHROMA_COLLECTION", "air4_memory")
        model_path = os.getenv("AIR4_EMBED_MODEL_PATH", "./models/bge-m3")
        _app_memory = ChromaMemoryManager(
            persist_dir=persist_dir,
            collection=collection,
            model_path=model_path,
        )
    else:
        _app_memory = None

    try:
        app.state.memory_manager = _app_memory
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    mem = get_memory()
    memory_info = {
        "backend": "chroma" if mem is not None else "fallback",
        "count": -1,
        "persist_dir": os.getenv("AIR4_CHROMA_DIR", "./storage/chroma"),
        "collection": os.getenv("AIR4_CHROMA_COLLECTION", "air4_memory"),
        "embed_model": os.getenv("AIR4_EMBED_MODEL_PATH", "./models/bge-m3"),
    }
    if mem is not None:
        try:
            memory_info["count"] = mem.count()
        except Exception:
            pass

    return {
        "ok": True,
        "status": "up",
        "version": APP_VERSION,
        "offline": AIR4_OFFLINE,
        "model": OLLAMA_MODEL_DEFAULT,
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
INGEST_DIR = STORAGE_DIR / "ingest"
UPLOADS_DIR = STORAGE_DIR / "uploads"
SUMMARY_DIR = STORAGE_DIR / "summaries"
SESSIONS_DIR = STORAGE_DIR / "sessions"
for d in (INGEST_DIR, UPLOADS_DIR, SUMMARY_DIR, SESSIONS_DIR):
    d.mkdir(parents=True, exist_ok=True)


# -----------------------------------------------------------------------------
# Chat endpoint (FIX: headers → chat.py)
# -----------------------------------------------------------------------------
@app.post("/chat")
async def chat_endpoint(request: Request):
    body = await request.json()
    headers = dict(request.headers)
    result = await chat_mod.chat_endpoint_call(body, headers=headers)
    return result


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