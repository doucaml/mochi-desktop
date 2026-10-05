# Agent Companion — Design

**Date:** 2026-10-05

**Builds on:** terminal coworking (`src/mochi/presence/terminal_cowork.py`), the standing-idle beat owner (`src/mochi/presence/idle_look.py`), and the AmbiSense privacy model (`docs/ambisense.md`)

**Status:** design draft, awaiting maintainer approval. No implementation yet.

## Purpose

More and more of the coding on this desk is done by AI agents: Claude Code and OpenAI's Codex CLI running in a terminal. While an agent works, the person often waits, switches to something else, or misses the moment the agent stops to ask a question. Mochi already coworks when you sit at a terminal. He should also cowork while your agent does:
- he opens his laptop while it works,
- he waves once if it is stuck waiting on you,
- he does a small happy bounce when a long run finishes.

The agents talk to the cloud. Mochi does not. Each agent's own hook system tells Mochi one coarse lifecycle word, through a tiny local command. Mochi never sees a prompt, a file, a command, or a reply.

## Goals

- Mochi opens his laptop while any configured agent is working, and puts it away when they all stop.
- A gentle, one-time "needs you" nudge when an agent has waited on a permission prompt for a while. A prompt the user answers quickly stays invisible.
- A small celebration when a run that lasted at least a minute finishes. Quick chat turns stay quiet.
- Optional speech for the nudge and the celebration, routed through `PresenceEngine`.
- Support Claude Code and Codex through one bridge command.
- Hooks must not slow the agent down, and must never break it when Mochi is not running.

## Non-goals

- Calling any LLM API, chatting, or any network access by Mochi.
- Controlling agents: approving or denying permissions, sending input, cancelling runs. This is rejected for security. Any process on the session bus could otherwise approve tool calls.
- Reading prompts, transcripts, tool inputs, tool results, file paths, or assistant messages. Only a hashed session id crosses into Mochi.
- Judging success or failure. `Stop` does not say whether the task worked, so the unused `build_failed`/`build_succeeded` engine events stay unused.
- A distinct "supervising" look, or showing intensity when several agents run. v1 reuses the terminal laptop art.
- A settings toggle. Configuring the hooks is the opt-in; removing them is the opt-out. Quiet mode and ambient reactions still silence the nudge and celebration. Curiosity set the same precedent.
- Editing `~/.claude` or `~/.codex` configuration from Mochi or `install.sh`.
- A packaged Claude Code plugin or a `--print-config` helper (possible follow-ups).
- Codex's legacy `notify` setting. Codex hooks have been stable and on by default since 0.124. `notify` is marked for removal in the Codex source, can only report turn completion, passes its payload in argv, and needs an absolute path because it does not run through a shell.
- Telling the user, after they return from idle, that an agent was waiting while they were away.

## Behavior

### Signals

Each agent runs `mochi-agent-signal <event>` from its hooks. There are five events:

| Event | Claude Code hook | Codex hook (first release) | Meaning |
|---|---|---|---|
| `working` | `UserPromptSubmit` | `UserPromptSubmit` (0.116) | A turn started. |
| `activity` | `PostToolUse` | `PostToolUse` (0.117) | Still alive. After a permission prompt, this means the user answered. |
| `needs_input` | `PermissionRequest` | `PermissionRequest` (0.122) | The agent is about to ask the user for permission. |
| `finished` | `Stop` | `Stop` (0.114) | The turn ended normally. |
| `ended` | `SessionEnd` | `SessionEnd` (0.145), `Interrupt` (0.150) | The session closed (`/clear`, exit, logout, resume), or, in Codex, the user interrupted the turn. |

Facts about these hooks:
- **Claude Code `Stop`** does not fire when the user interrupts a turn, and Claude Code has no interrupt hook.
- **Claude Code `PermissionRequest`** fires only when a permission dialog is about to be shown, not for auto-allowed tools.
- **Codex `Interrupt`** maps to `ended`, so an interrupted Codex turn closes the laptop right away instead of waiting for stale cleanup.

Sources are under [Verified facts](#verified-facts).

### Session model

Mochi keeps a small in-memory record per agent session, keyed by an opaque token (see [Privacy](#signals-and-privacy)). A session is `WORKING` or `WAITING`. Finished or ended sessions are dropped.

| Event | Unknown session | `WORKING` session | `WAITING` session |
|---|---|---|---|
| `working` | Create `WORKING`; the run clock starts | Refresh | → `WORKING`; nudge cancelled |
| `activity` | **Ignored** (see the ordering edge case) | Refresh | → `WORKING`; nudge cancelled |
| `needs_input` | Create `WAITING` (a Mochi restart mid-run still gets a nudge) | → `WAITING`; the wait clock starts | Refresh |
| `finished` | Ignored | Drop; **celebrate** if the run lasted ≥ 60 s | Drop; no celebration (most likely a denial) |
| `ended` | Ignored | Drop; no celebration | Drop; no celebration |

Every event refreshes the session's last-seen time.

**When agents count as working.** Agents are working if any session is `WORKING`, or is `WAITING` and still inside its 10 s grace period. The grace period keeps the laptop from flickering shut and open on a quick approval.

**Edges.** The model reports four edges to the presentation layer:
- `WORK_STARTED`: agents become working (none → some).
- `WORK_STOPPED`: agents stop working (some → none). This includes grace expiry and stale cleanup.
- `NEEDS_INPUT`: a session's grace period expires while it is still `WAITING`. It fires at most once per wait.
- `FINISHED_LONG`: a celebrated finish.

**Stale cleanup.** A session with no events for 15 minutes is dropped without a celebration. This is the recovery path for interrupted Claude Code turns, crashed agents, and Codex releases older than `SessionEnd`/`Interrupt`. Fifteen minutes is long enough for a long test run that emits no events in between.

### Constants

| Constant | Value | Why |
|---|---|---|
| `NEEDS_INPUT_GRACE_SECONDS` | 10.0 | Answering within 10 s produces no nudge. Claude Code's own desktop notification waits about 6 s. |
| `CELEBRATE_MIN_RUN_SECONDS` | 60.0 | Quick back-and-forth turns stay quiet. |
| `SESSION_STALE_SECONDS` | 900.0 | Recovers interrupted turns without cutting off long tool runs. |
| `MAX_SESSIONS` | 16 | Keeps memory bounded. The least recently seen session is evicted. |
| `AGENT_POLL_INTERVAL_SECONDS` | 1 | Resolution for the grace period and beat retries. |
| `AGENT_BEAT_TTL_SECONDS` | 30.0 | A nudge or celebration that cannot play within 30 s is dropped, never replayed late. |

### Reactions

| Edge | Visual | Speech (`PresenceEngine` event) |
|---|---|---|
| `WORK_STARTED` | Terminal coworking: `terminal_intro` → `terminal_loop`, with the existing 700 ms debounce | none |
| `WORK_STOPPED` | `terminal_outro`, unless a focused terminal still holds the laptop | none |
| `NEEDS_INPUT` | One `wave` beat, once Mochi is standing idle | `agent_needs_input` |
| `FINISHED_LONG` | One `excited` beat (the existing copy of `bounce`), once Mochi is standing idle | `agent_finished` |

**Laptop.** Agent work is one more reason for terminal coworking to be live. Today coworking is live when the focused app category is `terminal`. It becomes live when the category is `terminal` **or** agents are working and VS Code is not focused. VS Code focus keeps its own coworking (see [VS Code focus while an agent works](#vs-code-focus-while-an-agent-works)). Agent coworking needs no GNOME helper: without AmbiSense the category stays unknown, and agents alone drive the laptop. Everything terminal coworking already does stays as it is:
- the debounce,
- video outranking coworking,
- the user-idle gate (Mochi does not cowork for an empty room; he resumes when the user comes back),
- the authored intro/outro reopening.

**Beats.** Beats play through `IdleLookMixin._play_idle_beat(name)`, the same path curiosity's `investigate` beat uses. It plays one non-looping animation while the behavior state stays `IDLE`, then resumes idle where it left off. `_play_idle_beat` refuses unless Mochi is visually standing idle. So a nudge that arrives during coworking waits while the outro closes the laptop, then plays. Mochi stops typing, closes the laptop, and waves. A pending beat is retried on each poll tick until it plays, is replaced by a newer beat, or its 30 s TTL runs out.

**Speech.** Speech goes through `PresenceEngine.emit()` with two new events:
- Both are priority 30 in a new `agent` category, which gets the ordinary per-category cooldown (90–240 s).
- Both are spoken with `agent_event_probability = 0.90`, the same as the build events.
- Priority 30 is below the Focus floor of 40, so agents never talk over a Focus session.
- The engine's existing gates also apply: speech toggle, quiet mode, ambient reactions, bubble visible, recently dismissed, media playing, user inactive, and the 5 s evaluation tick.
- Phrases are Mochi-authored `EVENT_PHRASES`, lowercase, gentle, and without urgency or guilt. For example: "your agent's waiting on you", "all done over there 🌱". No `markup=`.

### Suppression

**Laptop.** It follows terminal coworking's existing gates unchanged:
- Focus owns the visual (`FocusSessionMixin._start_typing_emote` redirects).
- Sleep blocks it through `can_transition`. Mochi is never woken for an agent.
- It also yields to direct interaction, the context menu, video, shutdown, and user idle.

**Beats.** They use the same rule set as curiosity, by calling `ActiveWindowCuriosityMixin._curiosity_suppression()`:
- preview, shutting down, user idle, context menu, drag, press
- a Focus session (work or thinking)
- a non-`NORMAL` presentation, sleeping
- ambient reactions off, quiet mode

The model keeps tracking while reactions are suppressed, so the laptop state is correct as soon as the suppression lifts.

### Interruption and recovery

- **Pressing, dragging or picking up Mochi during agent coworking** cancels the emote through the existing `_cancel_active_emote` path. Afterwards `_maybe_resume_ambient_activity` → `_maybe_resume_vscode_coworking` → `_maybe_resume_terminal_coworking` reopens the laptop, because the context is still live. No "previous animation" is stored (Manual §15).
- **A beat interrupted by a press** ends through `IdleLookMixin._play_animation`, which restores idle. The beat is not retried, because it was consumed when it started.
- **On shutdown,** the poll source is removed and the model and pending beat are cleared (Manual rule 4). Events that arrive after shutdown are ignored.
- **After a Mochi restart,** the model starts empty. The next `working` event, or a `needs_input`, rebuilds the state. A run already in progress is not reconstructed until then.

### VS Code focus while an agent works

Both terminal art and VS Code coworking claim `TYPING`. If both claimed the laptop at once, leaving VS Code would call `Buddy._on_typing_stopped` and play `typing_outro` over the terminal art.

The fix is to let VS Code focus win. The agent half of the liveness predicate excludes VS Code:

```
live = category == "terminal" or (agents_working and category != "vscode")
```

- **Moving from the terminal or a browser to VS Code while an agent works.** The context stops being live, so it takes today's path exactly: the terminal outro plays, then VS Code coworking takes over. `_stop_terminal_coworking` already cancels the pending VS Code timer while the laptop closes, and `_finish_terminal_outro` reschedules it. Mochi still looks busy, in VS Code's art.
- **Leaving VS Code for a browser while the agent still works.** The base VS Code stop runs as today. Then the resume chain (`_maybe_resume_vscode_coworking` → `_maybe_resume_terminal_coworking`) finds the context live again and reopens the laptop.
- **No change to VS Code code.** The only change on the terminal side is the stop condition in `_on_presence_app_category_changed`. Today it reads "left the terminal"; it becomes "no longer live, and either just left the terminal or coworking is active". With no agent running, that is the same as today.

## Signals and privacy

### What crosses into Mochi

The command `mochi-agent-signal` receives the hook payload on stdin. Both agents put `session_id` in every hook payload. The bridge parses only that field, then sends Mochi an `(event, token)` pair:
- `event` is one of the five allow-listed words.
- `token` is `sha256(f"{source}:{session_id}")` truncated to 16 lowercase hex characters. If no id is available, the token is the same hash of `f"{source}:default"`, so every token has one shape.

The prompt text, tool names, tool inputs, tool results, paths, cwd and assistant messages are never kept, logged, sent, or written anywhere. Mochi itself receives two short strings and nothing else.

### Transport

The transport is the `org.gtk.Actions` interface that GApplication already exports for a unique application. `MochiApplication` registers one app action, `agent-event`, with parameter type `(ss)`. The bridge calls:

```
gdbus call --session --timeout 1 \
  --dest io.github.mochi_desktop.Mochi \
  --object-path /io/github/mochi_desktop/Mochi \
  --method org.gtk.Actions.Activate agent-event "[<('working', '<token>')>]" "{}"
```

This was verified on a private session bus with a probe `Gio.Application` (GLib 2.80):
- **Not running:** `ServiceUnknown` in 11 ms. Mochi's `.desktop` file is not `DBusActivatable` and installs no D-Bus service file, so nothing launches.
- **Running:** `org.gtk.Actions.List` shows the action, and `Activate` reaches the handler in 8 ms.
- **Wrong type:** GLib rejects a mismatched parameter type with `InvalidArgs` before the handler runs.

The handler validates the event and token again before using them. This adds no bus name, socket, file watch, or teardown beyond the action itself.

**Trust boundary.** Any process running as the same user on the session bus can call this action. That is the same boundary Mochi already accepts for AmbiSense helper signals. The worst a caller can do is make Mochi open his laptop, wave, or bounce, and it is rate-limited by the session cap, the speech cooldowns and the beat TTL. The action cannot read anything, change settings, or reach the filesystem.

### The bridge never hurts the agent

- It **always exits 0** and **writes nothing to stdout or stderr**. Claude Code adds `UserPromptSubmit` and `SessionStart` hook stdout to the model's context, and exit code 2 would block the agent.
- It is stdlib only, with no `gi` import, so startup stays small. Hooks are configured with `"async": true` in Claude Code, so they run in the background and never block a turn.
- **Bad arguments.** Argument mistakes never reach `argparse`'s default error path, which prints usage to stderr and exits 2. The bridge parses its two arguments by hand, and anything unexpected is a silent no-op.
- **stdin.** It is read with a 0.5 s overall deadline, and only when it is not a TTY. A hook runner that never closes stdin cannot hang the bridge.
- **gdbus.** The call has a 1 s D-Bus timeout and a 1.5 s process timeout. A missing `gdbus`, a timeout, or an `OSError` is silently ignored.
- **Total time.** The worst case is about 2 s. Typical runs take tens of milliseconds, because Mochi answers in under 10 ms. This matters for Codex `SessionEnd` and `Interrupt`, which always run synchronously with a 1 s default timeout (3 s maximum), so the setup snippet sets `"timeout": 3` on them.

### Rejected alternatives

| Alternative | Why not |
|---|---|
| Mochi calls the Claude/OpenAI APIs | Breaks "local only, no network" and the roadmap's "no AI/chat systems". |
| Two-way control (approve from Mochi) | Any session-bus process could approve tool calls. |
| Mochi exports its own D-Bus interface | More code and lifecycle work for the same result as one GAction. |
| Unix socket or a watched file | A new IPC surface with its own permissions, cleanup and teardown. |
| Detecting agents by scanning `/proc` or terminal titles | Privacy-adjacent, brittle, and against AmbiSense's title boundary. |
| Claude Code mods (JavaScript) | Claude-only. Command hooks share one shape with Codex. |
| The bridge sends nothing (one hook command per event, stdin unread) | Simplest privacy story, but two parallel agents would trample each other's state. Hashing the one id keeps sessions apart without exposing content. |
| Claude `Notification` (`permission_prompt`) instead of `PermissionRequest` | Claude-only, and it has its own ~6 s delay. `PermissionRequest` matches Codex, and Mochi applies one grace rule for both. |

## Agent setup

Mochi never edits these files. The README links `docs/agent-companion.md`, which carries copy-paste snippets.

### Claude Code (`~/.claude/settings.json`)

```json
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" working", "async": true}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" activity", "async": true}]}],
    "Notification": [{"matcher": "permission_prompt", "hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" prompt_waiting", "async": true}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" finished", "async": true}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" ended", "async": true}]}]
  }
}
```

The command uses the absolute launcher path, because a hook's `PATH` may not include `~/.local/bin`. The docs page tells users to merge this into an existing `hooks` object rather than replace it.

### Codex (`~/.codex/hooks.json`, Codex 0.124 or newer)

```json
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" working --source codex", "async": true}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" activity --source codex", "async": true}]}],
    "PermissionRequest": [{"matcher": "*", "hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" needs_input --source codex", "async": true}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" finished --source codex", "async": true}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" ended --source codex", "timeout": 3}]}],
    "Interrupt": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" ended --source codex", "timeout": 3}]}]
  }
}
```

Notes for `docs/agent-companion.md`:
- **No feature flag needed.** Hooks are stable and on by default (`[features] hooks`, legacy alias `codex_hooks`).
- **Hook trust.** Since 0.129, Codex runs user hooks only after the user trusts them in the `/hooks` review. Editing a trusted hook requires trusting it again. The docs must say this, or the setup will look broken.
- **Older releases.** One snippet works on every supported release. Codex ignores event names it does not know: `HookEventsToml` has no `deny_unknown_fields` in either 0.124.0 or 0.160.1. Releases before 0.145 or 0.150 just skip `SessionEnd`/`Interrupt`, and stale cleanup covers them.
- **Shape.** `hooks.json` accepts only the `description` and `hooks` top-level keys, and the `command` string runs through `$SHELL -lc`.

## Verified facts

Everything this design depends on outside Mochi was checked on 2026-10-05:

| Fact | Evidence |
|---|---|
| Claude Code `Stop` does not fire on user interrupts | Hooks guide: "Stop hooks fire whenever Claude finishes responding… They don't fire on user interrupts." (code.claude.com/docs/en/hooks-guide) |
| Claude Code `PermissionRequest` fires only before a real dialog | Hooks guide: "fire when Claude Code is about to ask you for permission, or when it would otherwise auto-deny a call that can't prompt." |
| Every Claude Code hook payload has `session_id` | Hooks guide ("Every event includes common fields like `session_id`…") and the per-event schemas in the hooks reference. |
| Claude Code `"async": true` runs a command hook in the background without blocking | Hooks reference, command hook fields. |
| Claude Code adds `UserPromptSubmit`/`SessionStart` stdout to model context | Hooks guide: "For `UserPromptSubmit`, `UserPromptExpansion`, `SessionStart`, and `PostModelSwitch` hooks, Claude Code adds stdout… to Claude's context." |
| Claude Code `SessionEnd` reasons | `clear`, `resume`, `logout`, `prompt_input_exit`, `other` (hooks guide). |
| Codex hooks are stable and on by default; key `hooks`, alias `codex_hooks` | openai/codex `codex-rs/features/src/lib.rs` (`Stage::Stable`, `default_enabled: true`) at commit `7c2ce907`; graduated in 0.124.0. |
| Codex event names and first releases | `codex-rs/config/src/hook_config.rs` `HookEventsToml`; the releases come from `git tag --contains` on the introducing commits. |
| Codex hook stdin carries `session_id`; `command` runs via `$SHELL -lc`; `async` exists; `SessionEnd`/`Interrupt` are synchronous with a 1 s default and 3 s maximum timeout | `codex-rs/hooks/src/schema.rs`, `engine/command_runner.rs`, `engine/discovery.rs`, `events/session_end.rs`. |
| Codex user hooks need trust since 0.129 | `codex-rs/hooks/src/engine/discovery.rs` (trusted hash in `[hooks.state]`). |
| Codex ignores unknown event names | No `deny_unknown_fields` on `HookEventsToml` at 0.124.0 or at 0.160.1. |
| A unique GApplication exports app actions over `org.gtk.Actions`; `gdbus call` fails fast and launches nothing when the app is absent; GLib type-checks the parameter | A probe `Gio.Application` on a private `dbus-run-session` bus with GLib 2.80: `List` → `(['agent-event'],)`; `Activate` delivered in 8 ms; absent app → `ServiceUnknown` in 11 ms; wrong type → `InvalidArgs`. |
| A one-shot beat that keeps `IDLE` already exists | `IdleLookMixin._play_idle_beat(name)` (`src/mochi/presence/idle_look.py`), used by curiosity's `investigate`. |

The developers.openai.com docs could not be fetched from the authoring environment, so Codex facts come from the source. Release numbers are "the first tag containing the change", not checked against release notes.

## Architecture

```
agent hook ─▶ mochi-agent-signal (src/mochi/agent_signal.py; stdlib only)
                │ event allow-list + hashed token; silent; exit 0
                ▼  gdbus → org.gtk.Actions.Activate("agent-event", (event, token))
MochiApplication action "agent-event" (src/mochi/app.py) ── validates ──▶ buddy.receive_agent_event()
                ▼
AgentCoworkMixin (src/mochi/presence/agent_cowork.py)
   owns AgentActivityTracker (src/mochi/agent_activity.py; pure, GTK-free)
   owns one GLib poll source while sessions or a beat are pending
   ├─ WORK_STARTED / WORK_STOPPED ─▶ TerminalCoworkMixin liveness (laptop)
   ├─ NEEDS_INPUT / FINISHED_LONG ─▶ pending beat → IdleLookMixin._play_idle_beat
   └─ NEEDS_INPUT / FINISHED_LONG ─▶ PresenceEngine.emit("agent_needs_input" | "agent_finished")
```

### `src/mochi/agent_activity.py` (new, pure)

- `AGENT_EVENTS = frozenset({"working", "activity", "needs_input", "finished", "ended"})` is the single allow-list. The bridge and the app action both import it.
- `AGENT_TOKEN_PATTERN = re.compile(r"[0-9a-f]{16}")`, used with `fullmatch`.
- `class AgentEdge(Enum)`: `WORK_STARTED`, `WORK_STOPPED`, `NEEDS_INPUT`, `FINISHED_LONG`.
- `class AgentActivityTracker(*, clock: Callable[[], float] = time.monotonic)`:
  - `record(event: str, token: str) -> list[AgentEdge]`
  - `poll() -> list[AgentEdge]`: grace expiry and stale cleanup
  - `working -> bool`, `has_sessions -> bool`, `clear() -> None`
- The constants from [Constants](#constants) are class attributes.
- Edges are computed by comparing the current "working" answer against the last reported one, so time-based changes from `poll()` and event-based changes from `record()` share one rule.
- Unknown events and malformed tokens are ignored and return `[]`.
- The module imports nothing from `gi`, `cairo`, or `mochi.presence`.

### `src/mochi/agent_signal.py` (new, console script `mochi-agent-signal`)

- `main(argv=None, *, stdin=None, run=subprocess.run, which=shutil.which, stdin_deadline_seconds=0.5) -> int` always returns 0. The injection follows `update_cli.main`'s style for tests.
- Arguments are parsed by hand, with no `argparse`, so a mistake can never print usage or exit 2:
  - `argv[0]` is the event.
  - An optional `--source claude|codex` defaults to `claude`.
  - Anything else makes the call a silent no-op.
- Steps:
  1. Validate the event against `AGENT_EVENTS`.
  2. Read stdin under the deadline if it is not a TTY.
  3. Parse JSON and take `session_id` if it is a non-empty string.
  4. Hash `source:session_id` into a token.
  5. Run `gdbus` with `stdin`, `stdout` and `stderr` set to `DEVNULL`.
- Every exception is swallowed. The whole body is one `try/except Exception`.
- The module imports only the stdlib and `mochi.agent_activity`. `mochi/__init__.py` holds only `__version__`, so the console script never loads `gi`.

### `src/mochi/app.py`

- `MochiApplication.__init__` registers `Gio.SimpleAction.new("agent-event", GLib.VariantType.new("(ss)"))`, unless `preview_animations` is set (the preview id is not the one the bridge targets).
- `_on_agent_event_action(action, parameter)` unpacks the pair and re-validates it with `AGENT_EVENTS` and `AGENT_TOKEN_PATTERN`. It forwards to `self._buddy.receive_agent_event(event, token)` when a buddy exists. Otherwise it does nothing.

### `src/mochi/presence/agent_cowork.py` (new, `AgentCoworkMixin`)

- Class-level defaults: `_agent_tracker = None`, `_agent_source_id = None`, `_agent_pending_beat = None`, `_agent_pending_beat_until = 0.0`. These follow curiosity's pattern, so `__new__`-built test buddies work.
- `receive_agent_event(event, token)`:
  - Ignored while shutting down or in preview.
  - Lazily creates the tracker with curiosity's `_boottime_seconds` clock, which keeps counting through suspend, so stale cleanup works after an overnight sleep.
  - Records the event, applies the edges, and ensures the poll source.
- `_terminal_cowork_context_live()` overrides the terminal predicate with `super()._terminal_cowork_context_live() or (self._presence_app_category != "vscode" and tracker.working)`.
- `_agent_tick()`:
  - polls the tracker and applies the edges,
  - retries or expires the pending beat,
  - returns `SOURCE_REMOVE` and clears the id once there are no sessions and no pending beat.
- `shutdown_presence()` removes the source, clears the tracker and the pending beat, then calls `super()`.
- Edge application:
  - `WORK_STARTED` → `_schedule_terminal_coworking()`.
  - `WORK_STOPPED` → `_stop_terminal_coworking()` if the context is no longer live.
  - `NEEDS_INPUT` / `FINISHED_LONG` → set the pending beat (`wave` / `excited`, TTL 30 s) and call `self._ambient_presence_engine.emit(...)`.

### `src/mochi/presence/terminal_cowork.py`

- Adds `_terminal_cowork_context_live() -> bool`, returning `self._presence_app_category == "terminal"`.
- Every inline `== "terminal"` / `!= "terminal"` liveness check uses it:
  - `_on_presence_app_category_changed`: the stop is skipped while the context is still live.
  - `_on_user_active`, `_on_typing_stopped`.
  - `_schedule_terminal_coworking`, `_begin_terminal_coworking`.
  - Both branches of `_finish_reaction`.
  - `_finish_terminal_outro`, `_maybe_resume_terminal_coworking`.
- The stop condition in `_on_presence_app_category_changed` becomes `not live and (previous == "terminal" or self._terminal_coworking_active)`. See [VS Code focus while an agent works](#vs-code-focus-while-an-agent-works).
- No other behavior change.

### `src/mochi/presence/click_dialogue.py`

`AgentCoworkMixin` is inserted immediately before `TerminalCoworkMixin` in both `PresenceBuddy` and `PresenceX11Buddy`. It must come first in the MRO for its predicate override to win. It sits below Focus and Fedora, matching the contextual recovery priority (Focus → Fedora → terminal/agent → VS Code → video → …).

### `src/mochi/presence/engine.py` and `phrases.py`

- `_EVENT_PRIORITY`: `"agent_needs_input": 30`, `"agent_finished": 30`.
- `_EVENT_CATEGORY`: both map to `"agent"`.
- `PresenceTuning.agent_event_probability: float = 0.90`, plus a branch in `_event_probability`.
- `EVENT_PHRASES["agent_needs_input"]` and `EVENT_PHRASES["agent_finished"]`.

### Packaging

- `pyproject.toml` `[project.scripts]`: `mochi-agent-signal = "mochi.agent_signal:main"`.
- `install.sh`:
  - Add `AGENT_SIGNAL_LAUNCHER="$BIN_DIR/mochi-agent-signal"`.
  - Call `install_launcher "$AGENT_SIGNAL_LAUNCHER" "$VENV/bin/mochi-agent-signal"` inside `install_integrations()`, right after the `mochi-update` launcher, with the same missing-binary guard.
  - The updater already runs `install.sh --refresh-integrations` from the new source tree (`src/mochi/update/worker.py`), so existing installs get the launcher through a normal update. The updater code itself is not touched.
- `uninstall.sh`: add `AGENT_SIGNAL_LAUNCHER="$HOME/.local/bin/mochi-agent-signal"` to the existing `rm -f` launcher list.
- `tests/test_installer.py`: its fake virtual environments create `bin/mochi-update` by hand, so they also need a `bin/mochi-agent-signal` stub. Add an assertion that the launcher is installed and removed.

## Edge cases

| Case | Behavior |
|---|---|
| Mochi is not running | The bridge's `gdbus` call fails in about 10 ms; it exits 0 silently. With `async` hooks, Claude Code is never blocked. |
| `gdbus` is not installed | `which` finds nothing, and the bridge exits 0. `gdbus` ships in Fedora's `glib2`. |
| A huge prompt on stdin | It is read and discarded under the deadline. Only `session_id` is taken. |
| stdin never closes | The 1 s deadline, then the default token. |
| Async hooks arrive out of order (`activity` after `finished`) | `activity` never creates a session, so a late `activity` cannot reopen the laptop. |
| The user interrupts a turn (no `Stop`) | The laptop stays open until the next event or the 15-minute stale cleanup. That cleanup is silent. |
| Two agents in parallel | Separate tokens. The laptop stays open until both stop. Each long finish may celebrate, limited by the engine cooldown and the latest-wins beat. |
| Permission approved within 10 s | `activity` cancels the wait. No nudge, and the laptop never closed. |
| Permission denied | `finished` from a `WAITING` session: no celebration. |
| Nudge while Mochi is asleep, in Focus, quiet mode, or in a menu | The beat waits or is dropped after its TTL. Speech is governed by the engine gates. Mochi is never woken. |
| Agent working while the user is idle (away) | No coworking for an empty room. The existing idle gate applies, and Mochi may nap. It reopens on return if the agent is still working. |
| Terminal focused, and the agent finishes | The laptop stays open (the terminal still holds it). The celebration waits for idle, which may never come while in the terminal; it is dropped after 30 s. |
| Video starts while the agent works | Video outranks coworking (existing rule). The laptop resumes after video if the agent is still working. |
| Spoofed events from another same-user process | Bounded harmless animations. Validated words, a session cap, cooldowns. |
| More than 16 sessions | The least recently seen session is evicted. The edges stay consistent. |
| Suspend mid-run | The boottime clock advances during suspend, so a stale run is cleaned up on resume. |
| Codex hooks added but not yet trusted | Codex skips them, so Mochi gets nothing. `docs/agent-companion.md` leads its troubleshooting with the `/hooks` trust step. |
| Codex `SessionEnd`/`Interrupt` (always synchronous) while Mochi is not running | The `gdbus` call fails in about 10 ms, well under the 3 s timeout in the snippet. |
| Codex runs hooks with a rebuilt environment | Codex clears the environment, then replays the session snapshot minus its own credential variables (`command_runner.rs`, `shell_environment.rs`). `DBUS_SESSION_BUS_ADDRESS` survives, so the bridge passes the environment through untouched. |

## Testing

All new behavior is covered by display-free tests. The ones that build buddies follow `tests/test_focus_context_recovery.py`: a `__new__` buddy with mocked collaborators, parametrized over `PresenceBuddy` and `PresenceX11Buddy`.

**Tracker (`tests/test_agent_activity.py`, pure):**
1. `working` on an empty tracker → `WORK_STARTED`. A second session adds no edge.
2. `finished` after ≥ 60 s → `[WORK_STOPPED, FINISHED_LONG]`. Under 60 s → `[WORK_STOPPED]` only.
3. `needs_input` then `activity` within 10 s: no edges at all, and still working throughout.
4. `needs_input` with no reply: `poll()` at 10 s → `NEEDS_INPUT` (and `WORK_STOPPED` if it was the only session). Later polls do not repeat `NEEDS_INPUT`.
5. A late approval (`activity` after the nudge) → `WORK_STARTED` again. A second wait can nudge again.
6. `finished` from `WAITING` → no `FINISHED_LONG`.
7. `ended` → no celebration. `activity` or `finished` for an unknown token → `[]`.
8. Stale: no events for 900 s → `poll()` drops the session with `WORK_STOPPED` and no celebration.
9. Unknown events and malformed tokens → `[]`, with no state change.
10. Session cap: the 17th token evicts the least recently seen, and the edges stay consistent.
11. The module source imports no `gi`, `cairo` or `mochi.presence` (source-text assertion).

**Bridge (`tests/test_agent_signal.py`, pure):**
1. A valid event calls `run` once with the exact `gdbus` argv, `DEVNULL` streams and a timeout.
2. An unknown event → `run` is not called, and the exit is 0.
3. The token is `sha256("claude:<id>")[:16]`. `--source codex` changes it. Missing or invalid JSON → the default-id hash.
4. Only `session_id` influences the argv: two payloads that differ in every other field produce identical argv.
5. Bad argv (none, an unknown flag, an unknown source, extra words) → `run` is not called, the exit is 0, and nothing is printed.
6. `which` returns `None`, or `run` raises `FileNotFoundError`, `TimeoutExpired` or `OSError` → exit 0.
7. **Nothing is written to stdout or stderr** in any case above (`capsys`).
8. Reading stdin respects the deadline. A stdin that never closes still returns within the deadline (fake stream).

**App action (`tests/test_agent_cowork.py`, or the existing app tests if they fit):**
1. The action is registered with type `(ss)` and is absent in preview mode.
2. A valid pair forwards to `receive_agent_event`. An invalid event or token, or no buddy, does nothing.

**Mixin (`tests/test_agent_cowork.py`):**
1. `WORK_STARTED` schedules terminal coworking, and the live predicate is true with category `browser`.
2. `WORK_STOPPED` with category `terminal` does not stop coworking. With category `browser`, it calls `_stop_terminal_coworking`.
3. `NEEDS_INPUT` sets the pending `wave` and emits `agent_needs_input`. The beat plays through `_play_idle_beat` on the next tick once idle, and expires after 30 s otherwise.
4. Beats respect `_curiosity_suppression()`: quiet mode, Focus, sleep and menu.
5. The poll source is created once and removed when there are no sessions and no pending beat. `shutdown_presence` removes it, and events after shutdown are ignored.
6. MRO: `AgentCoworkMixin` precedes `TerminalCoworkMixin`, which precedes `FedoraModeMixin`'s successors. Both buddy classes are checked.

**Terminal characterization, written before the refactor:**
1. Category `terminal` → coworking schedules; leaving to `browser` → `_stop_terminal_coworking`.
2. The intro finishing with the context live → loop; not live → outro.
3. The outro finishing with the context live → reopen; not live → `_finish_terminal_outro`.
4. Terminal → VS Code (no agent): the terminal stop runs, the pending VS Code timer is cancelled during the outro, and VS Code coworking is scheduled after it. This pins today's handoff.
5. With agents working: terminal → browser keeps the laptop; browser → VS Code stops terminal coworking (the handoff from item 4); VS Code → browser resumes the laptop through `_maybe_resume_terminal_coworking`.

**Engine (`tests/test_presence_engine.py`):**
1. Both new events are accepted, map to the `agent` category, and use `agent_event_probability`.
2. They are filtered during Focus (priority 30 < floor 40).
3. Quiet mode suppresses them.

**Opt-in real bus (`MOCHI_RUN_DBUS_TESTS=1`):** a probe `Gio.Application` with the same action, called through the real bridge `main()`. It asserts delivery, and asserts that a missing app causes no error.

Live desktop behavior is verified by the maintainer's Fedora QA (below). Automated tests cannot run GNOME.

## Documentation

- `docs/agent-companion.md` (new): what it does, privacy (what crosses, what never does), Claude Code and Codex setup snippets, how to turn it off, troubleshooting (a `gdbus call` to check that Mochi is reachable).
- `docs/ambisense.md`: a short "Agent Companion" section on the bridge, the hashed token and the trust boundary.
- `README.md`: a "Cowork with your coding agent" bullet in the feature list linking the doc.
- `CHANGELOG.md`: create `## Unreleased` → Added: "Mochi coworks with Claude Code and Codex…", in Mochi's voice, with the privacy claim inline.
- `REGRESSION_WATCHLIST.md`: a new "Agent Companion" section with checkboxes (below).

New watchlist items:

- [ ] Agent work opens the laptop once and does not replay on repeated `working` or `activity` events.
- [ ] The laptop stays open while any agent works and closes when the last one stops.
- [ ] A quick permission approval (< 10 s) produces no wave and no flicker.
- [ ] A long-waiting permission prompt produces one wave and at most one line, and never repeats for the same wait.
- [ ] Only runs ≥ 60 s celebrate. Denials and `/clear` do not.
- [ ] Interrupted turns recover on the next prompt or after 15 minutes. No stuck laptop.
- [ ] Focus, sleep, quiet mode, ambient reactions off, menu and drag behave as for curiosity. Mochi is never woken for an agent.
- [ ] Terminal → VS Code → browser while an agent works: laptop closes, VS Code coworking takes over, laptop returns. `typing_outro` never plays over terminal art.
- [ ] With Mochi not running, agent hooks produce no errors or delay.
- [ ] No agent events are handled after Mochi stops.

## Delivery

- Branch `claude/agent-companion-spec`, cut from `main`, with a draft PR that holds this spec and its plan. Implementation starts only after approval, and continues on the same branch.
- Implementation follows the plan test-first, in small commits.
- The maintainer's live Fedora GNOME QA:
  1. Configure the Claude Code hooks, then run a prompt that takes over a minute: the laptop opens within about 1 s, and Mochi bounces when it finishes.
  2. Trigger a permission prompt and wait over 10 s: the laptop closes, Mochi waves, and says at most one line. Approve quickly instead: nothing.
  3. Run two sessions at once: the laptop stays open until both finish.
  4. Press Esc mid-run: the next prompt or 15 minutes recovers.
  5. Quit Mochi and use Claude Code: no errors, no delay.
  6. Repeat under Focus, quiet mode, and a sleeping Mochi.
  7. Drag Mochi during agent coworking: the laptop comes back.
  8. Codex: add the hooks, trust them in `/hooks`, and repeat steps 1, 2 and 4. Step 4 uses Ctrl+C, which should close the laptop right away through `Interrupt`.

## Risks

- **Hook APIs move.** Codex hooks are experimental, and Claude Code's hook surface evolves. The bridge depends only on event names, `session_id` and argv, and fails silently. The docs pin the versions that were verified.
- **The terminal predicate refactor touches a proven sequence.** Mitigated by characterization tests written first, and by a one-predicate change with no new state.
- **The stop-condition change.** It is the only change to existing behavior beyond the liveness predicate. Characterization tests pin today's terminal → VS Code handoff before it is touched.
- **Async ordering.** It is handled by "only `working` or `needs_input` creates a session". A rare misordering can at worst leave a stale laptop for 15 minutes.
- **Spoofing on the session bus.** Bounded and harmless (see [Transport](#transport)).
- **Setup friction.** Hand-merging JSON into two agents' configs, plus Codex's trust step, is the most likely way this feature "doesn't work". The docs carry exact snippets and a one-line `gdbus` reachability check. A packaged Claude Code plugin is the natural follow-up if this proves painful.
