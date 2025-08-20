# backend/app/llm_client.py
"""
Шим под любой твой локальный клиент.
Пытается использовать backend/app/llm_ollama.py, но оставляет общий интерфейс:
- complete(prompt: str) -> str
- chat_complete(messages: list[dict]) -> str
"""

from typing import List, Dict

try:
    # пробуем использовать уже существующий файл
    from . import llm_ollama as _src
except Exception as e:  # нет llm_ollама — оставим понятную ошибку
    _src = None
    _import_err = e

class LLMNotConfigured(RuntimeError):
    pass

def _ensure():
    if _src is None:
        raise LLMNotConfigured(f"LLM backend is not configured: {_import_err}")

def complete(prompt: str) -> str:
    """
    Одноразовое завершение (для саммари).
    """
    _ensure()
    # предпочитаемые имена функций
    for name in ("complete", "generate", "completion"):
        fn = getattr(_src, name, None)
        if callable(fn):
            return (fn(prompt) or "").strip()
    # fallback через чат
    chat_fn = getattr(_src, "chat_complete", None) or getattr(_src, "chat", None) or getattr(_src, "generate_chat", None)
    if callable(chat_fn):
        return (chat_fn([{"role": "user", "content": prompt}]) or "").strip()
    raise LLMNotConfigured("No suitable method found in llm_ollama.*")

def chat_complete(messages: List[Dict]) -> str:
    """
    Многоходовый чат (для /chat).
    """
    _ensure()
    for name in ("chat_complete", "chat", "generate_chat"):
        fn = getattr(_src, name, None)
        if callable(fn):
            return (fn(messages) or "").strip()
    # fallback через complete на последнем сообщении пользователя
    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    return complete(last_user)

