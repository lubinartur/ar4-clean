from pydantic import BaseModel
from typing import Any, Dict

class IngestReq(BaseModel):
    text: str
    meta: Dict[str, Any] = {}

class SearchReq(BaseModel):
    query: str
    k: int = 5

class ProfilePatch(BaseModel):
    patch: Dict[str, Any]

class ChatReq(BaseModel):
    message: str
    top_k: int = 5
    with_short_summary: bool = True

