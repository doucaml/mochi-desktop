# AGENTS.md — Mochi

Mochi is a local-first Linux desktop companion (Python 3.11+, GTK4, PyGObject, Cairo).
Primary target: Fedora + GNOME + Wayland. On GNOME Wayland the whole process runs with
GDK_BACKEND=x11 (XWayland), set in src/mochi/main.py. Do not change that.

## Read before changing runtime code
- docs/CODEBASE_MANUAL.md, especially section 2, "The five rules".
- REGRESSION_WATCHLIST.md sections for every area you touch.
- docs/ambisense.md for the privacy model.
- docs/superpowers/specs and docs/superpowers/plans for spec/plan format.

## Product rules (non-negotiable)
- Local only. New features make no network requests and add no telemetry.
- No streaks, decay, penalties, or guilt-based copy.
- Mochi stays easy to ignore: new speech respects speech_enabled, quiet mode, and
  presentation priority.
- Never read typed content, window titles, document names, or clipboard contents unless
  the user explicitly hands them to Mochi.

## Engineering rules
- One task = one feature = one reviewable diff. No drive-by refactors, renames, or reformatting.
- No new runtime dependencies (pyproject has `dependencies = []`; PyGObject comes from the system).
- New speech goes through PresenceEngine (src/mochi/presence/engine.py). New code never
  calls the speech bubble directly. Never pass text that did not originate in Mochi's own
  source code to any `markup=` parameter.
- Every long-lived source (GLib timeout, signal handler, D-Bus subscription, settings watch)
  has one owner and is torn down on shutdown (Manual rule 4).
- Keep logic GTK-free where possible so it is testable without a display. Follow existing
  injection patterns (e.g. `portal_factory` in src/mochi/color_scheme.py, the adapters in
  src/mochi/presence/signals.py).
- Do not touch the updater, src/mochi_launcher.py, or GDK backend selection unless the task says so.

## Workflow for feature tasks
1. Read the relevant code and the docs above.
2. Write a spec (docs/superpowers/specs/YYYY-MM-DD-<slug>-design.md) and a plan
   (docs/superpowers/plans/YYYY-MM-DD-<slug>.md) matching existing files.
3. Stop and wait for approval. Raise disagreements with the task design here, not mid-implementation.
4. After approval: test-first, small commits.

## Verification
- Run `python3 -m pytest -q` and report the actual output summary.
- You cannot run a GNOME session. Never claim desktop/manual QA passed. List exact manual
  QA steps for the maintainer instead.
- User-facing changes update CHANGELOG.md (Unreleased), README.md if usage or controls
  change, and REGRESSION_WATCHLIST.md.

## Final report
Summary; files changed; tests added; test command and result; what is unverified;
regressions/risks considered; follow-ups noticed but not done.
