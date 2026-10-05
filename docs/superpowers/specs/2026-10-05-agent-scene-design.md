# Agent Scene — Design

**Date:** 2026-10-05

**Builds on:** Agent Companion (`docs/superpowers/specs/2026-10-05-agent-companion-design.md`, #176), terminal coworking (`src/mochi/presence/terminal_cowork.py`), and the canonical-overlay build pattern of `tools/build_reading.py`

**Status:** design draft, awaiting maintainer approval. The art below is a draft for the maintainer to clean up in Pixelorama.

![Draft agent scene](media/2026-10-05-agent-scene-draft.gif)

## Purpose

Agent Companion v1 shows a working agent with Mochi's terminal laptop, the same art as "you're in a terminal". The maintainer asked for a scene of its own, so the two read differently:
- **Your work:** Mochi types at his laptop.
- **The agent's work:** Mochi sits back with a mug while a little monitor beside him scrolls code. He is keeping it company; he isn't doing the work.

## Goals

- Three new animations: `agent_intro`, `agent_loop` and `agent_outro`.
- They are built from **untouched canonical Mochi frames** plus one new prop, so Mochi cannot drift off-model.
- While agents work, the coworking sequence plays the agent scene instead of the laptop. It keeps every existing gate, interruption and recovery path.
- Swaps between the two scenes go through authored outro → intro transitions, never a frame pop.
- Quick back-and-forth turns in a terminal don't flicker between the scenes.

## Non-goals

- Separate "waiting for you" art. The `wave` beat stays the nudge.
- Any change to VS Code coworking, Focus, Fedora, beats, speech or the tracker.
- A new `MochiState`. The scene runs in the same `TYPING` slot as the laptop, as v1 does.
- Showing intensity when several agents run.
- Changing or retiring the terminal laptop art.

## The scene

All frames are 256×256 RGBA, anchored bottom-center, and drawn on Mochi's 4 px grid: 64-cell art shown ×4, like `coffee` and `terminal`. All three animations play at 8.33 fps, matching the terminal set.

| Animation | Frames | Mochi | Monitor |
|---|---|---|---|
| `agent_intro` | 7 | `coffee` 1 → 7: he picks up his mug and closes his eyes | Rises from below the bottom edge in whole grid steps (`hidden, hidden, 16, 9, 4, 1, 0` grid px below rest), and boots on the last frame |
| `agent_loop` | 18 | `coffee` 8 → 16, twice: an eyes-closed sip | At rest. Code scrolls up one line every two frames, and the bottom line types in with a cursor block |
| `agent_outro` | 5 | `coffee` 17 → 21: he puts the mug away | Screen off; it sinks (`0, 2, 6, 13, hidden`) |

**Seams:**
- The first intro frame and the last outro frame both have exactly the idle silhouette. `coffee` 1 and 21 match `idle_01`, and the monitor is fully hidden in both. So entering from idle and returning to idle never pops; the terminal set has the same check.
- The loop seam is `coffee` 16 → 8, both eyes-closed holds. The code cycle is 9 lines over 18 frames, so the screen is seamless too.

**The monitor prop:**
- **Size:** 24×22 grid px (96×88 on screen), resting at the bottom-right, 4 px above the bottom edge. It overlaps Mochi's side below eye level, like the laptop overlaps his front.
- **Palette:** five colors, keyed and cropped from the draft:
  - outline and screen `#021d0a`
  - casing `#a1a7c6` / `#ccceee` / `#eff1fa`
  - code `#67f760`
- **Screen:** the interior is grid rows 3–12 and columns 4–19. Code rows are 5, 7, 9 and 11, starting at column 6, with at most 12 columns.

**Provenance:**
- The prop was drafted with PixelEngine (`oai_gpt25_high`, style-referenced to `terminal_05.png`; jobs `17c83bfe…` and `c829ff79…`; 24 credits).
- It was then keyed: the magenta matte plus the near-magenta fringe were removed, leaving 5 colors.
- It was cropped and transcribed into the builder as palette art, the way `build_reading.py` carries its `BOOK`.
- No AI output touches Mochi himself.

**Builder:** `tools/build_agent_scene.py`.
- It reads the canonical `coffee` frames and writes `assets/mochi/agent/agent_{intro,loop,outro}_NN.png`.
- It is deterministic. Like the other `tools/` scripts it uses Pillow as a dev-only tool, never a runtime dependency.
- **The committed PNGs are the source of truth.** Once the maintainer hand-cleans frames in Pixelorama, the builder is only a record of the draft. Its docstring says so, and it refuses to overwrite existing frames without `--force`.

## Behavior: two costumes on one coworking sequence

The coworking sequence (intro → loop → outro on `TYPING`) wears one of two costumes:
- **`terminal`**: the laptop, as today.
- **`agent`**: the monitor scene.

**Choosing a costume.** The costume is chosen when an intro starts, and kept until that sequence's outro finishes. One open-close cycle never mixes art.

**Which costume an intro picks:**
- `agent` if agents are working. VS Code focus is already outside agent liveness, so VS Code keeps its own coworking.
- Otherwise `terminal`.

**Swaps.** Each swap uses the existing outro → reopen path.

| Situation | What plays |
|---|---|
| The laptop is open (you're in a terminal) and agents have worked for **≥ 5 s** (`AGENT_SCENE_SWAP_DELAY_SECONDS`) | Laptop outro → agent intro |
| An agent scene is open, all agents stop, and the terminal is still focused | Agent outro → laptop intro |
| An agent scene is open, all agents stop, and no terminal is focused | Agent outro → idle (as in v1) |
| You focus a terminal while the agent scene is up | No change; the agent scene stays |

**The 5 s delay.** It only matters when the laptop is already open. Chatting with an agent in a terminal means many short turns, and swapping on each would churn. A turn that finishes within 5 s never swaps. Away from a terminal the agent scene opens immediately, because agents are the only reason anything is live.

**What doesn't change:** debounce, video priority, the user-idle gate, sleep (never woken), Focus ownership, direct-interaction recovery, beats, speech, bond XP handling and VS Code exclusion. All of it works exactly as in #176, because the costume only changes which three animation names the sequence plays.

## Architecture

### `src/mochi/presence/terminal_cowork.py`

- **Costume tables.**
  - `COWORK_COSTUMES = {"terminal": ("terminal_intro", "terminal_loop", "terminal_outro")}`.
  - `_cowork_costume: str = "terminal"`, a class-level default.
  - `_cowork_costume_for_context() -> str` returns `"terminal"`. Subclasses override it.
- **Costume-aware playback.**
  - `_play_terminal_intro()` picks the costume with `_cowork_costume_for_context()` and stores it.
  - `_play_terminal_loop()` and `_play_terminal_outro()` play the stored costume's names.
- **Comparisons.** Every comparison against `TERMINAL_INTRO/LOOP/OUTRO_ANIMATION` becomes a role check on the current costume's names. These live in `_begin_terminal_coworking`, both `_finish_reaction` branches, `_stop_terminal_coworking` and `_start_watching_emote`.
  - Helper `_cowork_role(name) -> "intro" | "loop" | "outro" | None` looks the name up in **every** costume, so a stale costume never strands a sequence.
- **Constants.** The existing `TERMINAL_*_ANIMATION` constants stay as the `terminal` costume's names.
- **Equivalence.** Without agents the behavior is byte-for-byte the same. The #176 characterization tests pin it, and they must stay green unchanged.

### `src/mochi/presence/agent_cowork.py`

- **Registration.** It registers `COWORK_COSTUMES["agent"] = ("agent_intro", "agent_loop", "agent_outro")` as a class attribute merged with the base table; it does not mutate the base class.
- **Costume choice.** `_cowork_costume_for_context()` returns `"agent"` when `tracker.working` and the category is not `vscode`. Otherwise it defers to `super()`.
- **Swap requests.** `_maybe_swap_cowork_costume()` runs on every edge application and poll tick. When the sequence is open on the loop, the stored costume differs from the wanted one, and the 5 s rule allows it, it asks the sequence to swap. A swap plays the current outro and leaves `_terminal_coworking_active` true, so the outro-finish path reopens with the new costume.
- **Timing.** `_agent_work_started_at` is set on `WORK_STARTED` and cleared on `WORK_STOPPED`, using the mixin's boottime clock.
- **Existing checks.** `_TERMINAL_ART`, used by the typing-stop rule from #176, now covers both costumes.

### Assets and packaging

- **Assets:** `assets/mochi/agent/` holds 30 PNGs.
- **Manifest:** `assets/mochi/manifest.json` gets three entries in the `terminal_*` frame-list shape (`frames`, `frame_count`, `fps: 8.333333333333334`, `loop`).
- **Packaging:** `pyproject.toml` gets `"share/mochi/agent" = ["assets/mochi/agent/*.png"]`.
- **No `sprites.py` changes.** No derived animations are needed.

## Edge cases

| Case | Behavior |
|---|---|
| An agent starts during the laptop intro | The intro finishes. The swap waits for the loop, then laptop outro → agent intro once 5 s have passed. |
| Agents stop during the agent intro | The intro finishes, then the agent outro plays. This uses the existing "left during intro" rule. |
| Agents start and stop within 5 s while the laptop is open | No swap. |
| The user drags Mochi mid-scene | The existing recovery reopens with whichever costume the context wants then. |
| Video starts during the agent scene | Video wins, as for the laptop. After video, the resume chain reopens the agent scene if agents still work. |
| The frames are cleaned up later | The manifest and tests check structure, frame counts and the idle-silhouette seams, not exact pixels. Cleanup that keeps the first and last frames' silhouettes passes. |

## Testing

- **Assets** (`tests/test_agent_scene_assets.py`):
  - the manifest entries
  - every frame exists, 256×256 RGBA
  - the intro's first frame and the outro's last frame have the idle silhouette
  - the packaging line exists
  - the existing "manifest is the complete PNG inventory" test covers the new directory
- **Costume refactor.** The #176 terminal characterization tests stay unchanged. New tests check that:
  - `_cowork_role` works across costumes
  - intro, loop and outro play the stored costume's names
  - `_start_watching_emote` interrupts agent art too
- **Agent costumes:**
  - with agents working, intro picks `agent`; with none, `terminal`; with VS Code focused, `terminal`
  - swap timing: no swap before 5 s, a swap at 5 s, and only from the loop
  - agent → terminal on stop with the terminal focused
  - agent → idle on stop elsewhere
  - drag recovery picks the current costume
- **End-to-end harness:** the v1 end-to-end test, extended. Working outside a terminal opens the agent costume; working in a terminal swaps at 5 s; stopping in a terminal swaps back to the laptop.
- **Builder** (`tests/test_build_agent_scene.py`, skipped without Pillow):
  - it is deterministic
  - it refuses to overwrite without `--force`
  - outside the monitor's rectangle, every built frame is pixel-identical to its source `coffee` frame. This proves Mochi is untouched, including at the loop seam (`coffee` 16 → 8).

## Documentation

- `assets/mochi/README.md`: the `agent/` set, how it was built, and that the PNGs are the source of truth.
- `docs/agent-companion.md`: describes the monitor scene.
- `CHANGELOG.md` (`Unreleased`): the Agent Companion entry mentions the new scene.
- `REGRESSION_WATCHLIST.md`, under Agent Companion:
  - no frame pop entering or leaving the agent scene
  - quick terminal turns don't swap scenes
  - a swap after 5 s goes outro → intro
  - the scene returns to the laptop when the agent stops in a terminal
- **Manual QA:** check the art at 64, 112 and 256 px. The screen lines must stay legible at 112 and above, and are allowed to blur into texture at 64.

## Delivery

- Branch `claude/agent-companion-scene`, stacked on `claude/agent-companion-spec` (#176), in a draft PR based on that branch. When #176 merges, the PR is retargeted to `main`.
- The spec and plan are approved first, then the implementation goes in test-first.
- The maintainer cleans up the draft frames in Pixelorama, in this PR or a later one, and does the live Fedora QA.

## Risks

- **Art quality.** The draft frames are composites. The main risks are the mug and monitor coming close during the sip, and the code lines' legibility at small sizes. Mitigation: maintainer cleanup, plus the 64/112/256 px check.
- **Refactoring a proven sequence.** It is renaming plus a lookup. The #176 characterization tests guard the terminal path unchanged.
- **Swap churn.** Bounded by the 5 s rule and by authored transitions. Worst case, a long agent turn in a terminal costs two transitions (in and out).
