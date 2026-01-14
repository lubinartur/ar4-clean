from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx, urllib.parse
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter()

SYS = (
    "You are AIR4. Answer STRICTLY and ONLY using the provided Context.\n"
    "If the answer is not fully supported by Context, reply exactly: NOT IN MEMORY.\n"
    "Be concise."
)

async def fetch_memory(query: str, k: int = 4):
    url = f"http://127.0.0.1:8000/memory/search?q={urllib.parse.quote(query)}&k={k}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url)
        if r.status_code != 200:
            return []
        j = r.json()
        return j.get("results", []) if isinstance(j, dict) else []

class ChatRagRequest(BaseModel):
    q: Optional[str] = Field(None, description="Query text")
    msg: Optional[str] = Field(None, description="Query text (alias)")

    def get_query_text(self) -> str:
        """Extract query text from various possible fields."""
        for field in [self.q, self.msg]:
            if field and isinstance(field, str) and field.strip():
                return field.strip()
        return ""


@router.post("/chat/rag")
async def chat_rag(body: ChatRagRequest):
    """
    @deprecated Not used by GoogleUI. Alternative RAG endpoint.
    RAG chat endpoint (legacy, use /chat instead).
    """
    q = body.get_query_text()
    if not q:
        raise HTTPException(status_code=400, detail="Query text is required (provide 'q' or 'msg')")

    # ---- retrieve via HTTP API to ensure parity with /memory/search ----
    hits = await fetch_memory(q, k=4)
    parts = []
    for h in hits:
        t = (h.get("text") or "")[:900]
        meta = h.get("meta") or {}
        src = meta.get("source","")
        parts.append(f"[{src}] {t}")
    ctx = "\n\n".join(parts) if parts else ""

    # debug view
    if request.query_params.get("debug") == "1":
        return {"q": q, "hits": len(hits), "ctx_head": (ctx[:400] if ctx else "")}

    # ---- prompt ----
    if ctx:
        user_prompt = (
            f"Context:\n{ctx}\n\n"
            f"Question: {q}\n"
            "Rules: Use ONLY the Context above. If unknown or partial → reply exactly: NOT IN MEMORY."
        )
    else:
        user_prompt = (
            "Context:\n[EMPTY]\n\n"
            f"Question: {q}\n"
            "Rules: No context provided → reply exactly: NOT IN MEMORY."
        )

    # ---- LLM call, no streaming, t=0 ----
    payload = {
        "model": "llama3.1:8b",
        "stream": False,
        "messages": [
            {"role": "system", "content": SYS},
            {"role": "user",   "content": user_prompt},
        ],
        "options": {"temperature": 0}
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post("http://127.0.0.1:11434/api/chat", json=payload)
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and "message" in j:
                    return {"reply": (j["message"].get("content","") or "").strip()}
                return {"reply": str(j)[:4000]}
            return {"reply": f"llm http {r.status_code}"}
    except Exception as e:
        return {"reply": f"llm error: {e}"}
