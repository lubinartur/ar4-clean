from fastapi import FastAPI
from backend.app.memory.schemas import IngestReq, SearchReq, ProfilePatch, ChatReq
from backend.app.chat import build_context, on_user_message, on_assistant_message, add_fact
from backend.app.memory.manager import MemoryManager
from backend.app.llm_ollama import generate

app = FastAPI(title="AIR4 API — Phase 2")

# создаём общий MemoryManager
_mm = MemoryManager()

# передаём его в модуль chat
from backend.app import chat as chatmod
chatmod.set_memory_manager(_mm)


@app.post("/memory/ingest")
def ingest(req: IngestReq):
    doc_id = _mm.ingest(req.text, req.meta)
    return {"ok": True, "id": doc_id}


@app.post("/memory/search")
def search(req: SearchReq):
    hits = _mm.retrieve(req.query, k=req.k)
    return {"ok": True, "results": hits}


@app.post("/memory/upsert-profile")
def upsert(req: ProfilePatch):
    profile = _mm.upsert_profile(req.patch)
    return {"ok": True, "profile": profile}


@app.post("/chat")
def chat(req: ChatReq):
    on_user_message(req.message)
    ctx = build_context(req.message, top_k=req.top_k, with_short_summary=req.with_short_summary)

    messages = [
        {"role": "system", "content": ctx},
        {"role": "user", "content": req.message},
    ]

    answer = generate(messages)
    on_assistant_message(answer)

    if len(answer) > 250:
        add_fact(answer[:600], {"source": "auto_summary"})

    return {"ok": True, "answer": answer}

