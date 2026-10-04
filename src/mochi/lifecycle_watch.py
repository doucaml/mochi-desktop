"""Debug-only watchdog that names which animation layer stopped.

Mochi's animation pipeline has three independent layers:

    GLib timer tick  →  AnimationPlayer frame advance  →  GTK draw/paint

A visual freeze (issue #45) means one of them stopped. This watchdog only
observes: it logs window/lifecycle edges at debug level and, once a stall has
lasted long enough, one warning naming the layer plus a state snapshot, then
one "recovered" line when it resumes. It never restarts timers, replays
animations, or changes state, so it cannot hide the failure it is meant to
catch.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from mochi.animation import Animation


STALL_AFTER_SECONDS = 2.0
# A frame that has not changed for this many of its own durations is stuck.
PLAYER_STALL_FRAMES = 3


def motion_budget_ms(animation: Animation | None, *, held: bool) -> int | None:
    """Longest frame time of an animation that should visibly move, else None."""
    if animation is None or held or len(animation.frames) < 2:
        return None
    return max(
        frame.duration_ms or animation.frame_duration_ms for frame in animation.frames
    )


class LifecycleWatch:
    def __init__(
        self,
        *,
        logger: logging.Logger,
        snapshot: Callable[[], str],
        clock: Callable[[], float] = time.monotonic,
        stall_after_seconds: float = STALL_AFTER_SECONDS,
    ) -> None:
        self._logger = logger
        self._snapshot = snapshot
        self._clock = clock
        self._stall_after = stall_after_seconds
        now = clock()
        self._last_tick = now
        self._last_advance = now
        self._last_draw = now
        self._last_paint: float | None = None
        self._undrawn_since: float | None = None
        self._motion_budget_ms: int | None = None
        self._active: dict[str, float] = {}

    def edge(self, event: str) -> None:
        self._logger.debug("Lifecycle: %s", event)

    def tick(self, *, advanced: bool, motion_budget_ms: int | None) -> None:
        now = self._clock()
        self._last_tick = now
        self._motion_budget_ms = motion_budget_ms
        if advanced:
            self._last_advance = now
            if self._undrawn_since is None:
                self._undrawn_since = now

    def drew(self) -> None:
        self._last_draw = self._clock()
        self._undrawn_since = None

    def painted(self) -> None:
        self._last_paint = self._clock()

    def check(self) -> list[str]:
        """Log stalls that just began or ended; return the ones that began."""
        now = self._clock()
        ticks_stalled = now - self._last_tick > self._stall_after
        stalled = {
            name
            for name, is_stalled in (
                ("ticks", ticks_stalled),
                (
                    "draw",
                    self._undrawn_since is not None
                    and now - self._undrawn_since > self._stall_after,
                ),
                # Without ticks the player cannot advance; that is a tick stall.
                ("player", not ticks_stalled and self._player_stalled(now)),
            )
            if is_stalled
        }

        began = [
            name
            for name in ("ticks", "player", "draw")
            if name in stalled and name not in self._active
        ]
        for name in began:
            self._active[name] = now
            self._logger.warning(
                "Lifecycle stall [%s]: %s | last tick %.1fs ago, last frame "
                "advance %.1fs ago, last draw %.1fs ago, last paint %s | %s",
                name,
                _DESCRIPTIONS[name],
                now - self._last_tick,
                now - self._last_advance,
                now - self._last_draw,
                (
                    "never"
                    if self._last_paint is None
                    else f"{now - self._last_paint:.1f}s ago"
                ),
                self._snapshot(),
            )
        for name in [name for name in self._active if name not in stalled]:
            started = self._active.pop(name)
            self._logger.warning(
                "Lifecycle recovered [%s] after %.1fs | %s",
                name,
                now - started,
                self._snapshot(),
            )
        return began

    def _player_stalled(self, now: float) -> bool:
        if self._motion_budget_ms is None:
            return False
        limit = max(
            self._stall_after,
            PLAYER_STALL_FRAMES * self._motion_budget_ms / 1000,
        )
        return now - self._last_advance > limit


_DESCRIPTIONS = {
    "ticks": "the GLib animation timer stopped firing",
    "player": "the timer runs but the animation is not advancing frames",
    "draw": "frames advance but GTK has not drawn them",
}
