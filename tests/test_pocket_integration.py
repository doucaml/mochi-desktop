"""Pocket composition, menu, and lifecycle integration coverage."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

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
