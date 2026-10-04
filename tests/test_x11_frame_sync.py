"""Mochi's XWayland window must not wait on compositor frame replies (#45)."""

from __future__ import annotations

import pytest

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from mochi import windowing  # noqa: E402
from mochi.windowing import WindowPlacement  # noqa: E402
from mochi.x11 import disable_frame_sync  # noqa: E402

pytestmark = pytest.mark.skipif(
    Gdk.Display.get_default() is None, reason="needs a display (run under xvfb-run)"
)


def test_disable_frame_sync_needs_a_realized_x11_window() -> None:
    window = Gtk.Window()
    assert disable_frame_sync(window) is False  # no surface yet

    window.realize()
    try:
        assert disable_frame_sync(window) is True
    finally:
        window.destroy()


def test_placement_disables_frame_sync_when_the_window_is_realized(monkeypatch) -> None:
    calls: list[Gtk.Window] = []
    monkeypatch.setattr(windowing, "disable_frame_sync", lambda win: calls.append(win) or True)
    monkeypatch.delenv("MOCHI_X11_FRAME_SYNC", raising=False)
    window = Gtk.Window()

    WindowPlacement(window, None)
    assert calls == []  # nothing to configure before the surface exists
    window.realize()
    try:
        assert calls == [window]  # before the first frame is painted
    finally:
        window.destroy()


def test_frame_sync_can_be_kept_for_comparison(monkeypatch) -> None:
    calls: list[Gtk.Window] = []
    monkeypatch.setattr(windowing, "disable_frame_sync", lambda win: calls.append(win) or True)
    monkeypatch.setenv("MOCHI_X11_FRAME_SYNC", "1")
    window = Gtk.Window()

    WindowPlacement(window, None)
    window.realize()
    try:
        assert calls == []
    finally:
        window.destroy()
