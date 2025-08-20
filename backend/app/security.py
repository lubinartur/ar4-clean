# backend/app/security.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any
from datetime import datetime, timedelta
import os
import uuid
import os
from dotenv import load_dotenv
load_dotenv(override=True)


router = APIRouter(prefix="/api/v0/secure", tags=["secure"])
bearer_scheme = HTTPBearer(auto_error=False)

# ====== КОНФИГ И ОКРУЖЕНИЕ ======
SAFE_WORD = os.getenv("SAFE_WORD", "")
PANIC_PHRASE = os.getenv("PANIC_PHRASE", "")
DURESS_PIN = os.getenv("DURESS_PIN", "")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "pass1234")  # для verify_password совместимости
TOKEN_TTL_MIN = int(os.getenv("TOKEN_TTL_MIN", "240"))  # 4 часа по умолчанию

# ====== СОСТОЯНИЕ БЕЗОПАСНОСТИ (in‑proc) ======
class SecurityState:
    locked: bool = False
    duress_active: bool = False
    token_blacklist: set[str] = set()         # явные невалидные
    token_whitelist: dict[str, datetime] = {} # активные токены с истечением

SEC = SecurityState()

# ====== ВСПОМОГАТЕЛЬНОЕ ======
def now_utc() -> datetime:
    return datetime.utcnow()

def new_request_id() -> str:
    return uuid.uuid4().hex[:12]

def is_token_invalidated(token: str) -> bool:
    if "*ALL*" in SEC.token_blacklist:
        return True
    if token in SEC.token_blacklist:
        return True
    # если whitelist не пуст, токен должен быть в whitelist и не протухший
    if SEC.token_whitelist:
        exp = SEC.token_whitelist.get(token)
        if exp is None or exp <= now_utc():
            return True
    return False

def invalidate_all_tokens() -> None:
    SEC.token_blacklist.add("*ALL*")
    SEC.token_whitelist.clear()

def invalidate_token(token: str) -> None:
    SEC.token_blacklist.add(token)
    SEC.token_whitelist.pop(token, None)

def issue_session(user_id: str = "dev") -> str:
    """
    Back‑compat: создать "сеанс" и выдать токен.
    В реальном проекте замени на JWT/sessions. Здесь — in‑proc хранение.
    """
    token = uuid.uuid4().hex
    SEC.token_whitelist[token] = now_utc() + timedelta(minutes=TOKEN_TTL_MIN)
    return token

def verify_password(password: str) -> bool:
    """
    Back‑compat: простая проверка пароля из .env (AUTH_PASSWORD).
    В реальном проекте — Argon2id/PBKDF2 хэш.
    """
    return password == AUTH_PASSWORD

def verify_token(token: str) -> dict:
    """
    Проверка токена (упрощённо). В реальном проекте — подпись/TTL/claims.
    """
    if not token or len(token) < 10:
        raise HTTPException(status_code=401, detail="Invalid token")
    if is_token_invalidated(token):
        raise HTTPException(status_code=401, detail="Token revoked/expired")
    # Можно парсить user_id из клеймов; тут — фиктивно.
    return {"user_id": "dev", "token": token}

def perform_wipe() -> None:
    """
    Реальный вайп: удалить мастер‑ключи, закрыть доступ. Полный вайп данных — только опционально.
    """
    # TODO: удалить ключи из keychain/файлов, стереть секреты, очистить сессии
    pass

def perform_export() -> str:
    """
    Зашифрованный экспорт памяти/настроек. Вернёт путь артефакта.
    """
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    artifact = f"exports/export-{ts}.air4.enc"
    # TODO: создать каталог exports/, собрать архив, зашифровать AES-GCM
    return artifact

def require_unlocked():
    if SEC.locked:
        raise HTTPException(status_code=423, detail="Interface is locked")

def require_safeword(safeword: str):
    if not SAFE_WORD:
        raise HTTPException(status_code=500, detail="SAFE_WORD is not configured")
    if safeword != SAFE_WORD:
        raise HTTPException(status_code=403, detail="Safe-word mismatch")

CONFIRM_STRINGS: Dict[str, str] = {
    "wipe": "WIPE ALL",
    "export": "I UNDERSTAND",
    "lock": "LOCK",
}

def require_confirm(action: str, confirm: Optional[str]):
    need = CONFIRM_STRINGS.get(action)
    if need and confirm != need:
        raise HTTPException(status_code=400, detail=f'Confirmation phrase required: "{need}"')

# ====== AUTH MIDDLEWARE (для secure‑роутов) ======
class Authed(BaseModel):
    user_id: str
    token: str

async def require_auth(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Authed:
    # panic допускаем без токена (обработчик сам проверит фразу)
    if request.url.path.endswith("/panic"):
        return Authed(user_id="panic", token="panic")
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = creds.credentials
    payload = verify_token(token)
    if SEC.locked and not request.url.path.endswith("/status"):
        raise HTTPException(status_code=423, detail="Interface is locked")
    return Authed(user_id=payload["user_id"], token=token)

# ====== Pydantic схемы ======
ActionType = Literal["wipe", "lock", "export"]

class SecureActionRequest(BaseModel):
    type: ActionType
    safeword: str
    confirm: Optional[str] = None

class SecureActionResponse(BaseModel):
    ok: bool
    action: ActionType
    status: str
    request_id: str
    meta: Dict[str, Any] = {}

class PanicRequest(BaseModel):
    phrase: str

class StatusResponse(BaseModel):
    locked: bool
    duress_active: bool
    request_id: str

# ====== РОУТЫ SECURE ======
@router.get("/status", response_model=StatusResponse)
async def status_endpoint() -> StatusResponse:
    return StatusResponse(
        locked=SEC.locked,
        duress_active=SEC.duress_active,
        request_id=new_request_id(),
    )

@router.post("/action", response_model=SecureActionResponse)
async def secure_action(body: SecureActionRequest, _auth: Authed = Depends(require_auth)):
    rid = new_request_id()
    action = body.type

    require_unlocked()
    require_safeword(body.safeword)
    require_confirm(action, body.confirm)

    if action == "lock":
        SEC.locked = True
        invalidate_all_tokens()
        return SecureActionResponse(ok=True, action=action, status="locked", request_id=rid, meta={})

    if action == "wipe":
        SEC.locked = True
        invalidate_all_tokens()
        perform_wipe()
        return SecureActionResponse(ok=True, action=action, status="locked", request_id=rid, meta={"wiped": "keys"})

    if action == "export":
        artifact = perform_export()
        return SecureActionResponse(ok=True, action=action, status="ok", request_id=rid, meta={"artifact": artifact})

    raise HTTPException(status_code=400, detail="Unsupported action")

@router.post("/panic", response_model=SecureActionResponse, status_code=status.HTTP_200_OK)
async def panic_endpoint(body: PanicRequest):
    rid = new_request_id()
    if not PANIC_PHRASE:
        raise HTTPException(status_code=500, detail="PANIC_PHRASE is not configured")
    if body.phrase != PANIC_PHRASE:
        raise HTTPException(status_code=403, detail="Forbidden")

    SEC.locked = True
    invalidate_all_tokens()

    return SecureActionResponse(
        ok=True, action="lock", status="locked", request_id=rid, meta={"reason": "panic"}
    )

# ====== BACK‑COMPAT АПИ ДЛЯ ТВОЕГО main.py ======
def is_locked() -> bool:
    return SEC.locked

def secure_status() -> dict:
    return {"locked": SEC.locked, "duress_active": SEC.duress_active}

def lock() -> None:
    SEC.locked = True
    invalidate_all_tokens()
