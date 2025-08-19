from pathlib import Path
from typing import Optional

def read_text(path: str, encoding: Optional[str] = "utf-8", max_chars: int = 20000) -> str:
    p = Path(path).expanduser().resolve()
    return p.read_text(encoding=encoding)[:max_chars]

def read_pdf(path: str, max_chars: int = 20000) -> str:
    from pypdf import PdfReader
    p = Path(path).expanduser().resolve()
    r = PdfReader(str(p))
    out = []
    for pg in r.pages:
        out.append(pg.extract_text() or "")
        if sum(len(x) for x in out) >= max_chars:
            break
    return "\n".join(out)[:max_chars]

