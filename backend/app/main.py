# backend/app/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import subprocess
from dotenv import load_dotenv

# ── Env ────────────────────────────────────────────────────────────────────────
load_dotenv()
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
SAFE_WORD = os.getenv("SAFE_WORD", "")
PANIC_PHRASE = os.getenv("PANIC_PHRASE", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")  # инфо-поле

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="AIR4 API", version="0.0.1")

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

# ── Utils ──────────────────────────────────────────────────────────────────────
def run_ollama(model: str, prompt: str) -> str:
    """Запуск ollama run <model> <prompt> и возврат stdout как строки."""
    try:
        # Важно: prompt передаём как единый аргумент
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Ollama не найден в PATH.")
    if result.returncode != 0:
        err = (result.stderr or "Unknown error").strip()
        raise HTTPException(status_code=500, detail=f"Ollama error: {err}")
    return (result.stdout or "").strip()

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", tags=["health"])
def read_root():
    return {"message": "AIR4 API is running locally"}

@app.get("/health", tags=["health"])
def health():
    # Простая проверка наличия модели/хоста (информативно)
    return {
        "status": "ok",
        "ollama_model": OLLAMA_MODEL,
        "ollama_host": OLLAMA_HOST,
    }

@app.post("/chat", response_model=ChatResponse, tags=["chat"])
def chat(request: ChatRequest):
    # Короткий системный контекст по умолчанию
    system = (
        "Ты — локальный оффлайн‑ассистент AIR4. Отвечай кратко (1–3 строки) и по делу. "
        "По умолчанию трактуй финансовые термины в финансовом контексте. "
        "DTI = debt-to-income ratio (отношение ежемесячных долговых платежей к ежемесячному доходу, в %). "
        "Если аббревиатура многозначна — сначала предложи финансовую трактовку или задай уточнение."
    )
    prompt = f"{system}\n\nВопрос: {request.message}\nОтвет:"
    text = run_ollama(OLLAMA_MODEL, prompt)
    return ChatResponse(response=text)

