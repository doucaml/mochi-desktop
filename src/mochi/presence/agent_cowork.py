"""Cowork with local coding agents (Claude Code, Codex) while they run."""

from __future__ import annotations

from gi.repository import GLib

from mochi.agent_activity import AgentActivityTracker, AgentEdge
from mochi.state import MochiState

from .curiosity import _boottime_seconds
from .terminal_cowork import TerminalCoworkMixin


class AgentCoworkMixin:
    """Keep Mochi company with coding agents while they work.

    Agent hooks run ``mochi-agent-signal``, which reaches
    :meth:`receive_agent_event` through the application's ``agent-event``
    action with one lifecycle word and an opaque per-session token. No prompt,
    path, command, or reply ever reaches Mochi.

    A working agent is one more reason for terminal coworking's laptop to be
    live. A long-unanswered permission prompt earns one ``wave`` beat and a
    finished long run one ``excited`` beat, both through the standing-idle beat
    owner, plus an optional PresenceEngine line. This mixin owns one GLib poll
    source, alive only while sessions or a beat are pending.
    """

    AGENT_POLL_INTERVAL_SECONDS = 1
    AGENT_BEAT_TTL_SECONDS = 30.0
    AGENT_NEEDS_INPUT_BEAT = "wave"
    AGENT_FINISHED_BEAT = "excited"
    _TERMINAL_ART = frozenset(
        (
            TerminalCoworkMixin.TERMINAL_INTRO_ANIMATION,
            TerminalCoworkMixin.TERMINAL_LOOP_ANIMATION,
            TerminalCoworkMixin.TERMINAL_OUTRO_ANIMATION,
        )
    )

    # Class-level defaults: every value is immutable, and some tests build
    # production buddies with ``__new__`` without running mixin initializers.
    _agent_tracker: AgentActivityTracker | None = None
    _agent_source_id: int | None = None
    _agent_pending_beat: str | None = None
    _agent_pending_beat_until = 0.0

    def _agent_now(self) -> float:
        # Keeps counting through suspend, so a run left "working" overnight
        # goes stale on resume instead of holding the laptop open.
        return _boottime_seconds()

    # -- Events ---------------------------------------------------------------

    def receive_agent_event(self, event: str, token: str) -> None:
        """Take one validated lifecycle word from the application action."""
        if getattr(self, "_presence_shutting_down", False) or getattr(
            self, "_preview_mode", False
        ):
            return
        tracker = self._agent_tracker
        if tracker is None:
            tracker = AgentActivityTracker(clock=self._agent_now)
            self._agent_tracker = tracker
        self._apply_agent_edges(tracker.record(event, token))
        self._ensure_agent_source()

    def _terminal_cowork_context_live(self) -> bool:
        return super()._terminal_cowork_context_live() or self._agents_alone_keep_laptop_live()

    def _agents_alone_keep_laptop_live(self) -> bool:
        """Working agents, not a focused terminal, are why the laptop is live."""
        if self._presence_app_category in ("terminal", "vscode"):
            # Focused VS Code keeps its own coworking: both claim TYPING, so
            # the laptop yields and returns through the normal resume chain.
            return False
        tracker = self._agent_tracker
        return tracker is not None and tracker.working

    def _on_typing_stopped(self) -> None:
        if not self._agents_alone_keep_laptop_live():
            super()._on_typing_stopped()
            return
        if (
            self.state.current is MochiState.TYPING
            and self._current_animation in self._TERMINAL_ART
        ):
            # The agent's laptop stays open (terminal hold below), but the
            # user's typing burst is over: stop typing-based bond XP rather
            # than let it tick for the whole agent run.
            finish_bond_typing = getattr(self, "_finish_bond_typing_session", None)
            if callable(finish_bond_typing):
                finish_bond_typing()
            super()._on_typing_stopped()
            return
        # Generic typing art: run the normal typing stop past the terminal
        # hold. The resume chain then reopens the laptop, or resumes video,
        # which outranks it.
        super(TerminalCoworkMixin, self)._on_typing_stopped()

    def _apply_agent_edges(self, edges: list[AgentEdge]) -> None:
        engine = getattr(self, "_ambient_presence_engine", None)
        for edge in edges:
            if edge is AgentEdge.WORK_STARTED:
                if engine is not None:
                    # Work resumed: an unspoken "waiting" or "finished" line
                    # is no longer true.
                    engine.discard("agent_needs_input")
                    engine.discard("agent_finished")
                self._schedule_terminal_coworking()
            elif edge is AgentEdge.WORK_STOPPED:
                if not self._terminal_cowork_context_live():
                    self._stop_terminal_coworking()
            elif edge is AgentEdge.NEEDS_INPUT:
                self._queue_agent_beat(self.AGENT_NEEDS_INPUT_BEAT)
                if engine is not None:
                    engine.emit("agent_needs_input")
            elif edge is AgentEdge.FINISHED_LONG:
                self._queue_agent_beat(self.AGENT_FINISHED_BEAT)
                if engine is not None:
                    engine.emit("agent_finished")
        self._try_agent_beat()

    # -- Beats ----------------------------------------------------------------

    def _queue_agent_beat(self, name: str) -> None:
        """Remember one beat to play once Mochi stands idle; the latest wins."""
        self._agent_pending_beat = name
        self._agent_pending_beat_until = self._agent_now() + self.AGENT_BEAT_TTL_SECONDS

    def _try_agent_beat(self) -> None:
        name = self._agent_pending_beat
        if name is None:
            return
        if self._agent_now() >= self._agent_pending_beat_until:
            # Never replay a nudge or a celebration late.
            self._agent_pending_beat = None
            return
        # Same quiet rules as curiosity: menus, drags, Focus, sleep, quiet mode.
        if self._curiosity_suppression() is not None:
            return
        # Refuses unless Mochi stands idle, so a nudge waits for the laptop to
        # close through its outro.
        if self._play_idle_beat(name):
            self._agent_pending_beat = None

    # -- Poll source ----------------------------------------------------------

    def _agent_work_pending(self) -> bool:
        tracker = self._agent_tracker
        return (
            tracker is not None and tracker.has_sessions
        ) or self._agent_pending_beat is not None

    def _ensure_agent_source(self) -> None:
        if self._agent_source_id is not None or not self._agent_work_pending():
            return
        self._agent_source_id = GLib.timeout_add_seconds(
            self.AGENT_POLL_INTERVAL_SECONDS, self._agent_tick
        )

    def _agent_tick(self) -> bool:
        if getattr(self, "_presence_shutting_down", False):
            self._agent_source_id = None
            return GLib.SOURCE_REMOVE
        tracker = self._agent_tracker
        if tracker is not None:
            self._apply_agent_edges(tracker.poll())
        else:
            self._try_agent_beat()
        if self._agent_work_pending():
            return GLib.SOURCE_CONTINUE
        self._agent_source_id = None
        return GLib.SOURCE_REMOVE

    def _cancel_agent_source(self) -> None:
        source_id = self._agent_source_id
        self._agent_source_id = None
        if source_id is None:
            return
        try:
            GLib.source_remove(source_id)
        except Exception:
            pass

    def shutdown_presence(self) -> None:
        self._cancel_agent_source()
        if self._agent_tracker is not None:
            self._agent_tracker.clear()
        self._agent_pending_beat = None
        super().shutdown_presence()
