# backend/app/todos/store.py — Phase F3: Todos storage
from __future__ import annotations

import json
import os
import time
import uuid
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field

STORAGE_DIR = os.environ.get("TODOS_STORAGE_DIR", "data/todos")
TODOS_FILE = os.path.join(STORAGE_DIR, "todos.json")
os.makedirs(STORAGE_DIR, exist_ok=True)


def _safe_user_id(u: str) -> str:
    """Sanitize user_id for filesystem safety."""
    return "".join(c for c in u if c.isalnum() or c in ("-", "_")) or "dev"


def _load_all() -> Dict[str, List[Dict[str, Any]]]:
    """Load all todos from todos.json."""
    if not os.path.exists(TODOS_FILE):
        return {}
    try:
        with open(TODOS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[TODOS] failed to load todos: {e}")
        return {}


def _save_all(data: Dict[str, List[Dict[str, Any]]]) -> None:
    """Save all todos to todos.json."""
    os.makedirs(os.path.dirname(TODOS_FILE), exist_ok=True)
    with open(TODOS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class Todo(BaseModel):
    id: str = Field(..., description="Todo ID (t_<8hex>)")
    text: str = Field(..., description="Todo text")
    status: str = Field(default="open", description="Todo status: open or done")
    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))
    goal_id: Optional[str] = Field(default=None, description="Associated goal ID")
    session_id: Optional[str] = Field(default=None, description="Associated session ID")


def _load_todos(user_id: str) -> List[Todo]:
    """Load all todos for user."""
    user_id = _safe_user_id(user_id)
    all_data = _load_all()
    user_todos = all_data.get(user_id, [])
    return [Todo(**item) for item in user_todos]


def _save_todos(user_id: str, todos: List[Todo]) -> None:
    """Save todos list for user."""
    user_id = _safe_user_id(user_id)
    all_data = _load_all()
    all_data[user_id] = [t.dict() for t in todos]
    _save_all(all_data)


def list_todos(user_id: str, goal_id: Optional[str] = None, session_id: Optional[str] = None) -> List[Todo]:
    """List todos for user, optionally filtered by goal_id or session_id."""
    todos = _load_todos(user_id)
    if goal_id:
        todos = [t for t in todos if t.goal_id == goal_id]
    if session_id:
        todos = [t for t in todos if t.session_id == session_id]
    return todos


def add_todo(user_id: str, text: str, goal_id: Optional[str] = None, session_id: Optional[str] = None) -> Todo:
    """Create a new todo."""
    todos = _load_todos(user_id)
    todo_id = f"t_{uuid.uuid4().hex[:8]}"
    now = int(time.time())
    todo = Todo(
        id=todo_id,
        text=text,
        status="open",
        created_at=now,
        updated_at=now,
        goal_id=goal_id,
        session_id=session_id,
    )
    todos.append(todo)
    _save_todos(user_id, todos)
    return todo


def done_todo(user_id: str, todo_id: str) -> Optional[Todo]:
    """Mark todo as done. Returns updated todo or None if not found."""
    todos = _load_todos(user_id)
    for i, todo in enumerate(todos):
        if todo.id == todo_id:
            updated_todo = Todo(
                **{**todo.dict(), "status": "done", "updated_at": int(time.time())}
            )
            todos[i] = updated_todo
            _save_todos(user_id, todos)
            return updated_todo
    return None


def delete_todo(user_id: str, todo_id: str) -> bool:
    """Delete todo by ID. Returns True if deleted, False if not found."""
    todos = _load_todos(user_id)
    original_len = len(todos)
    todos = [t for t in todos if t.id != todo_id]
    if len(todos) < original_len:
        _save_todos(user_id, todos)
        return True
    return False
