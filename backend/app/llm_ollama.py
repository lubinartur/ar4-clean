import os
import requests

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct")  # поменяй при желании

def generate(messages):
    """
    messages: список dict [{"role":"system"/"user"/"assistant","content":"..."}]
    Возвращает: текст ответа ассистента (str)
    """
    url = f"{OLLAMA_BASE}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False
    }
    r = requests.post(url, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    # формат Ollama chat
    if "message" in data and "content" in data["message"]:
        return data["message"]["content"]
    # на случай другого формата
    if "choices" in data and data["choices"]:
        return data["choices"][0].get("message", {}).get("content", "")
    return ""

