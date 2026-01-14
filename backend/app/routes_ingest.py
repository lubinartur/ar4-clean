# backend/app/routes_ingest.py — Safe ingest (no hard imports)
from __future__ import annotations

import os
import tempfile
import time
from typing import Optional, Any
import logging

from fastapi import APIRouter, UploadFile, File, Request, Query, HTTPException
from pydantic import BaseModel, Field

from backend.app.ingest.readers import ingest_path

logger = logging.getLogger(__name__)

# Runtime guard limits
MAX_INGEST_BATCH_SIZE = 100  # Max files to process in one batch
MAX_INGEST_FILE_SIZE_MB = 50  # Max file size in MB

router = APIRouter(prefix="/ingest", tags=["ingest"])


def _get_manager(request: Request) -> Any:
    mgr = getattr(request.app.state, "memory_manager", None)
    if mgr is None:
        # не валим сервер — даём понятную ошибку на запросе
        raise RuntimeError("memory_manager not initialized in app.state")
    return mgr


@router.post("/file")
async def ingest_file(
    request: Request, 
    file: UploadFile = File(...), 
    session_id: str = Query(..., description="Session ID (required)", min_length=1),
    tag: Optional[str] = Query("phase10", description="Tag for the ingested file", min_length=1, max_length=100)
):
    """
    @deprecated Not used by GoogleUI. Use /ingest/file (routes_ingest) instead.
    Legacy ingest file endpoint.
    """
    # Validate session_id
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    mgr = _get_manager(request)
    suffix = os.path.splitext(file.filename or "")[1] or ".bin"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)

    try:
        # Runtime guard: file size limit
        file_content = await file.read()
        file_size_mb = len(file_content) / (1024 * 1024)
        if file_size_mb > MAX_INGEST_FILE_SIZE_MB:
            logger.warning(f"[INGEST GUARD] File size {file_size_mb:.2f}MB exceeds max {MAX_INGEST_FILE_SIZE_MB}MB")
            raise HTTPException(
                status_code=413,
                detail=f"File size {file_size_mb:.2f}MB exceeds maximum allowed size of {MAX_INGEST_FILE_SIZE_MB}MB"
            )
        
        with open(tmp_path, "wb") as f:
            f.write(file_content)

        # формируем базовые метаданные (добавляем filename и source_path)
        base_metadata = {
            "tag": tag or "phase10",
            "ts": int(time.time()),
            "kind": "file",
            "source": "file",
            "filename": file.filename or os.path.basename(tmp_path),
            "source_path": file.filename or os.path.basename(tmp_path),
            "session_id": session_id,  # Include session_id in metadata
        }

        added = ingest_path(mgr, tmp_path, base_metadata=base_metadata, chunk_size=512, overlap=64)
        # DEBUG: логируем, сколько чанков реально добавлено
        try:
            print("[INGEST FILE] tmp_path=", tmp_path, "tag=", base_metadata.get("tag"), "added=", added)
        except Exception:
            pass
        return {"ok": True, "chunks": added, "file": file.filename}
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


class URLIn(BaseModel):
    url: str = Field(..., description="URL to ingest", min_length=1, max_length=2048)


@router.post("/url")
async def ingest_url(
    request: Request, 
    body: URLIn, 
    session_id: str = Query(..., description="Session ID (required)", min_length=1),
    tag: Optional[str] = Query("phase10", description="Tag for the ingested URL", min_length=1, max_length=100)
):
    """
    @deprecated Not used by GoogleUI. Internal endpoint.
    Ingest from URL (legacy).
    """
    # Validate session_id
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
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
        "session_id": session_id,  # Include session_id in metadata
    }
    _id = f"url::{int(time.time())}"
    if hasattr(mgr, "add_texts"):
        mgr.add_texts([text], [meta], ids=[_id])
    else:
        mgr.collection.add(documents=[text], metadatas=[meta], ids=[_id])
    return {"ok": True, "saved": body.url}

# --- ingest: server-side process queue ---
from typing import List, Dict, Any
from fastapi import Request

@router.post("/process")
async def ingest_process(
    request: Request,
    session_id: str = Query(..., description="Session ID (required)", min_length=1)
) -> Dict[str, Any]:
    """
    @deprecated Not used by GoogleUI. Internal endpoint.
    Обрабатывает очередь: читает data/ingest/store/queue.json,
    извлекает текст и кладёт в память (meta.source=имя файла).
    """
    # Validate session_id
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    from pathlib import Path
    import json

    store = Path("data/ingest/store")
    queue_path = store / "queue.json"
    queue: List[Dict[str, Any]] = []
    if queue_path.exists():
        try:
            raw = queue_path.read_text(encoding="utf-8")
            queue = json.loads(raw) if raw.strip() else []
        except Exception as e:
            return {"ok": False, "error": f"queue read error: {e}"}  # экранировано

    if not isinstance(queue, list):
        return {"ok": False, "error": "queue.json is not a JSON list"}

    # Runtime guard: batch size limit
    if len(queue) > MAX_INGEST_BATCH_SIZE:
        logger.warning(f"[INGEST GUARD] Queue size {len(queue)} exceeds max batch size {MAX_INGEST_BATCH_SIZE}, truncating")
        queue = queue[:MAX_INGEST_BATCH_SIZE]

    def extract_text(p: Path) -> str:
        ext = ''.join(p.suffixes).lower() or p.suffix.lower()
        try:
            if ext in (".txt", ".md", ".log", ".csv", ""):
                try:  return p.read_text(encoding="utf-8", errors="ignore")
                except Exception: return p.read_text(errors="ignore")
            if ext == ".pdf":
                try:
                    from PyPDF2 import PdfReader  # type: ignore
                    parts = []
                    with p.open("rb") as fh:
                        r = PdfReader(fh)
                        pages = list(getattr(r, "pages", []) or [])
                        for pg in pages[:5]:
                            try: parts.append(pg.extract_text() or "")
                            except Exception: parts.append("")
                    return "\n".join(parts).strip()
                except Exception as e:
                    return f"[pdf extract error: {e}]"
            if ext == ".docx":
                try:
                    import docx  # type: ignore
                    d = docx.Document(str(p))
                    return "\n".join(par.text for par in d.paragraphs).strip()
                except Exception as e:
                    return f"[docx extract error: {e}]"
            try: return p.read_text(encoding="utf-8", errors="ignore")
            except Exception: return ""
        except Exception as e:
            return f"[extract error: {e}]"

    mgr = getattr(request.app.state, "memory_manager", None)
    if mgr is None:
        return {"ok": False, "error": "memory_manager not initialized in app.state"}

    processed, errors = [], []
    for item in queue:
        fname = (item or {}).get("file")
        if not fname:
            errors.append({"item": item, "err": "no file field"})
            continue
        fpath = store / fname
        if not fpath.exists() or not fpath.is_file():
            errors.append({"file": fname, "err": "not found in store"})
            continue

        text = extract_text(fpath)
        if not text.strip():
            errors.append({"file": fname, "err": "empty text"})
            continue

        meta = {"source": fname, "tag": "ingest", "session_id": session_id}
        try:
            if hasattr(mgr, "add_texts"):
                mgr.add_texts([text], [meta])
            elif hasattr(mgr, "collection"):
                mgr.collection.add(documents=[text], metadatas=[meta])
            elif hasattr(mgr, "add_text"):
                try:
                    mgr.add_text(user_id="dev", text=text, session_id=session_id, source="ingest")
                except TypeError:
                    mgr.add_text("dev", text, session_id, "ingest")
            else:
                raise RuntimeError("No supported add method on memory manager")
            processed.append(fname)
        except Exception as e:
            errors.append({"file": fname, "err": str(e)})

    try:
        queue_path.write_text("[]", encoding="utf-8")
    except Exception as e:
        errors.append({"queue_write": str(e)})

    return {"ok": True, "processed": processed, "errors": errors, "store": str(store)}


from fastapi import UploadFile, File, Request, Query
from pathlib import Path as _Path
import httpx as _httpx

@router.post("/ingest/file")
async def ingest_file(
    request: Request, 
    file: UploadFile = File(...), 
    session_id: str = Query(..., description="Session ID (required)", min_length=1),
    tag: str = Query(default="ui-upload", description="Tag for the ingested file", min_length=1, max_length=100)
):
    """
    Save -> commit -> process. Возвращает {"ok":true, digest, stored,...}
    Used by GoogleUI for file uploads.
    """
    # Validate session_id
    from backend.app.main import validate_session_id
    session_id = validate_session_id(session_id)
    inbox = _Path("data/ingest/inbox")
    inbox.mkdir(parents=True, exist_ok=True)

    name = _Path(file.filename).name
    dst = inbox / name

    # Runtime guard: file size limit (streaming check)
    total_size = 0
    with dst.open("wb") as fh:
        while True:
            chunk = await file.read(1024*1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_INGEST_FILE_SIZE_MB * 1024 * 1024:
                fh.close()
                dst.unlink(missing_ok=True)
                logger.warning(f"[INGEST GUARD] File size exceeds max {MAX_INGEST_FILE_SIZE_MB}MB during upload")
                raise HTTPException(
                    status_code=413,
                    detail=f"File size exceeds maximum allowed size of {MAX_INGEST_FILE_SIZE_MB}MB"
                )
            fh.write(chunk)

    async with _httpx.AsyncClient(timeout=30.0) as c:
        r_commit = await c.post("http://127.0.0.1:8000/ingest/commit", params={"name": name, "tag": request.query_params.get("tag","ui")})
        try:
            commit_json = r_commit.json()
        except Exception:
            commit_json = {"ok": False, "error": f"commit bad response: {r_commit.text}"}
        await c.post("http://127.0.0.1:8000/ingest/process")

    return {"ok": True, "saved": str(dst), **commit_json}

@router.get("/recent")
def ingest_recent(limit: int = 10):
    """
    @deprecated Not used by GoogleUI. Internal endpoint.
    AIR4: вернуть последние загруженные файлы из inbox.
    Основа для UI-индикатора "последние файлы".
    """
    inbox = _Path("data/ingest/inbox")
    inbox.mkdir(parents=True, exist_ok=True)

    files = sorted(
        [p for p in inbox.iterdir() if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    items = []
    for p in files[: max(1, min(limit, 50))]:
        st = p.stat()
        items.append({
            "name": p.name,
            "size": st.st_size,
            "mtime": st.st_mtime,
        })

    return {"ok": True, "files": items}
