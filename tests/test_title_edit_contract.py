"""Phase-0 offline tests for the future shared editor contract.

Pure mocks only: no imported macOS GUI, no images and no real item titles.
"""
import unittest
from unittest.mock import Mock

from doumao.core.title_edit_contract import (
    DuplicateSaveAttempt, EditOutcome, EditResult, SaveStage,
    SaveTransitionError, SingleSaveGuard, stopped_result,
)


class SingleSaveAttemptTests(unittest.TestCase):
    def test_new_operation_starts_without_save(self):
        guard = SingleSaveGuard()
        self.assertEqual(guard.stage, SaveStage.NOT_ATTEMPTED)
        self.assertFalse(guard.save_attempted)

    def test_success_exactly_one_click_then_list_confirmation(self):
        click = Mock()
        guard = SingleSaveGuard()
        guard.click_once(click)
        self.assertEqual(guard.stage, SaveStage.ATTEMPTED)
        guard.confirm_list_return()
        self.assertEqual(guard.stage, SaveStage.LIST_RETURN_CONFIRMED)
        with self.assertRaises(DuplicateSaveAttempt):
            guard.click_once(click)
        click.assert_called_once_with()

    def test_pre_save_validation_failure_never_clicks(self):
        click = Mock()
        guard = SingleSaveGuard()
        with self.assertRaisesRegex(ValueError, "readback"):
            raise ValueError("readback mismatch")
        result = stopped_result(guard, reason="readback mismatch")
        self.assertEqual(result.outcome, EditOutcome.FAILED_PRE_SAVE)
        self.assertFalse(guard.save_attempted)
        click.assert_not_called()

    def test_exception_from_click_is_still_an_attempt(self):
        click = Mock(side_effect=RuntimeError("GUI timeout during click"))
        guard = SingleSaveGuard()
        with self.assertRaises(RuntimeError):
            guard.click_once(click)
        self.assertEqual(guard.stage, SaveStage.ATTEMPTED)
        result = stopped_result(guard, reason="GUI timeout")
        self.assertEqual(result.outcome, EditOutcome.SAVE_UNCERTAIN)
        with self.assertRaises(DuplicateSaveAttempt):
            guard.click_once(click)
        click.assert_called_once_with()

    def test_return_not_confirmed_cannot_retry_save(self):
        click = Mock()
        guard = SingleSaveGuard()
        guard.click_once(click)
        result = stopped_result(guard, reason="list did not return")
        self.assertEqual(result.outcome, EditOutcome.SAVE_UNCERTAIN)
        with self.assertRaises(DuplicateSaveAttempt):
            guard.click_once(click)
        click.assert_called_once_with()

    def test_cancellation_before_save(self):
        click = Mock()
        guard = SingleSaveGuard()
        result = stopped_result(guard, cancelled=True)
        self.assertEqual(result.outcome, EditOutcome.CANCELLED)
        click.assert_not_called()

    def test_cancellation_after_save_attempt_is_uncertain(self):
        click = Mock()
        guard = SingleSaveGuard()
        guard.click_once(click)
        result = stopped_result(guard, cancelled=True)
        self.assertEqual(result.outcome, EditOutcome.SAVE_UNCERTAIN)
        with self.assertRaises(DuplicateSaveAttempt):
            guard.click_once(click)
        click.assert_called_once_with()

    def test_interrupted_before_save(self):
        result = stopped_result(SingleSaveGuard(), interrupted=True)
        self.assertEqual(result.outcome, EditOutcome.STOPPED)

    def test_interrupted_after_save_attempt_is_uncertain(self):
        guard = SingleSaveGuard()
        click = Mock()
        guard.click_once(click)
        result = stopped_result(guard, interrupted=True)
        self.assertEqual(result.outcome, EditOutcome.SAVE_UNCERTAIN)
        click.assert_called_once()

    def test_cannot_confirm_without_click(self):
        with self.assertRaises(SaveTransitionError):
            SingleSaveGuard().confirm_list_return()

    def test_cannot_double_confirm(self):
        guard = SingleSaveGuard()
        guard.click_once(Mock())
        guard.confirm_list_return()
        with self.assertRaises(SaveTransitionError):
            guard.confirm_list_return()

    def test_new_guard_for_distinct_item_only(self):
        first, second = SingleSaveGuard(), SingleSaveGuard()
        click_first, click_second = Mock(), Mock()
        first.click_once(click_first)
        second.click_once(click_second)
        click_first.assert_called_once()
        click_second.assert_called_once()

    def test_invalid_success_without_list_return_is_rejected(self):
        with self.assertRaises(ValueError):
            EditResult(EditOutcome.RETURNED_TO_LIST, SaveStage.ATTEMPTED)

    def test_invalid_uncertain_without_attempt_is_rejected(self):
        with self.assertRaises(ValueError):
            EditResult(EditOutcome.SAVE_UNCERTAIN, SaveStage.NOT_ATTEMPTED)

    def test_confirmation_not_cloud_sync(self):
        result = EditResult(EditOutcome.RETURNED_TO_LIST,
                            SaveStage.LIST_RETURN_CONFIRMED,
                            original_title="Demo A", proposed_title="Demo B")
        self.assertEqual(result.outcome, EditOutcome.RETURNED_TO_LIST)
        self.assertFalse(hasattr(result, "cloud_synced"))

    def test_later_failure_does_not_unverify_confirmed_save(self):
        guard = SingleSaveGuard()
        guard.click_once(Mock())
        guard.confirm_list_return()
        result = stopped_result(guard, reason="later logging error")
        self.assertEqual(result.outcome, EditOutcome.RETURNED_TO_LIST)


if __name__ == "__main__":
    unittest.main()
