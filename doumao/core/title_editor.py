"""Shared per-card title edit transaction, independent of GUI and workflows.

The caller chooses the card, opens its editor and supplies a TitleEditPort.
It also owns artwork identity, queue advance, batch position checks and the
name-transform rule. This module alone orders title edits and Save attempts.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .title_edit_contract import (
    EditOutcome, EditResult, SaveStage, SingleSaveGuard, TitleEditPort,
    stopped_result,
)


class TitleEditFailure(RuntimeError):
    """An edit stopped; `result` distinguishes pre-save from uncertain Save.

    Workflow runners must stop on this exception. They may inspect the result
    to write an accurate pending-item log, but must never retry the same card.
    """

    def __init__(self, result: EditResult):
        self.result = result
        super().__init__(result.reason or result.outcome.value)


class TitleEditInterrupted(KeyboardInterrupt):
    """User interrupt carrying the save state, without retrying the card."""

    def __init__(self, result: EditResult):
        self.result = result
        super().__init__(result.reason or "title edit interrupted")


# Kept as a simple callback rather than a configurable logging framework.
EventSink = Callable[..., None]
Proposer = Callable[[str], str | None]


def edit_open_title(
    port: TitleEditPort,
    propose: Proposer,
    *,
    do_save: bool,
    index: int,
    emit: EventSink | None = None,
) -> EditResult:
    """Execute a single open editor transaction without choosing a card.

    - Preview/skip close the editor without writing or saving.
    - Changes re-read the original before writing and verify exact readback.
    - Save is marked attempted before the GUI click; no automatic retries.
    - List return is not cloud sync; workflow-specific advance comes later.
    """
    guard = SingleSaveGuard()
    old: str | None = None
    proposed: str | None = None

    def event(name: str, **fields: Any) -> None:
        if emit is not None:
            emit(name, **fields)

    try:
        old = port.read_title()
        proposed = propose(old)
        event("inspected", index=index, old=old, proposed=proposed)
        if proposed is None:
            port.close_without_save()
            event("skipped", index=index, old=old)
            return EditResult(EditOutcome.SKIPPED, SaveStage.NOT_ATTEMPTED,
                              original_title=old, proposed_title=old)

        if not isinstance(proposed, str) or not proposed or len(proposed) > 64 or "\n" in proposed or "\r" in proposed:
            raise ValueError("Proposed title is invalid; no save attempted")
        if not do_save:
            port.close_without_save()
            event("would_change", index=index, old=old, new=proposed)
            return EditResult(EditOutcome.PREVIEW, SaveStage.NOT_ATTEMPTED,
                              original_title=old, proposed_title=proposed)

        # Recheck the displayed original before writing. A changed card or
        # unexpected editor is a hard stop rather than a best-effort update.
        actual_before = port.read_title()
        if actual_before != old:
            raise RuntimeError(f"Original title changed before write: {old!r} -> {actual_before!r}")
        port.replace_title(proposed)
        actual_after = port.read_back_title()
        if actual_after != proposed:
            raise RuntimeError(f"Title readback mismatch: {actual_after!r} != {proposed!r}")
        port.verify_save_ready()
        event("save_prepared", index=index, old=old, new=proposed)

        # No log or other ambiguous operation may be put between the guard
        # transition and the Save dispatch. Even if the click raises, the
        # attempt is recorded as possibly having reached the application.
        guard.click_once(port.click_save)
        event("save_clicked", index=index, old=old, new=proposed)
        port.verify_list_return()
        guard.confirm_list_return()
        event("save_returned_list", index=index, old=old, new=proposed)
        return EditResult(EditOutcome.RETURNED_TO_LIST, guard.stage,
                          original_title=old, proposed_title=proposed)
    except BaseException as exc:
        result = stopped_result(
            guard,
            interrupted=isinstance(exc, KeyboardInterrupt),
            original_title=old,
            proposed_title=proposed,
            reason=str(exc) or type(exc).__name__,
        )
        # Do not hide the original failure, nor accidentally turn a confirmed
        # list return into an unconfirmed result when event logging fails.
        try:
            event("title_edit_stopped", index=index,
                  outcome=result.outcome.value,
                  save_stage=result.save_stage.value,
                  reason=result.reason)
        except Exception:
            pass
        if isinstance(exc, KeyboardInterrupt):
            raise TitleEditInterrupted(result) from exc
        if isinstance(exc, Exception):
            raise TitleEditFailure(result) from exc
        raise


def resolve_click_command() -> str:
    """Locate cliclick once without any GUI access or mutable module config."""
    import shutil
    from pathlib import Path

    found = shutil.which('cliclick') or next(
        (p for p in ('/opt/homebrew/bin/cliclick', '/usr/local/bin/cliclick')
         if Path(p).exists()), None)
    if not found:
        raise RuntimeError('未发现 cliclick，请先运行 doctor 检查本地环境')
    return found


def edit_selected_card(
    target,
    frame,
    index: int,
    do_save: bool,
    rule: dict,
    *,
    click_command: str,
    emit: EventSink | None = None,
) -> EditResult:
    """Compose one card's GUI adapter with the shared edit transaction.

    Card selection and rule choice belong to the caller; import of the macOS
    backend is delayed until an actual card operation is requested.
    """
    from ..title_rules import proposal
    from .title_gui import open_title_port

    port = open_title_port(target, frame, click_command=click_command)
    return edit_open_title(
        port, lambda old: proposal(old, rule),
        do_save=do_save, index=index, emit=emit,
    )
