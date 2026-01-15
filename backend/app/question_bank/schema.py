from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence

Answer = str

@dataclass(frozen=True)
class Question:
    id: str
    domain: str
    signal: str
    question: str
    answers: Sequence[Answer]

@dataclass(frozen=True)
class Bank:
    version: str
    name: str
    questions: Sequence[Question]

def validate_question(q: Question) -> None:
    if not q.id or not q.domain or not q.signal:
        raise ValueError(f"Invalid question fields: {q}")
    if not q.question:
        raise ValueError(f"Empty question text: {q.id}")
    if not q.answers or len(q.answers) < 2:
        raise ValueError(f"Answers must have 2+ options: {q.id}")
