"""Read-only failure capture tests; never invokes macOS GUI."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from doumao.core.grid_detector import GridDetectionError
from doumao.workflows import visible_order_rename as workflow


class StubUI:
    def __init__(self):
        self.changed = False

    def shot(self):
        return np.full((900, 1450, 3), 245, dtype=np.uint8)

    def check_list(self, frame):
        return None

    def card_rows(self, frame):
        return []

    def edit_card(self, *args, **kwargs):
        self.changed = True
        raise AssertionError('Never edit in a diagnostic capture')


class FailureCaptureTests(unittest.TestCase):
    def test_no_visible_cards_preserves_raw_frame(self):
        app = StubUI()
        with tempfile.TemporaryDirectory() as tmp, patch.object(workflow, 'RUNTIME', Path(tmp)):
            with self.assertRaisesRegex(GridDetectionError, '垂直边界'):
                workflow.capture(app)
            result = Path(tmp) / 'visible_order_capture_failed.png'
            self.assertTrue(result.is_file())
            self.assertGreater(result.stat().st_size, 100)
        self.assertFalse(app.changed)

    def test_invalid_list_preserves_raw_frame(self):
        app = StubUI()
        app.check_list = Mock(side_effect=RuntimeError('Window is not a list'))
        with tempfile.TemporaryDirectory() as tmp, patch.object(workflow, 'RUNTIME', Path(tmp)):
            with self.assertRaisesRegex(RuntimeError, 'not a list'):
                workflow.capture(app)
            self.assertTrue((Path(tmp) / 'visible_order_capture_failed.png').exists())
        self.assertFalse(app.changed)


if __name__ == '__main__':
    unittest.main()
