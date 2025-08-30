# backend/app/routes_ingest.py — Safe ingest (no hard imports)
from __future__ import annotations

import os
import tempfile
import time
from typing import Optional, Any

from fastapi import APIRouter, UploadFile, File, Request
from pydantic import BaseModel

from backend.app.ingest.readers import ingest_path

router = APIRouter(prefix="/ingest", tags=["ingest"])


def _get_manager(request: Request) -> Any:
    mgr = getattr(request.app.state, "memory_manager", None)
    if mgr is None:
        # не валим сервер — даём понятную ошибку на запросе
        raise RuntimeError("memory_manager not initialized in app.state")
    return mgr


@router.post("/file")
async def ingest_file(
    request: Request, file: UploadFile = File(...), tag: Optional[str] = "phase10"
):
    mgr = _get_manager(request)
    suffix = os.path.splitext(file.filename or "")[1] or ".bin"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)

    try:
        with open(tmp_path, "wb") as f:
            f.write(await file.read())

        # формируем базовые метаданные (добавляем filename и source_path)
        base_metadata = {
            "tag": tag or "phase10",
            "ts": int(time.time()),
            "kind": "file",
            "source": "file",
            "filename": file.filename or os.path.basename(tmp_path),
            "source_path": file.filename or os.path.basename(tmp_path),
        }

        added = ingest_path(mgr, tmp_path, base_metadata=base_metadata)
        return {"ok": True, "chunks": added, "file": file.filename}
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


class URLIn(BaseModel):
    url: str


@router.post("/url")
async def ingest_url(request: Request, body: URLIn, tag: Optional[str] = "phase10"):
    mgr = _get_manager(request)
    # простая заглушка: сохраняем URL как документ
    text = f"URL: {body.url}"
    meta = {
        "tag": tag or "phase10",
        "kind": "url",
        "ts": int(time.time()),
        "source": "url",
        "filename": body.url,
        "source_path": body.url,
    }
    _id = f"url::{int(time.time())}"
    if hasattr(mgr, "add_texts"):
        mgr.add_texts([text], [meta], ids=[_id])
    else:
        mgr.collection.add(documents=[text], metadatas=[meta], ids=[_id])
    return {"ok": True, "saved": body.url}
