"""Agent Companion: the app action, terminal liveness, and the cowork mixin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from gi.repository import GLib

from mochi.app import MochiApplication
from mochi.config import ConfigStore
from mochi.presence import terminal_cowork
from mochi.presence.click_dialogue import PresenceBuddy, PresenceX11Buddy
from mochi.presence.integration import PresenceBuddyMixin
from mochi.presence.terminal_cowork import TerminalCoworkMixin
from mochi.sprites import ANIMATIONS
from mochi.state import MochiState, StateMachine

TOKEN = "0123456789abcdef"
BUDDY_TYPES = pytest.mark.parametrize("buddy_type", (PresenceBuddy, PresenceX11Buddy))


# -- App action -----------------------------------------------------------------


def _app(tmp_path: Path, *, preview: bool = False) -> MochiApplication:
    return MochiApplication(
        config=ConfigStore(tmp_path / "config.json"),
        preview_animations=preview,
    )


def _activate(app: MochiApplication, event: str, token: str) -> None:
    # GApplication.activate_action requires a registered app; activating the
    # action itself emits the same "activate" signal a D-Bus caller triggers.
    app.lookup_action("agent-event").activate(GLib.Variant("(ss)", (event, token)))


def test_agent_event_action_takes_an_event_and_token_pair(tmp_path: Path) -> None:
    action = _app(tmp_path).lookup_action("agent-event")

    assert action is not None
    assert action.get_parameter_type().dup_string() == "(ss)"


def test_preview_app_does_not_accept_agent_events(tmp_path: Path) -> None:
    assert _app(tmp_path, preview=True).lookup_action("agent-event") is None


def test_valid_agent_event_reaches_the_buddy(tmp_path: Path) -> None:
    app = _app(tmp_path)
    app._buddy = Mock()

    _activate(app, "working", TOKEN)

    app._buddy.receive_agent_event.assert_called_once_with("working", TOKEN)


@pytest.mark.parametrize(
    ("event", "token"),
    (
        ("bogus", TOKEN),
        ("WORKING", TOKEN),
        ("working", TOKEN.upper()),
        ("working", "0123"),
        ("working", ""),
    ),
)
def test_malformed_agent_event_is_dropped(tmp_path: Path, event, token) -> None:
    app = _app(tmp_path)
    app._buddy = Mock()

    _activate(app, event, token)

    app._buddy.receive_agent_event.assert_not_called()


def test_agent_event_before_the_buddy_exists_is_ignored(tmp_path: Path) -> None:
    app = _app(tmp_path)
    assert app._buddy is None

    _activate(app, "working", TOKEN)  # must not raise


# -- Terminal coworking characterization ------------------------------------------
#
# These pin today's terminal coworking behavior. They were written before the
# liveness predicate refactor and must keep passing after it.


class FakeTimers:
    def __init__(self) -> None:
        self.armed: list[tuple[int, object]] = []
        self.removed: list[int] = []
        self._next_id = 100

    def timeout_add(self, delay_ms, callback, *args):
        self._next_id += 1
        self.armed.append((delay_ms, callback))
        return self._next_id

    def timeout_add_seconds(self, delay_seconds, callback, *args):
        return self.timeout_add(delay_seconds * 1000, callback)

    def source_remove(self, source_id) -> bool:
        self.removed.append(source_id)
        return True


@pytest.fixture
def timers(monkeypatch) -> FakeTimers:
    fake = FakeTimers()
    monkeypatch.setattr(terminal_cowork.GLib, "timeout_add", fake.timeout_add)
    monkeypatch.setattr(terminal_cowork.GLib, "timeout_add_seconds", fake.timeout_add_seconds)
    monkeypatch.setattr(terminal_cowork.GLib, "source_remove", fake.source_remove)
    return fake


def _terminal_buddy(
    buddy_type,
    *,
    category: str = "terminal",
    state: MochiState = MochiState.IDLE,
    animation: str = "idle",
    active: bool = False,
):
    buddy = buddy_type.__new__(buddy_type)
    buddy.state = StateMachine()
    buddy.state.current = state
    buddy._presence_shutting_down = False
    buddy._presence_app_category = category
    buddy._user_idle = False
    buddy._context_menu_open = False
    buddy._media_monitor = None
    buddy._preview_mode = False
    buddy._current_animation = animation
    buddy._active_animation = ANIMATIONS[animation]
    buddy._pending_animation = None
    buddy._terminal_cowork_source_id = None
    buddy._terminal_coworking_active = active
    buddy._vscode_cowork_source_id = None
    buddy._vscode_coworking_active = False
    buddy._computer_idle_source_id = None
    buddy._idle_look_active = False
    buddy._logger = Mock()
    buddy._play_animation = Mock()
    buddy._transition_to = Mock(return_value=True)
    buddy._ambient_presence_engine = Mock()
    buddy._on_user_active = Mock()
    buddy._schedule_vscode_coworking = Mock()
    buddy._cancel_vscode_cowork_source = Mock()
    buddy._stop_vscode_coworking = Mock()
    return buddy


@BUDDY_TYPES
def test_terminal_focus_arms_one_debounced_start(buddy_type, timers) -> None:
    buddy = _terminal_buddy(buddy_type)

    TerminalCoworkMixin._schedule_terminal_coworking(buddy)

    assert [delay for delay, _ in timers.armed] == [
        TerminalCoworkMixin.TERMINAL_COWORK_DEBOUNCE_MS
    ]


@BUDDY_TYPES
def test_non_terminal_focus_arms_nothing(buddy_type, timers) -> None:
    buddy = _terminal_buddy(buddy_type, category="browser")

    TerminalCoworkMixin._schedule_terminal_coworking(buddy)

    assert timers.armed == []


@BUDDY_TYPES
def test_begin_claims_typing_with_terminal_intro(buddy_type, timers) -> None:
    buddy = _terminal_buddy(buddy_type)

    def start_typing() -> bool:
        buddy.state.current = MochiState.TYPING
        return True

    buddy._start_typing_emote = Mock(side_effect=start_typing)

    TerminalCoworkMixin._begin_terminal_coworking(buddy)

    assert buddy._terminal_coworking_active is True
    buddy._play_animation.assert_called_once_with("terminal_intro", after=None)


@BUDDY_TYPES
def test_begin_outside_the_terminal_does_nothing(buddy_type, timers) -> None:
    buddy = _terminal_buddy(buddy_type, category="browser")
    buddy._start_typing_emote = Mock()

    TerminalCoworkMixin._begin_terminal_coworking(buddy)

    buddy._start_typing_emote.assert_not_called()
    assert buddy._terminal_coworking_active is False


@BUDDY_TYPES
def test_leaving_the_terminal_stops_coworking(buddy_type, timers) -> None:
    buddy = _terminal_buddy(buddy_type, state=MochiState.TYPING, animation="terminal_loop", active=True)
    buddy._stop_terminal_coworking = Mock()

    TerminalCoworkMixin._on_presence_app_category_changed(buddy, "browser")

    buddy._stop_terminal_coworking.assert_called_once_with()


@BUDDY_TYPES
def test_entering_the_terminal_schedules_coworking(buddy_type, timers) -> None:
    buddy = _terminal_buddy(buddy_type, category="browser")
    buddy._schedule_terminal_coworking = Mock()
    buddy._stop_terminal_coworking = Mock()

    TerminalCoworkMixin._on_presence_app_category_changed(buddy, "terminal")

    buddy._schedule_terminal_coworking.assert_called_once_with()
    buddy._stop_terminal_coworking.assert_not_called()


@BUDDY_TYPES
def test_intro_finishing_while_live_plays_the_loop(buddy_type, timers) -> None:
    buddy = _terminal_buddy(buddy_type, state=MochiState.TYPING, animation="terminal_intro", active=True)

    TerminalCoworkMixin._finish_reaction(buddy, buddy._active_animation)

    buddy._play_animation.assert_called_once_with("terminal_loop", after=None)


@BUDDY_TYPES
def test_intro_finishing_after_leaving_plays_the_outro(buddy_type, timers) -> None:
    buddy = _terminal_buddy(
        buddy_type, category="browser", state=MochiState.TYPING, animation="terminal_intro", active=True
    )

    TerminalCoworkMixin._finish_reaction(buddy, buddy._active_animation)

    buddy._play_animation.assert_called_once_with("terminal_outro", after=None)


@BUDDY_TYPES
def test_outro_finishing_while_live_reopens(buddy_type, timers) -> None:
    buddy = _terminal_buddy(buddy_type, state=MochiState.TYPING, animation="terminal_outro", active=True)

    TerminalCoworkMixin._finish_reaction(buddy, buddy._active_animation)

    buddy._play_animation.assert_called_once_with("terminal_intro", after=None)


@BUDDY_TYPES
def test_outro_finishing_after_leaving_returns_to_idle(buddy_type, timers) -> None:
    buddy = _terminal_buddy(
        buddy_type, category="browser", state=MochiState.TYPING, animation="terminal_outro", active=True
    )
    buddy._finish_terminal_outro = Mock()

    TerminalCoworkMixin._finish_reaction(buddy, buddy._active_animation)

    buddy._finish_terminal_outro.assert_called_once_with()


@BUDDY_TYPES
def test_terminal_to_vscode_hands_off_after_the_outro(buddy_type, timers) -> None:
    buddy = _terminal_buddy(buddy_type, state=MochiState.TYPING, animation="terminal_loop", active=True)

    TerminalCoworkMixin._on_presence_app_category_changed(buddy, "vscode")

    # Base presence schedules VS Code at once; the terminal stop defers it
    # while the laptop closes through its authored outro.
    buddy._schedule_vscode_coworking.assert_called_once_with()
    buddy._cancel_vscode_cowork_source.assert_called_once_with()
    buddy._play_animation.assert_called_once_with("terminal_outro", after=None)
    assert buddy._terminal_coworking_active is False

    buddy._play_animation.reset_mock()
    TerminalCoworkMixin._finish_terminal_outro(buddy)

    buddy._transition_to.assert_called_once_with(MochiState.IDLE)
    buddy._play_animation.assert_called_once_with("idle")
    assert buddy._schedule_vscode_coworking.call_count == 2


@BUDDY_TYPES
def test_typing_burst_ending_keeps_the_laptop_in_the_terminal(buddy_type, timers) -> None:
    buddy = _terminal_buddy(buddy_type, state=MochiState.TYPING, animation="terminal_loop", active=True)

    TerminalCoworkMixin._on_typing_stopped(buddy)

    buddy._ambient_presence_engine.record_typing_stopped.assert_called_once_with()
    assert buddy._terminal_coworking_active is True
    buddy._play_animation.assert_not_called()


@BUDDY_TYPES
def test_user_returning_to_the_terminal_schedules_coworking(buddy_type, timers, monkeypatch) -> None:
    monkeypatch.setattr(PresenceBuddyMixin, "_on_user_active", lambda self: None)
    buddy = _terminal_buddy(buddy_type)
    del buddy._on_user_active
    buddy._schedule_terminal_coworking = Mock()

    TerminalCoworkMixin._on_user_active(buddy)

    buddy._schedule_terminal_coworking.assert_called_once_with()


@BUDDY_TYPES
def test_resume_reopens_only_while_live(buddy_type, timers) -> None:
    for category, expected in (("terminal", True), ("browser", False)):
        buddy = _terminal_buddy(buddy_type, category=category)
        buddy._is_idle_visual_active = Mock(return_value=True)
        buddy._start_typing_emote = Mock(return_value=True)

        assert TerminalCoworkMixin._maybe_resume_terminal_coworking(buddy) is expected


def test_every_terminal_liveness_check_uses_the_predicate() -> None:
    source = Path(terminal_cowork.__file__).read_text(encoding="utf-8")

    # The predicate itself is the only place the focused category decides
    # liveness; `category == "terminal"` (a focus edge) and
    # `previous == "terminal"` (the stop condition) are not liveness checks.
    assert source.count('self._presence_app_category == "terminal"') == 1
    assert 'self._presence_app_category != "terminal"' not in source
    assert "def _terminal_cowork_context_live(self) -> bool:" in source
