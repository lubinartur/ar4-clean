from __future__ import annotations
import io, re, hashlib
from typing import Tuple
import httpx

# опционально для PDF
try:
    import PyPDF2  # pip install PyPDF2
except Exception:
    PyPDF2 = None

MAX_CHARS = 50_000

def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_CHARS]

async def fetch_url_text(url: str) -> Tuple[str, str]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(15, read=30), follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        content = r.content

    if "pdf" in ct.lower():
        return (parse_pdf_bytes(content) or ""), ct

    if "html" in ct.lower() or b"<html" in content[:200].lower():
        # грубое удаление тегов
        txt = re.sub(br"<script[\s\S]*?</script>|<style[\s\S]*?</style>", b" ", content, flags=re.I)
        txt = re.sub(br"<[^>]+>", b" ", txt)
        try:
            text = txt.decode("utf-8", errors="ignore")
        except Exception:
            text = txt.decode("latin-1", errors="ignore")
        return _clean(text), ct

    # как обычный текст
    try:
        text = content.decode("utf-8", errors="ignore")
    except Exception:
        text = content.decode("latin-1", errors="ignore")
    return _clean(text), ct

def parse_pdf_bytes(data: bytes) -> str | None:
    if not PyPDF2:
        return None
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        pages = []
        for p in reader.pages:
            pages.append(p.extract_text() or "")
        return _clean("\n".join(pages))
    except Exception:
        return None

def synth_session_id(prefix: str, source_id: str) -> str:
    h = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{h}"
