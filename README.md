# Doumao Automation

**Computer Vision–Based macOS GUI Automation for Visual Asset Library Management**

Doumao Automation is a personal Python project for maintaining a visual asset library in a macOS desktop application. It combines screenshots, OpenCV-based recognition, and guarded GUI actions to locate items, update titles and metadata, and process batches without an official application API.

The user manually opens the appropriate collection and prepares the list or search filter. The tool does not identify the subject of artwork or choose its classification automatically.

## Project Highlights

| Milestone | Evidence and scope |
| --- | --- |
| Metadata cleanup | A **30-item collection** was organized in earlier macOS use |
| Rule-based title standardization | **11 titles automatically standardized**, plus **1 manually corrected** |
| Search-result queue renaming | **34 titles renamed** with the earlier validated workflow |
| Visible-order batch renaming | **176 items renamed** in one macOS collection (v3.5 functional validation) |
| CLI workflows | **4** independent workflows |
| Automated regression suite | **282 / 282 passed** in the owner's local macOS environment after Stage 4 |

These milestones came from different workflows and validation periods; they are **not** a count of unique items across the project. The historical results do not mean that every workflow has been fully revalidated end to end after each refactor. The test count reflects a local `unittest` run, not GitHub Actions CI.

## Workflows

### 1. Metadata Cleanup

- Detects qualifying tagged cards, opens the edit interface, and verifies the original item title.
- Clears notes and selected tags in a collection-specific workflow.
- Re-detects controls after each tag removal instead of reusing potentially stale click points.
- Performs one guarded Save attempt and observes the return to the list and visible tag changes.
- Reports structured results and save stages independently of JSONL diagnostic logging.

The configured cleanup workflow is **not** a generic add/remove-any-tag feature. It requires manual confirmation of the intended collection.

### 2. Rule-Based Title Standardization

- Reads original titles from the editor and applies configurable text-transformation rules.
- Separates naming rules from interface navigation and editing code.
- Verifies the proposed title before saving, with a preview/read-only mode and bounded processing.
- Skips out-of-scope titles and stops on ambiguous interface states.

### 3. Search-Result Queue Renaming

- Processes a search result list already filtered by the user in the application.
- Supports exact-prefix removal and literal text replacement.
- Verifies the title readback and that the search term no longer matches after a change.
- Uses artwork comparison and queue-transition checks; equal titles alone do not establish item identity.
- Stops rather than blindly retrying when a save or queue transition is uncertain.

The **34 renamed titles** are from a previously validated workflow. The refactored queue has automated safety and state-transition coverage, but that historical number is not a new complete macOS acceptance run for its refactored version.

See [Search-result queue design](docs/SEARCH_QUEUE.md).

### 4. Visible-Order Batch Renaming (v3.5 Functional Baseline)

- Associates user-supplied titles with currently visible card positions, left to right and top to bottom.
- Supports start positions such as `3:`, shorter batches, quoted names containing spaces, and inputs longer than the available grid capacity.
- Ignores excess names for the current batch without automatically carrying them into the next batch.
- Checks grid geometry, card order, and selected artwork fingerprints before editing.
- Uses the most recently verified click position, reads back the new title, and does not reopen a successfully saved card.
- Supports consecutive batches, with manual scrolling between screens.
- Includes a **read-only** `--preview` mode that neither opens items nor saves.

The workflow was used to rename a **176-item collection** on macOS. See [Visible-order usage](docs/VISIBLE_ORDER.md).

## Safety Design

Screenshot-based interaction is sensitive to changing layouts and cannot rely on stable application item IDs. The implementation therefore:

- Checks foreground application, list and editor states, card geometry, and title identity at relevant stages.
- Distinguishes **not attempted**, **attempted but unconfirmed**, and **list return confirmed** save stages. Returning to the list does **not** prove cloud sync.
- Does not retry a Save click when its delivery or outcome is uncertain.
- Stops when card boundaries, artwork identity, dialogs, or post-save transitions cannot be established safely.
- Stores personal screenshots and diagnostic JSONL files outside the Git repository.
- Retains PyAutoGUI's mouse-to-upper-left emergency stop.

Always test an unfamiliar layout with `--preview`, verify that the marked positions are correct, and manually check actual edits in the application.

## Architecture

```text
doumao-automation/
├── doumao/
│   ├── __main__.py                    # CLI and guarded command handling
│   ├── title_rules.py                 # Rule-based title transformations
│   ├── rules/                         # Collection-specific configurations
│   ├── core/
│   │   ├── artwork.py                 # Shared image matching
│   │   ├── grid_detector.py           # Complete 4 × 3 grid detection
│   │   ├── partial_grid_detector.py   # Complete 4-card / 8-card layouts
│   │   ├── grid_selection.py          # Conservative detector selection
│   │   ├── screen_capture.py          # Shared screenshot conversion
│   │   ├── visible_order_state.py     # Ordering, identity and stability
│   │   ├── title_edit_contract.py     # Structured results and save stages
│   │   ├── title_editor.py            # Shared editing transaction
│   │   ├── title_gui.py               # macOS title GUI adapter
│   │   ├── list_view.py               # List-view safety checks
│   │   └── ...                        # Other navigation/metadata helpers
│   └── workflows/
│       ├── clean_metadata.py
│       ├── normalize_titles.py
│       ├── search_queue_rename.py
│       └── visible_order_rename.py
├── tests/
├── docs/
├── examples/
├── requirements.txt
├── pyproject.toml
├── run.command
└── README.md
```

Workflow-specific selection rules are separated from shared visual recognition, title editing, and save-state contracts. The code retains different GUI safety checks where combining them would change established behavior.

## Technology

Python 3.10+, OpenCV, NumPy, PyAutoGUI, Pillow, `cliclick`, AppleScript/macOS utilities, JSON/JSONL, and Python `unittest`.

## Getting Started

**Requirements:** macOS, the target desktop application, Python 3.10+, Homebrew, and Accessibility/Screen Recording permissions for the automation environment.

From the repository root:

```bash
brew install cliclick
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m doumao doctor
```

Run the automated tests:

```bash
python -m unittest discover -s tests -v
```

### Visible-Order Preview (No Changes)

Open the correct collection in the application and arrange a stable four-column grid:

```bash
python -m doumao visible-order --preview
```

Enter a test name, inspect the numbered preview screenshot, and enter `退出` to finish. This mode does not edit or save.

### Visible-Order Renaming (Writes Titles)

Only after verifying the selected collection and the visible positions:

```bash
python -m doumao visible-order
```

Example input:

```text
3: Sample_A Sample_B "Sample C"
```

The user has five seconds to switch back to the application after submitting a batch. The tool never automatically switches collections or scrolls between screens.

### Other CLI Operations

Read-only title-rule evaluation:

```bash
python -m doumao titles --limit 1
```

Metadata cleanup (**writes and saves**; only for the configured collection, manually confirmed):

```bash
python -m doumao clean --auto-save --confirm-folder drinks --limit 1
```

Read-only search-result queue evaluation, after manually applying the indicated filter:

```bash
python -m doumao search-queue --mode remove-prefix --search 'DRAFT-' --prefix 'DRAFT-' --limit 1
```

Do not reuse the configured metadata-cleanup rules for unrelated collections. Additional write-mode commands require explicit CLI confirmation and appropriate verification.

## Development and Verification

| Stage | Scope | Regression result |
| --- | --- | --- |
| 0 | Baseline contracts and safe-stop regression tests | 179 / 179 |
| 1 | Shared title editor, result contracts, GUI adapter | 214 / 214 |
| 2 | Partial grids and safeguards against false complete-grid matches | 227 / 227 |
| 3 | Structured metadata results and separation from JSONL logging | 255 / 255 |
| 4 | Shared artwork comparison, detector selection, screenshot conversion | **282 / 282** |

Stage 2 also passed controlled real-save tests on four cards in a one-row layout and four cards in the second row of a two-row layout. Stage 3 passed a one-item real metadata-cleanup save with manual verification. Stage 4 passed a **12-card read-only positioning check** on macOS. Stage 4 did not repeat real saves, because its changes were limited to shared infrastructure and guarded by regression tests.

The automated test results are from the owner's **local Mac**, not a hosted continuous-integration system. These results do not establish compatibility with every application theme, screen size, or layout.

## Known Limitations

- **Initial mixed layout:** When subfolder/search/filter controls appear above two complete rows of cards and a third row is partially visible, the detector may report missing or duplicate columns and **stop without opening or saving an item**. Manually scroll to a verified continuous grid and use `visible-order --preview` before writing. Fixing this is deferred to a separate stage; safe stopping does not mean this layout is already supported.
- Grid identification assumes stable four-column cards in known interface conditions; unusual themes, scaling, incomplete loading, or occlusions may trigger a stop.
- The legacy fallback scanner retains some theme-specific color assumptions.
- Visually indistinguishable artworks may not provide enough evidence for automatic identity confirmation.
- A confirmed list return is not proof of successful cloud synchronization.

## Planned Work

- Diagnose mixed-layout recognition using a retained **private** failure screenshot; retain conservative stop behavior.
- Add a macOS workflow-selection interface while reusing the current Python backend.
- Build selective tag addition/removal as a separate workflow; it is not included in the current cleanup tool.
- Expand cross-theme support only with real screenshot evidence and focused regressions.

## Development Collaboration

The project owner identified practical needs, defined editing and safety rules, provided screenshots and logs, tested on macOS, verified results, and guided implementation choices. AI assisted with Python/OpenCV implementation, test design, debugging, architecture review, and incremental refactoring.

Additional documentation: [Development summary](docs/DEVELOPMENT.md), [Historical versions](docs/VERSIONS.md), [Search queue](docs/SEARCH_QUEUE.md), and [Visible order](docs/VISIBLE_ORDER.md).
