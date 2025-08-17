# backend/app/main.py
from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Optional

from .summarizer import AutoSummarizer
from . import llm_client

app = FastAPI()

# --- инициализация автосаммари ---
summarizer = AutoSummarizer()  # без llm_call — будет fallback

# === модели ===
class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: Optional[str] = "default"
    end_session: Optional[bool] = False
    web_query: Optional[str] = None  # <- для авто-подмешивания веб-контекста

class ChatResponse(BaseModel):
    reply: str
    injected_summaries: List[str] = []
    summary: Optional[str] = None

# === вспомогательное ===
def _recent_texts(user_id: str, k: int = 2) -> List[str]:
    rows = summarizer.recent(user_id=user_id, limit=k)
    return [text for (text, md) in rows]

def _messages_from_req(req: ChatRequest, injected: List[str]) -> List[Dict]:
    msgs: List[Dict] = []
    if injected:
        sys_block = "Короткая память:\n" + "\n\n".join(f"— {t}" for t in injected)
        msgs.append({
            "role": "system",
            "content": sys_block,
            "metadata": {"session_id": req.session_id}
        })
    msgs.append({
        "role": "user",
        "content": req.message,
        "metadata": {"session_id": req.session_id}
    })
    return msgs

# === эндпоинт /chat ===
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    injected = _recent_texts(req.user_id or "default", k=2)

    # при наличии web_query — подтягиваем веб-контекст и внедряем в system
    if req.web_query:
        try:
            from .tools.web import web_search, web_fetch
            hits = web_search(req.web_query, max_results=2)
            chunks: List[str] = []
            for h in hits:
                try:
                    page = web_fetch(h["url"], max_chars=3000)
                    chunks.append(f"# {page['title']}\n{page['url']}\n\n{page['text'][:1200]}")
                except Exception:
                    pass
            if chunks:
                injected.insert(0, "Веб-контекст:\n" + "\n\n---\n\n".join(chunks))
        except Exception:
            pass

    messages = _messages_from_req(req, injected)

    # аккуратный системный промт — строгость формата и опора на веб-контекст
    sys_prompt = (
        "Ты — техлид проекта AIR4 на macOS.\n"
        "Если в системном сообщении есть блок 'Веб-контекст', считай его единственным источником истины: "
        "опирайся ТОЛЬКО на него, не выдумывай и не добавляй неподтверждённые детали.\n"
        "Отвечай строго в формате:\n"
        "1) Цель (1–2 строки)\n"
        "2) Шаги с готовыми командами (zsh) и/или коротким корректным кодом\n"
        "3) Проверка (коротко)\n"
        "4) Что сохранить (коротко)\n"
        "Правила: будь точным, не придумывай инструментов/флагов; для Python показывай рабочие минимальные примеры. "
        "Пример для asyncio.run:\n"
        "  import asyncio\n"
        "  async def main(): ...\n"
        "  if __name__ == '__main__':\n"
        "      asyncio.run(main())\n"
        "Ограничения: нельзя вызывать внутри уже работающего цикла событий; "
        "в Jupyter/REPL использовать await или asyncio.Runner."
    )

    try:
        reply = llm_client.chat_complete([
            {"role": "system", "content": sys_prompt},
            *messages
        ])
    except Exception:
        reply = f"(LLM не настроен) Я получил: {req.message}"

    saved_summary: Optional[str] = None
    if req.end_session:
        saved = summarizer.summarize_session(messages, user_id=req.user_id, session_id=req.session_id)
        saved_summary = saved["summary"]

    return ChatResponse(reply=reply, injected_summaries=injected, summary=saved_summary)

# === health ===
@app.get("/health")
def health():
    return {"ok": True}

# === TOOLS REGISTRY ===
def _run_tool(name: str, params: dict):
    # ленивые импорты
    if name == "read_text":
        from .tools.files import read_text
        return read_text(**(params or {}))
    if name == "read_pdf":
        from .tools.files import read_pdf
        return read_pdf(**(params or {}))
    if name == "csv_head":
        from .tools.data import csv_head
        return csv_head(**(params or {}))
    if name == "web_search":
        from .tools.web import web_search
        return web_search(**(params or {}))
    if name == "web_fetch":
        from .tools.web import web_fetch
        return web_fetch(**(params or {}))
    if name == "docs_search":
        from .tools.web import docs_search
        return docs_search(**(params or {}))
    if name == "http_get":
        from .tools.web import http_get
        return http_get(**(params or {}))
    raise ValueError(f"Unknown tool: {name}")

@app.post("/tools")
def tools(payload: dict = Body(...)):
    name = payload.get("name")
    params = payload.get("params") or {}
    try:
        result = _run_tool(name, params)
        return {"ok": True, "tool": name, "result": result}
    except Exception as e:
        return JSONResponse(status_code=400, content={"ok": False, "tool": name, "error": str(e)})

