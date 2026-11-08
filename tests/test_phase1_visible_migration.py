"""Phase 1 visible-order dependency and save-state regressions.

These tests do not open Doumao or dispatch real GUI operations.
"""
from __future__ import annotations

import inspect
import unittest
from unittest.mock import Mock, patch

import numpy as np

from doumao.core.title_edit_contract import EditResult, EditOutcome, SaveStage
from doumao.core.title_editor import TitleEditFailure, TitleEditInterrupted
from doumao.core.visible_order_state import parse_line, VisibleOrderUncertain
from doumao.workflows import visible_order_rename as wf


def art(index):
    return {'col': index, 'top': 120, 'click': (100+index*100, 200),
            'fp': np.full((30, 30, 3), index, dtype=np.uint8)}


class VisibleMigrationTests(unittest.TestCase):
    def setUp(self):
        self.ui = Mock()
        self.frame = np.zeros((1200, 1600, 3), dtype=np.uint8)
        self.cards = [art(0), art(1)]
        self.events = []

    def process(self, editor):
        with patch.object(wf, 'capture', return_value=(self.frame, self.cards)), \
             patch.object(wf, 'check_snapshot', return_value=(self.frame, self.cards)), \
             patch.object(wf, 'emit', side_effect=lambda name, **fields: self.events.append((name, fields))):
            return wf.process_batch(self.ui, parse_line('A B'), editor=editor)

    def test_no_workflow_import_or_legacy_gui_globals(self):
        source = inspect.getsource(wf)
        self.assertNotIn('normalize_titles', source)
        self.assertNotIn('ui.cleaner.CLICK', source)
        self.assertNotIn('ui.LOG =', source)
        self.assertNotIn('ui.DIAGNOSTIC =', source)
        self.assertNotIn('handle_card', source)

    def test_result_has_explicit_save_stage(self):
        def stub(target, frame, index, do_save, rule):
            return EditResult(EditOutcome.RETURNED_TO_LIST, SaveStage.LIST_RETURN_CONFIRMED,
                              original_title='Old', proposed_title=rule['new'])
        state = self.process(stub)
        self.assertEqual(state.completed, [1, 2])
        events = [data for event, data in self.events if event == 'position_verified']
        self.assertEqual([e['save_stage'] for e in events],
                         [SaveStage.LIST_RETURN_CONFIRMED.value]*2)

    def test_uncertain_save_stops_and_preserves_stage(self):
        called = Mock(side_effect=[TitleEditFailure(EditResult(
            EditOutcome.SAVE_UNCERTAIN, SaveStage.ATTEMPTED,
            original_title='Old', proposed_title='A', reason='no list return'))])
        with self.assertRaises(VisibleOrderUncertain):
            self.process(called)
        called.assert_called_once()
        stopped = next(d for n, d in self.events if n == 'batch_stopped')
        self.assertEqual(stopped['pending'], 1)
        self.assertEqual(stopped['save_stage'], SaveStage.ATTEMPTED.value)
        self.assertEqual(stopped['completed'], [])

    def test_interrupted_save_stops_without_retrying(self):
        called = Mock(side_effect=[TitleEditInterrupted(EditResult(
            EditOutcome.SAVE_UNCERTAIN, SaveStage.ATTEMPTED,
            original_title='Old', proposed_title='A', reason='interrupt'))])
        with self.assertRaises(KeyboardInterrupt):
            self.process(called)
        called.assert_called_once()
        stopped = next(d for n, d in self.events if n == 'batch_stopped')
        self.assertEqual(stopped['save_stage'], SaveStage.ATTEMPTED.value)


if __name__ == '__main__':
    unittest.main()
