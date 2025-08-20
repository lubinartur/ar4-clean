from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
from typing import Optional, List
from security import Settings, AuditLogger, AuthManager, RBACMiddleware, AuditEventsMiddleware, SecureState

app = FastAPI(title="AIR4 API", version="0.5.0-phase5")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

settings = Settings(); audit = AuditLogger(settings.AUDIT_LOG); auth = AuthManager(settings, audit); secure_state = SecureState()
app.add_middleware(RBACMiddleware, auth=auth); app.add_middleware(AuditEventsMiddleware, audit=audit)

def _auth_header_token(request: Request) -> Optional[str]:
    ah = request.headers.get("authorization") or request.headers.get("Authorization")
    if not ah or not ah.lower().startswith("bearer "): return None
    return ah.split(" ", 1)[1].strip()

@app.get("/health")
async def health(): return {"ok": True, "v": app.version}

@app.post("/auth/login")
async def login(request: Request):
    try: data = await request.json()
    except Exception: data = {}
    password = (data.get("password") or "").strip()
    if not password: raise HTTPException(status_code=400, detail="Missing password")
    res = auth.login(password, request); return {"ok": True, **res}

@app.post("/auth/logout")
async def logout(request: Request):
    token = _auth_header_token(request)
    if not token: raise HTTPException(status_code=401, detail="Missing token")
    auth.revoke(token, request); return {"ok": True}

@app.get("/api/v0/secure/status")
async def secure_status(request: Request):
    token = _auth_header_token(request); duress_active=False; profile=None
    if token:
        try: ti = auth.verify(token); profile = ti.profile; duress_active = (ti.profile == "duress")
        except HTTPException: pass
    return {"locked": secure_state.is_locked(), "duress_active": duress_active, "profile": profile, "request_id": uuid.uuid4().hex[:12]}

@app.post("/api/v0/secure/lock")
async def secure_lock(request: Request):
    token = _auth_header_token(request); ti = auth.verify(token)
    if ti.profile == "duress": raise HTTPException(status_code=403, detail="RBAC: duress cannot lock")
    secure_state.set_locked(True); audit.log("lock", request, ti.profile, ok=True); return {"ok": True, "locked": True}

@app.post("/api/v0/secure/unlock")
async def secure_unlock(request: Request):
    token = _auth_header_token(request); ti = auth.verify(token)
    if ti.profile == "duress": raise HTTPException(status_code=403, detail="RBAC: duress cannot unlock")
    secure_state.set_locked(False); audit.log("unlock", request, ti.profile, ok=True); return {"ok": True, "locked": False}

_memory: List[str] = []

@app.get("/memory/search")
async def memory_search(q: Optional[str] = None, k: int = 3):
    if not q: return {"results": _memory[-k:][::-1]}
    res = [m for m in _memory if q.lower() in m.lower()]; return {"results": res[:k]}

@app.post("/memory/add")
async def memory_add(request: Request):
    data = await request.json(); text = (data.get("text") or "").strip()
    if not text: raise HTTPException(status_code=400, detail="Missing text")
    _memory.append(text); return {"ok": True, "size": len(_memory)}

@app.post("/chat")
async def chat(request: Request):
    data = await request.json(); message = (data.get("message") or "").strip()
    if not message: raise HTTPException(status_code=400, detail="Missing message")
    return {"ok": True, "reply": f"echo: {message}", "request_id": uuid.uuid4().hex[:8]}
