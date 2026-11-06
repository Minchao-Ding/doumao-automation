"""Phase-0 save-boundary regression for existing v3.5 metadata cleanup.

All screenshot, navigation, keyboard, tag and file-writing interactions in
run_one() are mocked. Real JSONL parser tests use only temporary test files.
No Doumao application, private screenshot, or production collection is used.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "darwin", "legacy GUI imports require macOS")
class MetadataRunOneBoundaryTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from doumao.core import batch_cleaner as batch

        self.batch = batch
        self.frame = np.zeros((1200, 1900, 3), dtype=np.uint8)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)

        def mock(target, name, **kwargs):
            return self.patches.enter_context(patch.object(target, name, **kwargs))

        mock(batch.cleaner, "LOG", new=Path(self.temporary.name) / "operations.jsonl")
        mock(batch.scanner, "assert_app")
        mock(batch, "screenshot", return_value=self.frame)
        mock(batch.cleaner, "find_save", return_value=None)
        mock(batch.navigator, "find_detail_modal", return_value=None)
        mock(batch.scanner, "scan_tag_groups", return_value=[(80, 90, 140, 110)])
        mock(batch.v08, "find_first_candidate", return_value=(1, (80, 90, 140, 110, 110, 200)))
        mock(batch, "save_preview")
        self.screen_click = mock(batch.v08, "screen_click")
        mock(batch.v08, "wait_for_detail", return_value=(self.frame, (30, 30, 200, 200)))
        mock(batch.navigator, "find_pencil", return_value=((100, 100), (70, 70, 50, 50)))
        self.wait_editor = mock(batch, "wait_for_editor_robust", return_value=(self.frame, (30, 700, 120, 40)))
        mock(batch.cleaner, "form_rects", return_value=((50, 100, 140, 35), (50, 200, 140, 35)))
        self.read_field = mock(batch.cleaner, "read_field", return_value="Sample Item")
        self.record = mock(batch, "record")
        self.clean_current = mock(batch.cleaner, "clean_current")
        self.new_event = mock(batch, "new_cleaner_event", return_value={
            "title": "Sample Item", "save_clicked": True,
            "edit_dialog_disappeared": True, "removed_tags": 2,
        })
        self.wait_list = mock(batch, "wait_for_list_after_save", return_value=self.frame)
        self.verify_tags = mock(batch, "verify_tag_disappeared", return_value=0)

    def perform(self):
        return self.batch.run_one(1, 2)

    def verified_records(self):
        return [call for call in self.record.call_args_list
                if len(call.args) > 1 and call.args[1] == "verified_on_list"]

    def test_success_calls_metadata_editor_once_then_verifies_list_and_tags(self):
        self.assertTrue(self.perform())
        self.clean_current.assert_called_once_with(title="Sample Item", auto_save=True)
        self.new_event.assert_called_once_with(0, "Sample Item")
        self.wait_list.assert_called_once_with()
        self.verify_tags.assert_called_once()
        self.assertEqual(len(self.verified_records()), 1)

    def test_editor_not_confirmed_never_invokes_save_path(self):
        self.wait_editor.side_effect = RuntimeError("editor not confirmed")
        with self.assertRaisesRegex(RuntimeError, "editor not confirmed"):
            self.perform()
        self.clean_current.assert_not_called()
        self.new_event.assert_not_called()
        self.assertEqual(self.verified_records(), [])

    def test_unreadable_title_never_invokes_save_path(self):
        self.read_field.return_value = ""
        with self.assertRaisesRegex(RuntimeError, "读取的原标题异常"):
            self.perform()
        self.clean_current.assert_not_called()
        self.new_event.assert_not_called()
        self.assertEqual(self.verified_records(), [])

    def test_error_inside_save_path_does_not_retry_metadata_edit(self):
        # The legacy boundary cannot reveal whether the nested click occurred.
        self.clean_current.side_effect = RuntimeError("Save possibly dispatched")
        with self.assertRaisesRegex(RuntimeError, "Save possibly dispatched"):
            self.perform()
        self.clean_current.assert_called_once()
        self.new_event.assert_not_called()
        self.wait_list.assert_not_called()
        self.assertEqual(self.verified_records(), [])

    def test_keyboard_interrupt_inside_save_path_does_not_retry(self):
        self.clean_current.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.perform()
        self.clean_current.assert_called_once()
        self.new_event.assert_not_called()
        self.wait_list.assert_not_called()
        self.assertEqual(self.verified_records(), [])

    def test_missing_save_log_stops_without_claiming_success(self):
        self.new_event.return_value = None
        with self.assertRaisesRegex(RuntimeError, "没有读到本次保存日志"):
            self.perform()
        self.clean_current.assert_called_once()
        self.wait_list.assert_not_called()
        self.assertEqual(self.verified_records(), [])

    def test_log_validation_failure_stops_without_repeating_save(self):
        self.new_event.side_effect = RuntimeError("save log corrupted")
        with self.assertRaisesRegex(RuntimeError, "save log corrupted"):
            self.perform()
        self.clean_current.assert_called_once()
        self.wait_list.assert_not_called()
        self.assertEqual(self.verified_records(), [])

    def test_list_return_timeout_stops_without_repeating_save(self):
        self.wait_list.side_effect = RuntimeError("list not confirmed")
        with self.assertRaisesRegex(RuntimeError, "list not confirmed"):
            self.perform()
        self.clean_current.assert_called_once()
        self.new_event.assert_called_once()
        self.verify_tags.assert_not_called()
        self.assertEqual(self.verified_records(), [])

    def test_tags_unchanged_stops_without_repeating_save(self):
        self.verify_tags.side_effect = RuntimeError("tags still present")
        with self.assertRaisesRegex(RuntimeError, "tags still present"):
            self.perform()
        self.clean_current.assert_called_once()
        self.wait_list.assert_called_once()
        self.assertEqual(self.verified_records(), [])


@unittest.skipUnless(sys.platform == "darwin", "legacy GUI imports require macOS")
class MetadataSaveLogTests(unittest.TestCase):
    def setUp(self):
        from doumao.core import batch_cleaner as batch
        self.batch = batch
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.log_path = Path(self.temporary.name) / "operations.jsonl"
        self.log_patch = patch.object(batch.cleaner, "LOG", self.log_path)
        self.log_patch.start()
        self.addCleanup(self.log_patch.stop)

    def write_records(self, *records):
        with self.log_path.open("w", encoding="utf-8") as f:
            for record in records:
                if isinstance(record, str):
                    f.write(record + "\n")
                else:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def valid(self, **changes):
        item = {"title": "Sample Item", "save_clicked": True,
                "edit_dialog_disappeared": True}
        item.update(changes)
        return item

    def test_single_new_save_event_accepted(self):
        self.write_records(self.valid())
        self.assertTrue(self.batch.new_cleaner_event(0, "Sample Item")["save_clicked"])

    def test_earlier_log_events_are_not_reused(self):
        self.write_records(self.valid())
        prior_length = self.log_path.stat().st_size
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(self.valid()) + "\n")
        self.assertEqual(self.batch.new_cleaner_event(prior_length, "Sample Item")["title"],
                         "Sample Item")
        with self.assertRaisesRegex(RuntimeError, "实际 0 条"):
            self.batch.new_cleaner_event(self.log_path.stat().st_size, "Sample Item")

    def test_corrupt_json_rejected(self):
        self.write_records("not JSON")
        with self.assertRaisesRegex(RuntimeError, "无法解析"):
            self.batch.new_cleaner_event(0, "Sample Item")

    def test_multiple_new_events_rejected(self):
        self.write_records(self.valid(), self.valid())
        with self.assertRaisesRegex(RuntimeError, "实际 2 条"):
            self.batch.new_cleaner_event(0, "Sample Item")

    def test_wrong_title_or_save_flag_rejected(self):
        for record in (self.valid(title="Different"), self.valid(save_clicked=False)):
            with self.subTest(record=record):
                self.write_records(record)
                with self.assertRaisesRegex(RuntimeError, "标题或保存状态不匹配"):
                    self.batch.new_cleaner_event(0, "Sample Item")

    def test_save_click_without_dialog_disappearance_rejected(self):
        self.write_records(self.valid(edit_dialog_disappeared=False))
        with self.assertRaisesRegex(RuntimeError, "编辑弹窗没有消失"):
            self.batch.new_cleaner_event(0, "Sample Item")


if __name__ == "__main__":
    unittest.main()
