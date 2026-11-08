"""Pure title-edit result and save-attempt contracts (no GUI side effects)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol


class SaveStage(str, Enum):
    NOT_ATTEMPTED = "not_attempted"
    ATTEMPTED = "attempted_unconfirmed"
    LIST_RETURN_CONFIRMED = "list_return_confirmed"


class EditOutcome(str, Enum):
    PREVIEW = "preview"
    SKIPPED = "skipped"
    RETURNED_TO_LIST = "returned_to_list"
    FAILED_PRE_SAVE = "failed_pre_save"
    CANCELLED = "cancelled_pre_save"
    STOPPED = "stopped_pre_save"
    SAVE_UNCERTAIN = "save_uncertain"


class DuplicateSaveAttempt(RuntimeError):
    """The current item has already attempted a side-effecting save."""


class SaveTransitionError(RuntimeError):
    """An invalid confirmation or state transition was attempted."""


class TitleEditPort(Protocol):
    """A per-operation GUI adapter; intentionally not implemented in Phase 0.

    The workflow owns card selection, identity checks and navigation into the
    editor.  A future adapter owns only the currently open title-edit dialog.
    """

    def read_title(self) -> str: ...
    def replace_title(self, proposed_title: str) -> None: ...
    def read_back_title(self) -> str: ...
    def verify_save_ready(self) -> None: ...
    def click_save(self) -> None: ...
    def verify_list_return(self) -> None: ...
    def close_without_save(self) -> None: ...


class SingleSaveGuard:
    """At-most-once local save *attempt*, even when clicking raises.

    A save attempt is marked *before* dispatching the action: an exception
    from the GUI backend cannot prove that the external click did not occur.
    The caller must explicitly confirm the post-save list return.  That
    confirmation still does not imply remote/cloud synchronization.
    """

    def __init__(self) -> None:
        self._stage = SaveStage.NOT_ATTEMPTED

    @property
    def stage(self) -> SaveStage:
        return self._stage

    @property
    def save_attempted(self) -> bool:
        return self._stage is not SaveStage.NOT_ATTEMPTED

    def click_once(self, click: Callable[[], None]) -> None:
        if self._stage is not SaveStage.NOT_ATTEMPTED:
            raise DuplicateSaveAttempt("Save already attempted: inspect manually; never retry")
        self._stage = SaveStage.ATTEMPTED
        click()

    def confirm_list_return(self) -> None:
        if self._stage is not SaveStage.ATTEMPTED:
            raise SaveTransitionError("Confirm only after an attempted, unconfirmed Save")
        self._stage = SaveStage.LIST_RETURN_CONFIRMED


@dataclass(frozen=True)
class EditResult:
    """Structured result; not permission to advance a workflow queue.

    Queue advancement and visible-position identity checks remain the
    responsibility of their respective workflows. A returned list view is
    not evidence that the server has synchronized the change.
    """

    outcome: EditOutcome
    save_stage: SaveStage
    original_title: str | None = None
    proposed_title: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.outcome is EditOutcome.RETURNED_TO_LIST:
            valid = self.save_stage is SaveStage.LIST_RETURN_CONFIRMED
        elif self.outcome is EditOutcome.SAVE_UNCERTAIN:
            valid = self.save_stage is SaveStage.ATTEMPTED
        else:
            valid = self.save_stage is SaveStage.NOT_ATTEMPTED
        if not valid:
            raise ValueError("EditOutcome disagrees with the observed SaveStage")


def stopped_result(
    guard: SingleSaveGuard,
    *,
    cancelled: bool = False,
    interrupted: bool = False,
    original_title: str | None = None,
    proposed_title: str | None = None,
    reason: str | None = None,
) -> EditResult:
    """Fail closed: any unconfirmed attempted save is always uncertain.

    No click occurs here.  KeyboardInterrupt / cancellation / GUI failure
    after a Save attempt must never be downgraded to a no-save outcome.
    """
    stage = guard.stage
    if stage is SaveStage.ATTEMPTED:
        outcome = EditOutcome.SAVE_UNCERTAIN
    elif stage is SaveStage.LIST_RETURN_CONFIRMED:
        # A later unrelated error must not erase an already confirmed edit.
        outcome = EditOutcome.RETURNED_TO_LIST
    elif cancelled:
        outcome = EditOutcome.CANCELLED
    elif interrupted:
        outcome = EditOutcome.STOPPED
    else:
        outcome = EditOutcome.FAILED_PRE_SAVE
    return EditResult(
        outcome=outcome,
        save_stage=stage,
        original_title=original_title,
        proposed_title=proposed_title,
        reason=reason,
    )
