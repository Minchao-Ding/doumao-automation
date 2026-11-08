"""Structural grid tests: fictional artwork only; no Mac UI calls."""
import unittest

import cv2
import numpy as np

from doumao.core.grid_detector import GridDetectionError, detect_visible_grid
from doumao.core.visible_order_state import ordered_cards, ensure_stable


def fixture(*, scheme='light', occupied=12, cut_bottom=False, offset_x=0):
    image = np.full((1180, 1450, 3), 235 if scheme == 'light' else 29, np.uint8)
    ink = (62, 62, 62) if scheme == 'light' else (185, 185, 185)
    xs = [90 + offset_x + 247*i for i in range(5)]
    ys = [140, 460, 780, 1100]
    for xx in xs:
        cv2.line(image, (xx, ys[0]), (xx, ys[-1]), ink, 2)
    for yy in ys:
        cv2.line(image, (xs[0], yy), (xs[-1], yy), ink, 2)
    for n in range(occupied):
        row, col = divmod(n, 4)
        left, top = xs[col], ys[row]
        x, y = left + 124, top + 135
        # Unique fictional thumbnail pattern, no title or collection information.
        cv2.circle(image, (x, y), 67, (45 + n*8, 73 + n*6, 210 - n*9), -1)
        cv2.rectangle(image, (x-38, y-20), (x+35, y+23),
                      (180 - n*3, 203 - n*8, 75 + n*7), -1)
        cv2.line(image, (x-30, y+32), (x+27, y-30), ink, 5)
    if cut_bottom:
        image[1040:] = 235 if scheme == 'light' else 29
    return image


class GridDetectorTests(unittest.TestCase):
    def test_finds_12_ordered_cards_in_fictional_4x3(self):
        cards=detect_visible_grid(fixture())
        self.assertEqual(len(cards),12)
        ordered=ordered_cards(cards,1450)
        self.assertEqual([c['col'] for c in ordered],[0,1,2,3]*3)
        self.assertEqual(len({c['top'] for c in ordered}),3)
        self.assertEqual(len({c['click'] for c in ordered}),12)

    def test_other_theme_is_not_depended_on(self):
        for scheme in ['light','dark']:
            with self.subTest(scheme=scheme):
                result=detect_visible_grid(fixture(scheme=scheme))
                self.assertEqual(len(result),12)

    def test_horizontal_move_not_fixed_to_screen_percentage(self):
        result=detect_visible_grid(fixture(offset_x=120))
        self.assertEqual(len(result),12)
        self.assertGreater(result[0]['click'][0],250)

    def test_diagnostics_identify_boundaries(self):
        values={}
        detect_visible_grid(fixture(),diagnostics=values)
        self.assertEqual(len(values['selected_columns']),5)
        self.assertEqual(len(values['selected_rows']),4)

    def test_unloaded_grid_is_rejected(self):
        blank=fixture(occupied=0)
        with self.assertRaises(GridDetectionError):detect_visible_grid(blank)

    def test_missing_bottom_cut_is_rejected(self):
        with self.assertRaises(GridDetectionError):detect_visible_grid(fixture(cut_bottom=True))

    def test_stable_geometry_and_thumbnails(self):
        cards=detect_visible_grid(fixture())
        again=detect_visible_grid(fixture())
        self.assertIsNone(ensure_stable(cards,again))

    def test_empty_screen_does_not_guess(self):
        with self.assertRaises(GridDetectionError):
            detect_visible_grid(np.full((1180,1450,3),235,dtype=np.uint8))


if __name__ == '__main__':
    unittest.main()

class WorkflowDetectionContractTests(unittest.TestCase):
    def test_full_grid_uses_structural_detector_without_legacy(self):
        from doumao.workflows import visible_order_rename as wf
        from unittest.mock import Mock
        class View:
            def shot(self): return fixture()
            def check_list(self, frame): pass
            card_rows = Mock(side_effect=AssertionError('legacy scanner must not run'))
        frame, cards = wf.capture(View())
        self.assertEqual(len(cards), 12)

    def test_partial_batch_can_use_previously_supported_scanner(self):
        from unittest.mock import Mock, patch
        from doumao.workflows import visible_order_rename as wf
        class View:
            def shot(self): return np.full((1180,1450,3),235,dtype=np.uint8)
            def check_list(self, frame): pass
        app=View()
        app.card_rows=Mock(return_value=[{
            'col':j,'top':140+320*(i//4), 'click':(200+j*245,300+320*(i//4)),
            'fp':np.ones((60,70,3),dtype=np.uint8)*i}
            for i in range(6) for j in [i%4]])
        with patch.object(wf, 'save_capture_failure'):
            _, cards=wf.capture(app)
        self.assertEqual(len(cards), 6)
        app.card_rows.assert_called_once()
