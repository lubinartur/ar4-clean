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
