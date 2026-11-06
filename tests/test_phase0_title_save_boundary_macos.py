"""Low-level Save-click regression for actual v3.5 title editor.

The module imports the legacy macOS GUI stack; run on the user's Mac.
All IO functions are mocked: tests never operate Doumao or click the screen.
"""
from __future__ import annotations

import sys
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch


@unittest.skipUnless(sys.platform == "darwin", "legacy PyAutoGUI imports need macOS")
class ExistingTitleSaveBoundaryTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from doumao.workflows import normalize_titles as ui
        self.ui = ui
        self.frame = np.zeros((1200, 1900, 3), dtype=np.uint8)
        self.title_rect = (50, 40, 170, 40)
        self.save_rect = (40, 300, 120, 40)
        self.target = {"click": (100, 300)}
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)

        def mock_attr(target, name, **opts):
            return self.patches.enter_context(patch.object(target, name, **opts))

        mock_attr(ui.scanner, "assert_app")
        mock_attr(ui.proven.v08, "screen_click")
        mock_attr(ui.proven.v08, "wait_for_detail", return_value=(self.frame, (20, 20, 200, 200)))
        mock_attr(ui.nav, "find_pencil", return_value=((100, 100), (0, 0, 20, 20)))
        mock_attr(ui, "wait_for_title_editor", return_value=(self.frame, self.save_rect, self.title_rect))
        self.read_title = mock_attr(ui, "read_title_only", side_effect=["Old", "Old", "New"])
        mock_attr(ui, "proposal", return_value="New")
        mock_attr(ui, "shot", return_value=self.frame)
        mock_attr(ui, "find_title_only", return_value=self.title_rect)
        mock_attr(ui.cleaner, "find_save", return_value=self.save_rect)
        self.click = mock_attr(ui.cleaner, "click_img")
        mock_attr(ui.cleaner, "shell")
        mock_attr(ui.cleaner, "press")
        mock_attr(ui.time, "sleep")
        mock_attr(ui, "emit")
        mock_attr(ui.proven, "wait_for_list_after_save", return_value=self.frame)
        mock_attr(ui, "check_list")
        mock_attr(ui, "go_back_to_list", return_value=self.frame)

    def do_edit(self, save=True):
        return self.ui.handle_card(self.target, self.frame, 1, save, {"rule_type": "unused"})

    def save_clicks(self):
        sx, sy, sw, sh = self.save_rect
        x, y = sx + sw * .50, sy + sh * .50
        return [call for call in self.click.call_args_list if call.args[:2] == (x, y)]

    def test_success_clicks_save_exactly_once(self):
        self.assertEqual(self.do_edit(), ("saved", "Old", "New"))
        self.assertEqual(len(self.save_clicks()), 1)

    def test_preview_never_clicks_save(self):
        self.assertEqual(self.do_edit(save=False), ("preview", "Old", "New"))
        self.assertEqual(len(self.save_clicks()), 0)

    def test_failed_readback_never_clicks_save(self):
        self.read_title.side_effect = ["Old", "Old", "Mismatch"]
        with self.assertRaisesRegex(RuntimeError, "回读不一致"):
            self.do_edit()
        self.assertEqual(len(self.save_clicks()), 0)

    def test_save_issued_but_list_not_confirmed_no_retry(self):
        self.ui.proven.wait_for_list_after_save.side_effect = RuntimeError("return timeout")
        with self.assertRaisesRegex(RuntimeError, "return timeout"):
            self.do_edit()
        self.assertEqual(len(self.save_clicks()), 1)

    def test_save_click_itself_raises_no_retry(self):
        self.click.side_effect = [None, RuntimeError("uncertain click")]
        with self.assertRaisesRegex(RuntimeError, "uncertain click"):
            self.do_edit()
        self.assertEqual(len(self.save_clicks()), 1)

    def test_keyboard_interrupt_after_click_does_not_repeat(self):
        self.ui.proven.wait_for_list_after_save.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.do_edit()
        self.assertEqual(len(self.save_clicks()), 1)


if __name__ == "__main__":
    unittest.main()
