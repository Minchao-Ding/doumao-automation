"""Fictional image-only partial grid checks; no Mac GUI or private screenshots."""
import unittest

import cv2
import numpy as np
from doumao.core.grid_detector import GridDetectionError
from doumao.core.partial_grid_detector import detect_partial_grid
from unittest.mock import Mock, patch


def fake_gallery(rows=2, missing=None):
    height, width = 956, 1470
    image = np.full((height, width, 3), (255, 250, 242), np.uint8)
    xs = [160 + 220*i for i in range(5)]
    ys = [360 + 260*i for i in range(rows+1)]
    ink=(65,70,75)
    for x in xs:
        cv2.line(image,(x,ys[0]),(x,ys[-1]),ink,2)
    for y in ys:
        cv2.line(image,(xs[0],y),(xs[-1],y),ink,2)
    for pos in range(rows*4):
        if pos == missing:
            continue
        row,col = divmod(pos,4)
        left,top=xs[col],ys[row]
        cx,cy=left+110,top+110
        rng=np.random.default_rng(200+pos)
        cv2.rectangle(image,(left+30,top+40),(left+188,top+190),(150,180,201),-1)
        for _ in range(180):
            x=int(rng.integers(left+50,left+160))
            y=int(rng.integers(top+48,top+178))
            color=tuple(int(v) for v in rng.integers(12,235,size=3))
            cv2.rectangle(image,(x,y),(x+4,y+4),color,-1)
    return image


class PartialGridTests(unittest.TestCase):
    def test_one_full_row(self):
        cards=detect_partial_grid(fake_gallery(1))
        self.assertEqual(len(cards),4)
        self.assertEqual([c['col'] for c in cards],[0,1,2,3])
        self.assertTrue(all(c['click'][1]>360 for c in cards))

    def test_two_full_rows(self):
        cards=detect_partial_grid(fake_gallery(2))
        self.assertEqual(len(cards),8)
        self.assertEqual([c['col'] for c in cards],[0,1,2,3]*2)
        self.assertEqual(len({c['top'] for c in cards}),2)

    def test_missing_art_does_not_guess(self):
        with self.assertRaises(GridDetectionError):
            detect_partial_grid(fake_gallery(2,missing=6))

    def test_blank_screen_rejected(self):
        blank=np.full((956,1470,3),245,np.uint8)
        with self.assertRaises(GridDetectionError):
            detect_partial_grid(blank)

    def test_invalid_screenshot_rejected(self):
        with self.assertRaises(GridDetectionError):
            detect_partial_grid(np.zeros((100,100),np.uint8))

    def test_workflow_fallback_to_partial_detector(self):
        from doumao.workflows import visible_order_rename as wf
        ui = Mock()
        ui.shot.return_value = fake_gallery(2)
        ui.card_rows.side_effect = AssertionError('Old scanner not needed')
        with patch.object(wf, 'detect_visible_grid',
                          side_effect=GridDetectionError('Needs three rows')):
            _, cards = wf.capture(ui)
        self.assertEqual(len(cards), 8)
        ui.card_rows.assert_not_called()


class RowStabilityRegression(unittest.TestCase):
    def test_panel_edge_snap_removes_hough_jitter(self):
        from doumao.core.partial_grid_detector import _align_visible_boundaries
        edges = np.zeros((1912, 2940), np.uint8)
        xs = [320, 746, 1172, 1609, 2034]
        pitch = 428.0
        # A true 2-row panel uses borders near 700, 1214, 1729. Hough can
        # return a nearby artwork edge at 720 on one observation.
        for y in (699, 700, 1213, 1214, 1728, 1729):
            edges[y, 345:2012] = 255
        a = _align_visible_boundaries(edges, xs, [700, 1214, 1729], pitch)
        b = _align_visible_boundaries(edges, xs, [720, 1214, 1729], pitch)
        self.assertEqual(a, b)
        self.assertEqual(a, [700, 1214, 1728])

    def test_missing_panel_border_stops(self):
        from doumao.core.partial_grid_detector import _align_visible_boundaries
        edges = np.zeros((1912, 2940), np.uint8)
        with self.assertRaises(GridDetectionError):
            _align_visible_boundaries(edges, [320, 746, 1172, 1609, 2034],
                                      [700, 1214, 1729], 428.0)

    def test_reject_thin_false_three_row_grid(self):
        from doumao.core.grid_detector import _row_pitch_valid
        xs = [320, 746, 1172, 1609, 2034]
        self.assertFalse(_row_pitch_valid(xs, [962, 1214, 1472, 1729]))
        self.assertTrue(_row_pitch_valid(xs, [215, 705, 1195, 1685]))

    def test_partial_detector_does_not_auto_edit(self):
        cards = detect_partial_grid(fake_gallery(2))
        self.assertEqual(len(cards), 8)
        self.assertTrue(all(0 < item['click'][0] for item in cards))


class FullGridColumnCoverageSafety(unittest.TestCase):
    def test_two_row_panel_cannot_fake_first_full_grid_row(self):
        from doumao.core.grid_detector import (
            _row_pitch_valid, _vertical_edges_span_grid,
        )
        xs = [320, 746, 1172, 1609, 2034]
        false_rows = [241, 629, 1017, 1405]
        # Before this fix, these dimensions could pass the pitch check.
        self.assertTrue(_row_pitch_valid(xs, false_rows))
        edges = [dict(coordinate=x, start=707, end=1729)
                 for x in xs[1:-1]]
        self.assertFalse(_vertical_edges_span_grid(edges, xs, false_rows))

    def test_real_three_rows_keep_full_height_internal_borders(self):
        from doumao.core.grid_detector import _vertical_edges_span_grid
        xs = [320, 746, 1172, 1609, 2034]
        rows = [245, 735, 1225, 1715]
        edges = [dict(coordinate=x, start=242, end=1719)
                 for x in xs[1:-1]]
        self.assertTrue(_vertical_edges_span_grid(edges, xs, rows))

    def test_missing_internal_border_stops_instead_of_guessing(self):
        from doumao.core.grid_detector import _vertical_edges_span_grid
        xs = [320, 746, 1172, 1609, 2034]
        rows = [245, 735, 1225, 1715]
        edges = [dict(coordinate=x, start=242, end=1719)
                 for x in xs[1:3]]
        self.assertFalse(_vertical_edges_span_grid(edges, xs, rows))


if __name__=='__main__':unittest.main()
