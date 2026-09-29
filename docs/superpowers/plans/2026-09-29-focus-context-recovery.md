# Focus Context Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Fix issue #147 so active Focus presentation remains authoritative during rapid VS Code/Terminal/app-context churn and cannot be replaced by cowork visuals.

**Architecture:** Keep the existing state machine and Focus session ownership intact. Prove the cross-mixin ownership bug with a production-MRO regression test, then make cowork activation verify that it actually acquired the shared `TYPING` state before setting cowork-active flags or starting terminal-specific artwork. Do not add timers, states, or detector suppression.

**Tech Stack:** Python 3.11+, pytest, GTK4/PyGObject runtime seams.

**Spec:** GitHub issue #147 (Focus animation lags or gets stuck after rapid window switching).

## Global Constraints

- Focus session truth remains separate from presentation state.
- Detection stays separate from presentation.
- Repeated context detection must not restart an already-authoritative Focus presentation.
- No new state machine, timer, dependency, or broad refactor.
- Existing Terminal and VS Code cowork behavior outside Focus remains unchanged.
- Real Fedora/GNOME/Wayland/XWayland QA remains required after automated verification.

## Review Focus

- Active Focus + Terminal focus: no terminal intro/loop may replace `focus_start`/`focus_loop`.
- Active Focus + VS Code focus: VS Code cowork must not falsely claim active ownership.
- Rapid terminal/vscode/unknown/browser churn: no accumulating cowork-active flags or stale visual takeover.
- Focus paused/break/cancelled: normal cowork ownership must still be able to acquire `TYPING`.
- Stale animation completions: existing active-animation identity guard must remain intact.

---

### Task 1: Guard cowork ownership behind the shared TYPING state

**Files:**
- Create: `tests/test_focus_context_recovery.py`
- Modify: `src/mochi/presence/terminal_cowork.py`
- Modify: `src/mochi/presence/integration.py`

**Interfaces:**
- Consumes: `FocusSessionMixin._start_typing_emote() -> bool`, which may return true because Focus handled the request while state remains `COMPUTER`.
- Produces: cowork activation only after `self.state.current is MochiState.TYPING`.

- [ ] **Step 1: Write failing production-MRO regression tests.**
  Build a minimal `PresenceBuddy` instance without GTK initialization, put it in an active Focus session with `state.current == COMPUTER` and `_current_animation == "focus_loop"`, then exercise VS Code and Terminal cowork begin paths repeatedly. Assert Focus remains unchanged, cowork-active flags remain false, and terminal intro is not requested.

- [ ] **Step 2: Verify RED.**
  Run the focused test in CI and confirm it fails because current cowork begin paths treat a true `_start_typing_emote()` return as proof they own `TYPING`, even when Focus intercepted the request.

- [ ] **Step 3: Implement the minimal ownership fix.**
  In both cowork begin paths, after `_start_typing_emote()` succeeds, require `self.state.current is MochiState.TYPING` before setting the cowork-active flag; Terminal must also require that state before starting `terminal_intro`.

- [ ] **Step 4: Verify GREEN and regressions.**
  Run the focused regression plus the full pytest/compile/wheel CI workflow. Confirm existing non-Focus cowork tests remain green.

- [ ] **Step 5: Commit and hand off for Fedora QA.**
  Use a conventional bug-fix commit. Mika should torture-test Focus while rapidly switching Terminal, VS Code, browser, unknown/Overview contexts and verify the Focus loop remains coherent.
