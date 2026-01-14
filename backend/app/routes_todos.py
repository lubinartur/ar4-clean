# backend/app/routes_todos.py — Phase F3: Todos routes
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Header
from pydantic import BaseModel, Field

from backend.app.todos.store import (
    list_todos,
    add_todo,
    done_todo,
    delete_todo,
    Todo,
)

router = APIRouter(prefix="/todos", tags=["todos"])


def _get_user_id(x_user: Optional[str] = None) -> str:
    """Get user_id from header or default to 'dev'."""
    return (x_user or "dev").strip() or "dev"


class AddTodoBody(BaseModel):
    text: str = Field(..., description="Todo text", min_length=1)
    goal_id: Optional[str] = Field(None, description="Associated goal ID")
    session_id: Optional[str] = Field(None, description="Associated session ID")


class DoneTodoBody(BaseModel):
    id: str = Field(..., description="Todo ID")


@router.get("/list")
async def todos_list(
    goal_id: Optional[str] = Query(None, description="Filter by goal ID"),
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    """List todos, optionally filtered by goal_id or session_id."""
    user_id = _get_user_id(x_user)
    todos = list_todos(user_id, goal_id=goal_id, session_id=session_id)
    return {"ok": True, "todos": [t.dict() for t in todos]}


@router.post("/add")
async def todos_add(
    body: AddTodoBody,
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    """Create a new todo."""
    user_id = _get_user_id(x_user)
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")
    todo = add_todo(user_id, body.text.strip(), goal_id=body.goal_id, session_id=body.session_id)
    return {"ok": True, "todo": todo.dict()}


@router.post("/done")
async def todos_done(
    body: DoneTodoBody,
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    """Mark todo as done."""
    user_id = _get_user_id(x_user)
    updated = done_todo(user_id, body.id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return {"ok": True, "todo": updated.dict()}


@router.delete("/delete")
async def todos_delete(
    id: str = Query(..., description="Todo ID"),
    x_user: Optional[str] = Header(default="dev", alias="X-User"),
):
    """Delete todo by ID."""
    user_id = _get_user_id(x_user)
    deleted = delete_todo(user_id, id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Todo not found")
    return {"ok": True, "deleted": True}
