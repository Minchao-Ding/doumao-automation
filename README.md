# Doumao Automation

**Computer Vision–Based macOS GUI Automation for Visual Asset Library Management**

Doumao Automation is a personal Python project that uses OpenCV, screenshots, and controlled macOS GUI interaction to organize titles and metadata in a desktop visual asset library. Users prepare the target collection or search results in the application; the tool applies the selected workflow without relying on an official API.

## Project Highlights

| Milestone | Result |
| --- | --- |
| Metadata cleanup | **30-item collection** organized |
| Rule-based title standardization | **11 titles** automatically standardized |
| Search-result queue renaming | **34 titles** renamed |
| Visible-order batch renaming | **176 items** renamed in one collection |
| CLI workflows | **4** |
| Automated regression tests | **282/282 passed** after Stage 4 |

## Key Features

### 1. Metadata Cleanup

- Detects eligible tagged cards, opens the editor, and checks the original title.
- Clears notes and selected tags using collection-specific rules, re-detecting controls as the interface changes.
- Records structured results and save stages independently of diagnostic JSONL logs.

### 2. Rule-Based Title Standardization

- Reads titles from the editor and applies configurable transformations.
- Separates naming rules from GUI operations, with title verification and read-only evaluation.

### 3. Search-Result Queue Renaming

- Processes a search list manually filtered in the application.
- Supports exact-prefix removal and literal text replacement.
- Uses title readback, artwork comparison, and queue-transition checks to verify each update, including cases where items share the same title.

See [Search-result queue design](docs/SEARCH_QUEUE.md).

### 4. Visible-Order Batch Renaming (v3.5)

- Assigns user-supplied names to visible card positions, ordered left to right and top to bottom.
- Supports starting positions such as `3:`, short batches, quoted names containing spaces, and ignoring excess names beyond the current grid.
- Checks card geometry, position stability, and image identity before edits. Supports successive batches with manual scrolling.
- Provides `--preview` to inspect numbered card positions without opening or saving items.

See [Visible-order usage](docs/VISIBLE_ORDER.md).

## Reliability and Safety

The shared editing architecture includes title readback, foreground and layout checks, single-save guards, explicit save states, and conservative error handling. If a card's identity, an interface transition, or a save result is uncertain, execution stops rather than guessing or repeating a potentially completed save. Returning to the list does not establish cloud synchronization.

Private screenshots and JSONL diagnostics remain outside the Git repository, under `~/.doumao-automation/runtime/`.

## Architecture

```text
doumao-automation/
├── doumao/
│   ├── __main__.py                 # CLI and guarded commands
│   ├── title_rules.py              # Title transformations
│   ├── rules/                      # Collection-specific configuration
│   ├── core/
│   │   ├── artwork.py              # Shared image comparison
│   │   ├── grid_detector.py        # 12-card full-grid detection
│   │   ├── partial_grid_detector.py # 4/8-card grid detection
│   │   ├── grid_selection.py       # Detection and fallback order
│   │   ├── screen_capture.py       # Shared screenshot conversion
│   │   ├── visible_order_state.py  # Position and identity checks
│   │   ├── title_edit_contract.py  # Save-state contracts
│   │   ├── title_editor.py         # Shared title editing
│   │   ├── title_gui.py            # GUI editing adapter
│   │   └── ...                     # Navigation and metadata helpers
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

The four workflows retain their own selection rules while sharing validated visual recognition, editing, and result-handling components.

**Stack:** Python 3.10+, OpenCV, NumPy, PyAutoGUI, Pillow, `cliclick`, AppleScript/macOS utilities, JSON/JSONL, and `unittest`.

## Getting Started

**Requirements:** macOS, the target desktop application, Python 3.10+, Homebrew, and Accessibility/Screen Recording permissions for the automation environment.

```bash
brew install cliclick
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m doumao doctor
```

Run the regression suite:

```bash
python -m unittest discover -s tests -v
```

### Visible-Order Renaming

Open the intended collection and arrange a stable grid. Check the detected positions first:

```bash
python -m doumao visible-order --preview
```

Once the layout is verified, run the interactive editing workflow:

```bash
python -m doumao visible-order
```

Example input:

```text
3: Sample_A Sample_B "Sample C"
```

After submitting a batch, switch back to the application during the five-second countdown. The application does not scroll automatically between batches. Enter `退出` to finish.

### Other Workflows

Read-only title standardization:

```bash
python -m doumao titles --limit 1
```

Collection-specific metadata cleanup (writes and saves; manually confirm the configured collection):

```bash
python -m doumao clean --auto-save --confirm-folder drinks --limit 1
```

Read-only search-result queue preview (after applying the search filter in the application):

```bash
python -m doumao search-queue --mode remove-prefix --search 'DRAFT-' --prefix 'DRAFT-' --limit 1
```

Use `python -m doumao --help` and each command's `--help` for the available options. The metadata cleanup command is intentionally scoped to its configured collection, not a general-purpose selective tag editor.

## Development and Validation

| Stage | Engineering milestone | Tests passed |
| --- | --- | --- |
| 0 | Safety contracts and regression baseline | 179/179 |
| 1 | Shared title-editing core and GUI adapter | 214/214 |
| 2 | 4/8/12-card grid recognition and safeguards | 227/227 |
| 3 | Structured metadata results and save-state tracking | 255/255 |
| 4 | Shared image matching, grid selection, and screenshot conversion | **282/282** |

Validation combines local macOS `unittest` runs with real application checks: Stage 2 verified two four-card save scenarios, Stage 3 verified a one-item metadata cleanup save, and Stage 4 verified a 12-card read-only position preview. The milestone counts above come from different historical workflows; neither the local test suite nor these checks establish compatibility with every GUI layout or theme.

## Known Limitation and Next Steps

An initial folder view containing subfolders, two complete card rows, and a partially visible third row may fail grid validation. The observed failure stopped without opening or saving items. For now, scroll to a continuous, fully visible grid and confirm the mapping with `visible-order --preview` before editing.

Future work includes targeted mixed-layout recognition, a macOS workflow-selection interface, selective tag editing, and evidence-based multi-theme support.

## Development Collaboration

The project owner defined requirements, editing rules, and safety boundaries; supplied real screenshots and logs; performed macOS tests; and verified outcomes. AI assisted with Python/OpenCV implementation, debugging, test design, and incremental refactoring.

Additional notes: [Development summary](docs/DEVELOPMENT.md), [Historical versions](docs/VERSIONS.md), [Search queue](docs/SEARCH_QUEUE.md), and [Visible order](docs/VISIBLE_ORDER.md).
