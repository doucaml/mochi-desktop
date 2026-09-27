# Mochi Pocket Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local-first Mochi Pocket prototype that accepts dragged files, text, URLs, and images, persists up to ten recent items, exposes them through Mochi's context menu, and plays the dedicated Pocket receive animation only after a successful save.

**Architecture:** Keep Pocket domain rules and persistence GTK-independent, put drag-and-drop and windows behind thin GTK adapters, and use a small controller to connect those pieces to Mochi's existing behavior/state path. Ordinary local files remain referenced in place; only raw image drops create Pocket-managed files.

**Tech Stack:** Python 3.11+, dataclasses/enums/pathlib/json/uuid/time, GTK4/PyGObject, Gio/Gdk, pytest, existing Mochi sprite/manifest and setuptools packaging.

**Spec:** `docs/superpowers/specs/2026-09-27-mochi-pocket-prototype-design.md`

## Global Constraints

- Pocket capacity is exactly 10 items.
- A text item may contain at most 64 KiB of UTF-8 data.
- Ordinary local files are stored as normalized absolute paths and are never copied, moved, modified, or deleted.
- Raw image drops may be persisted only inside `$XDG_DATA_HOME/mochi-desktop/pocket/images/`.
- Only `http://` and `https://` URLs are accepted as URL items.
- Multi-file drops are all-or-nothing transactions.
- Duplicate normalized file paths and URLs refresh to newest; duplicate text remains separate.
- Pocket metadata is stored outside `ConfigStore`.
- No shell command construction is permitted for opening Pocket items.
- The dedicated Pocket receive animation plays exactly once per successfully persisted external drop.
- Pocket does not introduce a second behavior-state machine or generic plugin framework.

## Review Focus

- A path-like string such as `/tmp/example.txt` arriving as text must stay text unless the GTK payload is explicitly a file list.
- A duplicate file inside a multi-item batch must not cause capacity math or eviction cleanup to delete the refreshed live entry.
- A corrupt top-level `pocket.json` must be preserved before the first later successful user mutation; preservation failure must reject the mutation.
- A failed JSON save after finalizing a raw-image file must remove the newly created managed image and leave prior state unchanged.
- A URI using a non-HTTP scheme or a non-local file URI must never become a launchable Pocket entry.

---

### Task 1: Pocket domain model

**Files:**
- Create: `src/mochi/pocket.py`
- Create: `tests/test_pocket.py`

**Interfaces:**
- Produces: `PocketItemKind`, `PocketItem`, `PocketMutation`, `make_local_file_item(path, *, received_at=None)`, `make_url_item(value, *, received_at=None)`, `make_text_item(value, *, received_at=None)`, `make_saved_image_item(path, *, received_at=None)`, `apply_items(current, incoming, *, capacity=10) -> PocketMutation`, `item_is_available(item) -> bool`, `item_to_record(item) -> dict`, `item_from_record(record) -> PocketItem`.
- Consumes: Python standard library only.

- [ ] **Step 1: Write failing tests** for item validation, file normalization, URL validation, 64 KiB text limit, duplicate rules, capacity, cleanup candidates, serialization, malformed record rejection, and missing-file availability.
- [ ] **Step 2: Run `pytest tests/test_pocket.py -q` and verify failures are caused by the missing module/API.**
- [ ] **Step 3: Implement the minimal pure domain API in `src/mochi/pocket.py`.**
- [ ] **Step 4: Run `pytest tests/test_pocket.py -q` and verify it passes.**
- [ ] **Step 5: Commit `feat: add Pocket domain model`.**

### Task 2: Transactional Pocket store

**Files:**
- Create: `src/mochi/pocket_store.py`
- Create: `tests/test_pocket_store.py`

**Interfaces:**
- Consumes: Task 1 item/mutation/serialization API.
- Produces: `PocketStore(path: Path | None = None, images_dir: Path | None = None)`, `load() -> list[PocketItem]`, `add_items(current, incoming) -> PocketMutation`, `save_raw_image(png_bytes) -> PocketItem`, `remove(current, item_id) -> list[PocketItem]`.

- [ ] **Step 1: Write failing tests** for XDG path selection, round-trip, atomic replacement, corrupt-file preservation and backup, malformed-record skipping, failed batch rollback, managed image rollback, safe eviction/removal cleanup, and original-file non-deletion.
- [ ] **Step 2: Run `pytest tests/test_pocket_store.py -q` and verify RED.**
- [ ] **Step 3: Implement minimal transactional persistence and managed-image lifecycle.**
- [ ] **Step 4: Run `pytest tests/test_pocket_store.py -q` and verify GREEN.**
- [ ] **Step 5: Commit `feat: add Pocket persistence store`.**

### Task 3: Dedicated Pocket receive animation

**Files:**
- Add: Pocket receive frames under the existing production Mochi asset root.
- Modify: current animation manifest / loader integration used by `src/mochi/sprites.py`.
- Test: existing sprite/manifest tests plus a focused Pocket animation assertion.

**Interfaces:**
- Produces: runtime animation name `pocket_grab`, 8 frames, one-shot playback.
- Consumes: uploaded `mochi_pocket_grab` asset bundle.

- [ ] **Step 1: Write a failing test asserting `pocket_grab` is loadable with 8 frames and is non-looping.**
- [ ] **Step 2: Run the focused sprite test and verify RED.**
- [ ] **Step 3: Add the eight supplied 256×256 frames and manifest/runtime entry following the repository's existing asset convention.**
- [ ] **Step 4: Run the focused sprite test and verify GREEN.**
- [ ] **Step 5: Commit `feat: add Pocket receive animation`.**

### Task 4: Pocket controller and behavior ownership

**Files:**
- Create: `src/mochi/pocket_controller.py`
- Modify: `src/mochi/behavior.py`
- Test: `tests/test_pocket_controller.py` and focused transition-policy tests.

**Interfaces:**
- Consumes: `PocketStore`, `pocket_grab`, buddy callbacks for transition/cancel/reaction/feedback.
- Produces: `PocketController.receive(items) -> bool`, `remove(item_id)`, `items`, `count`, protected-state gating and exactly-one receive reaction.

- [ ] **Step 1: Write failing tests** for persistence-before-reaction, one reaction per batch, busy guard, allowed ambient interruption, protected-state rejection, failure feedback, and normal completion/resume.
- [ ] **Step 2: Run focused tests and verify RED.**
- [ ] **Step 3: Implement controller and the narrow shared transition-policy rule.**
- [ ] **Step 4: Run focused tests and verify GREEN.**
- [ ] **Step 5: Commit `feat: add Pocket receive controller`.**

### Task 5: GTK drop adapter

**Files:**
- Create: `src/mochi/pocket_drop.py`
- Test: `tests/test_pocket_drop.py`

**Interfaces:**
- Consumes: `PocketController.receive` and Task 1 factories.
- Produces: GTK drop-target installation plus pure payload-normalization helpers.

- [ ] **Step 1: Write failing tests** for file lists, URL/text strings, texture-to-PNG handoff, unsupported payloads, drag highlight lifecycle, busy rejection, and no writes/reactions during motion.
- [ ] **Step 2: Run focused tests and verify RED.**
- [ ] **Step 3: Implement thin GTK adapter and pure normalization helpers.**
- [ ] **Step 4: Run focused tests and verify GREEN.**
- [ ] **Step 5: Commit `feat: add Pocket drag and drop`.**

### Task 6: Pocket management window

**Files:**
- Create: `src/mochi/pocket_window.py`
- Test: `tests/test_pocket_window.py`

**Interfaces:**
- Consumes: controller items/remove/open callbacks.
- Produces: Pocket list window, read-only text detail window, unavailable state, open/remove actions.

- [ ] **Step 1: Write failing tests** for empty/list states, missing file row, open/remove dispatch, read-only text, and launch failure preservation.
- [ ] **Step 2: Run focused tests and verify RED.**
- [ ] **Step 3: Implement minimal Mochi-styled GTK window using existing window/menu patterns.**
- [ ] **Step 4: Run focused tests and verify GREEN.**
- [ ] **Step 5: Commit `feat: add Pocket management window`.**

### Task 7: Buddy/menu integration

**Files:**
- Modify: `src/mochi/presence/click_dialogue.py` or the smallest existing composition seam selected during implementation.
- Modify: `src/mochi/app.py` or Buddy construction only if needed for single-owner dependencies.
- Modify: context-menu layout integration using existing helpers.
- Test: focused context-menu and architecture regressions.

**Interfaces:**
- Consumes: Pocket controller/drop/window.
- Produces: `Pocket · N` menu row, deferred window opening after menu close, controller lifecycle wiring, drop target attached to both production Buddy variants.

- [ ] **Step 1: Write failing integration tests** for menu row/count, deferred open, both Buddy variants, and controller teardown/lifecycle.
- [ ] **Step 2: Run focused tests and verify RED.**
- [ ] **Step 3: Wire Pocket through existing composition/menu seams without moving domain logic into Buddy.**
- [ ] **Step 4: Run focused tests and verify GREEN.**
- [ ] **Step 5: Commit `feat: integrate Mochi Pocket`.**

### Task 8: Whole-branch verification and packaging

**Files:**
- Modify packaging metadata only if the existing package-data rules do not already include the new animation frames.
- Add/update manual verification notes under `docs/` if the project has an established QA location.

**Interfaces:**
- Consumes all prior tasks.
- Produces a branch ready for manual Fedora/GNOME drag testing.

- [ ] **Step 1: Run all Pocket-focused tests.**
- [ ] **Step 2: Run the full existing test suite and record every failure.**
- [ ] **Step 3: Verify package discovery/package data contains every new module and Pocket animation frame.**
- [ ] **Step 4: Inspect the diff against `main` and perform whole-branch code review.**
- [ ] **Step 5: Record the manual Fedora/GNOME checklist as not-yet-verified unless actually exercised.**
