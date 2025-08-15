from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

from backend.app.llm_ollama import run_ollama

# Загружаем .env
load_dotenv()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

app = FastAPI(title="AIR4 API", version="0.0.1")

# CORS — на время разработки всё открыто
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "AIR4 API is running locally"}

@app.get("/health")
def health():
    return {"status": "ok", "ollama_model": OLLAMA_MODEL, "ollama_host": OLLAMA_HOST}

@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    message = data.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Empty 'message'")
    system = (
        "Ты — локальный оффлайн-ассистент AIR4. Отвечай кратко (1–3 строки) и по делу. "
        "По умолчанию трактуй финансовые термины в финансовом контексте. "
        "DTI = debt-to-income ratio (отношение ежемесячных долговых платежей к ежемесячному доходу, в %). "
        "Если аббревиатура многозначна — сначала предложи финансовую трактовку или задай уточнение."
    )
    prompt = f"{system}\n\nВопрос: {message}\nОтвет:"
    answer = run_ollama(OLLAMA_MODEL, prompt)
    return {"response": answer}

