"""Regression coverage for Focus presentation ownership during context churn."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from mochi.focus import FocusPlan, FocusSession
from mochi.presence.click_dialogue import PresenceBuddy, PresenceX11Buddy
from mochi.sprites import ANIMATIONS
from mochi.state import MochiState, StateMachine


def _focused_buddy(buddy_type, *, category: str):
    buddy = object.__new__(buddy_type)
    buddy.state = StateMachine()
    buddy.state.current = MochiState.COMPUTER

    buddy._focus_session = FocusSession(FocusPlan())
    buddy._focus_context_menu_visible = False
    buddy._focus_setup_pending = False
    buddy._focus_setup_visible = False

    buddy._presence_shutting_down = False
    buddy._presence_app_category = category
    buddy._user_idle = False
    buddy._context_menu_open = False
    buddy._media_monitor = None

    buddy._idle_look_active = False
    buddy._current_animation = "focus_loop"
    buddy._active_animation = ANIMATIONS["focus_loop"]
    buddy._pending_animation = None

    buddy._terminal_cowork_source_id = None
    buddy._terminal_coworking_active = False
    buddy._vscode_cowork_source_id = None
    buddy._vscode_coworking_active = False
    buddy._computer_idle_source_id = None

    buddy._ensure_focus_visual = Mock(return_value=True)
    buddy._play_terminal_intro = Mock()
    buddy._logger = Mock()
    return buddy


@pytest.mark.parametrize("buddy_type", (PresenceBuddy, PresenceX11Buddy))
def test_terminal_cowork_does_not_claim_active_focus_presentation(buddy_type) -> None:
    buddy = _focused_buddy(buddy_type, category="terminal")

    buddy._begin_terminal_coworking()

    assert buddy.state.current is MochiState.COMPUTER
    assert buddy._current_animation == "focus_loop"
    assert buddy._terminal_coworking_active is False
    buddy._play_terminal_intro.assert_not_called()


@pytest.mark.parametrize("buddy_type", (PresenceBuddy, PresenceX11Buddy))
def test_vscode_cowork_does_not_claim_active_focus_presentation(buddy_type) -> None:
    buddy = _focused_buddy(buddy_type, category="vscode")

    buddy._begin_vscode_coworking()

    assert buddy.state.current is MochiState.COMPUTER
    assert buddy._current_animation == "focus_loop"
    assert buddy._vscode_coworking_active is False


@pytest.mark.parametrize("buddy_type", (PresenceBuddy, PresenceX11Buddy))
def test_rapid_cowork_context_churn_leaves_focus_authoritative(buddy_type) -> None:
    buddy = _focused_buddy(buddy_type, category="terminal")

    for category in ("terminal", "vscode", "terminal", "vscode", "terminal"):
        buddy._presence_app_category = category
        if category == "terminal":
            buddy._begin_terminal_coworking()
        else:
            buddy._begin_vscode_coworking()

    assert buddy.state.current is MochiState.COMPUTER
    assert buddy._current_animation == "focus_loop"
    assert buddy._terminal_coworking_active is False
    assert buddy._vscode_coworking_active is False
    buddy._play_terminal_intro.assert_not_called()
