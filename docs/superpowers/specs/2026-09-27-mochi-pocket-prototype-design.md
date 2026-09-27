# Mochi Pocket Prototype — Design

**Date:** 2026-09-27

**Issue:** #14 — Prototype Mochi’s Pocket: drag files, text, images, and URLs onto Mochi

**Branch:** `feat/mochi-pocket-prototype`

**Status:** written spec ready for review; implementation not started

## Purpose

Mochi’s Pocket is the first concrete utility mechanic intended to make Mochi useful without separating utility from character.

The core interaction is:

> Give something to Mochi. Mochi reacts, holds it locally, and gives the user a simple next action.

This prototype must prove that drag-and-drop utility can feel like a native character interaction rather than a separate file-manager window bolted onto a desktop pet.

Success means a user can drag supported content onto Mochi, receive immediate visual/character feedback, and later view, open, or remove the held item without creating an account or relying on cloud services.

## Product principles

1. **The character is the interface.** Dragging onto Mochi is the primary entry point.
2. **Utility drives animation.** Accepted content causes a character reaction; the animation is not decorative afterthought.
3. **Local first.** Pocket requires no account, network service, or synchronization.
4. **Original files stay where they are.** Ordinary local files are referenced by absolute path and are never silently duplicated.
5. **Pocket is small and recent, not a file manager.** The prototype keeps at most ten items.
6. **Persistence is user data, not configuration.** Pocket contents live under the XDG data directory, separate from `ConfigStore`.
7. **One shared behavior-state path remains authoritative.** Pocket must cooperate with Mochi’s existing state machine rather than inventing a second one.
8. **GTK is an adapter, not the domain model.** Classification, capacity, persistence, and cleanup rules remain testable without a live desktop.
9. **Failure must be safe and visible.** Unsupported content, busy states, persistence failure, missing files, and launch failure must not corrupt Pocket or strand Mochi’s interaction state.
10. **YAGNI.** This issue does not create a generic utility/plugin framework.

## Scope

### In scope

- external drag-and-drop onto Mochi;
- local files and directories;
- plain text;
- HTTP/HTTPS URLs;
- raw image/texture drops where GTK provides image data;
- a persistent recent list of at most ten items;
- acceptance/rejection feedback during drag;
- one character receive reaction per accepted external drop;
- a user-facing Pocket row in Mochi’s context menu;
- a small Pocket management window;
- open/view/remove actions;
- missing-file state;
- safe persistence and rollback;
- regression coverage around state ownership and menu integration;
- manual Fedora/GNOME drag-and-drop verification.

### Out of scope

- copying ordinary local files into Mochi’s data directory;
- cloud synchronization or accounts;
- search, folders, tags, pinning, or manual reordering;
- thumbnails and image editing;
- dragging Pocket items back out to other applications;
- clipboard history or background capture;
- arbitrary URI schemes;
- file-content previews;
- a generic Mochi utility/plugin framework;
- new animation assets;
- new sound assets.

## Existing runtime constraints

Mochi has one authoritative behavior-state machine. Feature code requests transitions through the existing guarded state path rather than mutating `StateMachine` directly.

Direct user interaction has higher priority than ambient behavior, but protected lifecycle states retain ownership. Existing feeding behavior already demonstrates the required pattern: a direct interaction can interrupt lower-priority ambient presentation while respecting sleep/wake, pickup/drag/drop, and Fedora-held modes.

Context-menu features participate in the existing cooperative menu chain and register rows through the supported menu layout seam.

The production buddy is composed from feature layers and controllers. New subsystems with meaningful state, persistence, or windows should not make `Buddy` or `BuddyMenuController` the owner of unrelated domain logic.

## Architecture

Pocket is split into four focused pieces:

```text
external drag
    ↓
GTK drop adapter
    ↓
Pocket classifier/domain service
    ↓
PocketStore ─────→ persistent Pocket data
    ↓
Buddy feedback + receive reaction
    ↓
Pocket window → open / view / remove
```

### `pocket.py`

Pure Python domain model and rules.

Responsibilities:

- `PocketItem` model;
- supported item kinds;
- validation;
- normalization;
- deterministic newest-first ordering;
- duplicate policy;
- ten-item capacity;
- missing-file availability checks;
- JSON serialization/deserialization helpers;
- identifying managed images eligible for cleanup after eviction/removal.

No GTK imports.

Conceptual item fields:

```text
id
kind
display_name
value
received_at
```

Supported kinds:

```text
local_file
text
saved_image
url
```

### `pocket_store.py`

Persistence and transactional mutation.

Pocket data lives under Mochi’s XDG data directory rather than `config.json`.

Conceptual location:

```text
$XDG_DATA_HOME/mochi/pocket/
    pocket.json
    images/
```

If `XDG_DATA_HOME` is unset, use the platform-normal fallback under the user’s local data directory.

Responsibilities:

- load Pocket data;
- append/refresh batches transactionally;
- remove entries transactionally;
- atomically replace `pocket.json`;
- preserve the previous store on failed writes;
- keep corrupt top-level JSON for diagnosis rather than silently overwriting it;
- skip malformed individual records while preserving valid records;
- manage raw-image PNG files created by Pocket;
- delete only Pocket-managed images after successful metadata persistence.

Ordinary local files are never copied, moved, modified, or deleted.

### `pocket_drop.py`

GTK drag-and-drop adapter.

Responsibilities:

- register supported drop targets on Mochi;
- recognize file lists, strings, URLs, and textures;
- classify GTK payloads into normalized domain candidates;
- update acceptance highlight while a supported drag is over Mochi;
- clear highlight on leave, cancel, or completed drop;
- reject unsupported formats safely;
- reject while Pocket cannot claim interaction ownership;
- hand accepted batches to the Pocket service;
- trigger exactly one receive reaction per successful external drop.

The GTK adapter never writes Pocket JSON directly.

### `pocket_window.py`

Small user-facing management surface.

Responsibilities:

- list newest items first;
- render empty state;
- render available and unavailable file rows;
- display type icon, compact label, and receipt time;
- dispatch open/view/remove actions;
- show read-only text detail;
- preserve items after launch failure;
- keep the window lifecycle separate from the buddy drawing surface.

The Pocket row is registered through the existing context-menu layout interface and displays the current count:

```text
Pocket · N
```

Activating the row closes the context menu first, then opens the Pocket window.

## Data model and classification

### Local files and directories

A local file-list drop creates one Pocket item per local path.

Storage rule:

- normalize to an absolute path;
- store the path only;
- do not copy the file;
- preserve an entry if the referenced file later moves or disappears;
- mark the entry unavailable when the path no longer exists;
- allow removal even when unavailable.

Non-local file URIs are rejected in this prototype.

### Raw images

When GTK provides a raw image/texture rather than a stable local file path, Pocket saves a PNG under its managed image directory.

This is the one intentional exception to the path-only rule because raw image data otherwise disappears when the source application closes.

Managed image paths are owned by Pocket and may be deleted after successful Pocket metadata updates when the entry is removed or evicted.

### URLs

A single trimmed string beginning with `http://` or `https://` becomes a URL item.

Only HTTP and HTTPS are supported.

URLs are never passed to a shell or concatenated into command strings.

### Text

Any other non-empty supported string becomes a text item.

Maximum size:

```text
64 KiB per text item
```

Oversized text is rejected before any store mutation.

Text is stored and rendered as text, never interpreted as markup.

### Classification order

Payloads are classified in this order to avoid ambiguous interpretation:

1. GTK file list → one or more local-file items;
2. raw GTK texture/image → one managed PNG image item;
3. single HTTP/HTTPS string → URL;
4. other non-empty string → text;
5. empty strings, non-local file URIs, unsupported schemes, and unknown formats → reject.

## Ordering, duplicates, and capacity

Pocket is newest-first.

Maximum size:

```text
10 items
```

Adding beyond ten evicts the oldest entries.

Duplicate policy:

- same normalized local-file path → move existing item to the top and refresh receipt time;
- same normalized URL → move existing item to the top and refresh receipt time;
- identical text → allowed as separate entries;
- raw images → treated as separate drops.

A multi-file external drop is one logical transaction.

Either the complete accepted batch is persisted or the prior Pocket remains unchanged.

If capacity eviction occurs, user feedback must make it visible, for example:

```text
Held 3 items · removed the oldest 2
```

Managed images selected for eviction are deleted only after the new Pocket metadata has been persisted successfully.

## Drag feedback and receive flow

### Drag-over feedback

Supported content over Mochi produces a green acceptance highlight.

Unsupported content uses the system no-drop cursor where available.

Repeated drag-motion events may update the highlight but must not:

- write Pocket data;
- create items;
- restart an animation;
- mutate the behavior state.

Leaving or cancelling the drag clears the highlight immediately.

### Accepted drop

For a supported drop:

1. classify and validate the full batch;
2. verify Mochi’s current behavior can accept the interaction;
3. prepare any managed raw-image file through a temporary path;
4. construct the complete candidate Pocket state;
5. write candidate JSON through temporary-file replacement;
6. publish the live in-memory Pocket only after persistence succeeds;
7. clean up successfully evicted managed images;
8. record direct user interaction;
9. play one existing excited receive reaction;
10. recover through Mochi’s normal reaction/ambient-resume path.

The drop is reported successful only after persistence succeeds.

One external drop produces one reaction even when the batch contains multiple files.

### Unsupported or failed drop

Unsupported content must not mutate Pocket.

When presentation is available, Mochi gives brief feedback such as:

```text
I can’t hold that yet
```

Persistence failure keeps the previous Pocket active, cleans temporary managed-image files, and gives failure feedback.

## Behavior-state ownership

Pocket receive is direct user input, but it does not outrank every state.

It may interrupt lower-priority presentation such as:

- walking;
- blinking;
- idle emotes;
- typing;
- watching;
- dancing;
- searching;
- other ambient presentation.

It is rejected while Mochi is:

- sleeping;
- waking;
- being picked up;
- being dragged;
- settling from drag/drop;
- holding Fedora mode;
- already processing another Pocket drop;
- owned by another protected direct reaction.

Busy rejection writes nothing.

Where presentation is available, busy feedback may use a short line such as:

```text
My paws are full
```

### State implementation rule

Do not create a parallel Pocket behavior state machine.

The preferred implementation is to reuse the existing `EXCITED` reaction as the receive animation while adding one narrow transition-policy entry point for Pocket/direct receive ownership.

The implementation should follow the existing feeding pattern:

- cancel lower-priority walk/emote presentation when appropriate;
- ask the central transition guard for permission;
- preserve protected state ownership;
- return through the existing one-shot completion and ambient-resume path.

If the implementation requires substantial new behavior-state semantics beyond that narrow rule, stop and revisit the design rather than growing hidden Pocket-specific state policy.

## Pocket window behavior

### Empty state

When Pocket is empty, show a friendly explanation that items can be dragged onto Mochi.

### Row presentation

Each row shows a type icon, compact label, and receipt time.

Recommended labels:

**File**
- filename;
- containing folder.

**URL**
- host;
- shortened URL.

**Text**
- first meaningful line;
- visually truncated while preserving full stored text.

**Saved image**
- generated label such as `Dropped image · 3:42 PM`.

### Actions

**Open file/image**
- convert the local path to a file URI;
- launch through the desktop’s default application.

**Open URL**
- launch only previously validated HTTP/HTTPS URLs through the default handler.

**Open text**
- display full content in a read-only Mochi-styled detail window.

**Remove**
- persist removal immediately;
- delete only Pocket-managed image data;
- never delete or modify an original dropped file.

### Missing files

If an original local path no longer exists:

- keep the row;
- mark it unavailable;
- disable Open;
- keep Remove enabled.

### Launch failure

Launch failure:

- keeps the item;
- shows an error;
- never removes the entry as a side effect.

## Persistence and failure model

Pocket mutations are transactional at the JSON metadata boundary.

### Add transaction

1. classify/validate;
2. write managed raw image to a temporary file if needed;
3. calculate candidate Pocket state;
4. write candidate JSON to a temporary file;
5. atomically replace the old JSON;
6. publish the new in-memory state;
7. delete evicted managed images;
8. finalize/retain the managed raw image.

If JSON persistence fails:

- previous JSON remains authoritative;
- previous in-memory Pocket remains active;
- temporary files are cleaned;
- no receive reaction plays;
- the drop reports failure.

### Remove transaction

1. calculate candidate state without the target item;
2. atomically persist candidate JSON;
3. publish candidate in memory;
4. delete associated managed image if applicable.

If managed-image deletion fails after metadata persistence, log the failure but do not resurrect the removed entry.

### Corrupt data

**Corrupt top-level JSON**
- log the problem;
- preserve the corrupt file;
- load an empty in-memory Pocket;
- do not overwrite the corrupt file merely because startup occurred.

A later explicit successful write may require a deliberate recovery path rather than silently clobbering evidence.

**Malformed individual records**
- skip malformed records;
- continue loading valid records.

## Security and safety

- Never invoke a shell for Pocket open actions.
- Never build command strings from item content.
- Only HTTP/HTTPS URLs are launchable as URLs.
- Local files/images are launched as file URIs.
- Text is plain text, not markup.
- Managed image paths must remain under Pocket’s managed image directory.
- Serialization must not permit record data to escape into arbitrary filesystem deletion.
- Removal code must distinguish Pocket-managed images from original local files.
- Unsupported URI schemes are rejected before persistence.
- Failed operations must not partially mutate live state.

## Testing strategy

Implementation follows red-green-refactor cycles.

### Domain tests

Cover:

- URL versus text classification;
- local-path normalization;
- empty/oversized/non-local/unsupported rejection;
- newest-first ordering;
- duplicate file refresh;
- duplicate URL refresh;
- duplicate text retention;
- ten-item capacity;
- managed-image cleanup candidates;
- missing-file availability.

### Persistence tests

Cover:

- round-trip every item kind;
- prior JSON survives failed write;
- malformed records do not hide valid records;
- corrupt top-level data is preserved;
- failed multi-item transaction leaves prior state unchanged;
- temporary managed images are cleaned after failure;
- original local files are never deleted;
- managed image cleanup happens only after successful metadata persistence.

### GTK adapter tests

Cover:

- file lists;
- strings;
- URL classification;
- textures/images;
- drag-enter/motion feedback;
- leave/cancel/drop feedback clearing;
- one batch and one receive reaction for multi-file drops;
- unsupported format rejection;
- busy-state rejection;
- repeated motion events do not write or restart reaction.

Where GTK objects are difficult to construct headlessly, keep payload normalization behind thin functions so the domain-facing behavior remains independently testable.

### State-policy tests

Cover accepted receive from permitted ambient states and rejection from protected states.

Verify:

- idle;
- walking;
- blinking;
- idle emote;
- typing;
- watching;
- dancing;
- searching;
- sleeping;
- waking;
- pickup;
- dragged;
- dropping;
- Fedora;
- another active Pocket receive/direct ownership state.

Verify successful completion returns through the normal reaction/ambient-resume path.

Verify a stale or repeated completion callback cannot double-finish the receive reaction.

### UI integration tests

Cover:

- Pocket row registration through the supported context-menu layout API;
- count update after add/remove;
- deferred opening until the context menu closes;
- empty state;
- available file state;
- unavailable file state;
- open/remove dispatch;
- read-only text detail;
- launch failure preserves item.

### Regression verification

Before completion:

- run all new Pocket tests;
- run the full existing test suite;
- inspect final diff against `main`;
- verify package discovery includes every new Python module;
- confirm no new runtime dependency is required;
- perform a fresh whole-branch code review.

## Manual Fedora/GNOME verification

Automated tests do not prove cross-application desktop drag-and-drop.

Manual verification must cover:

### GNOME Files

- one file;
- one directory;
- multiple files.

### Browser

- selected text;
- page URL;
- linked image;
- dragged image where the browser exposes texture/image data.

### Text editor

- short text;
- multiline text;
- empty selection;
- oversized selection.

### Interaction and lifecycle

- green acceptance glow;
- cancellation/leave clears glow;
- unsupported feedback;
- busy-state feedback;
- open with system default app/browser;
- remove while original file remains untouched;
- restart Mochi and confirm persistence;
- move/delete original file and confirm unavailable state;
- add an eleventh item and confirm oldest eviction;
- repeat existing file and URL and confirm refresh-to-top;
- receive reaction returns to idle/ambient behavior;
- exercise normal GNOME/XWayland path;
- exercise native Wayland when explicitly enabled.

Manual results must be reported separately from unit-test results. Passing automated tests is not evidence that cross-application GTK drag-and-drop works on the desktop.

## Expected production files

The implementation is expected to introduce focused modules similar to:

```text
src/mochi/pocket.py
src/mochi/pocket_store.py
src/mochi/pocket_drop.py
src/mochi/pocket_window.py
```

Integration changes are expected to remain narrow in existing files, primarily around:

```text
src/mochi/behavior.py
src/mochi/presence/click_dialogue.py   # composition/menu integration location may vary
src/mochi/app.py or Buddy construction # only if dependency ownership requires it
```

Tests are expected under focused `tests/test_pocket*.py` modules plus small regression additions to existing state/menu architecture tests where appropriate.

Exact file ownership may change during implementation if repo inspection reveals a cleaner existing seam, but the domain/store/GTK/UI separation is a design requirement.

## Acceptance criteria mapping

### Mochi detects supported dropped content

Implemented by the GTK drop adapter and classifier.

### Accepted items enter a simple local Pocket

Implemented by the domain model plus transactional Pocket store.

### Unsupported drops fail safely with clear feedback

Implemented by adapter validation and feedback without store mutation.

### A received-item animation/reaction plays without breaking the state machine

Implemented by one existing excited reaction through the central transition policy and normal resume path.

### Pocket contents can be viewed, opened, and removed

Implemented by the Pocket context-menu row and management window.

### Closing/reopening Mochi preserves Pocket contents

Implemented by XDG data persistence.

### Prototype requires no account or cloud service

All persistence and actions are local.

## Approved decisions

The reviewed design decisions are:

- ordinary local files remain in their original location;
- Pocket stores absolute path references only;
- missing originals remain visible as unavailable;
- raw image drops may be copied into Pocket-managed local storage;
- Pocket capacity is ten items;
- duplicate files/URLs refresh to the top;
- duplicate text is allowed;
- multi-file drops are transactional;
- one external drop triggers one receive reaction;
- protected direct/lifecycle states reject Pocket receive;
- existing excited animation is reused;
- Pocket persistence is separate from `ConfigStore`;
- no generic utility framework is introduced in this issue.
