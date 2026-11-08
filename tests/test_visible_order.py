"""Tests of new visible-grid logic, without macOS GUI or real titles."""
import unittest
from unittest.mock import patch, Mock
import numpy as np

from doumao.core.visible_order_state import (
    BatchState, VisibleOrderUncertain, ensure_stable, ordered_cards,
    parse_line, verify_mapping,
)
from doumao.workflows import visible_order_rename as wf
from doumao.core.title_edit_contract import EditResult, EditOutcome, SaveStage


def card(col, top, token):
    image=np.random.default_rng(token).integers(0,256,(60,70,3),dtype=np.uint8)
    return {'col':col,'top':top,'click':(100+col*100,top+30),'fp':image}

class ParserTests(unittest.TestCase):
    def test_twelve(self):
        self.assertEqual([a.position for a in parse_line(' '.join('N'+str(i) for i in range(12)))],list(range(1,13)))
    def test_start_three(self):
        self.assertEqual([(a.position,a.title) for a in parse_line('3: 甲 乙')],[(3,'甲'),(4,'乙')])
    def test_full_width_colon(self):
        self.assertEqual(parse_line('12：甲')[0].position,12)
    def test_duplicate(self):
        self.assertEqual([a.title for a in parse_line('甲 甲')],['甲','甲'])
    def test_quoted_space(self):
        self.assertEqual(parse_line('"A B" C')[0].title,'A B')
    def test_small_batch(self):
        self.assertEqual(len(parse_line('A B')),2)
    def test_overflow(self):
        for line in ('3: '+('A '*11),' '.join('A' for _ in range(13)),'13: A',''):
            with self.subTest(line=line), self.assertRaises(ValueError): parse_line(line)
    def test_unclosed_quote(self):
        with self.assertRaises(ValueError): parse_line('"oops')
    def test_original_punctuation(self):
        self.assertEqual(parse_line('A｜B （测试）')[0].title,'A｜B')

class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.cards=[card(col,top+(col%2)*2,1+row*4+col)
                    for row,top in enumerate((200,400,600)) for col in range(4)]
    def test_grid_order_with_row_jitter(self):
        unordered=self.cards[::-1]
        self.assertEqual([c['col'] for c in ordered_cards(unordered,2047)],[0,1,2,3]*3)
        self.assertEqual([c['top'] for c in ordered_cards(unordered,2047)][:4],[200,202,200,202])
    def test_partial_final_row(self):
        self.assertEqual(len(ordered_cards(self.cards[:10],2047)),10)
        verify_mapping(parse_line('9: A B'),10)
    def test_missing_position(self):
        with self.assertRaises(ValueError):verify_mapping(parse_line('11: A B'),10)
    def test_missing_middle_card(self):
        with self.assertRaises(VisibleOrderUncertain):ordered_cards(self.cards[:5]+self.cards[6:],2047)
    def test_reordered_detected(self):
        after=list(self.cards)
        after[0],after[1]=after[1],after[0]
        with self.assertRaises(VisibleOrderUncertain):ensure_stable(self.cards,after)
    def test_thumbnail_change_detected(self):
        after=[dict(c) for c in self.cards]
        after[0]=dict(after[0],fp=card(0,200,900)['fp'])
        with self.assertRaises(VisibleOrderUncertain):ensure_stable(self.cards,after)
    def test_stable(self):
        self.assertIsNone(ensure_stable(self.cards,self.cards))
    def test_change_position_detected(self):
        after=[dict(c) for c in self.cards]
        after[0]=dict(after[0],top=100)
        with self.assertRaises(VisibleOrderUncertain):ensure_stable(self.cards,after)
    def test_pending_state(self):
        s=BatchState(parse_line('A B'))
        s.begin(1)
        with self.assertRaises(VisibleOrderUncertain):s.begin(2)
        s.verified(1)
        self.assertEqual([a.position for a in s.remaining],[2])

class FakeUI:
    def __init__(self, cards, *, fail=False, skip=False):
        self.cards=cards
        self.fail=fail
        self.skip=skip
        self.handled=[]
        self.cleaner=Mock()
        self.diagnostics=Mock()

    def shot(self):
        return np.zeros((1200,2047,3),dtype=np.uint8)
    def check_list(self, frame):
        pass
    def card_rows(self,frame):
        return self.cards
    def edit_card(self,target,frame,pos,save,rule):
        self.handled.append((pos,save,rule['new']))
        if self.fail and save:
            raise RuntimeError('uncertain saving')
        if save:
            return (EditResult(EditOutcome.SKIPPED, SaveStage.NOT_ATTEMPTED,
                           original_title=rule['new'], proposed_title=rule['new'])
                if self.skip else EditResult(EditOutcome.RETURNED_TO_LIST,
                    SaveStage.LIST_RETURN_CONFIRMED, original_title='old',
                    proposed_title=rule['new']))
        return EditResult(EditOutcome.SKIPPED, SaveStage.NOT_ATTEMPTED,
                          original_title=rule['new'], proposed_title=rule['new'])

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.cards=[card(c,200+c%2,1+c) for c in range(4)]
        self.events=[]
    def run_batch(self,ui,line):
        with patch.object(wf,'emit',side_effect=lambda event,**data:self.events.append((event,data))),\
             patch.object(wf.time,'sleep',return_value=None),\
             patch.object(wf,'detect_visible_grid',side_effect=lambda frame:ui.cards):
            return wf.process_batch(ui,parse_line(line),editor=ui.edit_card)
    def test_same_names_both_positions(self):
        ui=FakeUI(self.cards)
        state=self.run_batch(ui,'Same Same')
        self.assertEqual(state.completed,[1,2])
        self.assertEqual(ui.handled,[(1,True,'Same'),(2,True,'Same')])
    def test_save_returns_list_without_reopening(self):
        ui=FakeUI(self.cards)
        def refuse_reopen(target,frame,pos,save,rule):
            ui.handled.append((pos,save,rule['new']))
            if not save:
                raise AssertionError('保存后不应重新打开同一张图纸')
            return EditResult(EditOutcome.RETURNED_TO_LIST,
                              SaveStage.LIST_RETURN_CONFIRMED,
                              original_title='old', proposed_title=rule['new'])
        ui.edit_card=refuse_reopen
        state=self.run_batch(ui,'A B')
        self.assertEqual(state.completed,[1,2])
        self.assertEqual(ui.handled,[(1,True,'A'),(2,True,'B')])

    def test_saved_layout_shift_stops_next_position(self):
        ui=FakeUI(self.cards)
        original=ui.edit_card
        def shifted(target,frame,pos,save,rule):
            result=original(target,frame,pos,save,rule)
            if save:
                ui.cards[0]=dict(ui.cards[0],top=ui.cards[0]['top']+30)
            return result
        ui.edit_card=shifted
        with self.assertRaises(VisibleOrderUncertain):self.run_batch(ui,'A B')
        self.assertEqual(ui.handled,[(1,True,'A')])

    def test_start_two(self):
        ui=FakeUI(self.cards)
        self.assertEqual(self.run_batch(ui,'2: A B').completed,[2,3])
    def test_failure_never_advances(self):
        ui=FakeUI(self.cards,fail=True)
        with self.assertRaises(VisibleOrderUncertain):self.run_batch(ui,'A B')
        self.assertEqual(ui.handled,[(1,True,'A')])
        event=next(v for e,v in self.events if e=='batch_stopped')
        self.assertEqual(event['pending'],1)
        self.assertEqual([a['position'] for a in event['remaining']],[1,2])
    def test_bad_visible_count_no_click(self):
        ui=FakeUI(self.cards[:2])
        with self.assertRaises(ValueError):self.run_batch(ui,'3: A')
        self.assertEqual(ui.handled,[])
    def test_waiting_for_input_does_not_touch_gui(self):
        ui=FakeUI(self.cards)
        called=[]
        def enter(prompt):
            called.append(prompt)
            return '退出'
        with patch.object(wf,'frontend',return_value=ui), patch.object(wf,'resolve_click_command',return_value='/fake/cliclick'):
            wf.run(input_func=enter,sleep=lambda seconds:None, editor=ui.edit_card)
        self.assertEqual(len(called),1)
        self.assertEqual(ui.handled,[])
    def test_preview_only_never_opens_editor(self):
        ui=FakeUI(self.cards)
        inputs=iter(['A B','退出'])
        with patch.object(wf,'frontend',return_value=ui), \
             patch.object(wf,'resolve_click_command',return_value='/fake/cliclick'), patch.object(wf,'emit'), \
             patch.object(wf,'preview_batch') as preview:
            wf.run(input_func=lambda prompt:next(inputs),sleep=lambda seconds:None,preview_only=True, editor=ui.edit_card)
        self.assertEqual(ui.handled,[])
        self.assertEqual(preview.call_count,1)

    def test_consecutive_batches(self):
        ui=FakeUI(self.cards)
        inputs=iter(['A B','3: C D','退出'])
        with patch.object(wf,'frontend',return_value=ui),\
             patch.object(wf,'resolve_click_command',return_value='/fake/cliclick'),patch.object(wf,'emit'),patch.object(wf.time,'sleep'),\
             patch.object(wf,'detect_visible_grid',side_effect=lambda frame:ui.cards):
            wf.run(input_func=lambda prompt:next(inputs),sleep=lambda seconds:None, editor=ui.edit_card)
        self.assertEqual([x[0] for x in ui.handled if x[1]],[1,2,3,4])

if __name__ == '__main__': unittest.main()
