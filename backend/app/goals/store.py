# backend/app/goals/store.py — Phase F1: Goals storage
from __future__ import annotations

import json
import os
import time
import uuid
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field

STORAGE_DIR = os.environ.get("GOALS_STORAGE_DIR", "data/goals")
GOALS_FILE = os.path.join(STORAGE_DIR, "goals.json")
os.makedirs(STORAGE_DIR, exist_ok=True)


def _safe_user_id(u: str) -> str:
    """Sanitize user_id for filesystem safety."""
    return "".join(c for c in u if c.isalnum() or c in ("-", "_")) or "dev"


def _load_all() -> Dict[str, List[Dict[str, Any]]]:
    """Load all goals from goals.json."""
    if not os.path.exists(GOALS_FILE):
        return {}
    try:
        with open(GOALS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[GOALS] failed to load goals: {e}")
        return {}


def _save_all(data: Dict[str, List[Dict[str, Any]]]) -> None:
    """Save all goals to goals.json."""
    os.makedirs(os.path.dirname(GOALS_FILE), exist_ok=True)
    with open(GOALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class Goal(BaseModel):
    id: str = Field(..., description="Goal ID (g_<8hex>)")
    text: str = Field(..., description="Goal text")
    status: str = Field(default="active", description="Goal status: active or done")
    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))


def _load_goals(user_id: str) -> List[Goal]:
    """Load all goals for user."""
    user_id = _safe_user_id(user_id)
    all_data = _load_all()
    user_goals = all_data.get(user_id, [])
    return [Goal(**item) for item in user_goals]


def _save_goals(user_id: str, goals: List[Goal]) -> None:
    """Save goals list for user."""
    user_id = _safe_user_id(user_id)
    all_data = _load_all()
    all_data[user_id] = [g.dict() for g in goals]
    _save_all(all_data)


def list_goals(user_id: str) -> List[Goal]:
    """List all goals for user."""
    return _load_goals(user_id)


def create_goal(user_id: str, text: str) -> Goal:
    """Create a new goal."""
    goals = _load_goals(user_id)
    goal_id = f"g_{uuid.uuid4().hex[:8]}"
    now = int(time.time())
    goal = Goal(
        id=goal_id,
        text=text,
        status="active",
        created_at=now,
        updated_at=now,
    )
    goals.append(goal)
    _save_goals(user_id, goals)
    return goal


def update_goal(user_id: str, goal_id: str, patch: Dict[str, Any]) -> Optional[Goal]:
    """Update goal by ID. Returns updated goal or None if not found."""
    goals = _load_goals(user_id)
    for i, goal in enumerate(goals):
        if goal.id == goal_id:
            updated_data = goal.dict()
            updated_data.update(patch)
            updated_data["updated_at"] = int(time.time())
            updated_goal = Goal(**updated_data)
            goals[i] = updated_goal
            _save_goals(user_id, goals)
            return updated_goal
    return None


def delete_goal(user_id: str, goal_id: str) -> bool:
    """Delete goal by ID. Returns True if deleted, False if not found."""
    goals = _load_goals(user_id)
    original_len = len(goals)
    goals = [g for g in goals if g.id != goal_id]
    if len(goals) < original_len:
        _save_goals(user_id, goals)
        return True
    return False
