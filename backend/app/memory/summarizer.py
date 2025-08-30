# backend/app/memory/summarizer.py
from __future__ import annotations
from typing import Callable, Dict, Any, List, Optional
import re, json, time
from .manager import MemoryManager

_SUMMARY_PROMPT = """You are a concise analyst.
Given the latest user turn and assistant reply, produce a compact session rollup.

Return strict JSON with keys:
- "tldr": 1-3 short bullets (string with '•' bullets allowed)
- "facts": list of atomic facts worth remembering (<=6 items, short, timeless)
- "todos": list of actionable TODOs for the user (<=5)
- "entities": list of important names/IDs (<=6)

Avoid duplication with prior summary (if provided).
User turn: {user_msg}
Assistant: {assistant_msg}
Prior summary (may be empty JSON): {prior_summary}
"""

_ROLLUP_PROMPT = """You will merge a prior JSON summary with a delta JSON summary.
Deduplicate, keep it short, keep only durable facts/TODOs.
Return strict JSON with the same keys: tldr, facts, todos, entities.

Prior: {prior}
Delta: {delta}
"""

class Summarizer:
    def __init__(self, llm_fn: Callable[..., Any]):
        """
        llm_fn(message:str, system:Optional[str], model:str, history:Optional[List], stream:bool)->dict/str/asyncgen
        We will call it with stream=False and expect {"text": "..."} or str.
        """
        self.llm_fn = llm_fn
        self.memory = MemoryManager()

    async def _ask(self, prompt: str) -> str:
        resp = await self.llm_fn(prompt, history=None, system=None, model=None, stream=False)
        return resp.get("text") if isinstance(resp, dict) else str(resp)

    def _safe_json(self, text: str) -> Dict[str, Any]:
        # попытка вытащить JSON даже если модель добавит префикс
        m = re.search(r"\{.*\}\s*$", text, re.S)
        raw = m.group(0) if m else text
        try:
            return json.loads(raw)
        except Exception:
            return {"tldr": "", "facts": [], "todos": [], "entities": []}

    async def summarize_and_store(self, user_id: str, session_id: Optional[str],
                                  user_msg: str, assistant_msg: str) -> None:
        if not session_id:
            # если нет session_id — не сохраняем сводку (безопасный выход)
            return
        prior = self.memory.get_summary(user_id=user_id, session_id=session_id) or {}
        prompt = _SUMMARY_PROMPT.format(
            user_msg=user_msg.strip(), assistant_msg=assistant_msg.strip(),
            prior_summary=json.dumps(prior, ensure_ascii=False)
        )
        delta_json = self._safe_json(await self._ask(prompt))

        if prior:
            merge_prompt = _ROLLUP_PROMPT.format(
                prior=json.dumps(prior, ensure_ascii=False),
                delta=json.dumps(delta_json, ensure_ascii=False),
            )
            merged = self._safe_json(await self._ask(merge_prompt))
        else:
            merged = delta_json

        # Сохраняем сводку
        self.memory.save_summary(user_id=user_id, session_id=session_id, summary=merged)

        # Пишем факты/дела в память с дедупом
        facts = merged.get("facts") or []
        todos = merged.get("todos") or []
        if facts:
            self.memory.add_facts(user_id=user_id, session_id=session_id, facts=facts, tags=["summary"], dedup=True)
        if todos:
            self.memory.add_todos(user_id=user_id, session_id=session_id, todos=todos, tags=["summary"], dedup=True)
