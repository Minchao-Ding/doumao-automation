"""Phase 3 Batch 1: metadata Save state without macOS GUI side effects.

The legacy editor runs against a fully mocked image/clipboard/click backend.
Neither Doumao nor screenshots, titles or actual Save buttons are touched.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

# On non-macOS systems pyautogui may not import without a display. The
# operation is fully mocked here, so use an import-only stand-in for tests.
if sys.platform != 'darwin':
    with patch.dict(sys.modules, {'pyautogui': Mock()}):
        from doumao.core import metadata_editor as cleaner
else:
    from doumao.core import metadata_editor as cleaner

from doumao.core.title_edit_contract import SaveStage


class MetadataResultTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.frame = np.zeros((120, 200, 3), dtype=np.uint8)
        self.save = (700, 900, 200, 40)
        self.bar = (700, 620, 200, 50)
        self.finish = (300, 500, 80, 30)
        self.title_rect = (100, 100, 200, 40)
        self.note_rect = (100, 200, 200, 80)
        self.tag = (140, 260, 60, 30)
        self.saved_clicks = 0
        self.removed = False
        self.modal_closed = False
        self.click_error = None
        self.after_click_capture_error = None
        self.still_open = False
        self.emit_path = Path(self.temp.name) / 'operations.jsonl'

        def stub(name, **kwargs):
            return self.stack.enter_context(patch.object(cleaner, name, **kwargs))

        stub('CLICK', new=sys.executable)
        stub('LOG', new=self.emit_path)
        stub('assert_doumao')
        stub('time', new=Mock(sleep=lambda _: None))
        stub('form_rects', return_value=(self.title_rect, self.note_rect))
        stub('scroll_to_tags', return_value=(self.frame, self.bar))
        stub('find_tag_bar', return_value=self.bar)
        stub('mark')
        stub('cross', return_value=(170, 275))
        stub('read_field', side_effect=lambda rect, _: 'Sample Item' if rect == self.title_rect else '')
        stub('capture', side_effect=self.capture)
        stub('find_save', side_effect=self.find_save)
        stub('find_finish', side_effect=lambda _: None if self.modal_closed else self.finish)
        stub('selected_chips', side_effect=lambda *a, **kw: None if self.removed else [self.tag])
        stub('click_img', side_effect=self.click)

    def capture(self):
        if self.saved_clicks and self.after_click_capture_error is not None:
            raise self.after_click_capture_error
        return self.frame

    def find_save(self, _):
        if self.saved_clicks and not self.still_open:
            return None
        return self.save

    def click(self, x, y, _):
        at = (x, y)
        if at == cleaner.rect_center(self.save):
            self.saved_clicks += 1
            if self.click_error is not None:
                raise self.click_error
        elif at == cleaner.rect_center(self.finish):
            self.modal_closed = True
        elif at == (170, 275):
            self.removed = True

    def test_success_reports_attempt_and_audit_without_pretending_list_confirmed(self):
        result = cleaner.clean_current('Sample Item', auto_save=True)
        self.assertEqual(self.saved_clicks, 1)
        self.assertEqual(result.title, 'Sample Item')
        self.assertEqual(result.save_stage, SaveStage.ATTEMPTED)
        self.assertEqual(result.note_before_length, 0)
        self.assertEqual(result.removed_tags, 1)
        self.assertTrue(result.edit_dialog_disappeared)
        self.assertTrue(result.log_written)
        event = json.loads(self.emit_path.read_text().splitlines()[0])
        self.assertEqual(event['removed_tags'], 1)
        self.assertTrue(event['save_clicked'])

    def test_manual_save_mode_has_no_save_attempt(self):
        result = cleaner.clean_current('Sample Item', auto_save=False)
        self.assertEqual(self.saved_clicks, 0)
        self.assertEqual(result.save_stage, SaveStage.NOT_ATTEMPTED)
        self.assertIsNone(result.edit_dialog_disappeared)
        self.assertIsNone(result.log_written)

    def test_pre_save_failure_retains_not_attempted(self):
        with patch.object(cleaner, 'scroll_to_tags', side_effect=RuntimeError('tag bar unavailable')):
            with self.assertRaises(cleaner.MetadataCleanFailure) as caught:
                cleaner.clean_current('Sample Item', auto_save=True)
        self.assertEqual(caught.exception.result.save_stage, SaveStage.NOT_ATTEMPTED)
        self.assertEqual(self.saved_clicks, 0)

    def test_save_backend_error_is_uncertain_and_never_retried(self):
        self.click_error = RuntimeError('GUI click may have been delivered')
        with self.assertRaises(cleaner.MetadataCleanFailure) as caught:
            cleaner.clean_current('Sample Item', auto_save=True)
        self.assertEqual(caught.exception.result.save_stage, SaveStage.ATTEMPTED)
        self.assertEqual(self.saved_clicks, 1)
        self.assertFalse(self.emit_path.exists())

    def test_keyboard_interrupt_during_click_preserves_attempt(self):
        self.click_error = KeyboardInterrupt()
        with self.assertRaises(cleaner.MetadataCleanInterrupted) as caught:
            cleaner.clean_current('Sample Item', auto_save=True)
        self.assertEqual(caught.exception.result.save_stage, SaveStage.ATTEMPTED)
        self.assertEqual(self.saved_clicks, 1)

    def test_failure_after_click_before_audit_preserves_attempt(self):
        self.after_click_capture_error = RuntimeError('screenshot unavailable')
        with self.assertRaises(cleaner.MetadataCleanFailure) as caught:
            cleaner.clean_current('Sample Item', auto_save=True)
        self.assertEqual(caught.exception.result.save_stage, SaveStage.ATTEMPTED)
        self.assertEqual(self.saved_clicks, 1)
        self.assertIsNone(caught.exception.result.edit_dialog_disappeared)

    def test_dialog_still_open_does_not_claim_list_return(self):
        self.still_open = True
        result = cleaner.clean_current('Sample Item', auto_save=True)
        self.assertEqual(result.save_stage, SaveStage.ATTEMPTED)
        self.assertFalse(result.edit_dialog_disappeared)
        self.assertEqual(self.saved_clicks, 1)

    def test_log_write_failure_does_not_erase_observed_result(self):
        self.emit_path.mkdir()
        result = cleaner.clean_current('Sample Item', auto_save=True)
        self.assertEqual(result.save_stage, SaveStage.ATTEMPTED)
        self.assertTrue(result.edit_dialog_disappeared)
        self.assertFalse(result.log_written)
        self.assertEqual(self.saved_clicks, 1)


if __name__ == '__main__':
    unittest.main()
