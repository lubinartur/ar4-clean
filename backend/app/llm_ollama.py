# backend/app/llm_ollama.py
import os, httpx
from typing import List, Dict

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_MODEL", "mistral")  # например: "mistral" или "llama3:instruct"

def _chat(payload: dict) -> str:
    r = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    # новый API возвращает { "message": {"content": ...} }
    msg = (data.get("message") or {}).get("content") or ""
    # старый потоковый формат — на всякий:
    if not msg and "messages" in data:
        msg = "".join(m.get("content","") for m in data["messages"] if isinstance(m, dict))
    return msg.strip()

def chat_complete(messages: List[Dict]) -> str:
    """
    messages: [{"role":"system"/"user"/"assistant","content":"..."}]
    """
    return _chat({"model": MODEL, "messages": messages, "stream": False})

def complete(prompt: str) -> str:
    """
    Одноразовое завершение — оборачиваем в чат.
    """
    return chat_complete([{"role": "user", "content": prompt}])

