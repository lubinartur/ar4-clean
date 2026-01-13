# ============================================================================
# DEPRECATED: This file is NOT the main entrypoint.
# ============================================================================
# 
# DO NOT USE THIS FILE. It is kept for historical reference only.
# 
# The ONLY valid entrypoint is:
#   uvicorn backend.app.main:app --reload
# 
# This dev_server.py was a minimal test server and is no longer used.
# All functionality has been moved to backend/app/main.py
# 
# ============================================================================

from fastapi import FastAPI
from datetime import datetime

# DEPRECATED: This FastAPI instance is not used in production.
app = FastAPI(title="AIr4 – dev sanity [DEPRECATED]")

@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat() + "Z"}

if __name__ == "__main__":
    # DEPRECATED: Do not run this file directly.
    # Use: uvicorn backend.app.main:app --reload
    import uvicorn
    print("[WARNING] This entrypoint is DEPRECATED. Use: uvicorn backend.app.main:app --reload")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
