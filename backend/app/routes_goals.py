# backend/app/routes_goals.py — Phase F1: Goals routes
from __future__ import annotations

import json
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Header
from pydantic import BaseModel, Field

from backend.app.goals.store import (
    list_goals,
    create_goal,
    update_goal,
    delete_goal,
    Goal,
)

router = APIRouter(prefix="/goals", tags=["goals"])


def _get_user_id(x_user: Optional[str] = None) -> str:
    """Get user_id from header or default to 'dev'."""
    return (x_user or "dev").strip() or "dev"


class AddGoalBody(BaseModel):
    text: str = Field(..., description="Goal text", min_length=1)


class UpdateGoalBody(BaseModel):
    id: str = Field(..., description="Goal ID")
    text: Optional[str] = Field(None, description="Goal text")
    status: Optional[str] = Field(None, description="Goal status: active or done")


class AttachGoalBody(BaseModel):
    goal_id: str = Field(..., description="Goal ID")
    session_id: str = Field(..., description="Session ID")


@router.get("/list")
async def goals_list(
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    """List all goals for user."""
    user_id = _get_user_id(x_user)
    goals = list_goals(user_id)
    return {"ok": True, "goals": [g.dict() for g in goals]}


@router.post("/add")
async def goals_add(
    body: AddGoalBody,
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    """Create a new goal."""
    user_id = _get_user_id(x_user)
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")
    goal = create_goal(user_id, body.text.strip())
    return {"ok": True, "goal": goal.dict()}


@router.patch("/update")
async def goals_update(
    body: UpdateGoalBody,
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    """Update goal by ID."""
    user_id = _get_user_id(x_user)
    patch = {}
    if body.text is not None:
        if not body.text.strip():
            raise HTTPException(status_code=400, detail="text cannot be empty")
        patch["text"] = body.text.strip()
    if body.status is not None:
        if body.status not in ("active", "done"):
            raise HTTPException(status_code=400, detail="status must be 'active' or 'done'")
        patch["status"] = body.status
    
    updated = update_goal(user_id, body.id, patch)
    if updated is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"ok": True, "goal": updated.dict()}


@router.delete("/delete")
async def goals_delete(
    id: str = Query(..., description="Goal ID"),
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    """Delete goal by ID."""
    user_id = _get_user_id(x_user)
    deleted = delete_goal(user_id, id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"ok": True, "deleted": True}


@router.post("/attach")
async def goals_attach(
    body: AttachGoalBody,
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    """Attach goal to session."""
    user_id = _get_user_id(x_user)
    
    # Guard: goal_id is required
    if not body.goal_id or not body.goal_id.strip():
        raise HTTPException(status_code=400, detail="goal_id is required")
    
    # Validate session_id FIRST using existing utility
    try:
        from backend.app.main import validate_session_id
        validate_session_id(body.session_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session_id: session not found")
    
    # Verify goal exists
    goals = list_goals(user_id)
    goal_exists = any(g.id == body.goal_id for g in goals)
    if not goal_exists:
        raise HTTPException(status_code=404, detail="Goal not found")
    
    # Load or create session links
    LINKS_PATH = Path("data/goals/session_links.json")
    links = {}
    if LINKS_PATH.exists():
        try:
            links = json.loads(LINKS_PATH.read_text(encoding="utf-8"))
        except Exception:
            links = {}
    
    # Ensure user entry exists
    if user_id not in links:
        links[user_id] = {}
    
    # Ensure session entry exists
    if body.session_id not in links[user_id]:
        links[user_id][body.session_id] = []
    
    # Add goal_id if not already present
    if body.goal_id not in links[user_id][body.session_id]:
        links[user_id][body.session_id].append(body.goal_id)
    
    # Save links
    LINKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LINKS_PATH.write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return {"ok": True}


@router.get("/by_session")
async def goals_by_session(
    session_id: str = Query(..., description="Session ID"),
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    """Get goals attached to session."""
    user_id = _get_user_id(x_user)
    
    # Load session links
    LINKS_PATH = Path("data/goals/session_links.json")
    links = {}
    if LINKS_PATH.exists():
        try:
            links = json.loads(LINKS_PATH.read_text(encoding="utf-8"))
        except Exception:
            links = {}
    
    # Get goal_ids for this session
    goal_ids = links.get(user_id, {}).get(session_id, [])
    
    # Load all goals and filter
    all_goals = list_goals(user_id)
    session_goals = [g for g in all_goals if g.id in goal_ids]
    
    return {"ok": True, "goals": [g.dict() for g in session_goals]}
