"""Pure phase-1 edit orchestration tests; never import or operate the GUI."""
from __future__ import annotations

import unittest
from unittest.mock import Mock

from doumao.core.title_editor import TitleEditFailure, edit_open_title
from doumao.core.title_edit_contract import EditOutcome, SaveStage


class FakePort:
    def __init__(self, old="Old", new="New"):
        self.old, self.new = old, new
        self.read_calls = 0
        self.actions = []
        self.click_save = Mock(side_effect=lambda: self.actions.append("click_save"))
        self.verify_list_return = Mock(side_effect=lambda: self.actions.append("list_return"))
        self.close_without_save = Mock(side_effect=lambda: self.actions.append("close"))
        self.verify_save_ready = Mock(side_effect=lambda: self.actions.append("save_ready"))
        self.replace_title = Mock(side_effect=lambda value: self.actions.append(("replace", value)))
        self.read_back_title = Mock(side_effect=lambda: self.new)

    def read_title(self):
        self.read_calls += 1
        return self.old


class TitleEditorTests(unittest.TestCase):
    def run_editor(self, port, propose=lambda _: "New", save=True, emit=None):
        return edit_open_title(port, propose, do_save=save, index=3, emit=emit)

    def test_success_runs_single_save_and_confirms_return(self):
        port = FakePort()
        events = []
        result = self.run_editor(port, emit=lambda name, **fields: events.append((name, fields)))
        self.assertEqual(result.outcome, EditOutcome.RETURNED_TO_LIST)
        self.assertEqual(result.save_stage, SaveStage.LIST_RETURN_CONFIRMED)
        self.assertEqual((result.original_title, result.proposed_title), ("Old", "New"))
        port.click_save.assert_called_once_with()
        port.verify_list_return.assert_called_once_with()
        port.close_without_save.assert_not_called()
        self.assertEqual(port.read_calls, 2)
        self.assertEqual([v[0] for v in events], ["inspected", "save_prepared", "save_clicked", "save_returned_list"])

    def test_skipped_title_exits_without_write(self):
        port = FakePort()
        result = self.run_editor(port, propose=lambda _: None)
        self.assertEqual(result.outcome, EditOutcome.SKIPPED)
        self.assertEqual(result.original_title, "Old")
        port.close_without_save.assert_called_once()
        port.replace_title.assert_not_called()
        port.click_save.assert_not_called()

    def test_preview_closes_without_write_or_save(self):
        port = FakePort()
        result = self.run_editor(port, save=False)
        self.assertEqual(result.outcome, EditOutcome.PREVIEW)
        self.assertEqual(result.proposed_title, "New")
        port.replace_title.assert_not_called()
        port.click_save.assert_not_called()
        port.close_without_save.assert_called_once()

    def test_invalid_title_stops_before_side_effect(self):
        port = FakePort()
        with self.assertRaises(TitleEditFailure) as ctx:
            self.run_editor(port, propose=lambda _: "")
        self.assertEqual(ctx.exception.result.outcome, EditOutcome.FAILED_PRE_SAVE)
        port.click_save.assert_not_called()
        port.replace_title.assert_not_called()

    def test_original_changed_stops_without_write(self):
        port = FakePort()
        port.read_title = Mock(side_effect=["Old", "Changed"])
        with self.assertRaises(TitleEditFailure) as ctx:
            self.run_editor(port)
        self.assertEqual(ctx.exception.result.save_stage, SaveStage.NOT_ATTEMPTED)
        port.replace_title.assert_not_called()
        port.click_save.assert_not_called()

    def test_readback_mismatch_stops_without_save(self):
        port = FakePort(new="Wrong")
        with self.assertRaises(TitleEditFailure) as ctx:
            self.run_editor(port)
        self.assertEqual(ctx.exception.result.outcome, EditOutcome.FAILED_PRE_SAVE)
        port.click_save.assert_not_called()

    def test_save_ready_failure_stops_before_click(self):
        port = FakePort()
        port.verify_save_ready.side_effect = RuntimeError("dialog shifted")
        with self.assertRaises(TitleEditFailure) as ctx:
            self.run_editor(port)
        self.assertEqual(ctx.exception.result.save_stage, SaveStage.NOT_ATTEMPTED)
        port.click_save.assert_not_called()

    def test_exception_during_click_is_unconfirmed_attempt(self):
        port = FakePort()
        port.click_save.side_effect = RuntimeError("click status unknown")
        with self.assertRaises(TitleEditFailure) as ctx:
            self.run_editor(port)
        self.assertEqual(ctx.exception.result.outcome, EditOutcome.SAVE_UNCERTAIN)
        self.assertEqual(ctx.exception.result.save_stage, SaveStage.ATTEMPTED)
        port.click_save.assert_called_once()
        port.verify_list_return.assert_not_called()

    def test_return_timeout_is_unconfirmed_attempt(self):
        port = FakePort()
        port.verify_list_return.side_effect = RuntimeError("list timeout")
        with self.assertRaises(TitleEditFailure) as ctx:
            self.run_editor(port)
        self.assertEqual(ctx.exception.result.outcome, EditOutcome.SAVE_UNCERTAIN)
        port.click_save.assert_called_once()

    def test_logging_failure_after_click_does_not_reclassify_as_pre_save(self):
        port = FakePort()
        def report(name, **_):
            if name == "save_clicked":
                raise OSError("log unavailable")
        with self.assertRaises(TitleEditFailure) as ctx:
            self.run_editor(port, emit=report)
        self.assertEqual(ctx.exception.result.outcome, EditOutcome.SAVE_UNCERTAIN)
        port.click_save.assert_called_once()

    def test_logging_failure_after_confirm_keeps_confirmed_stage(self):
        port = FakePort()
        def report(name, **_):
            if name == "save_returned_list":
                raise OSError("log unavailable")
        with self.assertRaises(TitleEditFailure) as ctx:
            self.run_editor(port, emit=report)
        self.assertEqual(ctx.exception.result.save_stage, SaveStage.LIST_RETURN_CONFIRMED)
        self.assertEqual(ctx.exception.result.outcome, EditOutcome.RETURNED_TO_LIST)
        port.click_save.assert_called_once()

    def test_interrupt_after_click_propagates_no_retry_and_records_stage(self):
        port = FakePort()
        port.verify_list_return.side_effect = KeyboardInterrupt()
        events = []
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.run_editor(port, emit=lambda name, **fields: events.append((name, fields)))
        self.assertEqual(caught.exception.result.save_stage, SaveStage.ATTEMPTED)
        self.assertEqual(events[-1][1]["save_stage"], SaveStage.ATTEMPTED.value)
        port.click_save.assert_called_once()

    def test_stop_logging_failure_does_not_hide_root_error(self):
        port = FakePort()
        port.click_save.side_effect = RuntimeError("save failed")
        def report(name, **_):
            if name == "title_edit_stopped":
                raise OSError("logger failed")
        with self.assertRaises(TitleEditFailure) as ctx:
            self.run_editor(port, emit=report)
        self.assertIsInstance(ctx.exception.__cause__, RuntimeError)
        port.click_save.assert_called_once()


if __name__ == "__main__":
    unittest.main()


class SelectedCardCompositionTests(unittest.TestCase):
    def test_uses_shared_transaction_and_explicit_gui_configuration(self):
        import sys
        from types import ModuleType
        from unittest.mock import patch
        from doumao.core.title_editor import edit_selected_card

        fake_gui = ModuleType('doumao.core.title_gui')
        port = FakePort()
        fake_gui.open_title_port = Mock(return_value=port)
        fake_rules = ModuleType('doumao.title_rules')
        fake_rules.proposal = Mock(return_value='New')
        target, frame = {'click': (120, 200)}, object()
        events = []
        with patch.dict(sys.modules, {'doumao.core.title_gui': fake_gui,
                                      'doumao.title_rules': fake_rules}):
            result = edit_selected_card(target, frame, 4, True, {'rule_type': 'example'},
                                        click_command='/mock/cliclick',
                                        emit=lambda name, **kw: events.append(name))
        self.assertEqual(result.outcome, EditOutcome.RETURNED_TO_LIST)
        fake_gui.open_title_port.assert_called_once_with(target, frame,
                                                        click_command='/mock/cliclick')
        fake_rules.proposal.assert_called_once_with('Old', {'rule_type': 'example'})
        port.click_save.assert_called_once()
        self.assertIn('save_returned_list', events)

    def test_skipped_card_never_saves(self):
        import sys
        from types import ModuleType
        from unittest.mock import patch
        from doumao.core.title_editor import edit_selected_card

        fake_gui = ModuleType('doumao.core.title_gui')
        port = FakePort()
        fake_gui.open_title_port = Mock(return_value=port)
        fake_rules = ModuleType('doumao.title_rules')
        fake_rules.proposal = Mock(return_value=None)
        with patch.dict(sys.modules, {'doumao.core.title_gui': fake_gui,
                                      'doumao.title_rules': fake_rules}):
            result = edit_selected_card({'click': (1, 1)}, object(), 1, True,
                                        {'rule_type': 'unused'}, click_command='/mock/cliclick')
        self.assertEqual(result.outcome, EditOutcome.SKIPPED)
        port.click_save.assert_not_called()
        port.close_without_save.assert_called_once()
