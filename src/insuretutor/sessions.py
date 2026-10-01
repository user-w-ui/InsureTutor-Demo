"""Bounded, process-local histories; no SDK tool transcripts are retained."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


@dataclass
class HistoryTurn:
    question: str
    answer: str
    evidence_topics: list[str]

    def as_data(self) -> dict:
        return vars(self).copy()


@dataclass
class Session:
    id: str
    touched: float
    history: list[HistoryTurn] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0  # Includes callers waiting for the per-session lock.


class SessionCapacityError(RuntimeError):
    pass


class SessionStore:
    def __init__(
        self,
        *,
        capacity: int = 128,
        ttl: float = 1800,
        max_turns: int = 6,
        character_budget: int = 6000,
        clock: Callable[[], float] = time.monotonic,
    ):
        if min(capacity, ttl, max_turns, character_budget) <= 0:
            raise ValueError("Session limits must be positive")
        self.capacity, self.ttl, self.max_turns = capacity, ttl, max_turns
        self.character_budget, self.clock = character_budget, clock
        self.sessions: dict[str, Session] = {}

    @asynccontextmanager
    async def use(self, requested_id: str | None):
        now = self.clock()
        for sid, s in list(self.sessions.items()):
            if not s.users and now - s.touched >= self.ttl:
                del self.sessions[sid]
        session = self.sessions.get(requested_id)
        reset = requested_id is not None and session is None
        if session is None:
            if len(self.sessions) >= self.capacity:
                idle = [s for s in self.sessions.values() if not s.users]
                if not idle:
                    raise SessionCapacityError("All sessions are busy")
                del self.sessions[min(idle, key=lambda s: (s.touched, s.id)).id]
            session = Session(uuid.uuid4().hex, now)
            self.sessions[session.id] = session
        session.users += 1
        try:
            async with session.lock:
                yield session, reset
        finally:
            session.users -= 1
            session.touched = self.clock()

    def complete(self, session: Session, turn: HistoryTurn):
        # Keep whole turns; a very long answer is omitted rather than truncated into
        # a misleading fragment. A bounded history may legitimately be empty.
        session.history.append(turn)
        session.history = session.history[-self.max_turns :]
        while sum(len(h.question) + len(h.answer) for h in session.history) > self.character_budget:
            session.history.pop(0)
