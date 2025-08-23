from fastapi import FastAPI
from datetime import datetime

app = FastAPI(title="AIr4 – dev sanity")

@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat() + "Z"}

if __name__ == "__main__":
    # Если порт занят, поменяй на 8010
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
