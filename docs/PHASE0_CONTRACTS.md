# Doumao Automation — Phase 0 interface and regression contracts

**Baseline:** `feature/visible-order-renaming` at `68b5456292e610be84386b4a6f28e7acfa47b4ce` (v3.5).  **Status:** design and isolated test scaffolding only.  This document does **not** authorize changing GUI workflows, creating a commit, pushing a ref, or merging a branch.

## 1. Current behavior contracts (from baseline code)

| Workflow | Selection / navigation | Title and write | Save / return / advance | Uncertainty |
| --- | --- | --- | --- | --- |
| `clean_metadata` | `clean_metadata.run()` scans tag groups; selects earliest safe group; edge correction and auto scroll belong to this workflow. `batch_cleaner.run_one()` opens card/detail/editor. | `metadata_editor.clean_current()` verifies title and clears note and selected tags, re-detecting shifting elements. Does not rename titles. | `clean_current()` performs one Save click **after** final checks; `batch_cleaner.new_cleaner_event()` checks one new log event; `wait_for_list_after_save()` returns; `verify_tag_disappeared()` checks tag count and position; only then does the outer workflow count the item. | A click can precede the log write. If the dialog does not close or the log is missing, stop; never auto-resave. No general guarantee of cloud sync. |
| `normalize_titles` | `run()` scans unique thumbnail fingerprints while scrolling; `handle_card()` opens detail and editor. | Read actual title via `read_title_only()`; apply `title_rules.proposal()`; if relevant, re-read before write, replace title via clipboard, read back exact new title. Notes/tags untouched. | Verify Save button and title field, click Save once, `wait_for_list_after_save()`, `check_list()`, return `('saved', old, new)`. Skips and previews exit with Escape and do not save. | A failed click or post-click timeout throws; the caller must NOT treat it as proof that no save occurred. |
| `search_queue_rename` | User manually selects folder and search; `snapshot()` scrolls to top, checks first-column card; stable empty results need repeated observations. | Delegates title edit to `normalize_titles.handle_card()`; rules force search text to disappear. Distinct equal-title cards are allowed. | After editor returns `saved`, `await_advance()` requires a **second stable observation** of the next card or empty results; `QueueCounter.verified()` is the only queue-count advance. | Pending state blocks the next edit when advancement uncertain. A failure inside `handle_card()` may mean Save was clicked even though `was_saved` remains false. No retry. |
| `visible_order_rename` | User supplies names and optional `N:` start; takes frozen visible grid; `check_snapshot()` verifies full geometry and assigned-art fingerprints before each card; manual scrolling only between batches. | `replace_entire_title` rule delegates to `normalize_titles.handle_card()`; identical title may skip. | `saved` / exact unchanged `skipped` counts as completed position after editor returns to list; does **not** re-open saved card; next position gets fresh grid check. | `Exception` causes `batch_stopped`, pending position, local diagnostic and immediate stop. `KeyboardInterrupt` is not caught in `process_batch()`'s `except Exception`: it propagates without retry but may lack a structured batch stop event. |

### Non-negotiable common boundaries

1. A chosen card must be checked again before opening or editing; a title is **not** a stable unique item ID.
2. Read actual title from editor; apply workflow-specific business rule **outside** the common GUI port; exact readback must match proposed title before Save.
3. `Save` is a side effect: mark its attempt **before** dispatching the click. Do not retry after an exception, timeout, cancellation, Escape, or lack of confirmation.
4. UI list return is **not** cloud synchronization and **not** queue advance. Only the original workflow can perform its own verification.
5. Skip/preview/cancel before Save must not click Save. Do not reopen a card just to reconfirm a success when existing workflow uses a stable list observation.
6. Keep four top-level workflows, existing CLI prompts/options, image thresholds, scroll rules, coordinate conversion, PyAutoGUI/cliclick, and local diagnostic behavior unchanged in Phase 0.

## 2. Future interfaces, coordinated in Phase 0

The new **pure** module `doumao/core/title_edit_contract.py` defines:

- `TitleEditPort` (`Protocol`), implemented by a **per-operation** adapter later: `read_title()`, `replace_title(new)`, `read_back_title()`, `verify_save_ready()`, `click_save()`, `verify_list_return()`. No business-workflow globals or direct references to `LOG`, `CLICK`, `RUNTIME` or module-level current card.
- `SingleSaveGuard`, a per-card guard with `NOT_ATTEMPTED -> ATTEMPTED -> LIST_RETURN_CONFIRMED`. Mark `ATTEMPTED` **before** invoking `click_save()`. A second click is rejected even when the first raised. `confirm_list_return()` is never automatic.
- `EditResult`, a structured immutable result with `outcome`, `save_stage`, `original_title`, `proposed_title`, and `reason`. Valid terminal outcomes: `PREVIEW`, `SKIPPED`, `RETURNED_TO_LIST`, `FAILED_PRE_SAVE`, `CANCELLED`, `STOPPED`, `SAVE_UNCERTAIN`.
- `stopped_result()`: any exception, cancellation or interruption while Save is attempted and unconfirmed resolves to `SAVE_UNCERTAIN`, never a clean no-save result. A later logging error must not erase an already confirmed UI return.

**Port responsibilities:** The future adapter wraps only the editing dialog and accepts runtime dependencies explicitly (screen capture, click/press, image-to-screen converter, app assertion, wait/clock, event/log sink); it must preserve legacy behavior. The port itself does not discover cards, change search conditions, validate a visible grid, scroll the list, or apply naming rules.

**Workflow responsibilities:** A workflow chooses a card, preserves its own identity/selection validations, decides `skip`/`preview`, provides the explicit adapter, and only advances after its own verified postconditions. Metadata cleanup does not require the title-changing port; it can later share the side-effect guard/result primitives while retaining its separate fields and tag logic.

### Required mapping when migrating

| UI-stage result | Search queue policy | Visible-order policy | Rule-based titles policy | Metadata cleanup policy |
| --- | --- | --- | --- | --- |
| `PREVIEW` | Exit after first preview | No editor open in read-only grid preview | Return to list and skip saving | No Save in permitted preview path |
| `SKIPPED` | Do **not** assume search queue advanced; current matching head needs decision/stop | Only complete if old title equals exact assigned title | Count as unchanged, continue scanning | Not a completed cleanup |
| `RETURNED_TO_LIST` | Wait for stable `advanced` or `empty`, then count | Verify original position/grid contract for following item | Count local editor return as saved | Also require single log event and tag disappearance |
| `FAILED_PRE_SAVE` / `CANCELLED` / `STOPPED` | Stop or preview per existing flow; no Save | Stop current batch without advancing | Do not count save | Do not count save |
| `SAVE_UNCERTAIN` | Do not retry or start next card; record pending | Do not retry or continue batch; record pending | Do not retry; prompt manual check | Do not repeat cleanup; manual check needed |

A confirmed return to list must **not** be described as a guarantee of synchronization to the application's server. The queue's stable-advance check and visible-grid validation remain distinct policies.

## 3. Tests (offline, no Mac GUI interaction)

`tests/test_title_edit_contract.py` tests the new state machine: successful single attempt; refusal to double-click; exception during click; unconfirmed return; cancellation before/after click; keyboard interruption before/after click; failed pre-save validation; invalid result/stage combinations; independent guards per item; and later logging failure.

`tests/test_phase0_workflow_safety.py` is a **proposed** regression test for existing v3.5 modules, using synthetic item fingerprints and mocks: search queue success, failure inside editor, unconfirmed queue advance, cancellation and preview; visible-order success, first/second save failure, exact-title skip, and KeyboardInterrupt propagation. It has to be run from the real repository checkout before reporting a pass. Its mock is at the existing `handle_card()` boundary; it **cannot** directly prove the lower-level actual Save button is clicked at most once.

`tests/test_phase0_title_save_boundary_macos.py` adds **six** mocked, Mac-import-only tests against the actual `normalize_titles.handle_card()` Save-click boundary (success, preview, failed readback, post-click list timeout, click exception, and KeyboardInterrupt). These are staged but **not run on a Mac in this session**; source and UI imports must be verified there.

**Additional tests to add before production migration:** `metadata_editor.clean_current()`/`batch_cleaner.run_one()` failure-injection when a click succeeds but the subsequent capture/log/return fails. Use fail-injection immediately before and immediately after the click to distinguish true `NOT_ATTEMPTED` and unknown `ATTEMPTED`. Keep the original GUI semantics unchanged.

## 4. Real screenshot regression: smallest viable private corpus

Use synthetic drawings for public tests. The **private** corpus for visual regression should live **outside** the Git tree, for example `~/.doumao-automation/private-fixtures/phase0/`; no real title or artwork should appear in repository fixtures, test failure messages, uploaded PRs, GitHub Actions artifacts or the public patch.

**Likely reusable local-only images** (check actual availability first):

- `~/.doumao-automation/runtime/visible_order_capture_failed.png` — raw failure frame if previously generated.
- `~/.doumao-automation/runtime/visible_order_preview.png` and `visible_order_diagnostic.png` — marked frames; not replacements for original raw pixels.
- `~/.doumao-automation/runtime/search_queue_diagnostic.png` — queue-failure frame, if generated.
- `~/doumao-automation/screenshots/` — existing preview/diagnostic images from early workflows, if still present.

**Request from the user's Mac only if missing** (for one initial known resolution and theme):

1. Clean list with a complete 12-card grid, and a list with a partial last row / cropped boundary card.
2. Two stable, successive list observations plus a deliberately shifted/changed card; if existing screenshots cannot cover all conditions, collect new private frames.
3. Editor scrolled to top with title field and Save button visible; editor at bottom with tag controls and Save visible.
4. Search queue first-head before Save, stable next-head after Save, and stable empty result (including delayed-loading ambiguity if reproducible).

Start with approximately **8–10 distinct private source frames**; derive copies/perturbations in tests where valid. Treat this as a minimum candidate, not proof of every UI state. Preserve native screenshot resolution and coordinate metadata. Do **not** upload the frames to public GitHub or embed them in test output. The code patch here contains no screenshot assets.

## 5. Recommended migration order — not approved for Phase 0

1. Finish baseline tests and local screenshot inventory; record a clean local branch and working-tree state before any integration.
2. Adapt the shared title editor with an injected per-operation port and `SingleSaveGuard`; parity-test first in **preview**, then one-item real Mac testing. Preserve exact readback/save/list behavior.
3. Move `normalize_titles` to that adapter (already the shared execution site); validate its old CLI, skip and readback behavior.
4. Validate `search_queue_rename` against same adapter with stricter post-save queue transition and no `ui.LOG` / `ui.DIAGNOSTIC` global mutation; then test `visible_order_rename` while retaining its independent grid checks and manual batch scroll.
5. Last, consider introducing common save-result reporting into metadata cleanup. It retains a separate note/tag editor and independent verification; avoid forcing title-specific functions into it.
6. Only after successful automated and real Mac regressions consider targeted larger refactors. No wholesale redesign, no new dependencies, and no borrowed GPL/AGPL code.

## 6. Known phase-0 risks / not done

- `GitHub` exposes committed remote state, **not** `git status` or uncommitted changes on the user's Mac.
- The provided sandbox has no original repository checkout and cannot clone GitHub. The historical **132 passed** is a README claim, not a new test result.
- Existing search queue's `was_saved` flag is updated only after editor completion; it does not accurately classify post-click exceptions inside the editor. The proposed new guard would address this in a future migration.
- The visible-order batch uses `except Exception`, not `KeyboardInterrupt`, when writing stop events. It still stops but may omit the structured pending log on Ctrl+C.
- Local screenshot inventory and real Mac GUI checks are outstanding.
- The public GitHub branch, `main`, production modules and all existing user files remain untouched by the staged patch.
