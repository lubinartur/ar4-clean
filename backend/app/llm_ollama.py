from __future__ import annotations
import os, json
from typing import Any, Dict, List, Optional, AsyncGenerator
import httpx


# Настройки
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "mistral:latest")

def _build_messages(
    user_msg: str,
    history: Optional[List[Dict[str, str]]] = None,
    system: Optional[str] = None,
) -> List[Dict[str, str]]:
    msgs: List[Dict[str, str]] = []
    if system:
        msgs.append({"role": "system", "content": system})
    if history:
        for h in history:
            role = h.get("role") or "user"
            content = h.get("content") or ""
            if content:
                msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": user_msg})
    return msgs

async def _non_stream_chat(payload: Dict[str, Any]) -> Dict[str, str]:
    async with httpx.AsyncClient(base_url=OLLAMA_BASE_URL, timeout=httpx.Timeout(30, read=180)) as client:
        r = await client.post("/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()
        text = (data.get("message") or {}).get("content") or ""
        return {"text": text}

async def _stream_chat(payload: Dict[str, Any]) -> AsyncGenerator[Dict[str, str], None]:
    # Ollama в stream-режиме выдаёт JSON-объекты построчно
    async with httpx.AsyncClient(base_url=OLLAMA_BASE_URL, timeout=httpx.Timeout(30, read=None)) as client:
        async with client.stream("POST", "/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                delta = (obj.get("message") or {}).get("content") or ""
                if delta:
                    yield {"delta": delta}

async def chat_llm(
    user_msg: str,
    history: Optional[List[Dict[str, str]]] = None,
    system: Optional[str] = None,
    model: Optional[str] = None,
    stream: bool = False,
) -> Any:
    """
    Унифицированный клиент LLM:
      - stream=False -> dict {"text": "..."}
      - stream=True  -> async generator, дающий чанки {"delta": "..."}
    """
    messages = _build_messages(user_msg=user_msg, history=history, system=system)
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "stream": stream,
    }

    try:
        if stream:
            return _stream_chat(payload)
        else:
            return await _non_stream_chat(payload)
    except (httpx.ConnectError, httpx.HTTPError) as e:
        # Любая HTTP-проблема -> безопасный фолбэк, чтобы /chat не упал
        fallback = f"[LLM error] {type(e).__name__}: {e}"
        if stream:
            async def gen():
                yield {"delta": fallback}
            return gen()
        return {"text": fallback}
    except Exception as e:
        # Непредвиденное -> тоже фолбэк
        fallback = f"[LLM unexpected error] {type(e).__name__}: {e}"
        if stream:
            async def gen():
                yield {"delta": fallback}
            return gen()
        return {"text": fallback}
