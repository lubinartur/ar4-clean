# backend/app/chat.py — AIr4 v0.11.3 (Profile + RAG + styles + DeepSeek fix)
from __future__ import annotations

import os
import re
import uuid
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field

from backend.app.routes_profile import load_profile as _load_user_profile

# ==== ENV / defaults ====
PORT = int(os.getenv("PORT", "8000"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL_DEFAULT = os.getenv("OLLAMA_MODEL_DEFAULT", "llama3.1:8b")


def _memory_backend() -> str:
    return "fallback" if os.getenv("AIR4_MEMORY_FORCE_FALLBACK", "0") == "1" else "chroma"


RAG_MIN_SCORE_FALLBACK = float(os.getenv("AIR4_RAG_MIN_SCORE_FALLBACK", "0.60"))
RAG_MIN_SCORE_CHROMA = float(os.getenv("AIR4_RAG_MIN_SCORE_CHROMA", "0.20"))


def _min_score() -> float:
    return RAG_MIN_SCORE_FALLBACK if _memory_backend() == "fallback" else RAG_MIN_SCORE_CHROMA


GREETING_RE = re.compile(r"^(hi|hello|hey|привет|здрав|qq|ку|yo|sup)\b", re.I)


def _is_greeting(q: str) -> bool:
    q = (q or "").strip()
    return (len(q) < 5) or bool(GREETING_RE.search(q))


# ===== Style presets =====
STYLE_DEFAULT = "short"
STYLES: Dict[str, Dict[str, Any]] = {
    "short": {
        "prompt": (
            "Отвечай кратко и по-русски. Пиши по делу, без лишних предисловий. "
            "Формат: 1–3 коротких предложения или лаконичный список. "
            "Если нужен код/формула — дай минимально достаточный фрагмент. "
            "Не повторяй вопрос и не извиняйся."
        ),
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "repeat_penalty": 1.15,
            "num_ctx": 4096,
            "num_predict": 128,
        },
    },
    "normal": {
        "prompt": "Отвечай по-русски, понятно и без воды.",
        "options": {
            "temperature": 0.35,
            "top_p": 0.95,
            "repeat_penalty": 1.1,
            "num_ctx": 4096,
            "num_predict": 256,
        },
    },
    "detailed": {
        "prompt": (
            "Отвечай развёрнуто по-русски. Структурируй ответ, используй подзаголовки/списки по мере необходимости."
        ),
        "options": {
            "temperature": 0.6,
            "top_p": 0.97,
            "repeat_penalty": 1.05,
            "num_ctx": 6144,
            "num_predict": 512,
        },
    },
}


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class ChatBody(BaseModel):
    message: str
    session_id: Optional[str] = None
    system: Optional[str] = None
    stream: bool = False
    use_rag: bool = True
    k_memory: int = Field(4, ge=1, le=50)
    style: Optional[str] = Field(STYLE_DEFAULT, description="short | normal | detailed")
    settings: Optional[Dict[str, Any]] = None
    model_override: Optional[str] = Field(None, description="Preferred model from UI")


class ChatResult(BaseModel):
    ok: bool = True
    reply: str
    session_id: str
    memory_used: Optional[List[str]] = None


# -----------------------------------------------------------------------------
# Memory retrieval
# -----------------------------------------------------------------------------
async def _memory_search_http(query: str, k: int) -> List[Dict[str, Any]]:
    import httpx

    url = f"http://127.0.0.1:{PORT}/memory/search"
    params = {"q": query, "k": k}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params)
        r.raise_for_status()
        obj = r.json() or {}
    except Exception:
        return []

    results = obj.get("results") or []
    out: List[Dict[str, Any]] = []
    for it in results:
        rid = it.get("id") or it.get("h") or it.get("hash") or ""
        txt = (
            it.get("text")
            or it.get("chunk")
            or it.get("content")
            or it.get("value")
            or ""
        )
        scr = it.get("score", 0.0)
        if isinstance(txt, dict):
            txt = txt.get("text") or txt.get("content") or ""
        if str(txt).strip():
            out.append({"id": str(rid), "text": str(txt), "score": float(scr)})
    return out[:k]


def _format_sources_for_system(blocks: List[str]) -> str:
    return "Relevant context (top-k):\n" + "\n\n---\n".join(blocks)


def _profile_block_from_request(headers: Dict[str, str]) -> str:
    try:
        user_id = headers.get("X-User", "dev")
    except Exception:
        user_id = "dev"
    try:
        prof = _load_user_profile(user_id)
    except Exception:
        return ""

    prefs = getattr(prof, "preferences", {}) or {}
    facts = getattr(prof, "facts", {}) or {}
    goals = getattr(prof, "goals", []) or []

    parts = []
    if getattr(prof, "name", None):
        parts.append(f"name={prof.name}")
    if prefs:
        parts.append(
            "prefs=" + ",".join([f"{k}:{v}" for k, v in list(prefs.items())[:5]])
        )
    if facts:
        parts.append(
            "facts=" + ",".join([f"{k}:{v}" for k, v in list(facts.items())[:6]])
        )
    if goals:
        parts.append(
            "goals="
            + "; ".join(
                [getattr(g, "title", getattr(g, "id", "")) for g in goals][:3]
            )
        )

    return "USER_PROFILE: " + " | ".join(parts) if parts else ""


def build_messages(
    system: Optional[str],
    memory_blocks: List[str],
    user_text: str,
    headers: Dict[str, str],
    style_prompt: Optional[str],
) -> List[dict]:
    # Merge profile block
    profile_block = _profile_block_from_request(headers)
    if profile_block:
        system = (system + "\n" + profile_block) if system else profile_block

    # Prepend style prompt if provided
    if style_prompt:
        system = style_prompt + ("\n" + system if system else "")

    messages: List[dict] = []
    if system:
        messages.append({"role": "system", "content": str(system)})
    if memory_blocks:
        messages.append(
            {"role": "system", "content": _format_sources_for_system(memory_blocks)}
        )
    messages.append({"role": "user", "content": str(user_text)})
    return messages


def _summarize_for_sources_display(text: str, limit: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else (text[:limit].rstrip() + "…")


# -----------------------------------------------------------------------------
# Ollama call
# -----------------------------------------------------------------------------
async def call_ollama(
    messages: List[dict],
    session_id: Optional[str],
    options: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
) -> str:
    import httpx
    import json

    # Базовые опции из стиля
    options = options or STYLES[STYLE_DEFAULT]["options"]

    # Нормализуем имя модели
    resolved_model = _resolve_model_name(model)
    print(f"[LLM DEBUG] override={model!r} -> resolved={resolved_model!r}")

    # Для DeepSeek R1 даём минимум 256 токенов, чтобы было чем отвечать
    if resolved_model.startswith("deepseek-r1"):
        try:
            opts = dict(options)
        except Exception:
            opts = {"num_predict": 512}
        num_pred = int(opts.get("num_predict", 128))
        if num_pred < 512:
            opts["num_predict"] = 512
        options = opts

    url = f"{OLLAMA_BASE_URL}/api/chat"

    payload = {
        "model": resolved_model,
        "messages": messages,
        "stream": False,
        "options": options,
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=payload)
        r.raise_for_status()

        raw = (r.text or "").strip()
        msg_text = ""
        obj: Optional[dict] = None

        # 1) Пытаемся прочитать как NDJSON (несколько JSON-строк)
        if raw:
            last_obj = None
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except Exception:
                    continue
                last_obj = parsed

                # если по пути нашли контент — обновим msg_text
                m_obj = (parsed.get("message") or {}) if isinstance(parsed, dict) else {}
                candidate = (
                    m_obj.get("content")
                    or parsed.get("response")
                    or parsed.get("output_text")
                    or ""
                )
                if isinstance(candidate, str) and candidate.strip():
                    msg_text = candidate.strip()

            if isinstance(last_obj, dict):
                obj = last_obj

        # 2) Если NDJSON не дал результата — обычный JSON
        if not msg_text:
            try:
                obj = r.json() or {}
            except Exception:
                obj = None

            if isinstance(obj, dict):
                m_obj = obj.get("message") or {}
                candidate = (
                    m_obj.get("content")
                    or m_obj.get("response")
                    or obj.get("response")
                    or obj.get("output_text")
                    or ""
                )
                if isinstance(candidate, str) and candidate.strip():
                    msg_text = candidate.strip()

        # 3) Если DeepSeek вернул только thinking — берём первую содержательную строку
        if not msg_text and isinstance(obj, dict) and resolved_model.startswith(
            "deepseek-r1"
        ):
            m_obj = obj.get("message") or {}
            thinking = m_obj.get("thinking")
            if isinstance(thinking, str) and thinking.strip():
                # Берём первую более-менее вменяемую строку
                for line in thinking.splitlines():
                    line = line.strip()
                    if line:
                        msg_text = line
                        break

        # 4) Фолбэк — аккуратное сообщение об ошибке контента
        if not msg_text:
            msg_text = (
                "Модель не вернула явного текста ответа. "
                "Попробуй ещё раз или переформулируй запрос."
            )

        clean = str(msg_text).strip()

        # --- DeepSeek R1 cleanup: убираем мысли и служебные рассуждения ---
        resolved_model.startswith("deepseek-r1")
        return f"[{resolved_model}] " + clean

    except Exception as e:
        return f"[{resolved_model}] Ошибка при вызове Ollama: {str(e)}"


def _resolve_model_name(requested: Optional[str]) -> str:
    """
    Нормализует имя модели из UI/override в конкретный ID для Ollama.
    """
    if not requested:
        return OLLAMA_MODEL_DEFAULT

    key = str(requested).strip().lower()

    # LLaMA 3.1 family / default
    if key in {
        OLLAMA_MODEL_DEFAULT.lower(),
        "llama3.1:8b",
        "llama3.1-8b",
        "llama3",
        "llama3-8b",
        "llama 3.1 8b",
    }:
        return "llama3.1:8b"

    # Mistral
    if key in {"mistral-7b", "mistral", "mistral 7b"}:
        return "mistral:latest"

    # Hermes / Mixtral
    if key in {
        "hermes-7b",
        "nous-hermes",
        "nous-hermes2-mixtral:8x7b",
        "mixtral-8x7b",
        "mixtral",
    }:
        return "nous-hermes2-mixtral:8x7b"

    # DeepSeek 14B
    if key in {"deepseek-r1:14b", "deepseek-14b", "deepseek 14b"}:
        return "deepseek-r1:14b"

    # DeepSeek 32B / generic
    if key in {
        "deepseek-r1:32b",
        "deepseek",
        "deepseek-r1",
        "deepseek-32b",
        "deepseek 32b",
    }:
        return "deepseek-r1:32b"

    # Fallback
    return OLLAMA_MODEL_DEFAULT


# -----------------------------------------------------------------------------
# High-level endpoint helper
# -----------------------------------------------------------------------------
async def chat_endpoint_call(body: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    data = ChatBody(**body)

    style_key = (data.style or STYLE_DEFAULT).lower()
    cfg = STYLES.get(style_key, STYLES[STYLE_DEFAULT])
    style_prompt = cfg["prompt"]

    # RAG
    memory_blocks: List[str] = []
    if data.use_rag and not _is_greeting(data.message):
        memory_results = await _memory_search_http(data.message, data.k_memory)
        memory_blocks = [
            res["text"] for res in memory_results if res["score"] >= _min_score()
        ]

    messages = build_messages(
        data.system,
        memory_blocks,
        data.message,
        headers,
        style_prompt,
    )

    reply_text = await call_ollama(
        messages,
        session_id=data.session_id,
        options=cfg.get("options"),
        model=data.model_override,
    )

    return {
        "ok": True,
        "reply": reply_text,
        "session_id": data.session_id or str(uuid.uuid4()),
        "memory_used": [b[:100] for b in memory_blocks] if memory_blocks else None,
    }