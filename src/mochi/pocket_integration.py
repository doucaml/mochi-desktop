"""Thin Buddy composition layer for the Pocket subsystem."""

from __future__ import annotations

from collections.abc import Sequence
import math
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from mochi.pocket import PocketItem
from mochi.pocket_controller import PocketController
from mochi.pocket_drop import PocketDropAdapter
from mochi.pocket_store import PocketStore
from mochi.pocket_window import PocketWindow
from mochi.sprites import ANIMATIONS


POCKET_GLOW_PERIOD_SECONDS = 1.15


def _pocket_glow_pulse(elapsed_seconds: float) -> float:
    """Return a smooth 0..1 breathing pulse for Pocket hover feedback."""
    elapsed = max(0.0, float(elapsed_seconds))
    phase = (elapsed % POCKET_GLOW_PERIOD_SECONDS) / POCKET_GLOW_PERIOD_SECONDS
    return 0.5 - 0.5 * math.cos(phase * math.tau)


class PocketBuddyMixin:
    """Compose Pocket services without moving their logic into Buddy."""

    def __init__(self, *args, **kwargs) -> None:
        self._pocket_label: Gtk.Label | None = None
        self._pocket_window: PocketWindow | None = None
        self._pocket_drop: PocketDropAdapter | None = None
        store = getattr(self, "_pocket_store_override", None) or PocketStore()
        self._pocket_controller = PocketController(
            store,
            current_state=lambda: self.state.current,
            cancel_walk=self._cancel_walk,
            cancel_ambient=self._cancel_active_emote,
            transition=self._transition_to,
            play_animation=lambda name, after: self._play_animation(
                name, after=after
            ),
            mark_interaction=self._mark_interaction,
            resume_ambient=self._maybe_resume_ambient_activity,
            show_feedback=self._show_pocket_feedback,
            on_changed=self._on_pocket_changed,
        )
        super().__init__(*args, **kwargs)
        if not self._preview_mode:
            self._pocket_drop = PocketDropAdapter(self, self._pocket_controller)

    def _draw(self, area, context, width: int, height: int) -> None:
        """Add a breathing Pocket acceptance glow behind the Buddy render."""
        if self._pocket_controller.hover_active:
            now = time.monotonic()
            started_at = getattr(self, "_pocket_glow_started_at", None)
            if started_at is None or now < started_at:
                started_at = now
                self._pocket_glow_started_at = now

            frame = self.player.frame
            if frame is None:
                frame = ANIMATIONS["default"].frames[0]
            self.atlas.draw_glow(
                context,
                frame,
                width,
                height,
                pulse=_pocket_glow_pulse(now - started_at),
            )
        else:
            self._pocket_glow_started_at = None
        super()._draw(area, context, width, height)

    def _build_context_menu(self):
        menu = super()._build_context_menu()
        button, self._pocket_label = self._make_menu_button(
            f"Pocket · {self._pocket_controller.count}",
            "folder-download-symbolic",
            self._pocket_from_context_menu,
        )
        self._register_context_menu_row(
            "pocket",
            button,
            before="sleep",
        )
        return menu

    def _pocket_from_context_menu(self, _button: Gtk.Button) -> None:
        self._close_context_menu_then(self._show_pocket_window)

    def _show_pocket_window(self) -> None:
        if self._pocket_window is None:
            self._pocket_window = PocketWindow(self._pocket_controller)
            self._pocket_window.set_transient_for(self._window)
        else:
            self._pocket_window.refresh()
        self._pocket_window.present()

    def _on_pocket_changed(self, items: Sequence[PocketItem]) -> None:
        if self._pocket_label is not None:
            self._pocket_label.set_text(f"Pocket · {len(items)}")
        if (
            self._pocket_window is not None
            and self._pocket_window.get_visible()
        ):
            self._pocket_window.refresh()

    def _show_pocket_feedback(self, message: str) -> None:
        show_feedback = getattr(self, "show_nameplate_feedback", None)
        if callable(show_feedback):
            show_feedback(message)
        else:
            self._logger.info("Pocket: %s", message)

    def shutdown_presence(self) -> None:
        if self._pocket_drop is not None:
            self._pocket_drop.detach()
            self._pocket_drop = None
        if self._pocket_window is not None:
            self._pocket_window.destroy()
            self._pocket_window = None
        super().shutdown_presence()
