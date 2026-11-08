"""Stage 4 Batch 3: screenshot adapter consistency; no real GUI capture.

Each caller retains its original foreground verification boundary. This
module mocks the screenshot source and never clicks, edits or saves.
"""
from __future__ import annotations

import sys
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

if sys.platform != 'darwin':
    # Existing GUI modules use an import-only stand-in on headless systems.
    with patch.dict(sys.modules, {'pyautogui': Mock()}):
        from doumao.core import screen_capture, card_picker, batch_cleaner
        from doumao.core import metadata_editor, scrolling, list_view
else:
    from doumao.core import screen_capture, card_picker, batch_cleaner
    from doumao.core import metadata_editor, scrolling, list_view


class ScreenCaptureTests(unittest.TestCase):
    def test_rgb_to_bgr_preserves_pixel_location_and_dtype(self):
        image = Image.new('RGB', (3, 2), (11, 22, 33))
        image.putpixel((2, 1), (72, 105, 203))
        with patch.object(screen_capture.pyautogui, 'screenshot', return_value=image) as grab:
            frame = screen_capture.capture_bgr()
        grab.assert_called_once_with()
        self.assertEqual(frame.shape, (2, 3, 3))
        self.assertEqual(frame.dtype, np.dtype('uint8'))
        self.assertEqual(frame[0, 0].tolist(), [33, 22, 11])
        self.assertEqual(frame[1, 2].tolist(), [203, 105, 72])

    def test_rgba_is_explicitly_normalized_to_rgb_before_conversion(self):
        image = Image.new('RGBA', (2, 1), (21, 67, 194, 255))
        with patch.object(screen_capture.pyautogui, 'screenshot', return_value=image):
            frame = screen_capture.capture_bgr()
        self.assertEqual(frame.shape, (1, 2, 3))
        self.assertEqual(frame[0, 0].tolist(), [194, 67, 21])

    def test_screenshot_failure_is_not_hidden_or_retried(self):
        with patch.object(screen_capture.pyautogui, 'screenshot',
                          side_effect=RuntimeError('screen unavailable')) as grab:
            with self.assertRaisesRegex(RuntimeError, 'screen unavailable'):
                screen_capture.capture_bgr()
        grab.assert_called_once_with()

    def test_card_picker_still_uses_unguarded_capture_wrapper(self):
        sentinel = object()
        with patch.object(card_picker.scanner, 'assert_app',
                          side_effect=AssertionError('unexpected guard')) as front, \
             patch.object(screen_capture, 'capture_bgr', return_value=sentinel) as grab:
            self.assertIs(card_picker.screenshot(), sentinel)
        front.assert_not_called()
        grab.assert_called_once_with()

    def test_batch_cleaner_still_uses_unguarded_capture_wrapper(self):
        sentinel = object()
        with patch.object(batch_cleaner.scanner, 'assert_app',
                          side_effect=AssertionError('unexpected guard')) as front, \
             patch.object(screen_capture, 'capture_bgr', return_value=sentinel) as grab:
            self.assertIs(batch_cleaner.screenshot(), sentinel)
        front.assert_not_called()
        grab.assert_called_once_with()

    def test_metadata_editor_still_uses_unguarded_capture_wrapper(self):
        sentinel = object()
        with patch.object(metadata_editor, 'assert_doumao',
                          side_effect=AssertionError('unexpected guard')) as front, \
             patch.object(screen_capture, 'capture_bgr', return_value=sentinel) as grab:
            self.assertIs(metadata_editor.capture(), sentinel)
        front.assert_not_called()
        grab.assert_called_once_with()

    def test_scrolling_checks_foreground_before_capture(self):
        events = []
        sentinel = object()
        with patch.object(scrolling.scanner, 'assert_app',
                          side_effect=lambda: events.append('front')), \
             patch.object(screen_capture, 'capture_bgr',
                          side_effect=lambda: (events.append('capture'), sentinel)[1]):
            self.assertIs(scrolling.screenshot(), sentinel)
        self.assertEqual(events, ['front', 'capture'])

    def test_scrolling_refuses_capture_when_foreground_check_fails(self):
        with patch.object(scrolling.scanner, 'assert_app',
                          side_effect=RuntimeError('not Doumao')), \
             patch.object(screen_capture, 'capture_bgr') as grab:
            with self.assertRaisesRegex(RuntimeError, 'not Doumao'):
                scrolling.screenshot()
        grab.assert_not_called()

    def test_list_view_still_uses_existing_guarded_card_picker_path(self):
        events = []
        sentinel = object()
        with patch.object(list_view.scanner, 'assert_app',
                          side_effect=lambda: events.append('front')), \
             patch.object(list_view.card_picker, 'screenshot',
                          side_effect=lambda: (events.append('picker'), sentinel)[1]):
            self.assertIs(list_view.shot(), sentinel)
        self.assertEqual(events, ['front', 'picker'])


if __name__ == '__main__':
    unittest.main()
