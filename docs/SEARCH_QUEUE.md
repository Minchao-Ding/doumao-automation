# Search-result queue renaming · technical design

## Scope and provenance

This workflow is integrated into the existing `doumao` package, not a second application. It reuses the established card detection (`workflows/normalize_titles.py`), title read/write/readback, `core/navigation.py` detail modal detection, `core/batch_cleaner.py` save-return logic, and `core/scrolling.py` image-change measurement. The previous standalone search-queue experiment was successfully used by the project owner on 34 artworks; one other artwork did not require a title change. The previous script and its historic versioned dependencies are **not** included in this branch.

The user identified two real integration bugs: a false detail-modal detection when only one card remained in the search view, and the false assumption that equal original titles mean the same artwork. The navigation fix is placed in the shared module; the queue has no `seen_titles` set.

## Execution contract

The user chooses the target collection and enters the search filter in the application. The search term must disappear from each changed title. CLI validation and a title-specific postcondition both enforce this. The tool pauses for five seconds after launch for switching to the app, with no extra console confirmation prompt.

One cycle is:

1. Confirm list view and scroll search results to top.
2. Capture visible queue head (and any next visible card).
3. Open first artwork and read its full title via the clipboard.
4. Compute a transform: exact one-prefix removal or literal text replacement.
5. Reject titles outside the rule or those still matching the active search after transform.
6. Read old title again, edit only the title, read back the entire new title, click Save once.
7. Wait for the editor to close; observe the search queue advance or remain stably empty, with confirmation across two observations.
8. Count a successful edit **only after** confirming the queue transition. If uncertain, stop without another Save.

The full collection scan/thumbnail-dedup logic is not used in search-queue mode. Other workflows have their own traversal strategies.

## Identity, duplicate names, and ambiguity

Equal titles can belong to different artworks. They are never treated as duplicate IDs. A small-shift-tolerant thumbnail comparison verifies queue movement: if the old second card was visible and distinguishable, it should become the new head. If the old view contained only one fully visible card, a different stable thumbnail can indicate a new head. Stable empty results are a separate completion signal.

Two artworks with identical titles **and indistinguishable thumbnails** cannot be proven distinct using the current screenshot interface. That situation remains a conservative stop, not an automatic skip or duplicate edit. A future stable in-app ID or independent result counter would be needed for stronger identity proof.

## Save state and stopping

Saved count is distinct from inspected count and pending/uncertain save. Count ends when the requested number of *verified* edits is reached or when the search result is demonstrably empty, whichever occurs first. Failed Save, delayed refresh, disappearing modal, layout change or ambiguous next card stops the run, preserving a local JSONL event trail and screenshot when possible. All run artifacts are stored outside Git at `~/.doumao-automation/runtime/`.

## Local-only configuration and public hygiene

All collection names, personal artwork names and replacement strings are CLI inputs or a local JSON file. `examples/queue_rename.example.json` contains fictional strings only. Commit Python sources, tests, this document, and the sample; do not commit `runtime`, real screenshots, personal log files, or local configuration.

## Current validation

The refactored GUI engine has not received a full new Mac regression in this branch. Pure logic tests, synthetic OpenCV modal tests and mocked workflow tests can pass offline but do not prove actual application saves. Testing should proceed one item, then several distinct items, then the target batch; preserve the result of every failure and user decision in the private development log.
