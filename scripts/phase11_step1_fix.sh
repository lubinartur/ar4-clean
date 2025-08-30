#!/opt/homebrew/bin/bash
set -euo pipefail

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
APP_MAIN="backend.app.main:app"
PROFILE_PY="backend/app/routes_profile.py"
MAIN_PY="backend/app/main.py"

echo "==[1/6] Ensure routes_profile.py exists (overwrite-safe)=="
mkdir -p backend/app storage/profile
cat > "$PROFILE_PY" <<'PY'
from __future__ import annotations
import json, os
from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/memory/profile", tags=["memory-profile"])

STORAGE_DIR = os.environ.get("PROFILE_STORAGE_DIR", "storage/profile")
os.makedirs(STORAGE_DIR, exist_ok=True)

def _safe_user_id(u: str) -> str:
    return "".join(c for c in u if c.isalnum() or c in ("-", "_")) or "dev"

def _path(user_id: str) -> str:
    return os.path.join(STORAGE_DIR, f"{_safe_user_id(user_id)}.json")

class Goal(BaseModel):
    id: str
    title: str
    status: str = "active"
    progress: float = 0.0

class UserProfile(BaseModel):
    user_id: str = Field(default="dev")
    schema_version: int = 1
    name: Optional[str] = None
    preferences: Dict[str, Any] = Field(default_factory=dict)
    facts: Dict[str, Any] = Field(default_factory=dict)
    goals: List[Goal] = Field(default_factory=list)
    updated_at: Optional[str] = None

def load_profile(user_id: str) -> UserProfile:
    p = _path(user_id)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return UserProfile(**data)
    prof = UserProfile(user_id=user_id, updated_at=datetime.utcnow().isoformat())
    save_profile(prof)
    return prof

def save_profile(profile: UserProfile) -> None:
    profile.updated_at = datetime.utcnow().isoformat()
    with open(_path(profile.user_id), "w", encoding="utf-8") as f:
        json.dump(profile.model_dump(), f, ensure_ascii=False, indent=2)

@router.get("", response_model=UserProfile)
def get_profile(user_id: str = "dev"):
    return load_profile(user_id)

class ProfilePatch(BaseModel):
    name: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None
    facts: Optional[Dict[str, Any]] = None
    goals: Optional[List[Goal]] = None

@router.patch("", response_model=UserProfile)
def patch_profile(patch: ProfilePatch, user_id: str = "dev"):
    prof = load_profile(user_id)
    data = prof.model_dump()
    if patch.name is not None:
        data["name"] = patch.name
    if patch.preferences is not None:
        data["preferences"] = {**data.get("preferences", {}), **patch.preferences}
    if patch.facts is not None:
        data["facts"] = {**data.get("facts", {}), **patch.facts}
    if patch.goals is not None:
        data["goals"] = [g.model_dump() for g in patch.goals]
    new_prof = UserProfile(**data)
    save_profile(new_prof)
    return new_prof

@router.put("", response_model=UserProfile)
def put_profile(profile: UserProfile):
    save_profile(profile)
    return profile
PY

echo "==[2/6] Patch main.py to include router (idempotent)=="
python3 - <<'PY'
import pathlib, re
p = pathlib.Path("backend/app/main.py")
t = p.read_text(encoding="utf-8")

import_added = "from backend.app.routes_profile import router as profile_router" in t
include_added = re.search(r"app\.include_router\(\s*profile_router\s*\)", t) is not None

if not import_added:
    # Вставим импорт после других импортов
    lines = t.splitlines()
    # Найдём позицию последнего import/from блока сверху
    idx = 0
    for i, L in enumerate(lines[:200]):
        if L.startswith("from ") or L.startswith("import "):
            idx = i
    lines.insert(idx+1, "from backend.app.routes_profile import router as profile_router")
    t = "\n".join(lines)

if not include_added:
    # Вставим include после создания app или после других include_router
    m = re.search(r"\napp\s*=\s*FastAPI\([^)]*\)\s*\n", t)
    insert_pos = m.end() if m else len(t)
    # Найти последний include_router и стать после него
    last_inc = None
    for m2 in re.finditer(r"app\.include_router\([^)]*\)\s*\n", t):
        last_inc = m2
    if last_inc:
        insert_pos = last_inc.end()
    t = t[:insert_pos] + "app.include_router(profile_router)\n" + t[insert_pos:]

p.write_text(t, encoding="utf-8")
print("patched")
PY

echo "==[3/6] Restart uvicorn=="
if [[ -f .uvicorn.pid ]]; then
  pkill -P "$(cat .uvicorn.pid)" 2>/dev/null || true
  kill "$(cat .uvicorn.pid)" 2>/dev/null || true
  rm -f .uvicorn.pid
fi
uvicorn "$APP_MAIN" --host "$HOST" --port "$PORT" --reload > .uvicorn.out 2>&1 & echo $! > .uvicorn.pid

echo "==[4/6] Wait for /health=="
for i in {1..60}; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://$HOST:$PORT/health" || true)
  [[ "$code" == "200" ]] && { echo "health: $code"; break; }
  sleep 0.3
done
[[ "${code:-}" == "200" ]]

echo "==[5/6] Verify OpenAPI has /memory/profile=="
curl -s "http://$HOST:$PORT/openapi.json" | grep -q '"/memory/profile"' && echo "openapi: route present" || { echo "openapi: route NOT present"; tail -n 50 ./.uvicorn.out || true; exit 1; }

echo "==[6/6] GET/PATCH/GET profile=="
echo "GET #1"
curl -s "http://$HOST:$PORT/memory/profile" | jq '.user_id,.schema_version,.updated_at' || true

echo "PATCH"
curl -s -X PATCH "http://$HOST:$PORT/memory/profile" \
  -H 'Content-Type: application/json' \
  -d '{"name":"AR4","preferences":{"tone":"bro","lang":"ru"},"facts":{"country":"EE","bike":"Ducati"},"goals":[{"id":"g1","title":"Moonlight Sonata 1:30","progress":0.3}]}' \
  | jq '.name,.preferences,.facts,.goals[0]' || true

echo "GET #2"
curl -s "http://$HOST:$PORT/memory/profile" | jq '.name,.preferences,.facts,.goals[0],.updated_at' || true

echo "OK: profile endpoints alive."
