# backend/app/security.py
from __future__ import annotations

import os, time, hmac, json, hashlib
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException

try:
    import bcrypt  # pip install bcrypt
except Exception:
    bcrypt = None  # позволим работать в фолбэке (только с открытыми паролями из ENV)

router = APIRouter(prefix="/api/v0/secure", tags=["secure"])

# ===== ENV =====
AUTH_PASSWORD       = os.getenv("AUTH_PASSWORD", "")
AUTH_PASSWORD_HASH  = os.getenv("AUTH_PASSWORD_HASH", "")
DURESS_PIN          = os.getenv("DURESS_PIN", "0000")  # по умолчанию 0000 (можно очистить и оставить только HASH)
DURESS_PIN_HASH     = os.getenv("DURESS_PIN_HASH", "")

SAFE_WORD           = os.getenv("SAFE_WORD", "parrot")
PANIC_PHRASE        = os.getenv("PANIC_PHRASE", "redbutton")

AUTH_SECRET         = os.getenv("AUTH_SECRET", "CHANGE_ME_64_HEX_OR_RANDOM")
# Поддерживаем старую переменную TOKEN_TTL_MIN
_ttl_sec = os.getenv("TOKEN_TTL_SEC")
if _ttl_sec is None:
    TOKEN_TTL_SEC = int(os.getenv("TOKEN_TTL_MIN", "60")) * 60  # default: 60 мин
else:
    TOKEN_TTL_SEC = int(_ttl_sec)

# ===== Глобальное (процесс) состояние интерфейса =====
STATE: Dict[str, Any] = {
    "locked": False,
    "duress_active": False,  # включается при duress-логине, выключается при обычном логине/lock
}

# ===== Утилиты паролей/пинов =====
def _bcrypt_check(plain: str, hashed: str) -> bool:
    if not bcrypt:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def _check_secret(plain: str, hashed: str, fallback_plain: str = "") -> bool:
    """
    Сначала сверяем bcrypt-хэш, если задан.
    Иначе (на переходный период) сравниваем с открытым значением из ENV.
    """
    if hashed:
        return _bcrypt_check(plain, hashed)
    if fallback_plain:
        return hmac.compare_digest(plain, fallback_plain)
    return False

# ===== Токены (HMAC-JWS-подобный формат: body.json + '.' + sha256(body)) =====
def _sign(claims: Dict[str, Any]) -> str:
    body = json.dumps(claims, separators=(",", ":"), ensure_ascii=False)
    sig = hmac.new(AUTH_SECRET.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"

def _verify(token: str) -> Dict[str, Any]:
    try:
        body, sig = token.rsplit(".", 1)
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed token")
    good = hmac.new(AUTH_SECRET.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        claims = json.loads(body)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token body")
    return claims

# ===== Публичные функции, которые использует main.py =====
def issue_session(user_id: str = "default", duress: bool = False) -> str:
    now = int(time.time())
    claims = {
        "iat": now,
        "exp": now + TOKEN_TTL_SEC,
        "user_id": "duress" if duress else (user_id or "default"),
        "profile": "duress" if duress else "default",
        "duress": bool(duress),
    }
    # включаем/выключаем глобальный флаг duress для статуса
    STATE["duress_active"] = bool(duress)
    # при выдаче токена интерфейс считается разблокированным
    STATE["locked"] = False
    return _sign(claims)

def verify_token(token: str) -> Dict[str, Any]:
    claims = _verify(token)
    now = int(time.time())
    exp = int(claims.get("exp", 0))
    if exp and now > exp:
        raise HTTPException(status_code=401, detail="Token expired")
    # здесь можно подключить revocation-list при необходимости
    return claims

def verify_password(password: str) -> bool:
    """
    Проверка обычного пароля. Для duress используется DURESS_PIN отдельно в main.py.
    """
    return _check_secret(password, AUTH_PASSWORD_HASH, AUTH_PASSWORD)

def lock() -> None:
    STATE["locked"] = True
    # при явной блокировке можно сбрасывать duress-индикатор
    # STATE["duress_active"] = False

def unlock() -> None:
    STATE["locked"] = False

def is_locked() -> bool:
    return bool(STATE.get("locked"))

def secure_status() -> Dict[str, Any]:
    return {
        "locked": bool(STATE.get("locked")),
        "duress_active": bool(STATE.get("duress_active")),
    }

# ===== Роутер /api/v0/secure/* =====
@router.get("/status")
def api_secure_status():
    """Статус интерфейса/режима."""
    return {"locked": is_locked(), "duress_active": bool(STATE.get("duress_active"))}

# (опционально — можно включить по желанию)
# @router.post("/lock")
# def api_secure_lock():
#     lock()
#     return {"ok": True}
#
# @router.post("/unlock")
# def api_secure_unlock():
#     unlock()
#     return {"ok": True}
