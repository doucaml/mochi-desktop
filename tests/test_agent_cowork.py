"""Agent Companion: the app action, terminal liveness, and the cowork mixin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from gi.repository import GLib

from mochi.app import MochiApplication
from mochi.config import ConfigStore

TOKEN = "0123456789abcdef"


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
