# backend/app/ingest/readers.py — Phase 10: PDF/DOCX/MD/TXT + chunking
# с безопасным фолбэком на manager.add_text(...)
from __future__ import annotations

import os
import re
import time
from typing import Dict, List, Optional, Tuple

# ---- optional deps ----
_HAS_DOCX = False
_HAS_PYPDF = False
try:
    import docx  # python-docx
    _HAS_DOCX = True
except Exception:
    pass
try:
    from pypdf import PdfReader
    _HAS_PYPDF = True
except Exception:
    pass

# ---- readers ----
def read_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def read_md(path: str) -> str:
    text = read_txt(path)
    # убрать код-блоки ```...```
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    # [текст](url) -> текст
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # простая чистка маркдауна
    text = re.sub(r"[#*_>`~\-]{1,}", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()

def read_docx(path: str) -> str:
    if not _HAS_DOCX:
        raise RuntimeError("python-docx не установлен. Установи: pip install python-docx")
    d = docx.Document(path)
    return "\n".join(p.text for p in d.paragraphs)

def read_pdf(path: str) -> str:
    if not _HAS_PYPDF:
        raise RuntimeError("pypdf не установлен. Установи: pip install pypdf")
    reader = PdfReader(path)
    out = []
    for page in reader.pages:
        try:
            out.append(page.extract_text() or "")
        except Exception:
            pass
    return "\n".join(out)

# ---- chunking ----
def chunk_text(text: str, chunk_size: int = 900, overlap: int = 160) -> List[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks: List[str] = []
    i = 0
    step = max(1, chunk_size - overlap)
    n = len(text)
    while i < n:
        chunks.append(text[i : i + chunk_size])
        i += step
    return chunks

def infer_title(text: str) -> Optional[str]:
    t = text.strip().split("\n", 1)[0]
    t = re.sub(r"\s+", " ", t).strip()
    return t[:80] or None

# ---- ingest core ----
def ingest_path(
    manager,
    path: str,
    base_metadata: Optional[Dict] = None,
    chunk_size: int = 900,
    overlap: int = 160,
) -> int:
    """
    Ингест одного файла с чанкингом. Возвращает кол-во добавленных чанков.
    Пишем в хранилище одним из способов:
      1) manager.add_texts(docs, metas, ids=ids)
      2) manager.collection.add(...)
      3) ФОЛБЭК: manager.add_text(user_id='dev', text=chunk, ...) — по одному чанку
    """
    base_metadata = dict(base_metadata or {})
    base_metadata.setdefault("ts", int(time.time()))
    base_metadata.setdefault("source", os.path.abspath(path))
    ext = os.path.splitext(path)[1].lower()
    base_metadata.setdefault("ext", ext)

    if ext == ".txt":
        text = read_txt(path)
    elif ext in (".md", ".markdown"):
        text = read_md(path)
    elif ext == ".docx":
        text = read_docx(path)
    elif ext == ".pdf":
        text = read_pdf(path)
    else:
        raise RuntimeError(f"Unsupported extension: {ext}")

    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        return 0

    title = infer_title(text) or os.path.basename(path)
    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict] = []
    for i, ch in enumerate(chunks):
        ids.append(f"{path}::chunk-{i}")
        md = dict(base_metadata)
        md["chunk"] = i
        md["title"] = title
        docs.append(ch)
        metas.append(md)

    # --- путь 1: bulk API
    if hasattr(manager, "add_texts"):
        manager.add_texts(docs, metas, ids=ids)
        return len(chunks)

    # --- путь 2: прямая коллекция
    if hasattr(manager, "collection"):
        manager.collection.add(documents=docs, metadatas=metas, ids=ids)
        return len(chunks)

    # --- путь 3: фолбэк — по одному чанку через add_text(...)
    if hasattr(manager, "add_text"):
        user_id = getattr(manager, "default_user_id", "dev")
        for ch in docs:
            # у твоего Phase-9 менеджера сигнатура: add_text(user_id, text, session_id, source)
            try:
                manager.add_text(user_id=user_id, text=ch, session_id=None, source=base_metadata.get("kind", "file"))
            except TypeError:
                # если сигнатура другая — пробуем без именованных
                try:
                    manager.add_text(user_id, ch, None, base_metadata.get("kind", "file"))
                except Exception:
                    # крайний случай — проглатываем, чтобы не ронять сервер
                    pass
        return len(chunks)

    # если менеджер вообще не поддерживает добавление
    raise RuntimeError("Manager must provide add_texts(...), collection.add(...), or add_text(...)")


def ingest_path(
    manager,
    path: str,
    base_metadata: Optional[Dict] = None,
    chunk_size: int = 900,
    overlap: int = 160,
) -> int:
    base_metadata = dict(base_metadata or {})
    base_metadata.setdefault("ts", int(time.time()))
    # не трогаем base_metadata["source"], если её уже проставили снаружи (например, 'file'/'url')
    base_metadata.setdefault("source", "file")

    # добавляем путь и имя файла (их раньше не было)
    abs_path = os.path.abspath(path)
    base_metadata.setdefault("source_path", abs_path)
    base_metadata.setdefault("filename", os.path.basename(abs_path))

    ext = os.path.splitext(path)[1].lower()
    base_metadata.setdefault("ext", ext)

    if ext == ".txt":
        text = read_txt(path)
    elif ext in (".md", ".markdown"):
        text = read_md(path)
    elif ext == ".docx":
        text = read_docx(path)
    elif ext == ".pdf":
        text = read_pdf(path)
    else:
        raise RuntimeError(f"Unsupported extension: {ext}")

    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        return 0

    title = infer_title(text) or os.path.basename(path)
    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict] = []

    for i, ch in enumerate(chunks):
        ids.append(f"{path}::chunk-{i}")
        md = dict(base_metadata)
        md["chunk"] = i
        md["chunk_index"] = i          # совместимость с выдачей, где ожидается chunk_index
        md["title"] = title
        docs.append(ch)
        metas.append(md)

    if hasattr(manager, "add_texts"):
        manager.add_texts(docs, metas, ids=ids)
        return len(chunks)

    if hasattr(manager, "collection"):
        manager.collection.add(documents=docs, metadatas=metas, ids=ids)
        return len(chunks)

    if hasattr(manager, "add_text"):
        user_id = getattr(manager, "default_user_id", "dev")
        for ch in docs:
            try:
                manager.add_text(user_id=user_id, text=ch, session_id=None, source=base_metadata.get("kind", "file"))
            except TypeError:
                try:
                    manager.add_text(user_id, ch, None, base_metadata.get("kind", "file"))
                except Exception:
                    pass
        return len(chunks)

    raise RuntimeError("Manager must provide add_texts(...), collection.add(...), or add_text(...)")
