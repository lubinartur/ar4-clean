from __future__ import annotations

import time
import secrets
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


def _new_id(prefix: str = "qbs_") -> str:
    return prefix + secrets.token_hex(8)


@dataclass
class QBSession:
    id: str
    created_at: float = field(default_factory=lambda: time.time())
    updated_at: float = field(default_factory=lambda: time.time())
    # signal -> answer (yes/no/low/mid/high)
    answers: Dict[str, str] = field(default_factory=dict)
    # signal timestamps: signal -> epoch
    answered_at: Dict[str, float] = field(default_factory=dict)
    # question ids asked to user (avoid repeating)
    asked_ids: List[str] = field(default_factory=list)
    # asked question timestamps: qid -> epoch
    asked_at: Dict[str, float] = field(default_factory=dict)
    # last asked time per domain: domain -> epoch
    domain_last_asked_at: Dict[str, float] = field(default_factory=dict)
    # last time any question was asked (for cooldown between questions)
    last_asked_at: Optional[float] = None
    # last domain served (for go_deeper preference)
    last_domain: Optional[str] = None
    # last question id served (for go_deeper tracking)
    last_question_id: Optional[str] = None
    # signal -> count (for insight loop)
    signal_counts: Dict[str, int] = field(default_factory=dict)
    # last time insight was shown (for insight loop)
    last_insight_at: Optional[float] = None
    # last insight text shown (for capture)
    last_insight: Optional[str] = None
    # captured insights/snapshots (for QB capture feature)
    captures: List[Dict[str, Any]] = field(default_factory=list)
    # daily check-in date (YYYY-MM-DD), local user timezone should be applied by caller/UI
    last_checkin_date: Optional[str] = None
    # PHASE L1: Behavioral metrics counters
    continue_count: int = 0
    capture_count: int = 0
    go_deeper_count: int = 0
    answers_count: int = 0

    def touch(self) -> None:
        self.updated_at = time.time()


class QBSessionStore:
    """
    Minimal in-memory store.
    Replace later with your persistent session system if needed.
    """
    def __init__(self) -> None:
        self._sessions: Dict[str, QBSession] = {}

    def create(self) -> QBSession:
        s = QBSession(id=_new_id())
        self._sessions[s.id] = s
        return s

    def get(self, session_id: str) -> Optional[QBSession]:
        return self._sessions.get(session_id)

    def upsert_answer(self, session_id: str, signal: str, answer: str) -> QBSession:
        s = self._sessions.get(session_id)
        if s is None:
            # auto-create if missing (safe fallback)
            s = QBSession(id=session_id)
            self._sessions[session_id] = s
        s.answers[signal] = answer
        s.answered_at[signal] = time.time()
        s.touch()
        return s

    def mark_asked(self, session_id: str, asked_ids: List[str]) -> QBSession:
        s = self._sessions.get(session_id)
        if s is None:
            s = QBSession(id=session_id)
            self._sessions[session_id] = s
        # append unique
        existing = set(s.asked_ids)
        for qid in asked_ids:
            if qid not in existing:
                s.asked_ids.append(qid)
                existing.add(qid)
            s.asked_at[qid] = time.time()
        s.touch()
        return s

    def mark_domain_asked(self, session_id: str, domains: List[str]) -> QBSession:
        s = self._sessions.get(session_id)
        if s is None:
            s = QBSession(id=session_id)
            self._sessions[session_id] = s
        now = time.time()
        for d in domains:
            s.domain_last_asked_at[d] = now
        s.touch()
        return s

    def set_checkin_date(self, session_id: str, date_str: str) -> QBSession:
        s = self._sessions.get(session_id)
        if s is None:
            s = QBSession(id=session_id)
            self._sessions[session_id] = s
        s.last_checkin_date = date_str
        s.touch()
        return s

    def reset(self, session_id: str) -> Optional[QBSession]:
        s = self._sessions.get(session_id)
        if s is None:
            return None
        s.answers = {}
        s.answered_at = {}
        s.asked_ids = []
        s.asked_at = {}
        s.domain_last_asked_at = {}
        s.last_asked_at = None
        s.signal_counts = {}
        s.last_insight_at = None
        s.last_insight = None
        s.captures = []
        s.last_domain = None
        s.last_question_id = None
        # PHASE L1: Reset behavioral metrics
        s.continue_count = 0
        s.capture_count = 0
        s.go_deeper_count = 0
        s.answers_count = 0
        s.touch()
        return s

    def set_last_asked_at(self, session_id: str, timestamp: float) -> QBSession:
        s = self._sessions.get(session_id)
        if s is None:
            s = QBSession(id=session_id)
            self._sessions[session_id] = s
        s.last_asked_at = timestamp
        s.touch()
        return s

    def increment_answers_count(self, session_id: str) -> QBSession:
        """PHASE L1: Increment answers_count when user answers a question."""
        s = self._sessions.get(session_id)
        if s is None:
            s = QBSession(id=session_id)
            self._sessions[session_id] = s
        s.answers_count += 1
        s.touch()
        return s

    def increment_action_count(self, session_id: str, action: str) -> QBSession:
        """PHASE L1: Increment action counter (continue/capture/go_deeper)."""
        s = self._sessions.get(session_id)
        if s is None:
            s = QBSession(id=session_id)
            self._sessions[session_id] = s
        
        if action == "continue":
            s.continue_count += 1
        elif action == "capture":
            s.capture_count += 1
        elif action == "go_deeper":
            s.go_deeper_count += 1
        
        s.touch()
        return s
