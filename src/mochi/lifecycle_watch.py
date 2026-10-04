"""Debug-only watchdog that names which animation layer stopped.

Mochi's animation pipeline has three independent layers:

    GLib timer tick  →  AnimationPlayer frame advance  →  GTK draw/paint

A visual freeze (issue #45) means one of them stopped. This watchdog only
observes: it logs window/lifecycle edges at debug level and, once a stall has
lasted long enough, one warning naming the layer plus a state snapshot, then
one "recovered" line when it resumes. It never restarts timers, replays
animations, or changes state, so it cannot hide the failure it is meant to
catch.

The checks run on the GLib main loop, so they cannot report a loop that is
itself blocked. For that case every check re-arms faulthandler's hang dump:
if no check happens for HANG_DUMP_SECONDS, faulthandler's own thread prints
every Python thread's stack to stderr.
"""

from __future__ import annotations

import faulthandler
import logging
import sys
import time
from collections.abc import Callable

from mochi.animation import Animation


STALL_AFTER_SECONDS = 2.0
# A frame that has not changed for this many of its own durations is stuck.
PLAYER_STALL_FRAMES = 3
# Checks run every second; five missed checks means the main loop is blocked.
HANG_DUMP_SECONDS = 5.0


def _arm_faulthandler_dump(seconds: float) -> None:
    # Re-arming replaces the previous timer, so a healthy loop never fires it.
    faulthandler.dump_traceback_later(seconds, file=sys.stderr)


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
        arm_hang_dump: Callable[[float], None] = _arm_faulthandler_dump,
        cancel_hang_dump: Callable[[], None] = faulthandler.cancel_dump_traceback_later,
    ) -> None:
        self._logger = logger
        self._snapshot = snapshot
        self._clock = clock
        self._stall_after = stall_after_seconds
        self._arm_hang_dump = arm_hang_dump
        self._cancel_hang_dump = cancel_hang_dump
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
        if now - self._last_tick > self._stall_after:
            # Ticks are resuming after a gap; the player could not advance
            # without them, so its budget starts over instead of blaming it.
            self._last_advance = now
        self._last_tick = now
        if self._motion_budget_ms is None and motion_budget_ms is not None:
            self._last_advance = now
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
        self._arm_hang_dump(HANG_DUMP_SECONDS)
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

    def close(self) -> None:
        self._cancel_hang_dump()

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
