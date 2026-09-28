"""Pocket composition, menu, and lifecycle integration coverage."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from mochi.pocket_integration import PocketBuddyMixin
from mochi.presence.click_dialogue import PresenceBuddy, PresenceX11Buddy


class _MenuBase:
    def _build_context_menu(self):
        return "menu"

    def _make_menu_button(self, label, icon, callback):
        self.button_args = (label, icon, callback)
        self.pocket_label = Mock()
        return "pocket-button", self.pocket_label

    def _register_context_menu_row(self, row_id, widget, **kwargs):
        self.registered_row = (row_id, widget, kwargs)


class _MenuHarness(PocketBuddyMixin, _MenuBase):
    pass


class _ShutdownBase:
    def shutdown_presence(self) -> None:
        self.base_shutdown = True


class _ShutdownHarness(PocketBuddyMixin, _ShutdownBase):
    pass


def test_both_production_buddies_include_the_same_pocket_layer() -> None:
    assert PocketBuddyMixin in PresenceBuddy.__mro__
    assert PocketBuddyMixin in PresenceX11Buddy.__mro__


def test_pocket_menu_row_shows_count_and_uses_layout_seam() -> None:
    harness = object.__new__(_MenuHarness)
    harness._pocket_controller = SimpleNamespace(count=3)

    assert harness._build_context_menu() == "menu"

    label, icon, callback = harness.button_args
    assert label == "Pocket · 3"
    assert icon == "folder-download-symbolic"
    assert callback == harness._pocket_from_context_menu
    assert harness.registered_row == (
        "pocket",
        "pocket-button",
        {"before": "sleep"},
    )


def test_pocket_menu_action_defers_window_until_menu_closes() -> None:
    harness = object.__new__(PocketBuddyMixin)
    harness._close_context_menu_then = Mock()
    harness._show_pocket_window = Mock()

    harness._pocket_from_context_menu(None)

    harness._close_context_menu_then.assert_called_once_with(
        harness._show_pocket_window
    )
    harness._show_pocket_window.assert_not_called()


def test_count_change_updates_menu_label_and_open_window() -> None:
    harness = object.__new__(PocketBuddyMixin)
    harness._pocket_label = Mock()
    harness._pocket_window = Mock()
    harness._pocket_window.get_visible.return_value = True
    items = (object(), object())

    harness._on_pocket_changed(items)

    harness._pocket_label.set_text.assert_called_once_with("Pocket · 2")
    harness._pocket_window.refresh.assert_called_once_with()


def test_shutdown_detaches_drop_adapter_and_destroys_window() -> None:
    harness = object.__new__(_ShutdownHarness)
    harness._pocket_drop = Mock()
    harness._pocket_window = Mock()
    drop = harness._pocket_drop
    window = harness._pocket_window
    harness.base_shutdown = False

    harness.shutdown_presence()

    drop.detach.assert_called_once_with()
    window.destroy.assert_called_once_with()
    assert harness._pocket_drop is None
    assert harness._pocket_window is None
    assert harness.base_shutdown is True


class _DrawBase:
    def _draw(self, area, context, width, height):
        self.base_draws.append((area, context, width, height))


class _DrawHarness(PocketBuddyMixin, _DrawBase):
    pass


def test_pocket_hover_draws_breathing_glow_before_normal_render() -> None:
    harness = object.__new__(_DrawHarness)
    frame = object()
    harness._pocket_controller = SimpleNamespace(hover_active=True)
    harness.player = SimpleNamespace(frame=frame)
    harness.atlas = Mock()
    harness.base_draws = []

    with patch(
        "mochi.pocket_integration.time.monotonic",
        side_effect=(10.0, 10.575),
    ):
        harness._draw("area", "context", 112, 112)
        harness._draw("area", "context", 112, 112)

    first_call, second_call = harness.atlas.draw_glow.call_args_list
    assert first_call.args == ("context", frame, 112, 112)
    assert first_call.kwargs["pulse"] == pytest.approx(0.0)
    assert second_call.args == ("context", frame, 112, 112)
    assert second_call.kwargs["pulse"] == pytest.approx(1.0)
    assert harness.base_draws == [
        ("area", "context", 112, 112),
        ("area", "context", 112, 112),
    ]


def test_pocket_glow_phase_resets_after_hover_ends() -> None:
    harness = object.__new__(_DrawHarness)
    frame = object()
    harness._pocket_controller = SimpleNamespace(hover_active=True)
    harness.player = SimpleNamespace(frame=frame)
    harness.atlas = Mock()
    harness.base_draws = []

    with patch(
        "mochi.pocket_integration.time.monotonic",
        side_effect=(20.0, 20.2, 30.0),
    ):
        harness._draw("area", "context", 112, 112)
        harness._draw("area", "context", 112, 112)
        harness._pocket_controller.hover_active = False
        harness._draw("area", "context", 112, 112)
        harness._pocket_controller.hover_active = True
        harness._draw("area", "context", 112, 112)

    assert harness.atlas.draw_glow.call_args_list[-1].kwargs["pulse"] == pytest.approx(0.0)


def test_normal_render_skips_pocket_glow_when_not_hovering() -> None:
    harness = object.__new__(_DrawHarness)
    harness._pocket_controller = SimpleNamespace(hover_active=False)
    harness.player = SimpleNamespace(frame=object())
    harness.atlas = Mock()
    harness.base_draws = []

    harness._draw("area", "context", 112, 112)

    harness.atlas.draw_glow.assert_not_called()
    assert harness.base_draws == [("area", "context", 112, 112)]



def test_hidden_pocket_window_skips_row_rebuild_until_next_open() -> None:
    harness = object.__new__(PocketBuddyMixin)
    harness._pocket_label = Mock()
    harness._pocket_window = Mock()
    harness._pocket_window.get_visible.return_value = False

    harness._on_pocket_changed((object(),))

    harness._pocket_label.set_text.assert_called_once_with("Pocket · 1")
    harness._pocket_window.refresh.assert_not_called()
