"""Workflow-level regression for titles after extracting the GUI editor.

No real Doumao GUI, screenshot, clipboard, or input event is used.
"""
from __future__ import annotations

import sys
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch


@unittest.skipUnless(sys.platform == 'darwin', 'macOS GUI imports need macOS')
class NormalizeWorkflowTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from doumao.workflows import normalize_titles as normal
        from doumao.core.title_edit_contract import EditOutcome, EditResult, SaveStage
        from doumao.core.title_editor import TitleEditFailure, TitleEditInterrupted

        self.normal = normal
        self.EditOutcome = EditOutcome
        self.EditResult = EditResult
        self.SaveStage = SaveStage
        self.TitleEditFailure = TitleEditFailure
        self.TitleEditInterrupted = TitleEditInterrupted
        self.frame = np.zeros((1200, 1900, 3), dtype=np.uint8)
        self.card = {'col': 0, 'top': 200, 'click': (140, 210),
                     'fp': np.full((70, 60, 3), 120, dtype=np.uint8)}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

        def stub(obj, name, **opts):
            return self.stack.enter_context(patch.object(obj, name, **opts))

        self.stub = stub
        stub(normal, 'load_rule', return_value={'folder': 'sample'})
        stub(normal.list_view, 'shot', return_value=self.frame)
        stub(normal.list_view, 'check_list')
        stub(normal.list_view, 'card_rows', return_value=[self.card])
        stub(normal, 'title_gap_candidate', return_value=(False, 0, 0))
        stub(normal, 'preview')
        stub(normal.time, 'sleep')
        stub(normal.pyautogui, 'size', return_value=(1900, 1200))
        self.resolve = stub(normal, 'resolve_click_command', return_value='/local/cliclick')
        self.editor = stub(normal, 'edit_selected_card')
        self.emit = stub(normal, 'emit')

    def args(self, **options):
        data = dict(rule_config='unused', auto_save=True,
                    limit=1, scroll=3, max_scrolls=1,
                    current_screen_only=True, expect_visible=None,
                    expected_changes=None, list_preview=False)
        data.update(options)
        return SimpleNamespace(**data)

    def saved(self):
        return self.EditResult(self.EditOutcome.RETURNED_TO_LIST,
                               self.SaveStage.LIST_RETURN_CONFIRMED,
                               original_title='Old', proposed_title='New')

    def test_saved_item_calls_shared_editor_once(self):
        self.editor.return_value = self.saved()
        self.normal.run(self.args())
        self.editor.assert_called_once()
        kw = self.editor.call_args.kwargs
        self.assertEqual(kw['click_command'], '/local/cliclick')
        self.assertTrue(kw['emit'] is self.normal.edit_event)
        self.assertTrue(any(c.args[0] == 'session_finished' and c.kwargs['changed'] == 1
                            for c in self.emit.call_args_list))

    def test_unchanged_skipped_item_not_counted_as_save(self):
        self.editor.return_value = self.EditResult(self.EditOutcome.SKIPPED,
                         self.SaveStage.NOT_ATTEMPTED,
                         original_title='Same', proposed_title='Same')
        self.normal.run(self.args())
        self.assertTrue(any(c.args[0] == 'session_finished' and
                            c.kwargs['skipped'] == 1 and c.kwargs['changed'] == 0
                            for c in self.emit.call_args_list))

    def test_preview_never_requests_save(self):
        self.editor.return_value = self.EditResult(self.EditOutcome.PREVIEW,
                         self.SaveStage.NOT_ATTEMPTED,
                         original_title='Old', proposed_title='New')
        self.normal.run(self.args(auto_save=False))
        self.assertFalse(self.editor.call_args.args[3])

    def test_list_preview_never_opens_editor_or_resolves_backend(self):
        self.normal.run(self.args(list_preview=True))
        self.editor.assert_not_called()
        self.resolve.assert_not_called()

    def test_unconfirmed_save_aborts_without_retry(self):
        failure = self.TitleEditFailure(self.EditResult(
            self.EditOutcome.SAVE_UNCERTAIN, self.SaveStage.ATTEMPTED,
            original_title='Old', proposed_title='New', reason='return timeout'))
        self.editor.side_effect = failure
        with self.assertRaises(self.TitleEditFailure):
            self.normal.run(self.args())
        self.editor.assert_called_once()
        self.assertFalse(any(c.args[0] == 'session_finished' for c in self.emit.call_args_list))

    def test_interrupt_aborts_without_retry(self):
        failure = self.TitleEditInterrupted(self.EditResult(
            self.EditOutcome.SAVE_UNCERTAIN, self.SaveStage.ATTEMPTED,
            original_title='Old', proposed_title='New', reason='Ctrl+C'))
        self.editor.side_effect = failure
        with self.assertRaises(KeyboardInterrupt):
            self.normal.run(self.args())
        self.editor.assert_called_once()


if __name__ == '__main__':
    unittest.main()
