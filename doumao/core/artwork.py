"""Shared, pure artwork fingerprint comparison.

The strict identity predicate is shared by search-queue progression and
visible-order checks. The latter deliberately retains its own, more tolerant
fallback; neither threshold is changed by this module extraction.
"""
from __future__ import annotations

import cv2
import numpy as np


def looks_like_same_art(a: np.ndarray, b: np.ndarray, threshold: float = .012) -> bool:
    """Shift-tolerant thumbnail comparison; not a unique work identifier."""
    if not isinstance(a, np.ndarray) or not isinstance(b, np.ndarray):
        return False
    if a.ndim != 3 or a.shape != b.shape or min(a.shape[:2]) < 25:
        return False
    # Compare a central crop against b, allowing the image placement to move.
    margin = 5
    inner = a[margin:-margin, margin:-margin]
    if inner.size == 0:
        return False
    if np.array_equal(a, b):
        return True
    score = cv2.matchTemplate(b, inner, cv2.TM_SQDIFF_NORMED)
    return float(cv2.minMaxLoc(score)[0]) < threshold
