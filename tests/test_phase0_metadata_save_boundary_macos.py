"""Metadata single-card GUI/save boundary regression, migrated in Phase 3.

All GUI calls are patched; this test never clicks in Doumao. The former
JSONL parser assertions now protect direct MetadataCleanResult validation.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(sys.platform == 'darwin', 'legacy GUI imports require macOS')
class MetadataRunOneBoundaryTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from doumao.core import batch_cleaner as batch
        from doumao.core.title_edit_contract import SaveStage

        self.batch = batch
        self.SaveStage = SaveStage
        self.frame = np.zeros((1200, 1900, 3), dtype=np.uint8)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)

        def mock(target, name, **kwargs):
            return self.patches.enter_context(patch.object(target, name, **kwargs))

        mock(batch, 'LOG', new=Path(self.temporary.name) / 'batch_events.jsonl')
        mock(batch.scanner, 'assert_app')
        mock(batch, 'screenshot', return_value=self.frame)
        mock(batch.cleaner, 'find_save', return_value=None)
        mock(batch.navigator, 'find_detail_modal', return_value=None)
        self.tags = mock(batch.scanner, 'scan_tag_groups', return_value=[(80, 90, 140, 110)])
        mock(batch.v08, 'find_first_candidate', return_value=(1, (80, 90, 140, 110, 110, 200)))
        mock(batch, 'save_preview')
        self.screen_click = mock(batch.v08, 'screen_click')
        mock(batch.v08, 'wait_for_detail', return_value=(self.frame, (30, 30, 200, 200)))
        mock(batch.navigator, 'find_pencil', return_value=((100, 100), (70, 70, 50, 50)))
        self.wait_editor = mock(batch, 'wait_for_editor_robust', return_value=(self.frame, (30, 700, 120, 40)))
        mock(batch.cleaner, 'form_rects', return_value=((50, 100, 140, 35), (50, 200, 140, 35)))
        self.read_field = mock(batch.cleaner, 'read_field', return_value='Sample Item')
        self.real_record = batch.record
        self.record = mock(batch, 'record')
        self.cleaned = batch.cleaner.MetadataCleanResult(
            title='Sample Item', save_stage=SaveStage.ATTEMPTED,
            note_before_length=0, removed_tags=2, edit_dialog_disappeared=True,
            log_written=True,
        )
        self.clean_current = mock(batch.cleaner, 'clean_current', return_value=self.cleaned)
        self.wait_list = mock(batch, 'wait_for_list_after_save', return_value=self.frame)
        self.verify_tags = mock(batch, 'verify_tag_disappeared', return_value=0)

    def perform(self):
        return self.batch.run_one(1, 2)

    def verified_records(self):
        return [call for call in self.record.call_args_list
                if len(call.args) > 1 and call.args[1] == 'verified_on_list']

    def test_success_calls_metadata_editor_once_then_verifies_list_and_tags(self):
        result = self.perform()
        self.assertEqual(result.title, 'Sample Item')
        self.assertEqual(result.save_stage, self.SaveStage.LIST_RETURN_CONFIRMED)
        self.assertEqual(result.removed_tags, 2)
        self.assertEqual(result.tag_groups_after, 0)
        self.clean_current.assert_called_once_with(title='Sample Item', auto_save=True)
        self.wait_list.assert_called_once_with()
        self.verify_tags.assert_called_once()
        self.assertEqual(len(self.verified_records()), 1)

    def test_no_candidate_returns_none_without_editing(self):
        self.tags.return_value = []
        self.assertIsNone(self.perform())
        self.clean_current.assert_not_called()
        self.wait_list.assert_not_called()

    def test_editor_not_confirmed_never_invokes_save_path(self):
        self.wait_editor.side_effect = RuntimeError('editor not confirmed')
        with self.assertRaisesRegex(RuntimeError, 'editor not confirmed'):
            self.perform()
        self.clean_current.assert_not_called()
        self.assertEqual(self.verified_records(), [])

    def test_unreadable_title_never_invokes_save_path(self):
        self.read_field.return_value = ''
        with self.assertRaisesRegex(RuntimeError, '读取的原标题异常'):
            self.perform()
        self.clean_current.assert_not_called()
        self.assertEqual(self.verified_records(), [])

    def test_error_inside_save_path_does_not_retry_metadata_edit(self):
        self.clean_current.side_effect = self.batch.cleaner.MetadataCleanFailure(
            self.batch.cleaner.MetadataCleanResult(
                title='Sample Item', save_stage=self.SaveStage.ATTEMPTED,
                reason='Save possibly dispatched'))
        with self.assertRaises(self.batch.cleaner.MetadataCleanFailure) as caught:
            self.perform()
        self.assertEqual(caught.exception.result.save_stage, self.SaveStage.ATTEMPTED)
        self.clean_current.assert_called_once()
        self.wait_list.assert_not_called()
        self.assertEqual(self.verified_records(), [])

    def test_keyboard_interrupt_inside_save_path_does_not_retry(self):
        self.clean_current.side_effect = self.batch.cleaner.MetadataCleanInterrupted(
            self.batch.cleaner.MetadataCleanResult(
                title='Sample Item', save_stage=self.SaveStage.ATTEMPTED,
                reason='user interrupted'))
        with self.assertRaises(self.batch.cleaner.MetadataCleanInterrupted) as caught:
            self.perform()
        self.assertEqual(caught.exception.result.save_stage, self.SaveStage.ATTEMPTED)
        self.clean_current.assert_called_once()
        self.wait_list.assert_not_called()
        self.assertEqual(self.verified_records(), [])

    def test_result_invalid_stops_without_claiming_success(self):
        self.clean_current.return_value = None
        with self.assertRaisesRegex(RuntimeError, '结构化保存结果'):
            self.perform()
        self.wait_list.assert_not_called()
        self.assertEqual(self.verified_records(), [])

    def test_list_return_timeout_preserves_attempt_without_repeating_save(self):
        self.wait_list.side_effect = RuntimeError('list not confirmed')
        with self.assertRaises(self.batch.MetadataCardFailure) as caught:
            self.perform()
        self.assertIn('list not confirmed', str(caught.exception))
        self.assertEqual(caught.exception.save_stage, self.SaveStage.ATTEMPTED)
        self.clean_current.assert_called_once()
        self.verify_tags.assert_not_called()
        self.assertEqual(self.verified_records(), [])

    def test_batch_audit_write_failure_does_not_hide_confirmed_result(self):
        bad_log = Path(self.temporary.name) / 'directory_instead_of_batch_log'
        bad_log.mkdir()
        with patch.object(self.batch, 'LOG', bad_log):
            with patch.object(self.batch, 'record', wraps=self.real_record):
                result = self.perform()
        self.assertEqual(result.save_stage, self.SaveStage.LIST_RETURN_CONFIRMED)
        self.clean_current.assert_called_once()

    def test_tags_unchanged_preserves_attempt_without_repeating_save(self):
        self.verify_tags.side_effect = RuntimeError('tags still present')
        with self.assertRaises(self.batch.MetadataCardFailure) as caught:
            self.perform()
        self.assertEqual(caught.exception.save_stage, self.SaveStage.ATTEMPTED)
        self.clean_current.assert_called_once()
        self.wait_list.assert_called_once()
        self.assertEqual(self.verified_records(), [])

    def test_interrupt_during_list_verification_retains_attempt(self):
        self.wait_list.side_effect = KeyboardInterrupt()
        with self.assertRaises(self.batch.MetadataCardInterrupted) as caught:
            self.perform()
        self.assertEqual(caught.exception.save_stage, self.SaveStage.ATTEMPTED)
        self.clean_current.assert_called_once()
        self.assertEqual(self.verified_records(), [])


@unittest.skipUnless(sys.platform == 'darwin', 'legacy GUI imports require macOS')
class MetadataResultValidationTests(unittest.TestCase):
    def setUp(self):
        from doumao.core import batch_cleaner as batch
        from doumao.core.title_edit_contract import SaveStage
        self.batch = batch
        self.SaveStage = SaveStage
        self.valid = batch.cleaner.MetadataCleanResult(
            title='Sample Item', save_stage=SaveStage.ATTEMPTED,
            removed_tags=2, edit_dialog_disappeared=True, log_written=False)

    def check(self, value):
        self.batch.verify_editor_result(value, 'Sample Item')

    def test_observed_save_result_accepted_independently_of_jsonl(self):
        self.check(self.valid)

    def test_wrong_title_rejected(self):
        self.valid.title = 'Different'
        with self.assertRaisesRegex(RuntimeError, '标题'):
            self.check(self.valid)

    def test_not_attempted_rejected(self):
        self.valid.save_stage = self.SaveStage.NOT_ATTEMPTED
        with self.assertRaisesRegex(RuntimeError, '保存尝试'):
            self.check(self.valid)

    def test_unexpected_confirmed_stage_rejected(self):
        self.valid.save_stage = self.SaveStage.LIST_RETURN_CONFIRMED
        with self.assertRaisesRegex(RuntimeError, '保存尝试'):
            self.check(self.valid)

    def test_editor_not_closed_rejected(self):
        self.valid.edit_dialog_disappeared = False
        with self.assertRaisesRegex(RuntimeError, '弹窗'):
            self.check(self.valid)

    def test_missing_or_invalid_tag_count_rejected(self):
        for count in (None, 0, 6, True, '2'):
            with self.subTest(count=count):
                self.valid.removed_tags = count
                with self.assertRaisesRegex(RuntimeError, '标签删除数量'):
                    self.check(self.valid)

    def test_missing_result_rejected(self):
        with self.assertRaisesRegex(RuntimeError, '结构化保存结果'):
            self.check(None)


if __name__ == '__main__':
    unittest.main()
