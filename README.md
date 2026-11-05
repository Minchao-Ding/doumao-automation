# Doumao Automation

**Computer Vision–Based macOS GUI Automation for Visual Asset Library Management**

Doumao Automation is a Python tool for organizing visual assets in a macOS desktop application. It combines computer vision and GUI automation to locate item cards, edit titles and metadata, and process collections through reusable workflows.

## Project Highlights

| Milestone | Result |
| --- | --- |
| Metadata-cleanup collection | **30 items** organized |
| Rule-based title standardization | **11 titles** automatically standardized |
| Search-result queue renaming | **34 titles** renamed |
| Visible-order collection | **176 items** organized |
| Automation workflows | **4** |
| Automated regression tests | **132 passed** |

## Key Features

### 1. Automated Metadata Cleanup

Processes item metadata through visual detection and GUI interaction.

- Locates item cards, detail views, and editing controls using screenshots.
- Clears notes and removes selected tags according to the workflow rules.
- Re-detects controls as the layout changes after each removal.
- Saves updates and checks the return to the collection view.

### 2. Rule-Based Title Standardization

Reads item titles in the editor and applies configurable naming rules.

- Separates title-transformation rules from GUI navigation.
- Reads the original title and verifies the updated text before saving.
- Processes matching items and retains other titles.
- Supports preview and bounded batch processing.

### 3. Search-Result Queue Renaming

Renames items sequentially within a search result list filtered in the desktop application.

- Removes an exact prefix or replaces specified text.
- Opens the current result, updates its title, and checks the result-list transition after saving.
- Handles different items with identical titles.
- Tracks completed edits, uncertain saves, and queue completion.
- Produces structured logs and diagnostic screenshots.

See [Search-result queue design](docs/SEARCH_QUEUE.md).

### 4. Visible-Order Batch Renaming (v3.5)

Renames cards in their displayed grid order using names supplied through the terminal.

- Detects and orders cards from grid geometry and screenshots.
- Accepts a one-line list of names, with an optional starting position such as `3:`.
- Supports short batches and pasted lists longer than the available grid capacity.
- Processes names that fit the current fully visible cards and reports any extras skipped for that batch.
- Replaces the complete title, reads back the new value, saves, and returns to the list.
- Supports consecutive batches in a single terminal session, with manual scrolling between screens.
- Uses layout checks and shift-tolerant image comparison for reliable card selection.

The workflow was used to organize a **176-item collection** on macOS.

See [Visible-order usage](docs/VISIBLE_ORDER.md).

## Technology Stack

| Technology | Purpose |
| --- | --- |
| Python | Workflow orchestration and command-line interface |
| OpenCV and NumPy | Card detection, grid geometry, and image comparison |
| PyAutoGUI and `cliclick` | Screenshot capture and macOS GUI control |
| Pillow | Image handling |
| AppleScript / macOS utilities | Desktop interactions |
| JSON | Naming rules, configuration, and operation logs |
| `unittest` | Automated regression testing |

## Project Structure

```text
doumao-automation/
├── doumao/
│   ├── __main__.py                # CLI entry point
│   ├── title_rules.py             # Title transformations
│   ├── rules/                     # Rule configurations
│   ├── core/
│   │   ├── grid_detector.py       # Card-grid detection
│   │   ├── visible_order_state.py  # Batch parsing and layout checks
│   │   └── ...                    # Shared GUI components
│   └── workflows/
│       ├── clean_metadata.py
│       ├── normalize_titles.py
│       ├── search_queue_rename.py
│       └── visible_order_rename.py
├── tests/
├── docs/
│   ├── SEARCH_QUEUE.md
│   ├── VISIBLE_ORDER.md
│   ├── DEVELOPMENT.md
│   └── VERSIONS.md
├── examples/
├── requirements.txt
├── pyproject.toml
├── run.command
└── README.md
```

Each workflow has its own item-selection strategy and uses shared components for visual recognition, navigation, editing, and saving.

## Getting Started

### Requirements

- macOS
- Python 3.10+
- The target desktop library application
- Accessibility and Screen Recording permissions
- Homebrew and `cliclick`

Install the dependencies from the project directory:

```bash
brew install cliclick
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Check the environment and run the tests:

```bash
python -m doumao doctor
python -m unittest discover -s tests -q
```

### Visible-Order Renaming

Open the target collection in the desktop application and position the list so the cards to rename are fully visible.

```bash
python -m doumao visible-order
```

Enter the new titles on one line:

```text
3: Sample_A Sample_B "Sample C" Sample_D
```

The example starts at the third visible card. Without a position prefix, the batch starts at the first card. Quotation marks group titles containing spaces.

After submitting a batch, switch to the desktop application during the five-second countdown. The program renames the selected visible cards and then prompts for the next batch. Scroll to the next screen manually when needed.

If the input contains more names than the visible positions can accommodate, the program processes the fitting names and reports the remaining count. Paste the remaining names in a later batch. Enter `退出` to finish.

For a read-only card-position preview:

```bash
python -m doumao visible-order --preview
```

### Other Workflows

Preview card detection:

```bash
python -m doumao preview
```

Preview rule-based title standardization:

```bash
python -m doumao titles --limit 1
```

Run metadata cleanup or rule-based title standardization with the configured sample collection:

```bash
python -m doumao clean --auto-save --confirm-folder drinks --limit 1
python -m doumao titles --auto-save --confirm-folder drinks --limit 1
```

Run search-result queue renaming after applying a matching search filter in the application:

```bash
python -m doumao search-queue --mode remove-prefix --search 'DRAFT-' --prefix 'DRAFT-' --limit 1 --auto-save --confirm-selection
```

See the workflow documentation for additional options and usage examples.

## Validation and Development

The project includes **132 automated tests** covering title rules, input parsing, grid detection, workflow transitions, and error handling. Development has combined automated regression testing with macOS GUI testing across metadata cleanup, title standardization, search-result queues, and visible-order renaming.

Key improvements include dynamic control detection, title readback before saving, queue-transition verification, flexible batch sizes, and shift-tolerant card comparison.

The next development stage focuses on **code-structure review and targeted refactoring**: consolidating reusable GUI operations, simplifying workflow dependencies, and maintaining the tested interaction behavior.

Additional background: [Development notes](docs/DEVELOPMENT.md) · [Version notes](docs/VERSIONS.md).
