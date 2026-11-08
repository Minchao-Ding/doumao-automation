"""Phase 3 Batch 2: direct metadata card results instead of JSONL reads.

The outer workflow is mocked; tests make no GUI calls or real saves.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import numpy as np


@unittest.skipUnless(sys.platform == 'darwin', 'legacy GUI imports require macOS')
class MetadataWorkflowResultTests(unittest.TestCase):
    def setUp(self):
        from doumao.workflows import clean_metadata as workflow
        from doumao.core.title_edit_contract import SaveStage

        self.workflow = workflow
        self.SaveStage = SaveStage
        self.image = np.zeros((1200, 1900, 3), dtype=np.uint8)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

        def mock(target, name, **kwargs):
            return self.stack.enter_context(patch.object(target, name, **kwargs))

        mock(workflow.time, 'sleep')
        mock(workflow, 'frame', return_value=self.image)
        mock(workflow, 'ensure_clean_list')
        mock(workflow, 'ensure_layout', return_value=(100, 100))
        mock(workflow.scanner, 'scan_tag_groups', return_value=[(30, 50, 90, 70)])
        mock(workflow, 'safety_check_candidates', return_value=((30, 50, 90, 70, 60, 100), 0))
        self.item = workflow.proven_batch.MetadataCardResult(
            title='Sample Item', save_stage=SaveStage.LIST_RETURN_CONFIRMED,
            note_before_length=0, removed_tags=2, tag_groups_before=1, tag_groups_after=0)
        self.run_one = mock(workflow.proven_batch, 'run_one', return_value=self.item)
        self.original_emit = workflow.emit
        self.emit = mock(workflow, 'emit')

    def run_single(self):
        return self.workflow.run(limit=1, max_scrolls=0, edge_scroll=4, scan_scroll=3)

    def test_verified_card_title_and_count_pass_without_log_reads(self):
        self.run_single()
        self.run_one.assert_called_once_with(1, 1)
        events = [c for c in self.emit.call_args_list if c.args[0] == 'saved_verified']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kwargs['title'], 'Sample Item')
        self.assertEqual(events[0].kwargs['removed_tags'], 2)

    def test_missing_card_result_stops_before_claiming_success(self):
        self.run_one.return_value = None
        with self.assertRaisesRegex(RuntimeError, '已验证结果'):
            self.run_single()
        self.assertFalse(any(c.args[0] == 'saved_verified' for c in self.emit.call_args_list))

    def test_invalid_card_stage_does_not_count_success(self):
        self.run_one.return_value = self.workflow.proven_batch.MetadataCardResult(
            title='Sample Item', save_stage=self.SaveStage.ATTEMPTED,
            note_before_length=0, removed_tags=2, tag_groups_before=1, tag_groups_after=0)
        with self.assertRaisesRegex(RuntimeError, '尚未确认'):
            self.run_single()
        self.assertFalse(any(c.args[0] == 'saved_verified' for c in self.emit.call_args_list))

    def test_uncertain_failure_never_starts_second_card(self):
        original = self.workflow.proven_batch.cleaner.MetadataCleanResult(
            title='Sample Item', save_stage=self.SaveStage.ATTEMPTED)
        self.run_one.side_effect = self.workflow.proven_batch.MetadataCardFailure(original, 'tags unclear')
        with self.assertRaisesRegex(RuntimeError, 'tags unclear'):
            self.run_single()
        self.run_one.assert_called_once()
        self.assertFalse(any(c.args[0] == 'saved_verified' for c in self.emit.call_args_list))

    def test_user_interrupt_stops_without_retry(self):
        self.run_one.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.run_single()
        self.run_one.assert_called_once()

    def test_audit_failure_does_not_change_operation_result(self):
        with tempfile.TemporaryDirectory() as root:
            bad_log = Path(root) / 'directory_instead_of_jsonl'
            bad_log.mkdir()
            with patch.object(self.workflow, 'LOG', bad_log):
                # Real emit() must swallow a local audit write problem.
                with patch.object(self.workflow, 'emit', wraps=self.original_emit):
                    self.run_single()
        self.run_one.assert_called_once()


if __name__ == '__main__':
    unittest.main()
