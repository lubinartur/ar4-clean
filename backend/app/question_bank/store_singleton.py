from __future__ import annotations

"""
Shared QB store singleton.
Both /qb/* and /chat must use the same store instance,
otherwise stateful QB sessions won't work.
"""

from .session_store import QBSessionStore

store = QBSessionStore()
