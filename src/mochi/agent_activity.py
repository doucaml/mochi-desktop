"""Coarse lifecycle tracking for local coding agents (Claude Code, Codex).

Agent hooks report one allow-listed word per lifecycle step plus an opaque
per-session token. Nothing here knows what the agent is doing: no prompts,
paths, or replies ever reach this module. It is pure and display-free so the
bridge command can import the shared allow-list without loading GTK.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

AGENT_EVENTS = frozenset(
    {"working", "activity", "needs_input", "prompt_waiting", "finished", "ended"}
)
AGENT_TOKEN_PATTERN = re.compile(r"[0-9a-f]{16}")


class AgentEdge(Enum):
    WORK_STARTED = "work_started"
    WORK_STOPPED = "work_stopped"
    NEEDS_INPUT = "needs_input"
    FINISHED_LONG = "finished_long"


@dataclass(slots=True)
class _Session:
    run_started_at: float
    last_seen_at: float
    waiting_since: float | None = None
    nudged: bool = False


class AgentActivityTracker:
    """Turn agent lifecycle words into presentation edges.

    A session is working, or waiting on a permission prompt. ``needs_input``
    means a prompt is about to show; it still counts as working for a grace
    period, because no hook fires when the user approves: ``activity`` only
    arrives once the approved tool finishes. ``prompt_waiting`` means the agent
    itself says the prompt is still unanswered, so it nudges at once. Finished
    and ended sessions are dropped; silent ones go stale.
    """

    NEEDS_INPUT_GRACE_SECONDS = 45.0
    CELEBRATE_MIN_RUN_SECONDS = 60.0
    SESSION_STALE_SECONDS = 900.0
    MAX_SESSIONS = 16

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._sessions: dict[str, _Session] = {}
        self._reported_working = False

    @property
    def has_sessions(self) -> bool:
        return bool(self._sessions)

    @property
    def working(self) -> bool:
        return self._working_at(self._clock())

    def clear(self) -> None:
        self._sessions.clear()
        self._reported_working = False

    def record(self, event: str, token: str) -> list[AgentEdge]:
        if (
            event not in AGENT_EVENTS
            or not isinstance(token, str)
            or AGENT_TOKEN_PATTERN.fullmatch(token) is None
        ):
            return []
        now = self._clock()
        edges: list[AgentEdge] = []
        session = self._sessions.get(token)
        if event == "working":
            if session is None:
                self._admit(token, _Session(run_started_at=now, last_seen_at=now))
            else:
                # Every prompt is a new run: an interrupted turn sends no
                # finish, and its length must not count toward the next one.
                session.run_started_at = now
                session.last_seen_at = now
                self._stop_waiting(session)
        elif event == "activity":
            # Async hooks can arrive out of order; a late `activity` must not
            # reopen a finished run, so it never creates a session.
            if session is not None:
                session.last_seen_at = now
                self._stop_waiting(session)
        elif event == "needs_input":
            if session is None:
                session = _Session(run_started_at=now, last_seen_at=now)
                self._admit(token, session)
            session.last_seen_at = now
            if session.waiting_since is None:
                session.waiting_since = now
                session.nudged = False
        elif event == "prompt_waiting":
            if session is None:
                session = _Session(run_started_at=now, last_seen_at=now)
                self._admit(token, session)
            session.last_seen_at = now
            if not session.nudged:
                # The agent says the prompt is still unanswered: no grace left.
                session.waiting_since = now - self.NEEDS_INPUT_GRACE_SECONDS
                session.nudged = True
                edges.append(AgentEdge.NEEDS_INPUT)
        elif event == "finished":
            if session is not None:
                del self._sessions[token]
                if (
                    session.waiting_since is None
                    and now - session.run_started_at >= self.CELEBRATE_MIN_RUN_SECONDS
                ):
                    edges.append(AgentEdge.FINISHED_LONG)
        else:  # "ended"
            self._sessions.pop(token, None)
        return self._with_working_edge(now, edges)

    def poll(self) -> list[AgentEdge]:
        """Expire grace periods and stale sessions."""
        now = self._clock()
        edges: list[AgentEdge] = []
        for token, session in list(self._sessions.items()):
            if now - session.last_seen_at >= self.SESSION_STALE_SECONDS:
                del self._sessions[token]
                continue
            if (
                session.waiting_since is not None
                and not session.nudged
                and now - session.waiting_since >= self.NEEDS_INPUT_GRACE_SECONDS
            ):
                session.nudged = True
                edges.append(AgentEdge.NEEDS_INPUT)
        return self._with_working_edge(now, edges)

    def _working_at(self, now: float) -> bool:
        return any(
            session.waiting_since is None
            or now - session.waiting_since < self.NEEDS_INPUT_GRACE_SECONDS
            for session in self._sessions.values()
        )

    def _with_working_edge(self, now: float, edges: list[AgentEdge]) -> list[AgentEdge]:
        # Compare against the last reported answer, so time-based changes from
        # poll() and event-based changes from record() share one rule.
        working = self._working_at(now)
        if working != self._reported_working:
            self._reported_working = working
            edges.insert(0, AgentEdge.WORK_STARTED if working else AgentEdge.WORK_STOPPED)
        return edges

    def _admit(self, token: str, session: _Session) -> None:
        if len(self._sessions) >= self.MAX_SESSIONS:
            oldest = min(self._sessions, key=lambda key: self._sessions[key].last_seen_at)
            del self._sessions[oldest]
        self._sessions[token] = session

    @staticmethod
    def _stop_waiting(session: _Session) -> None:
        session.waiting_since = None
        session.nudged = False
