"""Live-observation regressions: partial batches, no reopening, click drift.

These are simulator tests: no macOS GUI clicks or real user content.
"""
import unittest
from unittest.mock import Mock, patch

import numpy as np

from doumao.core.visible_order_state import VisibleOrderUncertain, ensure_stable, parse_line
from doumao.workflows import visible_order_rename as wf
from doumao.core.title_edit_contract import EditResult, EditOutcome, SaveStage


def grid():
    result = []
    for i in range(12):
        row, col = divmod(i, 4)
        result.append({
            'col': col, 'top': 135+row*285,
            'click': (205+col*225, 245+row*285),
            'fp': np.random.default_rng(100+i).integers(0, 256, (70,60,3), dtype=np.uint8),
        })
    return result


class UI:
    def __init__(self, cards):
        self.cards = cards
        self.handled = []
        self.diagnostics = Mock()
        self.modal_opened_again = False
        self.on_save = None

    def shot(self):
        return np.zeros((1400,1600,3),dtype=np.uint8)

    def check_list(self, frame):
        return None

    def edit_card(self, target, frame, position, do_save, rule):
        if not do_save:
            self.modal_opened_again = True
            raise AssertionError('保存后不得二次打开图纸')
        self.handled.append((position, target['click'], rule['new']))
        if self.on_save:
            self.on_save(position)
        return EditResult(EditOutcome.RETURNED_TO_LIST, SaveStage.LIST_RETURN_CONFIRMED,
                          original_title='existing', proposed_title=rule['new'])


def run(ui, names):
    with patch.object(wf,'detect_visible_grid',side_effect=lambda _:ui.cards), \
         patch.object(wf,'emit'), \
         patch.object(wf.time,'sleep',return_value=None):
        return wf.process_batch(ui, parse_line(names), editor=ui.edit_card)


class FlexibleBatchTests(unittest.TestCase):
    def test_user_can_enter_one_two_three_or_twelve_names(self):
        self.assertEqual([a.position for a in parse_line('3: 甲')],[3])
        self.assertEqual([a.position for a in parse_line('6: 甲 乙')],[6,7])
        self.assertEqual([a.position for a in parse_line('3: 甲 乙 丙')],[3,4,5])
        self.assertEqual(len(parse_line(' '.join('T'+str(i) for i in range(12)))),12)

    def test_same_screen_can_be_completed_in_two_user_chosen_batches(self):
        ui=UI(grid())
        first=run(ui,'3: 甲 乙 丙')
        second=run(ui,'6: 丁 戊 己 庚 辛 壬 癸')
        self.assertEqual(first.completed,[3,4,5])
        self.assertEqual(second.completed,list(range(6,13)))
        self.assertEqual([p for p,_,_ in ui.handled],list(range(3,13)))
        self.assertFalse(ui.modal_opened_again)

    def test_three_successful_saves_are_recorded_before_next_error(self):
        ui=UI(grid())
        def after_save(position):
            if position == 5:
                ui.cards=[dict(c) for c in ui.cards]
                ui.cards[5]=dict(ui.cards[5],top=ui.cards[5]['top']+30)
        ui.on_save=after_save
        captured=[]
        with patch.object(wf,'detect_visible_grid',side_effect=lambda _:ui.cards), \
             patch.object(wf,'emit',side_effect=lambda event,**kwargs:captured.append((event,kwargs))), \
             patch.object(wf.time,'sleep',return_value=None):
            with self.assertRaisesRegex(VisibleOrderUncertain,'超过三行完整卡片'):
                wf.process_batch(ui,parse_line('3: 甲 乙 丙 丁'), editor=ui.edit_card)
        stop = next(data for event,data in captured if event=='batch_stopped')
        self.assertEqual(stop['completed'],[3,4,5])
        self.assertIsNone(stop['pending'])
        self.assertEqual([a['position'] for a in stop['remaining']],[6])
        self.assertEqual([p for p,_,_ in ui.handled],[3,4,5])

    def test_detected_click_point_can_shift_inside_same_card(self):
        before=grid()
        after=[dict(c,click=(c['click'][0]+35,c['click'][1]+35)) for c in before]
        ensure_stable(before,after,fingerprint_positions=range(3,13))

    def test_new_click_uses_latest_snapshot_not_frozen_first_point(self):
        ui=UI(grid())
        original=ui.cards
        counter=[0]
        def detect(_):
            counter[0]+=1
            if counter[0] == 1:
                return original
            return [dict(c,click=(c['click'][0]+34,c['click'][1]+30)) for c in original]
        with patch.object(wf,'detect_visible_grid',side_effect=detect), \
             patch.object(wf,'emit'),patch.object(wf.time,'sleep',return_value=None):
            result=wf.process_batch(ui,parse_line('3: 新标题'), editor=ui.edit_card)
        self.assertEqual(result.completed,[3])
        self.assertEqual(ui.handled[0][1],(original[2]['click'][0]+34, original[2]['click'][1]+30))

    def test_large_horizontal_motion_still_stops_without_click(self):
        ui=UI(grid())
        original=ui.cards
        counter=[0]
        def detect(_):
            counter[0]+=1
            if counter[0]==1:
                return original
            return [dict(c,click=(c['click'][0]+110,c['click'][1])) for c in original]
        with patch.object(wf,'detect_visible_grid',side_effect=detect), \
             patch.object(wf,'emit'),patch.object(wf.time,'sleep',return_value=None):
            with self.assertRaisesRegex(VisibleOrderUncertain,'点击位置大幅改变'):
                wf.process_batch(ui,parse_line('3: 甲'), editor=ui.edit_card)
        self.assertEqual(ui.handled,[])

    def test_large_vertical_drift_stops(self):
        before=grid()
        after=[dict(c,click=(c['click'][0],c['click'][1]+90)) for c in before]
        with self.assertRaisesRegex(VisibleOrderUncertain,'点击位置大幅改变'):
            ensure_stable(before,after,fingerprint_positions=[3])

    def test_wrong_target_art_stops_despite_geometry_tolerance(self):
        before=grid()
        after=[dict(c,click=(c['click'][0]+30,c['click'][1]+30)) for c in before]
        after[2]=dict(after[2],fp=before[3]['fp'])
        with self.assertRaisesRegex(VisibleOrderUncertain,'第 3 张图像'):
            ensure_stable(before,after,fingerprint_positions=[3])

    def test_only_assigned_positions_get_written(self):
        ui=UI(grid())
        result=run(ui,'6: 新名')
        self.assertEqual(result.completed,[6])
        self.assertEqual([p for p,_,_ in ui.handled],[6])

    def test_invalid_overflow_still_does_not_write(self):
        with self.assertRaises(ValueError):
            parse_line('11: 甲 乙 丙')


if __name__=='__main__':
    unittest.main()
