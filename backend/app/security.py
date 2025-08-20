import os, hmac, hashlib, json, threading, time, uuid
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

def _getenv(name: str, default: Optional[str] = None) -> str:
    val = os.getenv(name);  return default if (val is None or val=="") else val

class Settings:
    def __init__(self)->None:
        self.AUTH_PASSWORD=_getenv("AUTH_PASSWORD","0000")
        self.AUTH_PASSWORD_HASH=_getenv("AUTH_PASSWORD_HASH","")
        self.DURESS_PASSWORD=_getenv("DURESS_PASSWORD","9111")
        self.DURESS_PASSWORD_HASH=_getenv("DURESS_PASSWORD_HASH","")
        self.SECRET_KEY=_getenv("SECRET_KEY","dev-secret-key")
        self.TOKEN_TTL_SEC=int(_getenv("TOKEN_TTL_SEC","86400") or "86400")
        self.AUDIT_LOG=_getenv("AUDIT_LOG","storage/audit.log")

def sha256_hex(s:str)->str: return hashlib.sha256(s.encode("utf-8")).hexdigest()
def constant_time_eq(a:str,b:str)->bool: return hmac.compare_digest(a,b)
def ensure_dir(path:str)->None:
    d=os.path.dirname(path);  os.makedirs(d,exist_ok=True) if d and not os.path.exists(d) else None
def get_client_ip(request:Request)->str:
    xff=request.headers.get("x-forwarded-for")
    if xff: return xff.split(",")[0].strip()
    xri=request.headers.get("x-real-ip")
    if xri: return xri.strip()
    client=request.client;  return getattr(client,"host","unknown")

class AuditLogger:
    def __init__(self, filepath:str):
        self.filepath=filepath; ensure_dir(filepath); self._lock=threading.Lock()
    def log(self,event:str,request:Optional[Request],profile:Optional[str],ok:bool=True,**fields:Any)->None:
        rec={"ts":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"event":event,"ok":ok,
             "ip": get_client_ip(request) if request is not None else None,
             "ua": (request.headers.get("user-agent") if request else None) if request else None,
             "profile":profile}
        rec.update(fields)
        line=json.dumps(rec,ensure_ascii=False)
        with self._lock:
            with open(self.filepath,"a",encoding="utf-8") as f: f.write(line+"\n")

class TokenInfo:
    __slots__=("token","profile","created_at","expires_at","revoked")
    def __init__(self, token:str, profile:str, ttl_sec:int):
        now=int(time.time()); self.token=token; self.profile=profile
        self.created_at=now; self.expires_at=now+ttl_sec; self.revoked=False

class AuthManager:
    def __init__(self, settings:Settings, audit:AuditLogger):
        self.settings=settings; self.audit=audit; self._tokens:Dict[str,TokenInfo]={}; self._lock=threading.Lock()
    def _password_matches(self, provided:str, target_plain:str, target_hash:str)->bool:
        return constant_time_eq(sha256_hex(provided), target_hash.lower()) if target_hash else constant_time_eq(provided, target_plain)
    def login(self, password:str, request:Request)->Dict[str,Any]:
        profile=None
        if self._password_matches(password,self.settings.DURESS_PASSWORD,self.settings.DURESS_PASSWORD_HASH): profile="duress"
        elif self._password_matches(password,self.settings.AUTH_PASSWORD,self.settings.AUTH_PASSWORD_HASH): profile="default"
        else:
            self.audit.log("login",request,None,ok=False,reason="bad-password"); raise HTTPException(status_code=401, detail="Invalid credentials")
        token=uuid.uuid4().hex; ti=TokenInfo(token,profile,self.settings.TOKEN_TTL_SEC)
        with self._lock: self._tokens[token]=ti
        self.audit.log("login",request,profile,ok=True,token=token[:8])
        return {"token":token,"profile":profile,"ttl_sec":self.settings.TOKEN_TTL_SEC}
    def verify(self, token:Optional[str])->TokenInfo:
        if not to




# ПЕРЕЗАПИСАТЬ ФАЙЛЫ Ф5
cat > backend/app/security.py <<'PY'
import os, hmac, hashlib, json, threading, time, uuid
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

def _getenv(name: str, default: Optional[str] = None) -> str:
    val = os.getenv(name);  return default if (val is None or val=="") else val

class Settings:
    def __init__(self)->None:
        self.AUTH_PASSWORD=_getenv("AUTH_PASSWORD","0000")
        self.AUTH_PASSWORD_HASH=_getenv("AUTH_PASSWORD_HASH","")
        self.DURESS_PASSWORD=_getenv("DURESS_PASSWORD","9111")
        self.DURESS_PASSWORD_HASH=_getenv("DURESS_PASSWORD_HASH","")
        self.SECRET_KEY=_getenv("SECRET_KEY","dev-secret-key")
        self.TOKEN_TTL_SEC=int(_getenv("TOKEN_TTL_SEC","86400") or "86400")
        self.AUDIT_LOG=_getenv("AUDIT_LOG","storage/audit.log")

def sha256_hex(s:str)->str: return hashlib.sha256(s.encode("utf-8")).hexdigest()
def constant_time_eq(a:str,b:str)->bool: return hmac.compare_digest(a,b)
def ensure_dir(path:str)->None:
    d=os.path.dirname(path);  os.makedirs(d,exist_ok=True) if d and not os.path.exists(d) else None
def get_client_ip(request:Request)->str:
    xff=request.headers.get("x-forwarded-for")
    if xff: return xff.split(",")[0].strip()
    xri=request.headers.get("x-real-ip")
    if xri: return xri.strip()
    client=request.client;  return getattr(client,"host","unknown")

class AuditLogger:
    def __init__(self, filepath:str):
        self.filepath=filepath; ensure_dir(filepath); self._lock=threading.Lock()
    def log(self,event:str,request:Optional[Request],profile:Optional[str],ok:bool=True,**fields:Any)->None:
        rec={"ts":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"event":event,"ok":ok,
             "ip": get_client_ip(request) if request is not None else None,
             "ua": (request.headers.get("user-agent") if request else None) if request else None,
             "profile":profile}
        rec.update(fields)
        line=json.dumps(rec,ensure_ascii=False)
        with self._lock:
            with open(self.filepath,"a",encoding="utf-8") as f: f.write(line+"\n")

class TokenInfo:
    __slots__=("token","profile","created_at","expires_at","revoked")
    def __init__(self, token:str, profile:str, ttl_sec:int):
        now=int(time.time()); self.token=token; self.profile=profile
        self.created_at=now; self.expires_at=now+ttl_sec; self.revoked=False

class AuthManager:
    def __init__(self, settings:Settings, audit:AuditLogger):
        self.settings=settings; self.audit=audit; self._tokens:Dict[str,TokenInfo]={}; self._lock=threading.Lock()
    def _password_matches(self, provided:str, target_plain:str, target_hash:str)->bool:
        return constant_time_eq(sha256_hex(provided), target_hash.lower()) if target_hash else constant_time_eq(provided, target_plain)
    def login(self, password:str, request:Request)->Dict[str,Any]:
        profile=None
        if self._password_matches(password,self.settings.DURESS_PASSWORD,self.settings.DURESS_PASSWORD_HASH): profile="duress"
        elif self._password_matches(password,self.settings.AUTH_PASSWORD,self.settings.AUTH_PASSWORD_HASH): profile="default"
        else:
            self.audit.log("login",request,None,ok=False,reason="bad-password"); raise HTTPException(status_code=401, detail="Invalid credentials")
        token=uuid.uuid4().hex; ti=TokenInfo(token,profile,self.settings.TOKEN_TTL_SEC)
        with self._lock: self._tokens[token]=ti
        self.audit.log("login",request,profile,ok=True,token=token[:8])
        return {"token":token,"profile":profile,"ttl_sec":self.settings.TOKEN_TTL_SEC}
    def verify(self, token:Optional[str])->TokenInfo:
        if not token: raise HTTPException(status_code=401, detail="Missing token")
        with self._lock: ti=self._tokens.get(token)
        if ti is None: raise HTTPException(status_code=401, detail="Invalid token")
        now=int(time.time())
        if ti.revoked: raise HTTPException(status_code=401, detail="Token revoked")
        if now>=ti.expires_at: raise HTTPException(status_code=401, detail="Token expired")
        return ti
    def revoke(self, token:str, request:Request)->None:
        with self._lock:
            ti=self._tokens.get(token)
            if ti is None: self.audit.log("logout",request,None,ok=False,reason="unknown-token"); return
            ti.revoked=True
        self.audit.log("logout",request,ti.profile,ok=True,token=token[:8])

class SecureState:
    def __init__(self): self._lock=threading.Lock(); self._locked=False
    def set_locked(self,v:bool): 
        with self._lock: self._locked=v
    def is_locked(self)->bool:
        with self._lock: return self._locked

class RBACMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, auth:AuthManager, allow_paths:Optional[list[str]]=None):
        super().__init__(app); self.auth=auth
        self.allow_paths=allow_paths or ["/health","/auth/login","/auth/logout","/api/v0/secure/status","/chat","/memory/search"]
    async def dispatch(self, request:Request, call_next):
        path=request.url.path
        if path.startswith("/health") or path.startswith("/auth/login"):
            return await call_next(request)
        auth_header=request.headers.get("authorization") or request.headers.get("Authorization")
        token=None
        if auth_header and auth_header.lower().startswith("bearer "): token=auth_header.split(" ",1)[1].strip()
        if not token: return JSONResponse({"detail":"Missing token"}, status_code=401)
        try: ti=self.auth.verify(token)
        except HTTPException as exc: return JSONResponse({"detail":exc.detail}, status_code=exc.status_code)
        if ti.profile=="duress":
            if not any(path.startswith(p) for p in self.allow_paths):
                return JSONResponse({"detail":"RBAC: blocked in duress profile"}, status_code=403)
        request.state.auth=ti
        return await call_next(request)

class AuditEventsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, audit:AuditLogger):
        super().__init__(app); self.audit=audit
    async def dispatch(self, request:Request, call_next):
        response=await call_next(request)
        try:
            path=request.url.path; method=request.method.upper()
            profile=getattr(getattr(request,"state",None),"auth",None); prof=profile.profile if profile else None
            if method=="POST" and path.startswith("/chat"):
                self.audit.log("chat",request,prof,ok=(200<=response.status_code<400))
            elif method=="POST" and path.startswith("/memory/add"):
                self.audit.log("memory.add",request,prof,ok=(200<=response.status_code<400))
        except Exception: pass
        return response
