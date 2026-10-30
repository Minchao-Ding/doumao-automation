# Doumao Automation

**Computer Vision–Based macOS GUI Automation for Perler Bead Pattern Management**

An AI-assisted Python automation project developed to streamline the organization and maintenance of a personal Perler bead pattern library.

Doumao Automation uses computer vision and GUI interaction to identify patterns, navigate editing interfaces, update metadata, and process collections through repeatable workflows.

## Project Highlights

| Metric                      | Result |
| --------------------------- | ------ |
| Patterns organized          | **30** |
| Pattern titles standardized | **12** |
| Core automation workflows   | **2**  |
| Automated tests passed      | **9**  |

The project was developed and validated using the *Drinks* collection in Doumao, a desktop application for managing Perler bead patterns.

## Key Features

### 1. Automated Metadata Cleanup

Identifies patterns requiring metadata updates and performs the editing workflow automatically.

- Detects tagged pattern cards using OpenCV.
- Opens pattern details and navigates to the editing interface.
- Clears notes and removes selected tags.
- Dynamically relocates UI elements as tags are removed.
- Saves changes and verifies the updated list view.
- Skips patterns that do not meet the processing criteria.

### 2. Rule-Based Title Standardization

Reads pattern titles directly from the editing interface and applies configurable naming rules.

For example:

```text
Before: Vitamin Water Peach
After:  Vitamin Water｜Peach

Before: Vitamin Water Lemon
After:  Vitamin Water｜Lemon
```

The workflow:

1. Discovers pattern cards from the collection view.
2. Opens each pattern and retrieves its original title.
3. Evaluates the title against a transformation rule.
4. Applies the change when appropriate.
5. Reads back the updated title to verify correctness.
6. Saves the update and continues scanning.

Title transformations are separated from GUI operations, allowing new naming rules to be introduced independently.

### 3. Computer Vision and GUI Navigation

The automation framework combines screenshot analysis with mouse and keyboard interaction to work with Doumao's visual interface.

Core capabilities include:

- Pattern card and tag detection
- Modal window and editing control recognition
- Dynamic UI element positioning
- Screenshot-based navigation
- Scroll position adjustment and recovery
- Visual confirmation of completed actions

### 4. Validation and Error Handling

The project incorporates checks throughout the editing process.

- Original-title verification before modification
- Post-edit title verification
- Dynamic re-detection of selected tags
- Save-state and interface-transition checks
- Diagnostic screenshots and structured operation logs
- Safe termination when interface elements cannot be reliably identified

These mechanisms support consistent batch processing while reducing the risk of unintended changes.

## Technology Stack

| Technology                    | Application                                                   |
| ----------------------------- | ------------------------------------------------------------- |
| Python                        | Workflow orchestration and automation logic                   |
| OpenCV                        | Image processing and UI element detection                     |
| NumPy                         | Image array operations and comparisons                        |
| PyAutoGUI                     | Screenshot capture, mouse, keyboard, and scrolling automation |
| Pillow                        | Image handling                                                |
| cliclick                      | macOS mouse interaction                                       |
| AppleScript / macOS utilities | Application interaction and supporting operations             |
| JSON                          | Naming rules and configuration                                |
| Python unittest               | Automated tests                                               |

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

This structure provides a foundation for extending the project to additional pattern collections and metadata workflows.

## Getting Started

### Requirements

- macOS
- Python 3.11 or compatible version
- Doumao desktop application
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

### Preview Pattern Detection

Open the target collection in Doumao and close any editing windows.

```bash
python -m doumao preview
```

This command generates a visual preview of detected pattern cards.

### Preview Title Standardization

```bash
python -m doumao titles --limit 1
```

The title workflow reads and evaluates the title without saving changes.

### Run an Automation Workflow

**Metadata cleanup:**

```bash
python -m doumao clean --auto-save --confirm-folder drinks --limit 1
```

**Title standardization:**

```bash
python -m doumao titles --auto-save --confirm-folder drinks --limit 1
```

The `--limit` parameter controls the number of patterns processed in a run. The `--confirm-folder` parameter provides an explicit confirmation of the selected collection.

## Development and Iteration

The project evolved through iterative testing in the actual macOS application.

Key development improvements included:

- Transitioning from fixed coordinates to visual UI element detection
- Repositioning dynamically changing controls after each interaction
- Handling retained scroll positions between editing sessions
- Introducing screenshot-based diagnostics and safe-stop behavior
- Refining scroll intervals based on observed application responsiveness
- Separating title-reading logic from metadata editing
- Improving pattern deduplication and collection traversal
- Refactoring experimental scripts into reusable modules

The metadata cleanup and title-standardization workflows were validated in real use. The refactored project has also passed nine automated tests and a macOS read-only interface preview.

Additional technical decisions and version history are documented in [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) and [`docs/VERSIONS.md`](docs/VERSIONS.md).

## Future Development

The next development priorities are:

- Improve pattern deduplication across scrolling positions
- Optimize collection traversal and scrolling efficiency
- Expand configurable naming and metadata rules
- Support additional pattern collections through reusable workflows
- Extend automated testing for GUI interactions

## AI-Assisted Development

This project was developed through human–AI collaboration.

The project owner defined the requirements, observed application behavior, conducted real-world testing, and guided key design decisions. AI assisted with Python implementation, computer vision techniques, debugging, and code refactoring.

The development process emphasizes practical problem-solving, iterative validation, and maintainable automation design.