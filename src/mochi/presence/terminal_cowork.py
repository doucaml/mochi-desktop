"""Terminal-focus coworking behavior for Mochi."""

from __future__ import annotations

from gi.repository import GLib

from mochi.sprites import ANIMATIONS
from mochi.state import MochiState


class TerminalCoworkMixin:
    """Keep Mochi at a terminal while a terminal window has active focus.

    Terminal coworking is a three-part contextual sequence:
    terminal_intro -> terminal_loop -> terminal_outro. Focus owns the mode,
    while direct interactions and higher-priority watchable video may interrupt
    it without changing the existing pointer or context-menu architecture.

    The sequence can wear different costumes: (intro, loop, outro) trios in
    ``COWORK_COSTUMES``. An intro picks the costume the context wants; loop and
    outro follow the art already on screen, so one open-close cycle never mixes
    costumes.
    """

    TERMINAL_COWORK_DEBOUNCE_MS = 700
    TERMINAL_INTRO_ANIMATION = "terminal_intro"
    TERMINAL_LOOP_ANIMATION = "terminal_loop"
    TERMINAL_OUTRO_ANIMATION = "terminal_outro"
    COWORK_COSTUMES = {
        "terminal": (
            TERMINAL_INTRO_ANIMATION,
            TERMINAL_LOOP_ANIMATION,
            TERMINAL_OUTRO_ANIMATION,
        ),
    }
    _COWORK_ROLES = ("intro", "loop", "outro")
    # Class-level default: immutable, and some tests build buddies with __new__.
    _cowork_costume = "terminal"

    def __init__(self, *args, **kwargs) -> None:
        self._terminal_cowork_source_id: int | None = None
        self._terminal_coworking_active = False
        super().__init__(*args, **kwargs)

    # -- Costumes -------------------------------------------------------------

    def _cowork_costume_for_context(self) -> str:
        """The costume a newly opening sequence should wear."""
        return "terminal"

    def _cowork_costume_of(self, name: str | None) -> str | None:
        for costume, names in self.COWORK_COSTUMES.items():
            if name in names:
                return costume
        return None

    def _cowork_role(self, name: str | None) -> str | None:
        """``intro``, ``loop`` or ``outro`` for any costume's art, else ``None``."""
        costume = self._cowork_costume_of(name)
        if costume is None:
            return None
        return self._COWORK_ROLES[self.COWORK_COSTUMES[costume].index(name)]

    def _cowork_names(self) -> tuple[str, str, str]:
        """The open cycle's trio: the art on screen, else the costume chosen at intro."""
        costume = self._cowork_costume_of(self._current_animation) or self._cowork_costume
        return self.COWORK_COSTUMES.get(costume, self.COWORK_COSTUMES["terminal"])

    def _terminal_cowork_context_live(self) -> bool:
        """Whether something currently calls for the terminal laptop.

        A focused terminal does. ``AgentCoworkMixin`` extends this so a working
        coding agent does too; every liveness check here goes through it.
        """
        return self._presence_app_category == "terminal"

    def _on_presence_app_category_changed(self, category: str) -> None:
        previous = self._presence_app_category
        super()._on_presence_app_category_changed(category)

        if not self._terminal_cowork_context_live() and (
            previous == "terminal" or self._terminal_coworking_active
        ):
            self._stop_terminal_coworking()
        if category == "terminal" or (
            self._terminal_cowork_context_live() and not self._terminal_coworking_active
        ):
            self._schedule_terminal_coworking()

    def _on_user_active(self) -> None:
        super()._on_user_active()
        if self._terminal_cowork_context_live():
            self._schedule_terminal_coworking()

    def _on_typing_stopped(self) -> None:
        # A real typing burst ending must not put the laptop away while the
        # terminal itself is still focused. Focus, not keystroke cadence, owns
        # this contextual companion state.
        if (
            self._terminal_cowork_context_live()
            and self.state.current is MochiState.TYPING
        ):
            self._ambient_presence_engine.record_typing_stopped()
            self._terminal_coworking_active = True
            return
        super()._on_typing_stopped()

    def _cancel_terminal_cowork_source(self) -> None:
        source_id = self._terminal_cowork_source_id
        self._terminal_cowork_source_id = None
        if source_id is not None:
            try:
                GLib.source_remove(source_id)
            except Exception:
                pass

    def _schedule_terminal_coworking(self) -> None:
        """Debounce terminal focus so quick Alt-Tab passes stay visually quiet."""
        self._cancel_terminal_cowork_source()
        if (
            self._presence_shutting_down
            or not self._terminal_cowork_context_live()
            or self._user_idle
        ):
            return
        self._terminal_cowork_source_id = GLib.timeout_add(
            self.TERMINAL_COWORK_DEBOUNCE_MS,
            self._begin_terminal_coworking,
        )

    def _begin_terminal_coworking(self) -> bool:
        self._terminal_cowork_source_id = None
        if (
            self._presence_shutting_down
            or not self._terminal_cowork_context_live()
            or self._user_idle
            or self._context_menu_open
        ):
            return GLib.SOURCE_REMOVE

        # Real video remains the highest contextual ambient state.
        if (
            self.state.current is MochiState.WATCHING
            or (
                self._media_monitor is not None
                and self._media_monitor.youtube_playing
            )
        ):
            return GLib.SOURCE_REMOVE

        if self.state.current is MochiState.TYPING:
            role = self._cowork_role(self._current_animation)
            if role == "loop":
                self._terminal_coworking_active = True
                return GLib.SOURCE_REMOVE
            if role == "intro":
                self._terminal_coworking_active = True
                return GLib.SOURCE_REMOVE
            if role == "outro":
                # A fast refocus while the laptop is closing should finish the
                # close cleanly, then reopen through the normal intro path.
                self._terminal_coworking_active = True
                self._logger.debug("Terminal coworking return queued after outro")
                return GLib.SOURCE_REMOVE

            self._terminal_coworking_active = True
            self._play_terminal_intro()
            self._logger.debug("Terminal coworking mode started")
            return GLib.SOURCE_REMOVE

        # Reuse the proven TYPING state for lifecycle/interruptions. The normal
        # typing intro is immediately replaced with terminal-specific artwork.
        if (
            self._start_typing_emote()
            and self.state.current is MochiState.TYPING
        ):
            self._terminal_coworking_active = True
            self._play_terminal_intro()
            self._logger.debug("Terminal coworking mode started")
        return GLib.SOURCE_REMOVE

    def _play_terminal_intro(self) -> None:
        if self._computer_idle_source_id is not None:
            GLib.source_remove(self._computer_idle_source_id)
            self._computer_idle_source_id = None
        # The only place a costume is chosen: loop and outro follow its art.
        self._cowork_costume = self._cowork_costume_for_context()
        intro, _loop, _outro = self.COWORK_COSTUMES[self._cowork_costume]
        self._play_animation(intro, after=None)

    def _play_terminal_loop(self) -> None:
        if self._computer_idle_source_id is not None:
            GLib.source_remove(self._computer_idle_source_id)
            self._computer_idle_source_id = None
        self._play_animation(self._cowork_names()[1], after=None)

    def _play_terminal_outro(self) -> None:
        self._play_animation(self._cowork_names()[2], after=None)

    def _finish_reaction(self, finished_animation) -> None:
        """Advance terminal transition frames without changing Buddy's core FSM."""
        if finished_animation is self._active_animation:
            if self._cowork_role(self._current_animation) == "intro":
                self._pending_animation = None
                if (
                    self._terminal_coworking_active
                    and self._terminal_cowork_context_live()
                    and not self._presence_shutting_down
                    and not self._user_idle
                    and self.state.current is MochiState.TYPING
                ):
                    self._play_terminal_loop()
                    self._logger.debug("Terminal coworking intro finished")
                else:
                    # Focus may leave while the intro is still opening. Finish
                    # opening first, then play the authored closing transition.
                    self._play_terminal_outro()
                return

            if self._cowork_role(self._current_animation) == "outro":
                self._pending_animation = None
                if (
                    self._terminal_coworking_active
                    and self._terminal_cowork_context_live()
                    and not self._presence_shutting_down
                    and not self._user_idle
                    and self.state.current is MochiState.TYPING
                ):
                    # The user returned before closing completed. Finish the
                    # authored close, then reopen rather than snapping frames.
                    self._play_terminal_intro()
                    return
                self._finish_terminal_outro()
                return

        super()._finish_reaction(finished_animation)

    def _stop_terminal_coworking(self) -> None:
        """Leave terminal coworking through the authored closing transition."""
        self._cancel_terminal_cowork_source()
        was_active = self._terminal_coworking_active
        self._terminal_coworking_active = False
        if not was_active:
            return

        if self.state.current is MochiState.TYPING:
            # Base presence schedules VS Code after its own debounce as soon as
            # the app category changes. Defer that timer while terminal artwork
            # is still closing so it cannot claim TYPING midway through outro.
            if self._presence_app_category == "vscode":
                self._cancel_vscode_cowork_source()

            role = self._cowork_role(self._current_animation)
            if role == "intro":
                # Complete the open first, then close. _finish_reaction sees the
                # inactive flag and advances into the costume's outro.
                self._pending_animation = self._cowork_names()[2]
            elif role == "loop":
                self._play_terminal_outro()
            elif role == "outro":
                pass
            else:
                # Terminal focus may have arrived while a generic typing phase
                # was still finishing. Use the authored laptop outro when possible.
                self._cowork_costume = "terminal"
                self._play_terminal_outro()
        # If a direct interaction already interrupted terminal coworking, leave
        # that reaction alone. Its normal completion path will restore whatever
        # contextual activity is appropriate for the newly focused app.

        self._logger.debug("Terminal coworking mode stopping")

    def _finish_terminal_outro(self) -> None:
        """Return to idle, then restore the destination's contextual activity."""
        if self.state.current is MochiState.TYPING:
            self._transition_to(MochiState.IDLE)
            self._play_animation("idle")

        if self._presence_shutting_down:
            return

        if self._presence_app_category == "vscode":
            self._schedule_vscode_coworking()
        elif self._terminal_cowork_context_live():
            self._schedule_terminal_coworking()
        elif self._user_idle:
            self._begin_sleep()
        elif not self._maybe_resume_ambient_activity():
            self._schedule_computer_idle_emote()

        self._logger.debug("Terminal coworking mode stopped")

    def _maybe_resume_terminal_coworking(self) -> bool:
        if (
            not self._terminal_cowork_context_live()
            or self._user_idle
            or self.state.current is not MochiState.IDLE
            or self._context_menu_open
            or not self._is_idle_visual_active()
            or (
                self._media_monitor is not None
                and self._media_monitor.youtube_playing
            )
        ):
            return False

        if not self._start_typing_emote():
            return False
        self._terminal_coworking_active = True
        self._play_terminal_intro()
        self._logger.debug("Terminal coworking mode resumed")
        return True

    def _maybe_resume_vscode_coworking(self) -> bool:
        """Insert terminal focus immediately ahead of VS Code in cowork priority."""
        if self._maybe_resume_terminal_coworking():
            return True
        return super()._maybe_resume_vscode_coworking()

    def _start_watching_emote(self) -> bool:
        # Explicit watchable video can interrupt any terminal phase immediately.
        terminal_animation_active = self._cowork_role(self._current_animation) is not None
        if (
            self.state.current is MochiState.TYPING
            and (self._terminal_coworking_active or terminal_animation_active)
        ):
            self._terminal_coworking_active = False
            self._pending_animation = None
            self._transition_to(MochiState.IDLE)
            self._play_animation("idle")
        return super()._start_watching_emote()

    def shutdown_presence(self) -> None:
        self._cancel_terminal_cowork_source()
        self._terminal_coworking_active = False
        super().shutdown_presence()
