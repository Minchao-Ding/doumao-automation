"""Oversized pasted name batches stop at currently visible slots; no extra GUI writes."""
import unittest
from unittest.mock import Mock, patch
import numpy as np
from doumao.core.visible_order_state import parse_line, fit_visible_assignments
from doumao.workflows import visible_order_rename as wf


def cards(n=12):
    return [{'col':i%4, 'top':180+(i//4)*250,
             'click':(120+(i%4)*220,290+(i//4)*250),
             'fp':np.random.default_rng(i+51).integers(0,256,(70,60,3),dtype=np.uint8)}
            for i in range(n)]


class UI:
    def __init__(self,n=12):
        self.cards=cards(n)
        self.handled=[]
        self.diagnostics=Mock()
    def shot(self):
        return np.zeros((1200,1400,3),dtype=np.uint8)
    def check_list(self,frame): pass
    def handle_card(self, target, frame, pos, save, rule):
        self.handled.append((pos,rule['new']))
        return 'saved','old',rule['new']


class OverflowTests(unittest.TestCase):
    def test_old_strict_parser_unchanged(self):
        with self.assertRaises(ValueError):
            parse_line('11: A B C D')

    def test_15_names_start_three_clips_to_ten(self):
        names=[f'T{i}' for i in range(15)]
        selected,ignored=parse_line('3: '+' '.join(names),truncate_excess=True,return_ignored=True)
        self.assertEqual([a.position for a in selected],list(range(3,13)))
        self.assertEqual([a.title for a in selected],names[:10])
        self.assertEqual(ignored,names[10:])

    def test_start_twelve_only_first_and_duplicate_names(self):
        selected,ignored=parse_line('12: X X X',truncate_excess=True,return_ignored=True)
        self.assertEqual([(a.position,a.title) for a in selected],[(12,'X')])
        self.assertEqual(ignored,['X','X'])

    def test_default_starts_one_and_ignores_rest(self):
        selected,ignored=parse_line(' '.join('X'+str(i) for i in range(20)),truncate_excess=True,return_ignored=True)
        self.assertEqual(len(selected),12)
        self.assertEqual(len(ignored),8)

    def test_quoted_title_and_invalid_names(self):
        selected,ignored=parse_line('11: "A B" C D',truncate_excess=True,return_ignored=True)
        self.assertEqual([a.title for a in selected],['A B','C'])
        self.assertEqual(ignored,['D'])
        with self.assertRaisesRegex(ValueError,'64'):
            parse_line('12: OK '+('Z'*65),truncate_excess=True,return_ignored=True)
        with self.assertRaisesRegex(ValueError,'引号'):
            parse_line('12: OK "bad',truncate_excess=True,return_ignored=True)
        with self.assertRaises(ValueError):
            parse_line('13: A B',truncate_excess=True,return_ignored=True)

    def test_visible_count_can_drop_more_names(self):
        selected,ignored=parse_line('3: '+' '.join('T'+str(i) for i in range(15)),truncate_excess=True,return_ignored=True)
        usable,dropped=fit_visible_assignments(selected,8)
        self.assertEqual([a.position for a in usable],list(range(3,9)))
        self.assertEqual(dropped,4)
        self.assertEqual(len(ignored),5)
        with self.assertRaises(ValueError):
            fit_visible_assignments(selected,2)

    def test_full_grid_only_writes_capacity(self):
        ui=UI()
        selected,_=parse_line('3: '+' '.join('T'+str(i) for i in range(16)),truncate_excess=True,return_ignored=True)
        with patch.object(wf,'detect_visible_grid',side_effect=lambda frame:ui.cards),patch.object(wf,'emit'),patch.object(wf.time,'sleep',return_value=None):
            state=wf.process_batch(ui,selected,trim_to_visible=True)
        self.assertEqual(len(state.completed),10)
        self.assertEqual(ui.handled,[(i,'T'+str(i-3)) for i in range(3,13)])

    def test_partial_visible_grid_trims_without_writing_offscreen(self):
        ui=UI(8)
        selected,_=parse_line('3: '+' '.join('T'+str(i) for i in range(15)),truncate_excess=True,return_ignored=True)
        with patch.object(wf,'detect_visible_grid',side_effect=lambda frame:ui.cards),patch.object(wf,'emit'),patch.object(wf.time,'sleep',return_value=None):
            state=wf.process_batch(ui,selected,trim_to_visible=True)
        self.assertEqual(state.completed,list(range(3,9)))
        self.assertEqual([p for p,_ in ui.handled],list(range(3,9)))

    def test_run_oversized_two_batches_no_auto_carry(self):
        ui=UI()
        lines=iter(['11: A B C D E','1: Z','退出'])
        with patch.object(wf,'frontend',return_value=ui),patch.object(wf,'configure'),patch.object(wf,'emit'),patch.object(wf,'detect_visible_grid',side_effect=lambda _:ui.cards),patch.object(wf.time,'sleep',return_value=None):
            wf.run(input_func=lambda _:next(lines),sleep=lambda _:None)
        self.assertEqual(ui.handled,[(11,'A'),(12,'B'),(1,'Z')])

    def test_single_batch_oversized_only_drops_no_automatic_scroll(self):
        ui=UI()
        names=' '.join('V'+str(i) for i in range(30))
        lines=iter([names,'退出'])
        with patch.object(wf,'frontend',return_value=ui),patch.object(wf,'configure'),patch.object(wf,'emit'),patch.object(wf,'detect_visible_grid',side_effect=lambda _:ui.cards),patch.object(wf.time,'sleep',return_value=None):
            wf.run(input_func=lambda _:next(lines),sleep=lambda _:None)
        self.assertEqual(len(ui.handled),12)
        self.assertEqual([p for p,_ in ui.handled],list(range(1,13)))


if __name__=='__main__': unittest.main()
