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

        added = ingest_path(mgr, tmp_path, base_metadata=base_metadata, chunk_size=512, overlap=64)
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

# --- ingest: server-side process queue ---
from typing import List, Dict, Any
from fastapi import Request

@router.post("/process")
async def ingest_process(request: Request) -> Dict[str, Any]:
    """Обрабатывает очередь: читает data/ingest/store/queue.json,
    извлекает текст и кладёт в память (meta.source=имя файла)."""
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

        meta = {"source": fname, "tag": "ingest"}
        try:
            if hasattr(mgr, "add_texts"):
                mgr.add_texts([text], [meta])
            elif hasattr(mgr, "collection"):
                mgr.collection.add(documents=[text], metadatas=[meta])
            elif hasattr(mgr, "add_text"):
                try:
                    mgr.add_text(user_id="dev", text=text, session_id=None, source="ingest")
                except TypeError:
                    mgr.add_text("dev", text, None, "ingest")
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
async def ingest_file(request: Request, file: UploadFile = File(...), tag: str = Query(default="ui-upload")):
    """
    Save -> commit -> process. Возвращает {"ok":true, digest, stored,...}
    """
    inbox = _Path("data/ingest/inbox")
    inbox.mkdir(parents=True, exist_ok=True)

    name = _Path(file.filename).name
    dst = inbox / name

    with dst.open("wb") as fh:
        while True:
            chunk = await file.read(1024*1024)
            if not chunk:
                break
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
