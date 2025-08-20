# backend/app/rag.py
from __future__ import annotations
from typing import List, Dict

MAX_CONTEXT_CHARS = 6000

def build_rag_context(blocks: List[str], max_chars: int = MAX_CONTEXT_CHARS) -> str:
    out, total = [], 0
    for b in blocks:
        blen = len(b)
        if total + blen <= max_chars:
            out.append(b); total += blen
        else:
            remain = max_chars - total
            if remain > 0:
                out.append(b[:remain])
            break
    return "\n\n---\n\n".join(out)

def build_messages_with_rag(query: str, context_blocks: List[str]) -> List[Dict[str, str]]:
    """
    Формируем messages для LLM. Контекст отдаём в system, запрос — в user.
    """
    rag_context = build_rag_context(context_blocks)
    sys = (
        "Ты — ассистент AIR4. Отвечай ТОЛЬКО на основе предоставленного контекста.\n"
        "Если контекста недостаточно — скажи об этом кратко.\n"
        "Формат: 1) Краткий ответ 2) Аргументы из контекста (2–4 пункта).\n"
        "Запрещено использовать внешние знания.\n\n"
        f"RAG-контекст:\n{rag_context}"
    )
    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": query},
    ]
