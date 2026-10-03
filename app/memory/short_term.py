"""Short-term (per-session) conversation memory.

Holds the last N messages verbatim plus a rolling extractive summary of older turns. Kept in process
behind a small interface; in production this would be Redis (TTL per session key) so that any API
pod can serve any session.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Turn:
    role: str                      # "user" | "assistant"
    content: str
    meta: dict[str, Any] = field(default_factory=dict)   # intent, areas, context item ids used


@dataclass
class SessionState:
    turns: deque
    summary: str = ""
    turn_count: int = 0
    last_active: float = field(default_factory=time.monotonic)

    def last(self, role: str) -> Turn | None:
        for t in reversed(self.turns):
            if t.role == role:
                return t
        return None


class ShortTermMemory:
    def __init__(self, max_messages: int = 6, ttl_seconds: int = 6 * 3600, max_sessions: int = 10_000,
                 summary_chars: int = 600):
        self.max_messages = max_messages
        self.ttl = ttl_seconds
        self.max_sessions = max_sessions
        self.summary_chars = summary_chars
        self._sessions: OrderedDict[tuple[str, str], SessionState] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, user_id: str, session_id: str) -> SessionState:
        # Keyed by (user, session) so a guessed/colliding session_id never leaks another user's chat.
        key = (user_id, session_id)
        with self._lock:
            self._evict()
            state = self._sessions.get(key)
            if state is None:
                state = SessionState(turns=deque())
                self._sessions[key] = state
            self._sessions.move_to_end(key)
            return state

    def append(self, user_id: str, session_id: str, role: str, content: str, meta: dict | None = None) -> None:
        state = self.get(user_id, session_id)
        with self._lock:
            state.turns.append(Turn(role, content, meta or {}))
            state.turn_count += 1
            state.last_active = time.monotonic()
            while len(state.turns) > self.max_messages:
                old = state.turns.popleft()
                state.summary = self._fold(state.summary, old)

    def _fold(self, summary: str, turn: Turn) -> str:
        snippet = turn.content.strip().replace("\n", " ")
        snippet = snippet if len(snippet) <= 140 else snippet[:137] + "..."
        who = "User" if turn.role == "user" else "Naksh"
        merged = (summary + f" {who}: {snippet}").strip()
        return merged[-self.summary_chars:]

    def _evict(self) -> None:
        now = time.monotonic()
        for key in [k for k, s in self._sessions.items() if now - s.last_active > self.ttl]:
            del self._sessions[key]
        while len(self._sessions) > self.max_sessions:
            self._sessions.popitem(last=False)
