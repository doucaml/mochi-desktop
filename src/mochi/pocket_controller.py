"""GTK-independent orchestration for Mochi's Pocket interactions."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import logging

from mochi.behavior import can_start_pocket_receive
from mochi.pocket import PocketItem
from mochi.pocket_store import PocketStore
from mochi.state import MochiState


class PocketController:
    """Own the live Pocket list and one persistence-first receive transaction."""

    def __init__(
        self,
        store: PocketStore,
        *,
        current_state: Callable[[], MochiState],
        cancel_walk: Callable[[], None],
        cancel_ambient: Callable[[], None],
        transition: Callable[[MochiState], bool],
        play_animation: Callable[[str, str | None], None],
        mark_interaction: Callable[[], None],
        show_feedback: Callable[[str], None],
        on_changed: Callable[[tuple[PocketItem, ...]], None] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._store = store
        self._current_state = current_state
        self._cancel_walk = cancel_walk
        self._cancel_ambient = cancel_ambient
        self._transition = transition
        self._play_animation = play_animation
        self._mark_interaction = mark_interaction
        self._show_feedback = show_feedback
        self._on_changed = on_changed or (lambda _items: None)
        self._logger = logger or logging.getLogger(__name__)
        self._items = tuple(store.load())
        self._busy = False

    @property
    def items(self) -> tuple[PocketItem, ...]:
        return self._items

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def busy(self) -> bool:
        return self._busy

    def can_receive(self) -> bool:
        return not self._busy and can_start_pocket_receive(self._current_state())

    def receive(self, incoming: Iterable[PocketItem]) -> bool:
        candidates = tuple(incoming)
        if not candidates:
            self._show_feedback("I can't hold that yet")
            return False
        if not self.can_receive():
            self._show_feedback("My paws are full")
            return False

        self._busy = True
        try:
            try:
                mutation = self._store.add_items(self._items, candidates)
            except OSError as error:
                self._logger.warning("Could not persist Pocket drop: %s", error)
                self._show_feedback("I couldn't hold that")
                return False

            self._items = mutation.items
            self._on_changed(self._items)

            state = self._current_state()
            if state is MochiState.WALKING:
                self._cancel_walk()
            else:
                self._cancel_ambient()

            if not self._transition(MochiState.EXCITED):
                # Persistence is already authoritative. A transition rejection
                # cannot safely roll back the accepted content, so retain it and
                # report the presentation fault without replaying the animation.
                self._logger.warning(
                    "Pocket persisted but receive presentation was rejected from %s",
                    self._current_state().name,
                )
                self._show_feedback(self._held_message(len(candidates), len(mutation.evicted)))
                return True

            self._mark_interaction()
            self._play_animation("pocket_grab", "idle")
            self._show_feedback(
                self._held_message(len(candidates), len(mutation.evicted))
            )
            return True
        finally:
            self._busy = False

    def remove(self, item_id: str) -> bool:
        if not any(item.id == item_id for item in self._items):
            return False
        try:
            remaining = self._store.remove(self._items, item_id)
        except OSError as error:
            self._logger.warning("Could not persist Pocket removal: %s", error)
            self._show_feedback("I couldn't update Pocket")
            return False
        self._items = tuple(remaining)
        self._on_changed(self._items)
        return True

    @staticmethod
    def _held_message(received: int, evicted: int) -> str:
        noun = "item" if received == 1 else "items"
        message = f"Held {received} {noun}"
        if evicted:
            removed = "item" if evicted == 1 else "items"
            message += f" · removed the oldest {evicted} {removed}"
        return message
