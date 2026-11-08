"""Shared macOS screenshot conversion used by existing GUI adapters.

This primitive deliberately does not check the foreground application. The
caller retains its established preflight order and must not treat an image
as confirmation that it is safe to click.
"""
from __future__ import annotations

import cv2
import numpy as np
import pyautogui


def capture_bgr() -> np.ndarray:
    """Capture once; return uint8 BGR pixels in screenshot coordinates."""
    return cv2.cvtColor(np.asarray(pyautogui.screenshot().convert('RGB')),
                        cv2.COLOR_RGB2BGR)
