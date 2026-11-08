"""Conservative detector selection for the existing visible-order gallery.

Keep detector thresholds, card coordinates, and safety fallbacks owned by their
original implementations. This module only makes the current precedence explicit.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .grid_detector import GridDetectionError


def select_visible_card_candidates(
    frame: Any,
    *,
    full_detector: Callable,
    partial_detector: Callable,
    legacy_detector: Callable,
) -> list[dict]:
    """Preserve full (12), partial (4/8), then legacy (<12) precedence.

    Only known grid-detection failures trigger a fallback. A legacy count of
    zero or twelve-plus is rejected with the original full-grid exception.
    Structural validation and card ordering remain with the caller.
    """
    try:
        return full_detector(frame)
    except GridDetectionError as structural_error:
        try:
            return partial_detector(frame)
        except GridDetectionError:
            cards = legacy_detector(frame)
            if not 1 <= len(cards) < 12:
                raise structural_error
            return cards
