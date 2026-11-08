"""Pure search-result queue transition checks; no application interaction.

A title is not an item identifier. Image comparisons are used only to check
that a search result list plausibly advanced after a single save, never to
skip distinct items with equal names. When the visuals cannot prove progress,
stop instead of retrying the same card.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .artwork import looks_like_same_art


class QueueUncertain(RuntimeError):
    """Post-save result could not be verified, so no retry is permitted."""


def queue_transition(before: Sequence[dict[str, Any]], after: Sequence[dict[str, Any]]) -> str:
    """Return 'advanced', 'empty', or 'uncertain'. Does not look at titles.

    When a previously visible second card is distinct from the first, insist
    that it becomes the next head. When only one card was visible, a different
    head is sufficient. Equal-looking duplicates cannot be uniquely identified.
    """
    if not before:
        raise ValueError('Missing pre-save queue head')
    if not after:
        return 'empty'  # caller must separately verify stable, fully loaded empty state
    old_first, new_first = before[0], after[0]
    if looks_like_same_art(old_first['fp'], new_first['fp']):
        return 'uncertain'
    if len(before) > 1:
        old_second = before[1]
        # If second was visible, post-save head should be that specific art.
        if not looks_like_same_art(old_second['fp'], new_first['fp']):
            return 'uncertain'
    return 'advanced'


@dataclass(frozen=True)
class Result:
    outcome: str
    changed: int
    inspected: int


class QueueCounter:
    """Separate confirmed edits, pending saves and exhausted-result outcomes."""
    def __init__(self, limit: int | None):
        if limit is not None and (type(limit) is not int or limit < 1):
            raise ValueError('limit must be a positive integer or None (all)')
        self.limit = limit
        self.changed = 0
        self.inspected = 0
        self.pending = False

    def start(self) -> None:
        if self.pending:
            raise QueueUncertain('Prior edit has not been verified')
        self.inspected += 1
        self.pending = True

    def verified(self, transition: str) -> None:
        if not self.pending or transition not in ('advanced', 'empty'):
            raise QueueUncertain('Post-save queue transition is not confirmed')
        self.changed += 1
        self.pending = False

    def finished(self, queue_empty: bool) -> Result:
        if self.pending:
            raise QueueUncertain('A save is pending verification')
        if self.limit is not None and self.changed >= self.limit:
            return Result('limit_reached', self.changed, self.inspected)
        if queue_empty:
            return Result('exhausted', self.changed, self.inspected)
        raise QueueUncertain('Neither limit reached nor queue exhausted')
