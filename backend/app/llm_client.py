# backend/app/llm_client.py
from __future__ import annotations
import httpx
from typing import List, Dict, Any, Optional

class LLMClient:
    def __init__(self, base_url: str, model: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        stream: bool = False,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        messages = [{"role": "system"|"user"|"assistant", "content": "..."}]
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": options or {"temperature": temperature},
        }
        url = f"{self.base_url}/api/chat"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # Expected Ollama /api/chat response:
        # { "message": {"role": "assistant", "content": "..."} , "done": true, ... }
        if isinstance(data, dict) and "message" in data and isinstance(data["message"], dict):
            return data["message"].get("content", "").strip()

        # Fallback: try /api/generate format if needed
        # { "response": "..." }
        if isinstance(data, dict) and "response" in data:
            return str(data["response"]).strip()

        # If format unknown:
        return str(data).strip()
