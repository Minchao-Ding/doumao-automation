# Doumao Automation

**Computer Vision–Based macOS GUI Automation for Personal Visual Asset Library Management**

A Python automation project developed to streamline the organization and maintenance of a personal visual asset library.

Doumao Automation uses computer vision and GUI interaction to identify library items, navigate editing interfaces, update metadata, and process collections through repeatable, rule-based workflows.

## Project Highlights

| Metric | Result |
| --- | --- |
| Library items organized | **30** |
| Titles standardized | **12** |
| Core automation workflows | **2** |
| Automated tests passed | **9** |

The first use case was a 30-item collection in a macOS desktop library application, covering metadata cleanup and title standardization.

## Key Features

### 1. Automated Metadata Cleanup

Identifies library items requiring metadata updates and performs the editing workflow automatically.

- Detects tagged item cards using OpenCV.
- Opens item details and navigates to the editing interface.
- Clears notes and removes selected tags according to the processing rules.
- Dynamically relocates UI elements as tags are removed.
- Saves changes and verifies the updated list view.
- Skips items that do not meet the processing criteria.

### 2. Rule-Based Title Standardization

Reads item titles directly from the editing interface and applies configurable naming rules.

For example:

```text
Before: Sample Alpha
After:  Sample｜Alpha

Before: Sample Beta
After:  Sample｜Beta
```

The workflow:

1. Discovers item cards from the collection view.
2. Opens each item and retrieves its original title.
3. Evaluates the title against a transformation rule.
4. Applies the change when appropriate.
5. Reads back the updated title to verify correctness.
6. Saves the update and continues scanning.

Title transformations are separated from GUI operations, allowing new naming rules to be introduced independently.

### 3. Computer Vision and GUI Navigation

The automation framework combines screenshot analysis with mouse and keyboard interaction to work with a macOS desktop application's visual interface.

Core capabilities include:

- Item card and tag detection
- Modal window and editing control recognition
- Dynamic UI element positioning
- Screenshot-based navigation
- Scroll position adjustment and recovery
- Visual confirmation of completed actions

### 4. Validation and Error Handling

The project incorporates checks throughout the editing process.

- Original-title verification before modification
- Post-edit title verification
- Dynamic re-detection of selected tags after each removal
- Save-state and interface-transition checks
- Diagnostic screenshots and structured operation logs
- Safe termination when interface elements cannot be reliably identified

These checks connect each edit to the intended item and make failures easier to diagnose.

## Technology Stack

| Technology | Application |
| --- | --- |
| Python | Workflow orchestration and automation logic |
| OpenCV | Image processing and UI element detection |
| NumPy | Image array operations and comparisons |
| PyAutoGUI | Screenshot capture, mouse, keyboard, and scrolling automation |
| Pillow | Image handling |
| cliclick | macOS mouse interaction |
| AppleScript / macOS utilities | Application interaction and supporting operations |
| JSON | Naming rules and configuration |
| Python unittest | Automated tests |

## Project Architecture

The project organizes reusable GUI automation components and task-specific workflows under a unified command-line interface.

```text
doumao-automation/
├── doumao/
│   ├── __main__.py
│   ├── title_rules.py
│   ├── rules/
│   │   └── drinks.json
│   ├── core/
│   │   ├── tag_scanner.py
│   │   ├── navigation.py
│   │   ├── card_picker.py
│   │   ├── metadata_editor.py
│   │   ├── batch_cleaner.py
│   │   └── scrolling.py
│   └── workflows/
│       ├── clean_metadata.py
│       └── normalize_titles.py
├── tests/
├── docs/
├── requirements.txt
├── pyproject.toml
└── README.md
```

**Core modules** handle visual recognition, navigation, interaction, and scrolling.

**Workflow modules** coordinate metadata cleanup and title standardization.

**Rule modules** define naming transformations independently of the automation interface.

This separation enables new naming rules and collection-specific workflows to reuse existing GUI operations.

## Getting Started

### Requirements

- macOS
- Python 3.11 or a compatible version
- The target desktop library application
- Screen Recording and Accessibility permissions for the terminal application

Install the required dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Install `cliclick` using Homebrew:

```bash
brew install cliclick
```

### Environment Check

From the project root directory:

```bash
python -m doumao doctor
```

Run the automated tests:

```bash
python -m unittest discover -s tests -v
```

### Preview Item Detection

Open the target collection in the desktop application and close any editing windows.

```bash
python -m doumao preview
```

This command generates a visual preview of detected item cards.

### Preview Title Standardization

```bash
python -m doumao titles --limit 1
```

The title workflow reads and evaluates the original title without saving changes.

### Run an Automation Workflow

The following commands use the current collection configuration. Back up the collection and open the intended list before making changes.

**Metadata cleanup:**

```bash
python -m doumao clean --auto-save --confirm-folder drinks --limit 1
```

**Title standardization:**

```bash
python -m doumao titles --auto-save --confirm-folder drinks --limit 1
```

The `--limit` parameter controls the number of items processed in a run. The `--confirm-folder` parameter records the user's confirmation of the selected collection. Moving the mouse to the upper-left corner triggers PyAutoGUI's emergency stop.

## Development and Iteration

The project evolved through iterative testing in the actual macOS application.

Key development improvements included:

- Transitioning from fixed coordinates to visual UI element detection after encountering limited accessibility controls.
- Re-detecting tag removal buttons after each interaction because the remaining tags shift position.
- Handling retained scroll positions between editing sessions so title and notes fields can be found again.
- Introducing screenshot-based diagnostics, title readback, and safe-stop behavior for uncertain interface states.
- Refining scroll intervals and item selection when cards are partially visible at the screen edge.
- Separating title-reading and naming logic from metadata editing so the two workflows can be run independently.
- Improving collection traversal and investigating repeated item checks across scrolling positions.
- Refactoring experimental scripts into reusable modules, with independent workflow and rule components.

The metadata-cleanup and title-standardization workflows were validated through macOS use. The refactored project has passed nine automated tests and a read-only interface preview.

Additional technical decisions and version history are documented in [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) and [`docs/VERSIONS.md`](docs/VERSIONS.md).

## Future Development

The next development priorities are:

- Improve item deduplication across scrolling positions.
- Optimize collection traversal and scrolling efficiency.
- Expand configurable naming and metadata rules.
- Support additional collections through reusable workflows.
- Extend automated and end-to-end GUI regression testing.

## Development Collaboration

The project owner defined the requirements and editing rules, identified interface issues, performed macOS testing, and guided design decisions based on the results. AI assisted with Python implementation, computer vision techniques, debugging, and code refactoring.
