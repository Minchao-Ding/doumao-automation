"""Phase 1 actual title-dialog adapter tests, no real clicks or Doumao GUI.

The adapter imports the established macOS GUI stack.  Its public workflow
boundary is exercised with mocks and the real shared title transaction.
"""
from __future__ import annotations

import sys
import unittest
from contextlib import ExitStack
from unittest.mock import patch


@unittest.skipUnless(sys.platform == 'darwin', 'macOS GUI stack')
class MacTitlePortTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from doumao.core import title_gui as gui
        self.gui = gui
        self.frame = np.zeros((1200, 1900, 3), dtype=np.uint8)
        self.save_rect = (40, 300, 120, 40)
        self.title_rect = (50, 40, 170, 40)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

        def stub(module, name, **opts):
            return self.stack.enter_context(patch.object(module, name, **opts))

        self.stub = stub
        self.shot = stub(gui.list_view, 'shot', return_value=self.frame)
        stub(gui.cleaner, 'find_save', return_value=self.save_rect)
        stub(gui, 'find_title_only', return_value=self.title_rect)
        self.reader = stub(gui, 'read_title_only', side_effect=['Old', 'Old', 'New'])
        self.click = stub(gui.cleaner, 'click_img')
        self.shell = stub(gui.cleaner, 'shell')
        self.press = stub(gui.cleaner, 'press')
        stub(gui.scanner, 'assert_app')
        stub(gui.time, 'sleep')
        self.return_list = stub(gui.list_view, 'wait_for_list_after_save', return_value=self.frame)
        self.check_list = stub(gui.list_view, 'check_list')
        self.close = stub(gui.list_view, 'go_back_to_list')
        self.port = gui.MacTitlePort('/local/cliclick', _initial=(self.frame, self.title_rect))

    def execute(self, *, save=True):
        from doumao.core.title_editor import edit_open_title
        return edit_open_title(self.port, lambda original: 'New', do_save=save, index=1)

    def save_clicks(self):
        x, y, w, h = self.save_rect
        return [c for c in self.click.call_args_list
                if c.args[:2] == (x+w*.5, y+h*.5)]

    def test_success_uses_explicit_backend_and_saves_once(self):
        from doumao.core.title_edit_contract import EditOutcome
        result = self.execute()
        self.assertEqual(result.outcome, EditOutcome.RETURNED_TO_LIST)
        self.assertEqual(len(self.save_clicks()), 1)
        self.assertEqual(self.press.call_args.kwargs['click_command'], '/local/cliclick')
        self.check_list.assert_called_once_with(self.frame)
        self.return_list.assert_called_once()
        self.assertEqual(self.reader.call_count, 3)

    def test_preview_never_writes_or_saves(self):
        from doumao.core.title_edit_contract import EditOutcome
        result = self.execute(save=False)
        self.assertEqual(result.outcome, EditOutcome.PREVIEW)
        self.close.assert_called_once()
        self.click.assert_not_called()
        self.press.assert_not_called()

    def test_changed_original_stops_before_writing(self):
        from doumao.core.title_editor import TitleEditFailure
        from doumao.core.title_edit_contract import SaveStage
        self.reader.side_effect = ['Old', 'Different']
        with self.assertRaises(TitleEditFailure) as caught:
            self.execute()
        self.assertEqual(caught.exception.result.save_stage, SaveStage.NOT_ATTEMPTED)
        self.click.assert_not_called()

    def test_save_click_exception_is_uncertain_and_not_retried(self):
        from doumao.core.title_editor import TitleEditFailure
        from doumao.core.title_edit_contract import SaveStage
        self.click.side_effect = [None, RuntimeError('click uncertain')]
        with self.assertRaises(TitleEditFailure) as caught:
            self.execute()
        self.assertEqual(caught.exception.result.save_stage, SaveStage.ATTEMPTED)
        self.assertEqual(len(self.save_clicks()), 1)
        self.return_list.assert_not_called()

    def test_return_timeout_stops_without_another_save(self):
        from doumao.core.title_editor import TitleEditFailure
        from doumao.core.title_edit_contract import EditOutcome
        self.return_list.side_effect = RuntimeError('return timeout')
        with self.assertRaises(TitleEditFailure) as caught:
            self.execute()
        self.assertEqual(caught.exception.result.outcome, EditOutcome.SAVE_UNCERTAIN)
        self.assertEqual(len(self.save_clicks()), 1)

    def test_keyboard_interrupt_after_save_does_not_retry(self):
        self.return_list.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.execute()
        self.assertEqual(len(self.save_clicks()), 1)

    def test_open_title_port_follows_original_navigation(self):
        self.stub(self.gui.card_picker, 'screen_click')
        self.stub(self.gui.card_picker, 'wait_for_detail',
                  return_value=(self.frame, (20, 20, 400, 500)))
        self.stub(self.gui.navigation, 'find_pencil',
                  return_value=((90, 100), (80, 90, 20, 20)))
        self.stub(self.gui, 'wait_for_title_editor',
                  return_value=(self.frame, self.save_rect, self.title_rect))
        port = self.gui.open_title_port({'click': (110, 220)}, self.frame,
                                        click_command='/local/cliclick')
        self.assertIsInstance(port, self.gui.MacTitlePort)
        self.assertEqual(self.gui.card_picker.screen_click.call_count, 2)
        self.assertEqual(port._initial[1], self.title_rect)


@unittest.skipUnless(sys.platform == 'darwin', 'macOS GUI stack')
class ListViewAndBackendTests(unittest.TestCase):
    def test_explicit_cli_used_without_mutating_global(self):
        from doumao.core import metadata_editor as cleaner
        with patch.object(cleaner, 'assert_doumao'), patch.object(cleaner, 'shell') as shell:
            original = cleaner.CLICK
            cleaner.press('t:a', click_command='/local/custom-cli')
            self.assertEqual(shell.call_args.args[:3], ('/local/custom-cli', '-w', '130'))
            self.assertEqual(cleaner.CLICK, original)

    def test_list_check_preserves_original_aspect_ratio_guard(self):
        import numpy as np
        from doumao.core import list_view
        frame = np.zeros((1200, 2047, 3), dtype=np.uint8)
        with patch.object(list_view.cleaner, 'find_save', return_value=None), \
             patch.object(list_view.navigation, 'find_detail_modal', return_value=None):
            with self.assertRaisesRegex(RuntimeError, '截图比例'):
                list_view.check_list(frame)

    def test_detail_modal_after_save_gets_only_one_escape(self):
        import numpy as np
        from doumao.core import list_view
        frame = np.zeros((1200, 1900, 3), dtype=np.uint8)
        with patch.object(list_view, 'shot', return_value=frame), \
             patch.object(list_view.cleaner, 'find_save', return_value=None), \
             patch.object(list_view.navigation, 'find_detail_modal',
                          side_effect=[(10, 10, 20, 20), None]), \
             patch.object(list_view.scanner, 'assert_app'), \
             patch.object(list_view.time, 'sleep'), \
             patch.object(list_view.pyautogui, 'press') as press:
            self.assertIs(list_view.wait_for_list_after_save(), frame)
            press.assert_called_once_with('esc')


if __name__ == '__main__':
    unittest.main()
