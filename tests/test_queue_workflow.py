"""Mock workflow tests: no Mac I/O, no GUI imports, no private data."""
import unittest
import ast
from pathlib import Path
from unittest.mock import Mock, patch, call
import numpy as np
from doumao.core.queue_state import QueueUncertain
from doumao.core.title_edit_contract import EditResult, EditOutcome, SaveStage
from doumao.core.title_editor import TitleEditFailure
from doumao.workflows import search_queue_rename as mod

A=np.random.default_rng(1).integers(0,255,(60,70,3),dtype=np.uint8)
B=np.random.default_rng(2).integers(0,255,(60,70,3),dtype=np.uint8)
C=np.random.default_rng(3).integers(0,255,(60,70,3),dtype=np.uint8)

def card(image):return {'fp':image,'col':0,'click':(100,100)}

def saved(old, new):
    return EditResult(EditOutcome.RETURNED_TO_LIST, SaveStage.LIST_RETURN_CONFIRMED,
                      original_title=old, proposed_title=new)


class FakeGUI:
    def __init__(self, outputs):
        self.edit_results = Mock(side_effect=outputs)

class GuiFlowTests(unittest.TestCase):
    def run_mock(self,ui,first,advances,limit):
        mock_py=Mock()
        mock_py.FailSafeException=type('FailSafeException',(Exception,),{})
        with patch.dict('sys.modules',{'pyautogui':mock_py}), \
             patch.object(mod,'_frontend',return_value=ui), \
             patch.object(mod,'edit_selected_card',ui.edit_results), \
             patch.object(mod,'snapshot',return_value=(None,first)), \
             patch.object(mod,'await_advance',side_effect=advances) as advance, \
             patch.object(mod,'emit') as emitted, \
             patch.object(mod,'resolve_click_command',return_value='/usr/bin/cliclick'), \
             patch.object(mod.time,'sleep',return_value=None):
            mod.run(rule={'rule_type':'remove_prefix','prefix':'TEMP:',
                          'search_must_disappear':'TEMP:'},
                    limit=limit,auto_save=True,search='TEMP:')
        return emitted,advance

    def test_equal_titles_different_art_both_processed(self):
        ui=FakeGUI([saved('TEMP: Same','Same'),saved('TEMP: Same','Same')])
        events,_=self.run_mock(ui,[card(A),card(B)],
                  [(None,[card(B)],'advanced'),(None,[],'empty')],limit=9)
        self.assertEqual(ui.edit_results.call_count,2)
        self.assertIn('exhausted',[c.kwargs.get('result') for c in events.call_args_list])
    def test_limit_reached_without_exhausting(self):
        ui=FakeGUI([saved('TEMP: A','A')])
        events,_=self.run_mock(ui,[card(A),card(B)],
                       [(None,[card(B)],'advanced')],limit=1)
        self.assertEqual(ui.edit_results.call_count,1)
        self.assertIn('limit_reached',[c.kwargs.get('result') for c in events.call_args_list])
    def test_empty_from_start_zero(self):
        ui=FakeGUI([])
        events,_=self.run_mock(ui,[],[],limit=5)
        self.assertEqual(ui.edit_results.call_count,0)
    def test_failed_refresh_never_saves_again(self):
        ui=FakeGUI([saved('TEMP: A','A')])
        with self.assertRaises(QueueUncertain):
            self.run_mock(ui,[card(A),card(B)],[QueueUncertain('no refresh')],limit=5)
        self.assertEqual(ui.edit_results.call_count,1)
    def test_save_error_does_not_retry(self):
        ui=FakeGUI([TitleEditFailure(EditResult(EditOutcome.SAVE_UNCERTAIN,
                        SaveStage.ATTEMPTED, 'TEMP: A', 'A', reason='click uncertainty'))])
        with self.assertRaises(QueueUncertain):
            self.run_mock(ui,[card(A)],[ ],limit=5)
        self.assertEqual(ui.edit_results.call_count,1)


class QueueArchitectureTests(unittest.TestCase):
    def test_no_horizontal_workflow_import_or_global_backend_mutation(self):
        tree = ast.parse(Path(mod.__file__).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                self.assertNotIn('normalize_titles', [item.name for item in node.names])
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    self.assertFalse(isinstance(target, ast.Attribute)
                                     and target.attr in {'CLICK', 'LOG', 'DIAGNOSTIC'})
