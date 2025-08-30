from typing import List, Dict
import re

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 200) -> List[Dict]:
    if not text:
        return []
    t = re.sub(r"\s+", " ", text.strip())
    if not t:
        return []
    chunks = []
    start = 0
    n = len(t)
    while start < n:
        end = min(start + chunk_size, n)
        chunk = t[start:end]
        idx = len(chunks)
        chunks.append({"text": chunk, "index": idx})
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks
