"""Phase 3: interrupted metadata cleanup must not suggest Save was definitely absent."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace

from doumao.__main__ import guarded
from doumao.core.title_edit_contract import SaveStage


class MetadataCliInterruptionTests(unittest.TestCase):
    def capture_stop(self, error, *, cleanup=True):
        def interrupted():
            raise error
        output = io.StringIO()
        with redirect_stdout(output):
            with self.assertRaises(SystemExit) as caught:
                guarded(interrupted, lambda *args: None, cleanup=cleanup)
        self.assertEqual(caught.exception.code, 130)
        return output.getvalue()

    def test_nested_attempted_save_warns_against_retry(self):
        error = KeyboardInterrupt()
        error.result = SimpleNamespace(save_stage=SaveStage.ATTEMPTED)
        message = self.capture_stop(error)
        self.assertIn('保存点击已尝试', message)
        self.assertIn('不要直接重跑', message)
        self.assertNotIn('关闭任何未保存', message)

    def test_direct_attempted_save_warns_against_retry(self):
        error = KeyboardInterrupt()
        error.save_stage = SaveStage.ATTEMPTED
        self.assertIn('保存点击已尝试', self.capture_stop(error))

    def test_pre_save_interrupt_reports_no_attempt(self):
        error = KeyboardInterrupt()
        error.result = SimpleNamespace(save_stage=SaveStage.NOT_ATTEMPTED)
        message = self.capture_stop(error)
        self.assertIn('本次未尝试保存', message)
        self.assertNotIn('保存点击已尝试', message)

    def test_unknown_stage_conservatively_warns(self):
        message = self.capture_stop(KeyboardInterrupt())
        self.assertIn('无法确认', message)
        self.assertIn('不要直接重跑', message)

    def test_confirmed_list_return_not_claimed_as_cloud_sync(self):
        error = KeyboardInterrupt()
        error.save_stage = SaveStage.LIST_RETURN_CONFIRMED
        message = self.capture_stop(error)
        self.assertIn('返回列表', message)
        self.assertIn('不代表云端同步完成', message)

    def test_other_workflow_message_unchanged(self):
        message = self.capture_stop(KeyboardInterrupt(), cleanup=False)
        self.assertIn('关闭任何未保存的编辑弹窗', message)


if __name__ == '__main__':
    unittest.main()
