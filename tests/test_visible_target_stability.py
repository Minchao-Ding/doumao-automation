"""Regression for unrelated thumbnail changes during a partial batch."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from doumao.core.visible_order_state import VisibleOrderUncertain, ensure_stable, parse_line
from doumao.workflows import visible_order_rename as workflow


def card(slot):
    row, col = divmod(slot - 1, 4)
    return {
        'col': col,
        'top': 140 + row*320,
        'click': (180 + col*250, 280 + row*320),
        'fp': np.random.default_rng(slot).integers(0,256, (70,60,3), dtype=np.uint8),
    }


class _UI:
    def __init__(self):
        self.frame = np.zeros((1200, 1450, 3), dtype=np.uint8)
        self.handled = []
        self.diagnostics = Mock()

    def shot(self):
        return self.frame.copy()

    def check_list(self, frame):
        pass

    def handle_card(self, target, frame, pos, do_save, rule):
        self.handled.append((pos, do_save))
        if do_save:
            return 'saved', 'previous', rule['new']
        return 'skipped', rule['new'], rule['new']


class TargetStabilityTests(unittest.TestCase):
    def setUp(self):
        self.original = [card(i) for i in range(1,13)]
        self.with_unrelated_change = [dict(c) for c in self.original]
        self.with_unrelated_change[0] = dict(self.with_unrelated_change[0], fp=card(300)['fp'])
        self.with_unrelated_change[1] = dict(self.with_unrelated_change[1], fp=card(301)['fp'])

    def test_unassigned_thumbnails_can_refresh(self):
        ensure_stable(self.original, self.with_unrelated_change,
                      fingerprint_positions=range(3,13))

    def test_assigned_thumbnail_change_stops(self):
        observed = [dict(c) for c in self.with_unrelated_change]
        observed[2] = dict(observed[2], fp=card(302)['fp'])
        with self.assertRaisesRegex(VisibleOrderUncertain, '第 3 张图像'):
            ensure_stable(self.original, observed, fingerprint_positions=range(3,13))

    def test_unassigned_geometry_change_still_stops(self):
        observed = [dict(c) for c in self.with_unrelated_change]
        observed[0] = dict(observed[0], top=observed[0]['top']+20)
        with self.assertRaisesRegex(VisibleOrderUncertain, '第 1 张卡片的位置'):
            ensure_stable(self.original, observed, fingerprint_positions=range(3,13))

    def test_default_all_thumbnails_check_remains(self):
        with self.assertRaisesRegex(VisibleOrderUncertain, '第 1 张图像'):
            ensure_stable(self.original, self.with_unrelated_change)

    def test_invalid_positions_fail_closed(self):
        for selected in ([], [0], [13], ['3']):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                ensure_stable(self.original, self.original, fingerprint_positions=selected)

    def test_first_real_batch_targets_only_and_preserves_saving(self):
        ui = _UI()
        first = {'count': 0}
        def detect(_):
            first['count'] += 1
            return self.original if first['count'] == 1 else self.with_unrelated_change
        with patch.object(workflow, 'detect_visible_grid', side_effect=detect), \
             patch.object(workflow, 'emit'), patch.object(workflow.time, 'sleep', return_value=None):
            state = workflow.process_batch(ui, parse_line('3: C D'))
        self.assertEqual(state.completed, [3,4])
        self.assertEqual(ui.handled, [(3, True), (4, True)])

    def test_assigned_change_stops_before_any_save(self):
        ui = _UI()
        bad = [dict(c) for c in self.original]
        bad[2] = dict(bad[2], fp=card(400)['fp'])
        first = {'count': 0}
        def detect(_):
            first['count'] += 1
            return self.original if first['count'] == 1 else bad
        with patch.object(workflow, 'detect_visible_grid', side_effect=detect), \
             patch.object(workflow, 'emit'), patch.object(workflow.time, 'sleep', return_value=None):
            with self.assertRaisesRegex(VisibleOrderUncertain, '第 3 张图像'):
                workflow.process_batch(ui, parse_line('3: C D'))
        self.assertEqual(ui.handled, [])

    def test_preview_matches_real_preflight_target_selection(self):
        ui = _UI()
        first = {'count': 0}
        def detect(_):
            first['count'] += 1
            return self.original if first['count'] == 1 else self.with_unrelated_change
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(workflow, 'RUNTIME', Path(folder)), \
             patch.object(workflow, 'detect_visible_grid', side_effect=detect), \
             patch.object(workflow, 'emit'), patch.object(workflow.time, 'sleep', return_value=None):
            workflow.preview_batch(ui, parse_line('3: C D'))
            self.assertTrue((Path(folder)/'visible_order_preview.png').exists())
        self.assertEqual(ui.handled, [])


if __name__ == '__main__':
    unittest.main()
