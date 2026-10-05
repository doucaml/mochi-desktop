# Agent Scene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use beads-superpowers:subagent-driven-development (recommended) or beads-superpowers:executing-plans to implement this plan task by task.
> - Each Task becomes a bead (`bd create -t task --parent <epic-id>`). If `bd` is not installed, use the session task list.
> - Steps use checkbox (`- [ ]`) syntax.
> - Do not start until the spec and this plan are approved.

**Goal:** While coding agents work, Mochi's coworking sequence plays a new **agent scene** instead of the terminal laptop: he sips from his mug while a little monitor scrolls code. Swaps between the two scenes go through authored outro → intro transitions.

**Architecture:**
1. A deterministic builder composites untouched canonical `coffee` frames with a monitor prop, written as palette art in the script, and outputs three new animations.
2. The terminal coworking sequence gains costume indirection, so it can play either name set.
3. `AgentCoworkMixin` picks the costume and requests swaps.

There is no new `MochiState` and no new gate.

**Tech Stack:** Python 3.11+, GTK4/PyGObject, Pillow (dev-only, `tools/`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-05-agent-scene-design.md`

## Global Constraints

- **Mochi's pixels are canonical.** Outside the monitor rectangle, every built frame equals its source `coffee` frame byte for byte.
- **Art contract:**
  - 256×256 RGBA, bottom-center, 4 px grid, nearest-neighbor only, 8.33 fps
  - names `agent_intro` (7), `agent_loop` (18, loops), `agent_outro` (5)
  - frames `assets/mochi/agent/agent_{intro,loop,outro}_NN.png`
- **Seams.** The intro's first frame and the outro's last frame have exactly the idle silhouette.
- **One costume per cycle.** The costume is chosen at intro and kept until the outro finishes. Swaps only start from the loop.
- **Constants (exact values):**
  - `AGENT_SCENE_SWAP_DELAY_SECONDS = 5.0`
  - `COWORK_COSTUMES["terminal"] == ("terminal_intro", "terminal_loop", "terminal_outro")`
  - `COWORK_COSTUMES["agent"] == ("agent_intro", "agent_loop", "agent_outro")`
- **No terminal regressions.** Without agents, terminal coworking behaves exactly as before: the #176 characterization tests stay unchanged and green.
- **Pillow is dev-only.** The runtime stays at `dependencies = []`, and the builder test is skipped when Pillow is missing.
- **Test command:** `PYTHONPATH=src xvfb-run -a /usr/bin/python3.12 -m pytest -q -p no:cacheprovider` (CI: `xvfb-run -a python3 -m pytest -q`). For the builder, install `python3-pil` locally.
- **Baseline:** the #176 head `45f9fab` gives 1323 passed, 5 skipped.
- **Branch:** `claude/agent-companion-scene`, stacked on `claude/agent-companion-spec`. The draft PR is based on that branch.

## File Map

| File | Responsibility | Task |
|---|---|---|
| `tools/build_agent_scene.py` (new) | Deterministic builder: monitor palette art, screen animation, composition, `--force` | 1 |
| `tests/test_build_agent_scene.py` (new) | Builder determinism, no-overwrite, Mochi untouched outside the prop | 1 |
| `assets/mochi/agent/*.png` (new, 30) | Draft frames written by the builder | 2 |
| `assets/mochi/manifest.json`, `pyproject.toml` | Three entries; one data-files line | 2 |
| `tests/test_agent_scene_assets.py` (new) | Manifest shape, inventory, idle-silhouette seams, packaging | 2 |
| `src/mochi/presence/terminal_cowork.py` | Costume tables, `_cowork_role`, costume-aware play and compare | 3 |
| `src/mochi/presence/agent_cowork.py` | `agent` costume, `_cowork_costume_for_context`, `_maybe_swap_cowork_costume`, work clock | 4 |
| `tests/test_agent_cowork.py` | Costume and swap tests; end-to-end extension | 3, 4 |
| `assets/mochi/README.md`, `docs/agent-companion.md`, `CHANGELOG.md`, `REGRESSION_WATCHLIST.md` | Docs and QA | 5 |

---

### Task 1: Builder

**Interfaces:**
- **Produces:**
  - `build(out_dir: Path, *, force: bool = False) -> dict[str, list[Path]]`
  - a CLI: `python3 tools/build_agent_scene.py [--out DIR] [--force]`
- **Consumes:** `assets/mochi/coffee/mochi_coffee_NNNN.png`.

**Acceptance Criteria:**
- **Prop data.**
  - `MONITOR` is 22 strings, each 24 characters wide, over a 5-entry palette, transcribed from the keyed draft.
  - The screen interior is rows 3–12 and columns 4–19; code rows are 5, 7, 9 and 11, starting at column 6, with at most 12 columns.
  - `LINES` is the 9-entry `(indent, length)` cycle.
- **Sequencing:**
  - Intro: `coffee` 1–7, prop drops `hidden, hidden, 16, 9, 4, 1, 0` grid px; the screen is off until the last frame, which shows loop screen 0.
  - Loop: `coffee` 8–16 twice; the screen at frame `f` scrolls one line per two frames, and the bottom line types half then full, with a cursor.
  - Outro: `coffee` 17–21, screen off, drops `0, 2, 6, 13, hidden`.
- **Placement.** The prop is placed ×4 at `x = 256 - 96`, `y = 256 - 88 - 4 + drop*4`, clipped at the bottom edge.
- **Output and safety.**
  - Output is deterministic: two builds into fresh directories are byte-identical.
  - It refuses to overwrite existing frames unless given `force`, with the message "frames exist; they may be hand-cleaned — pass --force".
- **Docstring.** It records provenance: the PixelEngine jobs, the keying, and that committed PNGs become the source of truth after cleanup.

- [ ] **Steps:**
  - write `tests/test_build_agent_scene.py`, guarded with `pytest.importorskip("PIL")`:
    - determinism
    - refusing to overwrite
    - frame counts
    - every pixel outside the prop rectangle equals the source `coffee` frame
    - the prop rectangle at rest contains only palette colors
  - see the tests fail
  - implement, porting the scratch prototype that produced the approved preview
  - see the tests pass
  - commit `feat(art): agent scene builder`

### Task 2: Draft assets, manifest, packaging

**Acceptance Criteria:**
- The 30 frames are built with the Task 1 builder and committed.
- **Manifest entries:**
  - `agent_intro`: 7 frames, `loop: false`
  - `agent_loop`: 18 frames, `loop: true`
  - `agent_outro`: 5 frames, `loop: false`
  - all three: `fps: 8.333333333333334`, frame lists under `agent/`
- **Packaging:** `pyproject.toml` gets `"share/mochi/agent" = ["assets/mochi/agent/*.png"]`.
- **`tests/test_agent_scene_assets.py`:**
  - the manifest shape
  - every frame exists, 256×256 RGBA
  - intro frame 1 and outro frame 5 have the idle silhouette (as in `test_terminal_transition_assets.py`)
  - the packaging line
- The existing `test_manifest_is_the_complete_runtime_png_inventory` passes.
- **Loading.** `mochi.sprites.ANIMATIONS` contains all three, with `agent_loop.looping`.

- [ ] **Steps:** failing asset tests → build and commit frames, manifest and pyproject → pass → full suite → commit `feat(art): draft agent scene animation`.

### Task 3: Costume indirection in terminal coworking

**Interfaces:**
- **Produces** on `TerminalCoworkMixin`:
  - `COWORK_COSTUMES`
  - `_cowork_costume` (class default `"terminal"`)
  - `_cowork_costume_for_context() -> str` (returns `"terminal"`)
  - `_cowork_names() -> tuple[str, str, str]` (the stored costume)
  - `_cowork_role(name) -> str | None` (searches all costumes)

**Acceptance Criteria:**
- **Playback.** `_play_terminal_intro` sets `_cowork_costume = _cowork_costume_for_context()`, then plays that costume's intro. `_play_terminal_loop` and `_play_terminal_outro` play the stored costume.
- **Role checks.** Every `== self.TERMINAL_*_ANIMATION` comparison, and the `_start_watching_emote` set, become role checks (`_cowork_role(...) == "intro"`, and so on):
  - `_begin_terminal_coworking`
  - both `_finish_reaction` branches
  - `_stop_terminal_coworking`
  - `_start_watching_emote`
- **No terminal regressions:**
  - All #176 terminal characterization tests pass unmodified.
  - A new source-text test asserts that no bare `TERMINAL_*_ANIMATION` comparison remains outside the costume table.
- **New tests:**
  - a costume stored at intro is used for loop and outro, even if `_cowork_costume_for_context()` changes mid-cycle
  - `_cowork_role("agent_loop") == "loop"` once the agent costume is registered
  - watching interrupts any costume's art

- [ ] **Steps:** characterization stays green → failing new tests → refactor → pass → full suite → commit `refactor(terminal): costume-aware coworking sequence`.

### Task 4: Agent costume and swaps

**Interfaces:**
- **Produces** on `AgentCoworkMixin`:
  - `COWORK_COSTUMES` = the base table plus `"agent"`
  - `AGENT_SCENE_SWAP_DELAY_SECONDS = 5.0`
  - `_agent_work_started_at: float | None`
  - `_cowork_costume_for_context()` (override)
  - `_maybe_swap_cowork_costume()`

**Acceptance Criteria:**
- **Costume choice.** It returns `"agent"` when `tracker.working` and the category is not `vscode`. Otherwise it defers to `super()`.
- **Work clock.** `WORK_STARTED` sets `_agent_work_started_at = _agent_now()`; `WORK_STOPPED` clears it.
- **Swap check.** `_maybe_swap_cowork_costume()` runs after each edge application and each tick.
  - It acts only when **all** of these hold:
    - the sequence is active
    - the state is `TYPING`
    - the current animation's role is `loop`
    - the stored costume differs from `_cowork_costume_for_context()`
    - for terminal → agent only: `now - _agent_work_started_at >= 5.0`
  - When it acts, it plays the current costume's outro and keeps `_terminal_coworking_active` true, so the existing outro-finish path reopens with the new costume.
- **`_TERMINAL_ART`** covers every costume's names, which keeps the #176 typing-stop rule intact.
- **Tests:**
  - choice: working outside a terminal → `agent`; none → `terminal`; VS Code focused → `terminal`
  - no swap before 5 s; swap at 5 s; never from intro or outro
  - agent → terminal when agents stop while the terminal is focused
  - agent outro → idle when agents stop elsewhere
  - recovery after a drag picks the current costume
  - the end-to-end harness extended with the three scenarios in the spec's Testing section

- [ ] **Steps:** failing tests → implement → pass → full suite → commit `feat(agent): play the agent scene while agents work`.

### Task 5: Docs and QA

**Acceptance Criteria:**
- `assets/mochi/README.md`: an `agent/` section covering composition, builder, provenance, and "PNGs are the source of truth".
- `docs/agent-companion.md`: the first bullet describes the monitor scene.
- `CHANGELOG.md` (`Unreleased`): the entry mentions the new scene.
- `REGRESSION_WATCHLIST.md`: the four spec items.
- `git diff --check` is clean.

- [ ] **Steps:** write → proofread against the spec → commit `docs(art): agent scene`.

### Task 6: Verification and PR

- [ ] Run the full suite under `xvfb-run` and report the summary against the baseline. Run the opt-in D-Bus test under `dbus-run-session`.
- [ ] Run `compileall src`, `git diff --check`, and the builder twice to show determinism.
- [ ] Do an Xvfb smoke render: load `ANIMATIONS["agent_loop"]` and draw each frame at 64, 112 and 256 px via the sprite loader, with no errors.
- [ ] Produce a GIF preview for the PR.
- [ ] Adversarially self-review the diff against AGENTS.md and the spec.
- [ ] Push, then open a draft PR with base `claude/agent-companion-spec`, following the template. List the manual QA steps (64/112/256 px legibility; the three swap scenarios; drag and video recovery) and state that desktop QA was not run.
