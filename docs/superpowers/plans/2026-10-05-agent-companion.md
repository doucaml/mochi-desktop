# Agent Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use beads-superpowers:subagent-driven-development (recommended) or beads-superpowers:executing-plans to implement this plan task by task.
> - Each Task becomes a bead (`bd create -t task --parent <epic-id>`). If `bd` is not installed, use the session task list.
> - Steps use checkbox (`- [ ]`) syntax.
> - Do not start until the spec and this plan are approved.

**Goal:** Mochi coworks with Claude Code and Codex.
- He opens his laptop while any agent works.
- He waves once when an agent has waited on a permission prompt for more than 10 s.
- He bounces once when a run of 60 s or longer finishes.
- Each reaction can come with a gentle line through `PresenceEngine`.
- No prompt, path, command or reply ever reaches Mochi.

**Architecture:**
1. A stdlib-only bridge command (`mochi-agent-signal`) runs from agent hooks. It forwards an allow-listed event and a hashed session token over the `org.gtk.Actions` interface that GApplication already exports.
2. A pure tracker turns events into four edges.
3. A presence mixin maps the edges onto the existing terminal-coworking laptop (via one liveness predicate), onto `IdleLookMixin._play_idle_beat` beats, and onto two new engine events.

There is no new `MochiState`, no new art, and no new bus name.

**Tech Stack:** Python 3.11+ (stdlib for the bridge), GTK4/PyGObject, GLib timers, `gdbus`, pytest.

**Spec:** `docs/superpowers/specs/2026-10-05-agent-companion-design.md`

## Global Constraints

- **Privacy.**
  - The bridge parses the hook payload only to read a string `session_id`.
  - It never stores, logs, prints or sends any other field.
  - Mochi receives exactly `(event, token)`, where `event ∈ AGENT_EVENTS` and the token is 16 lowercase hex characters.
- **The bridge never hurts the agent.**
  - It always exits 0 and writes nothing to stdout or stderr.
  - It never uses `argparse` and never imports `gi`.
  - It reads stdin under a 0.5 s deadline.
  - `gdbus` runs with `--timeout 1` and a 1.5 s process timeout.
- **One allow-list.** `AGENT_EVENTS` and `AGENT_TOKEN_PATTERN` live in `src/mochi/agent_activity.py`. The bridge and the app action both import them.
- **No new animation path.** Beats run only through `IdleLookMixin._play_idle_beat`, and the laptop runs only through `TerminalCoworkMixin`.
- **Speech** goes only through `PresenceEngine.emit()`. No direct bubble calls and no `markup=`.
- **Untouched:** the updater (`src/mochi/update/`), `src/mochi_launcher.py`, GDK backend selection, and VS Code coworking code (`integration.py`).
- **Constants (exact values):**
  - `AgentActivityTracker.NEEDS_INPUT_GRACE_SECONDS = 10.0`
  - `AgentActivityTracker.CELEBRATE_MIN_RUN_SECONDS = 60.0`
  - `AgentActivityTracker.SESSION_STALE_SECONDS = 900.0`
  - `AgentActivityTracker.MAX_SESSIONS = 16`
  - `AgentCoworkMixin.AGENT_POLL_INTERVAL_SECONDS = 1`
  - `AgentCoworkMixin.AGENT_BEAT_TTL_SECONDS = 30.0`
  - `AgentCoworkMixin.AGENT_NEEDS_INPUT_BEAT = "wave"`
  - `AgentCoworkMixin.AGENT_FINISHED_BEAT = "excited"`
  - `agent_signal.STDIN_DEADLINE_SECONDS = 0.5`
  - `agent_signal.GDBUS_TIMEOUT_SECONDS = 1`
  - `agent_signal.PROCESS_TIMEOUT_SECONDS = 1.5`
  - `agent_signal.MAX_STDIN_BYTES = 8 * 1024 * 1024`
  - `PresenceTuning.agent_event_probability = 0.90`
  - Engine priority `30` for both `agent_needs_input` and `agent_finished`, category `"agent"`.
- **Test command.**
  - In this container the default `python3` is 3.11 without `gi`, and the GTK bindings are for 3.12. Install the CI packages first: `apt-get install -y --no-install-recommends gir1.2-gtk-4.0 python3-pytest python3-cairo python3-gi-cairo gsettings-desktop-schemas`.
  - Then run: `PYTHONPATH=src xvfb-run -a /usr/bin/python3.12 -m pytest -q -p no:cacheprovider <paths>`.
  - CI runs `xvfb-run -a python3 -m pytest -q`.
- **Baseline** at `main` @ `79a5857`: **1145 passed, 3 skipped**. It was measured with AGENTS.md on top, which touches no code.
- **Commits** end with the session's attribution trailer. Branch: `claude/agent-companion-spec`, cut from `main`. Merge `main` in if it moves.

## File Map

| File | Responsibility | Task |
|---|---|---|
| `src/mochi/agent_activity.py` (new) | Allow-list, token pattern, pure tracker and edges | 1 |
| `tests/test_agent_activity.py` (new) | Tracker behavior | 1 |
| `src/mochi/agent_signal.py` (new) | `mochi-agent-signal` bridge | 2 |
| `tests/test_agent_signal.py` (new) | Bridge behavior, silence, failure tolerance | 2 |
| `pyproject.toml` | Console script | 2 |
| `src/mochi/app.py` | `agent-event` GAction → buddy | 3 |
| `tests/test_agent_cowork.py` (new) | App action, terminal characterization, mixin | 3, 4, 5 |
| `src/mochi/presence/terminal_cowork.py` | `_terminal_cowork_context_live()` predicate, stop condition | 4 |
| `src/mochi/presence/agent_cowork.py` (new) | `AgentCoworkMixin` | 5 |
| `src/mochi/presence/click_dialogue.py` | MRO insertion | 5 |
| `src/mochi/presence/engine.py`, `phrases.py` | Two events, probability, phrases | 6 |
| `tests/test_presence_engine.py` | Engine coverage | 6 |
| `install.sh`, `uninstall.sh`, `tests/test_installer.py` | Launcher install and removal | 7 |
| `docs/agent-companion.md` (new), `docs/ambisense.md`, `README.md`, `CHANGELOG.md`, `REGRESSION_WATCHLIST.md` | Docs and QA | 8 |
| `tests/test_agent_dbus_integration.py` (new, opt-in) | Real-bus round trip | 9 |

---

### Task 1: Pure tracker (`src/mochi/agent_activity.py`)

**Files:** Create `src/mochi/agent_activity.py` and `tests/test_agent_activity.py`.

**Interfaces:**
- **Produces:**
  - `AGENT_EVENTS: frozenset[str]` = `{"working", "activity", "needs_input", "finished", "ended"}`
  - `AGENT_TOKEN_PATTERN: re.Pattern`, `[0-9a-f]{16}`, used with `fullmatch`
  - `class AgentEdge(Enum)`: `WORK_STARTED`, `WORK_STOPPED`, `NEEDS_INPUT`, `FINISHED_LONG`
  - `class AgentActivityTracker(*, clock: Callable[[], float] = time.monotonic)`:
    - `record(event: str, token: str) -> list[AgentEdge]`
    - `poll() -> list[AgentEdge]`
    - `working: bool` (property), `has_sessions: bool` (property)
    - `clear() -> None`
- **Consumes:** nothing outside the stdlib.

**Acceptance Criteria:**
- **Edge order.** A working edge, if any, always comes first in the returned list: `[WORK_STOPPED, FINISHED_LONG]`, never the reverse.
- **Working.** Agents are working if any session is `WORKING`, or is `WAITING` with `now - waiting_since < 10.0`.
- **Creating sessions.** Only `working` and `needs_input` create a session. `activity`, `finished` and `ended` never do.
- **Celebration.** `finished` celebrates only for a session that is not `WAITING`, after a run of 60 s or more.
- **Nudges.** `NEEDS_INPUT` comes only from `poll()`, once per wait. Leaving `WAITING` resets it.
- **Stale cleanup.** `poll()` drops sessions idle for 900 s or more, with no celebration.
- **Session cap.** Over 16 sessions, the least recently seen session is evicted.
- **Rejected input.** Invalid events and tokens return `[]` and change nothing.
- **Purity.** The module imports no `gi`, `cairo` or `mochi.presence`.

- [ ] **Step 1: Write the failing tests.** Cover each Acceptance Criterion with a fake clock (`now = [0.0]; clock = lambda: now[0]`) and a valid token such as `"0123456789abcdef"`. Required cases:
  - `test_first_working_session_starts_work_and_second_adds_no_edge`
  - `test_long_run_finish_stops_then_celebrates` (61 s) and `test_short_run_finish_only_stops` (59 s)
  - `test_quick_approval_inside_grace_produces_no_edges` (after the initial `WORK_STARTED`: `needs_input` at 0 s, `activity` at 5 s, `poll()` at 5 s and 20 s all return `[]`)
  - `test_unanswered_prompt_nudges_once_after_grace`: `poll()` at 10 s returns `[WORK_STOPPED, NEEDS_INPUT]`, and later polls return `[]`
  - `test_late_approval_restarts_work_and_allows_a_second_nudge`
  - `test_finish_while_waiting_never_celebrates` (even after 120 s)
  - `test_ended_never_celebrates`, and `test_unknown_session_activity_finished_ended_are_ignored`
  - `test_stale_session_is_dropped_silently` (900 s with no events → `[WORK_STOPPED]`, no `FINISHED_LONG`, `has_sessions` is False)
  - `test_invalid_event_or_token_changes_nothing` (`"WORKING"`, `"0123"`, `"0123456789ABCDEF"`, `"g" * 16`, `None`)
  - `test_session_cap_evicts_least_recently_seen` (17 tokens; the oldest is gone, `working` is still True)
  - `test_parallel_sessions_keep_working_until_last_stops`
  - `test_module_is_display_free`: a source-text check for `import gi`, `cairo` and `mochi.presence`
- [ ] **Step 2: Run the tests and see them fail.** `… pytest -q tests/test_agent_activity.py` → `ModuleNotFoundError: No module named 'mochi.agent_activity'`.
- [ ] **Step 3: Implement.** Reference implementation:

```python
"""Coarse lifecycle tracking for local coding agents (Claude Code, Codex).

Pure and display-free: hooks report one allow-listed word per lifecycle step and
an opaque per-session token. Nothing here knows what the agent is doing.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

AGENT_EVENTS = frozenset({"working", "activity", "needs_input", "finished", "ended"})
AGENT_TOKEN_PATTERN = re.compile(r"[0-9a-f]{16}")


class AgentEdge(Enum):
    WORK_STARTED = "work_started"
    WORK_STOPPED = "work_stopped"
    NEEDS_INPUT = "needs_input"
    FINISHED_LONG = "finished_long"


@dataclass(slots=True)
class _Session:
    run_started_at: float
    last_seen_at: float
    waiting_since: float | None = None
    nudged: bool = False


class AgentActivityTracker:
    """Turn agent lifecycle words into presentation edges."""

    NEEDS_INPUT_GRACE_SECONDS = 10.0
    CELEBRATE_MIN_RUN_SECONDS = 60.0
    SESSION_STALE_SECONDS = 900.0
    MAX_SESSIONS = 16

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._sessions: dict[str, _Session] = {}
        self._reported_working = False

    @property
    def has_sessions(self) -> bool:
        return bool(self._sessions)

    @property
    def working(self) -> bool:
        return self._working_at(self._clock())

    def clear(self) -> None:
        self._sessions.clear()
        self._reported_working = False

    def record(self, event: str, token: str) -> list[AgentEdge]:
        if (
            event not in AGENT_EVENTS
            or not isinstance(token, str)
            or AGENT_TOKEN_PATTERN.fullmatch(token) is None
        ):
            return []
        now = self._clock()
        edges: list[AgentEdge] = []
        session = self._sessions.get(token)
        if event == "working":
            if session is None:
                self._admit(token, _Session(run_started_at=now, last_seen_at=now))
            else:
                session.last_seen_at = now
                self._stop_waiting(session)
        elif event == "activity":
            # Async hooks can arrive out of order; a late `activity` must not
            # reopen a finished run, so it never creates a session.
            if session is not None:
                session.last_seen_at = now
                self._stop_waiting(session)
        elif event == "needs_input":
            if session is None:
                session = _Session(run_started_at=now, last_seen_at=now)
                self._admit(token, session)
            session.last_seen_at = now
            if session.waiting_since is None:
                session.waiting_since = now
                session.nudged = False
        elif event == "finished":
            if session is not None:
                del self._sessions[token]
                if (
                    session.waiting_since is None
                    and now - session.run_started_at >= self.CELEBRATE_MIN_RUN_SECONDS
                ):
                    edges.append(AgentEdge.FINISHED_LONG)
        else:  # "ended"
            self._sessions.pop(token, None)
        return self._with_working_edge(now, edges)

    def poll(self) -> list[AgentEdge]:
        now = self._clock()
        edges: list[AgentEdge] = []
        for token, session in list(self._sessions.items()):
            if now - session.last_seen_at >= self.SESSION_STALE_SECONDS:
                del self._sessions[token]
                continue
            if (
                session.waiting_since is not None
                and not session.nudged
                and now - session.waiting_since >= self.NEEDS_INPUT_GRACE_SECONDS
            ):
                session.nudged = True
                edges.append(AgentEdge.NEEDS_INPUT)
        return self._with_working_edge(now, edges)

    def _working_at(self, now: float) -> bool:
        return any(
            session.waiting_since is None
            or now - session.waiting_since < self.NEEDS_INPUT_GRACE_SECONDS
            for session in self._sessions.values()
        )

    def _with_working_edge(self, now: float, edges: list[AgentEdge]) -> list[AgentEdge]:
        working = self._working_at(now)
        if working != self._reported_working:
            self._reported_working = working
            edges.insert(0, AgentEdge.WORK_STARTED if working else AgentEdge.WORK_STOPPED)
        return edges

    def _admit(self, token: str, session: _Session) -> None:
        if len(self._sessions) >= self.MAX_SESSIONS:
            oldest = min(self._sessions, key=lambda key: self._sessions[key].last_seen_at)
            del self._sessions[oldest]
        self._sessions[token] = session

    @staticmethod
    def _stop_waiting(session: _Session) -> None:
        session.waiting_since = None
        session.nudged = False
```

- [ ] **Step 4: Run the tests and see them pass.** Then run the full suite and confirm the baseline plus the new tests.
- [ ] **Step 5: Commit.** `feat(agent): pure agent activity tracker`

---

### Task 2: Bridge command (`src/mochi/agent_signal.py`)

**Files:** Create `src/mochi/agent_signal.py` and `tests/test_agent_signal.py`. Modify `pyproject.toml` by adding `mochi-agent-signal = "mochi.agent_signal:main"` under `[project.scripts]`.

**Interfaces:**
- **Consumes:** `AGENT_EVENTS` from Task 1.
- **Produces:**
  - `parse_args(argv) -> tuple[str, str] | None`
  - `read_payload(stream, *, deadline_seconds) -> bytes`
  - `session_token(payload: bytes, source: str) -> str`
  - `gdbus_command(gdbus: str, event: str, token: str) -> list[str]`
  - `main(argv=None, *, stdin=None, run=subprocess.run, which=shutil.which, stdin_deadline_seconds=0.5) -> int`

**Acceptance Criteria:**
- **Arguments.**
  - `parse_args`: `["working"]` gives `("working", "claude")`, and `["working", "--source", "codex"]` gives `("working", "codex")`.
  - Everything else gives `None`: no arguments, an unknown event, an unknown source, a lone `--source`, or extra words.
- **Token.**
  - `session_token` returns `sha256(f"{source}:{session_id}".encode("utf-8", "surrogatepass")).hexdigest()[:16]`.
  - It falls back to `session_id = "default"` for empty, invalid or deeply nested JSON (`ValueError`, `RecursionError`), for a non-dict payload, or for a missing or non-string or empty `session_id`.
- **stdin.**
  - `read_payload` returns `b""` for `None`, a TTY, or an unusable stream.
  - Otherwise it drains until EOF or the deadline, keeping at most `MAX_STDIN_BYTES`.
  - It returns within `deadline_seconds + 0.2` even if the writer never closes.
  - It reads `/dev/null` and regular files, which `epoll` refuses, through the non-polling fallback: `/dev/null` gives `b""`, and a file gives its contents. This was found by smoke-testing the reference code. Without the fallback, `mochi-agent-signal working < /dev/null` silently sent nothing.
- **D-Bus call.** `gdbus_command` gives exactly `[gdbus, "call", "--session", "--timeout", "1", "--dest", "io.github.mochi_desktop.Mochi", "--object-path", "/io/github/mochi_desktop/Mochi", "--method", "org.gtk.Actions.Activate", "agent-event", "[<('<event>', '<token>')>]", "{}"]`.
- **main.**
  - It always returns 0.
  - Invalid arguments mean no stdin read and no `run`.
  - If `which("gdbus")` is `None`, there is no `run`.
  - `run` is called with `stdin`, `stdout` and `stderr` set to `subprocess.DEVNULL`, `timeout=1.5` and `check=False`.
  - Any exception from `run` (`FileNotFoundError`, `TimeoutExpired`, `OSError`, `RuntimeError`) is swallowed.
- **Silence.** In every test case, `capsys` captures empty stdout and empty stderr.
- **Imports.** The module imports nothing from `gi`.

- [ ] **Step 1: Write the failing tests.** Cover each criterion. Use `os.pipe()` for real stdin streams: write and close for the normal path, and keep the write end open for the deadline test. Inject a `run` stub that records calls. Include `test_only_session_id_reaches_gdbus`: two payloads with the same `session_id` but different `prompt`, `tool_input`, `cwd` and `transcript_path` give identical argv.
- [ ] **Step 2: Run the tests and see them fail** (module missing).
- [ ] **Step 3: Implement.** Reference implementation:

```python
"""``mochi-agent-signal``: tell a running Mochi what a coding agent is doing.

Claude Code and Codex hooks run this command. It forwards one allow-listed
lifecycle word and an opaque per-session token to Mochi's ``agent-event``
action. The hook payload is read only to hash ``session_id``; nothing else is
kept, logged, or sent. It never prints and always exits 0: hook stdout can be
added to the agent's context, and exit code 2 would block the agent.
"""

from __future__ import annotations

import hashlib
import json
import os
import selectors
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence

from mochi.agent_activity import AGENT_EVENTS

APPLICATION_ID = "io.github.mochi_desktop.Mochi"
OBJECT_PATH = "/io/github/mochi_desktop/Mochi"
ACTION_NAME = "agent-event"
SOURCES = frozenset({"claude", "codex"})
STDIN_DEADLINE_SECONDS = 0.5
GDBUS_TIMEOUT_SECONDS = 1
PROCESS_TIMEOUT_SECONDS = 1.5
MAX_STDIN_BYTES = 8 * 1024 * 1024


def parse_args(argv: Sequence[str]) -> tuple[str, str] | None:
    """Return ``(event, source)``, or ``None`` for anything unexpected.

    Parsed by hand: argparse prints usage and exits 2 on errors, and exit
    code 2 from a hook blocks the agent.
    """
    args = list(argv)
    if not args:
        return None
    event, rest = args[0], args[1:]
    source = "claude"
    if rest:
        if len(rest) != 2 or rest[0] != "--source":
            return None
        source = rest[1]
    if event not in AGENT_EVENTS or source not in SOURCES:
        return None
    return event, source


def read_payload(stream, *, deadline_seconds: float) -> bytes:
    """Drain the hook payload without ever blocking past the deadline."""
    try:
        if stream is None or stream.isatty():
            return b""
        fd = stream.fileno()
    except (AttributeError, OSError, ValueError):
        return b""
    chunks: list[bytes] = []
    kept = 0

    def keep(chunk: bytes) -> None:
        nonlocal kept
        if kept < MAX_STDIN_BYTES:
            chunks.append(chunk[: MAX_STDIN_BYTES - kept])
            kept += len(chunks[-1])

    deadline = time.monotonic() + deadline_seconds
    with selectors.DefaultSelector() as selector:
        try:
            selector.register(fd, selectors.EVENT_READ)
        except (OSError, ValueError):
            # epoll refuses regular files and /dev/null. Those never block, so
            # a plain bounded read loop is safe for them.
            while kept < MAX_STDIN_BYTES and (chunk := os.read(fd, 65536)):
                keep(chunk)
            return b"".join(chunks)
        while (remaining := deadline - time.monotonic()) > 0:
            if not selector.select(remaining):
                break
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            keep(chunk)
    return b"".join(chunks)


def session_token(payload: bytes, source: str) -> str:
    session_id = "default"
    try:
        data = json.loads(payload)
    except (ValueError, RecursionError):
        data = None
    if isinstance(data, dict):
        candidate = data.get("session_id")
        if isinstance(candidate, str) and candidate:
            session_id = candidate
    digest = hashlib.sha256(f"{source}:{session_id}".encode("utf-8", "surrogatepass"))
    return digest.hexdigest()[:16]


def gdbus_command(gdbus: str, event: str, token: str) -> list[str]:
    # Both values are validated (allow-list, hex), so the GVariant text is safe.
    return [
        gdbus, "call", "--session", "--timeout", str(GDBUS_TIMEOUT_SECONDS),
        "--dest", APPLICATION_ID, "--object-path", OBJECT_PATH,
        "--method", "org.gtk.Actions.Activate", ACTION_NAME,
        f"[<('{event}', '{token}')>]", "{}",
    ]


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin=None,
    run: Callable[..., object] = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
    stdin_deadline_seconds: float = STDIN_DEADLINE_SECONDS,
) -> int:
    try:
        parsed = parse_args(sys.argv[1:] if argv is None else argv)
        if parsed is None:
            return 0
        event, source = parsed
        payload = read_payload(
            sys.stdin if stdin is None else stdin,
            deadline_seconds=stdin_deadline_seconds,
        )
        token = session_token(payload, source)
        gdbus = which("gdbus")
        if gdbus is None:
            return 0
        run(
            gdbus_command(gdbus, event, token),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=PROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception:
        pass
    return 0
```

- [ ] **Step 4: Run the tests and see them pass.**
- [ ] **Step 5: Measure.** Install editable into a scratch venv, or run `time PYTHONPATH=src python3 -m mochi.agent_signal working < /dev/null`. This needs a `__main__` guard; if one is added, keep it to `raise SystemExit(main())`. Record the measured wall time in the PR. The target is under 100 ms with Mochi absent. The reference code measured 48–60 ms per call during planning: five runs on a `dbus-run-session` bus with no Mochi, payload piped on stdin, exit 0, no output.
- [ ] **Step 6: Commit.** `feat(agent): mochi-agent-signal bridge command`

---

### Task 3: App action (`src/mochi/app.py`)

**Files:** Modify `src/mochi/app.py`. Add tests to `tests/test_agent_cowork.py`.

**Interfaces:**
- **Consumes:** `AGENT_EVENTS` and `AGENT_TOKEN_PATTERN` (Task 1).
- **Produces:**
  - `AGENT_EVENT_ACTION = "agent-event"`
  - `MochiApplication._on_agent_event_action(action, parameter) -> None`
  - The buddy contract: `receive_agent_event(event: str, token: str) -> None` (implemented in Task 5)

**Acceptance Criteria:**
- **Registration.** `MochiApplication(config, preview_animations=False).lookup_action("agent-event")` exists, and its `get_parameter_type().dup_string()` is `"(ss)"`. With `preview_animations=True` it is `None`.
- **Forwarding.** `app.activate_action("agent-event", GLib.Variant("(ss)", ("working", "0123456789abcdef")))` with `app._buddy = Mock()` calls `receive_agent_event("working", "0123456789abcdef")` once.
- **Rejection.** An unknown event, an uppercase or short token, or `_buddy is None` → no call and no exception.
- **Lifetime.** Constructing the app in tests uses a `ConfigStore(tmp_path / "config.json")`, like `tests/test_update_handshake.py`.

- [ ] **Step 1: Write the failing tests.**
- [ ] **Step 2: Run and see them fail.**
- [ ] **Step 3: Implement.**
  - Import `GLib` alongside `Gio`.
  - Register the action at the end of `__init__` when `not preview_animations`, following the scratch probe from the spec.
  - The handler unpacks, validates, looks up `self._buddy`, and forwards.
  - Validation failures are logged at debug with no payload text.
- [ ] **Step 4: Run and see them pass.** Then run the full suite.
- [ ] **Step 5: Commit.** `feat(agent): accept agent events through the app's GAction`

---

### Task 4: Terminal coworking liveness predicate (characterization first)

**Files:** Modify `src/mochi/presence/terminal_cowork.py`. Add tests to `tests/test_agent_cowork.py`.

**Interfaces:**
- **Produces:** `TerminalCoworkMixin._terminal_cowork_context_live() -> bool`, which returns `self._presence_app_category == "terminal"`.

**Acceptance Criteria:**
- **Characterization tests pass before any source edit, and still pass after it.** Use a `__new__` harness modelled on `tests/test_focus_context_recovery.py::_focused_buddy`, with state `IDLE` or `TYPING`, mocked `_play_animation`/`_transition_to`, and mocked timers via `monkeypatch.setattr(GLib, "timeout_add", …)`. Parametrize over `PresenceBuddy` and `PresenceX11Buddy`. Cases:
  1. Category `terminal` → `_schedule_terminal_coworking` arms one source.
  2. Terminal → `browser` → `_stop_terminal_coworking` is called.
  3. Intro finishes while live → loop; while not live → outro.
  4. Outro finishes while live → reopen; while not live → `_finish_terminal_outro`.
  5. Terminal → `vscode` with coworking active → the pending VS Code source is cancelled during the outro, and `_finish_terminal_outro` schedules VS Code coworking.
  6. `_on_typing_stopped` while `terminal` and `TYPING` keeps coworking.
  7. `_on_user_active` while `terminal` → schedules.
- **Every liveness check uses the predicate.** No literal `== "terminal"` / `!= "terminal"` liveness comparison remains in `terminal_cowork.py` outside `_terminal_cowork_context_live`. Check with a source-text test, allowing the `previous == "terminal"` check in the stop condition.
- **Stop condition.** In `_on_presence_app_category_changed` it becomes `not live and (previous == "terminal" or self._terminal_coworking_active)`.
- **No behavior change without agents.** All characterization tests are unchanged and green.

- [ ] **Step 1: Write the characterization tests and run them green** against unmodified code.
- [ ] **Step 2: Add the source-text predicate test and see it fail.**
- [ ] **Step 3: Refactor.** Introduce the predicate and replace the checks in:
  - `_on_presence_app_category_changed` (with the new stop condition)
  - `_on_user_active`, `_on_typing_stopped`
  - `_schedule_terminal_coworking`, `_begin_terminal_coworking`
  - both `_finish_reaction` branches
  - `_finish_terminal_outro` (the `elif self._presence_app_category == "terminal"` branch)
  - `_maybe_resume_terminal_coworking`
- [ ] **Step 4: Run the characterization tests, the predicate test, `tests/test_focus_context_recovery.py` and the full suite.**
- [ ] **Step 5: Commit.** `refactor(terminal): name the coworking liveness predicate`

---

### Task 5: `AgentCoworkMixin` and MRO

**Files:** Create `src/mochi/presence/agent_cowork.py`. Modify `src/mochi/presence/click_dialogue.py`. Add tests to `tests/test_agent_cowork.py`.

**Interfaces:**
- **Consumes:**
  - Tasks 1 and 4.
  - `IdleLookMixin._play_idle_beat(name) -> bool`
  - `ActiveWindowCuriosityMixin._curiosity_suppression() -> str | None`
  - `curiosity._boottime_seconds`
  - `TerminalCoworkMixin._schedule_terminal_coworking()` / `_stop_terminal_coworking()`
  - `self._ambient_presence_engine.emit(name)`
- **Produces:** `AgentCoworkMixin`, with:
  - `receive_agent_event(event, token)`
  - `_terminal_cowork_context_live()` (override)
  - `_agent_tick()`, `_apply_agent_edges(edges)`, `_try_agent_beat()`, `_cancel_agent_source()`
  - `shutdown_presence()`

**Acceptance Criteria:**
- **Class-level defaults** (so `__new__` harnesses work): `_agent_tracker = None`, `_agent_source_id = None`, `_agent_pending_beat = None`, `_agent_pending_beat_until = 0.0`.
- **Receiving events.**
  - `receive_agent_event` ignores events while `_presence_shutting_down` or `_preview_mode` is set.
  - It creates the tracker lazily, with `clock=_boottime_seconds`.
  - It records the event, applies the edges, and calls `_ensure_agent_source()`. That arms exactly one `GLib.timeout_add_seconds(1, self._agent_tick)` if none is armed.
- **Predicate.** `_terminal_cowork_context_live()` is `super()._terminal_cowork_context_live() or (self._presence_app_category != "vscode" and tracker is not None and tracker.working)`.
- **Applying edges.**
  - `WORK_STARTED` → `_schedule_terminal_coworking()`.
  - `WORK_STOPPED` → `_stop_terminal_coworking()` if not `_terminal_cowork_context_live()`.
  - `NEEDS_INPUT` → pending `wave` with TTL 30 s, plus `emit("agent_needs_input")`.
  - `FINISHED_LONG` → pending `excited` with TTL 30 s, plus `emit("agent_finished")`.
  - The latest pending beat replaces any earlier one.
- **Beats.** `_try_agent_beat()`:
  - It drops the beat when the TTL has passed.
  - Otherwise, if `_curiosity_suppression()` is `None` and `_play_idle_beat(name)` returns True, it clears the pending beat.
  - It runs at the end of every edge application and every tick.
- **Tick.** `_agent_tick()`:
  - It returns `SOURCE_REMOVE` and clears the id if shutting down.
  - It polls and applies edges, then tries the beat.
  - It keeps going while the tracker has sessions or a beat is pending; otherwise it clears the id and returns `SOURCE_REMOVE`.
- **Shutdown.** `shutdown_presence()` removes the source, clears the tracker and the pending beat, then calls `super()`.
- **MRO.** `AgentCoworkMixin` sits immediately before `TerminalCoworkMixin` in both `PresenceBuddy` and `PresenceX11Buddy`. A test asserts `mro.index(AgentCoworkMixin) + 1 == mro.index(TerminalCoworkMixin)` for both.

- [ ] **Step 1: Write the failing tests.** Use the Task 4 harness, plus mocked `_play_idle_beat`, `_curiosity_suppression` and `_ambient_presence_engine`, and a patched `_boottime_seconds` fake clock. Cover:
  - each edge mapping
  - the predicate with `browser`, `terminal` and `vscode`
  - beat retry, TTL expiry and suppression
  - the source created once and removed when there is no work
  - events after shutdown ignored
  - MRO for both classes
  - an end-to-end case: `working`, then the debounce fires, then intro → loop; then `finished` at 61 s → outro → idle → `excited` plays on the next tick
- [ ] **Step 2: Run and see them fail.**
- [ ] **Step 3: Implement** the mixin and the MRO insertion. Keep the docstring style of `curiosity.py`: purpose, privacy line, ownership of the source.
- [ ] **Step 4: Run the new tests, then `tests/test_active_window_curiosity.py`, `tests/test_idle_beats.py`, `tests/test_focus_context_recovery.py` and the full suite.**
- [ ] **Step 5: Commit.** `feat(agent): cowork, nudge, and celebrate with coding agents`

---

### Task 6: Engine events and phrases

**Files:** Modify `src/mochi/presence/engine.py`, `src/mochi/presence/phrases.py` and `tests/test_presence_engine.py`.

**Acceptance Criteria:**
- **Event tables.**
  - `_EVENT_PRIORITY["agent_needs_input"] == _EVENT_PRIORITY["agent_finished"] == 30`.
  - Both `_EVENT_CATEGORY` entries are `"agent"`.
- **Probability.** `PresenceTuning.agent_event_probability == 0.90`, and `_event_probability` returns it for both events.
- **Phrases.**
  - `EVENT_PHRASES` has 3 to 5 lines for each event, lowercase, with no urgency words ("now", "hurry", "!!") and no guilt.
  - Suggested `agent_needs_input` lines: "your agent's waiting on you", "psst. your agent has a question", "someone needs a yes or no 🌱", "your helper is waiting whenever you're ready".
  - Suggested `agent_finished` lines: "your agent finished!", "all done over there 🌱", "that was a long one. done!", "the agent wrapped up".
- **Behavior.**
  - With the RNG seeded to pass, each event yields a `PresenceAction` with priority 30 and category `"agent"`.
  - The Focus filter (priority under 40) rejects it.
  - Quiet mode suppresses it.

- [ ] **Steps:** failing tests → implement → pass → full suite → commit `feat(agent): presence lines for agent nudges and finishes`.

---

### Task 7: Install and uninstall the launcher

**Files:** Modify `install.sh`, `uninstall.sh` and `tests/test_installer.py`.

**Acceptance Criteria:**
- **`install.sh`.**
  - Defines `AGENT_SIGNAL_LAUNCHER="$BIN_DIR/mochi-agent-signal"`.
  - `install_integrations()` installs it right after the `mochi-update` launcher, with the same missing-binary `warn … return 1` guard.
- **`uninstall.sh`.** Defines `AGENT_SIGNAL_LAUNCHER="$HOME/.local/bin/mochi-agent-signal"` and adds it to the existing `rm -f` list.
- **`tests/test_installer.py`.**
  - Its fake virtual environments, which today create a `bin/mochi-update` stub at around lines 122–144 and 204, also create `bin/mochi-agent-signal`.
  - A new assertion checks the launcher exists after install and is gone after uninstall.
- `bash -n install.sh uninstall.sh` passes.

- [ ] **Steps:** failing installer test → implement → pass → full suite → commit `build(agent): install the mochi-agent-signal launcher`.

---

### Task 8: Documentation and QA watchlist

**Files:** Create `docs/agent-companion.md`. Modify `docs/ambisense.md`, `README.md`, `CHANGELOG.md` and `REGRESSION_WATCHLIST.md`.

**Acceptance Criteria:**
- **`docs/agent-companion.md`** contains:
  - what Mochi does
  - what crosses to Mochi and what never does
  - the Claude Code and Codex snippets, copied from the spec
  - "merge into your existing `hooks`"
  - the Codex `/hooks` trust step
  - how to turn it off (remove the hooks)
  - troubleshooting: a `gdbus call … org.gtk.Actions.List` reachability check, and checking for `~/.local/bin/mochi-agent-signal`
- **`docs/ambisense.md`** gets an "Agent Companion" section: the bridge, the hashed token, the same-user trust boundary, and the statement that it is not an LLM integration.
- **`README.md`** gets a feature bullet linking the doc.
- **`CHANGELOG.md`** gets a new `## Unreleased` → `### Added` entry in Mochi's voice, with the privacy claim inline.
- **`REGRESSION_WATCHLIST.md`** gets the new "Agent Companion" section with the spec's checkboxes.
- `git diff --check` is clean.

- [ ] **Steps:** write → proofread against the spec → commit `docs(agent): agent companion setup, privacy, and QA`.

---

### Task 9: Opt-in real-bus test, final verification, push, draft PR

**Files:** Create `tests/test_agent_dbus_integration.py`. It is skipped unless `MOCHI_RUN_DBUS_TESTS=1`, following `tests/test_helper_dbus_integration.py`.

**Acceptance Criteria:**
- **Opt-in test.**
  - It starts a probe `Gio.Application` with a unique test id and the same `agent-event` action, in a subprocess on the current session bus.
  - It runs `agent_signal.main(["working"], stdin=<pipe with a session_id payload>)` with `gdbus_command`'s destination patched to the probe id.
  - It asserts the probe received `("working", <expected token>)`.
  - It asserts that calling a non-existent destination returns 0 with no output.
- **Final checks.**
  - The full suite under `xvfb-run` is green. Report the exact summary against the 1145/3 baseline.
  - `python3 -m compileall -q src`, `bash -n install.sh uninstall.sh` and `git diff --check` all pass.
  - An adversarial self-review of the whole diff against AGENTS.md: privacy, speech path, teardown, no drive-by refactors.
- **Delivery.**
  - Push, then open a draft PR that follows `.github/pull_request_template.md`.
  - The PR lists the maintainer's manual QA steps from the spec and states that desktop QA was not run.

- [ ] **Steps:** opt-in test → run with `MOCHI_RUN_DBUS_TESTS=1 dbus-run-session -- …` → the full verification list → push → draft PR → report.
