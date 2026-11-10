"""Stage 5 deterministic synthetic gallery tests. No private screenshots in repo."""
import unittest
import cv2
import numpy as np
from doumao.core.gallery_layout import (
    detect_gallery_layout, UnsafeGalleryLayout, MIN_VISIBLE_THUMBNAIL_FRACTION,
    _anchored_side_border, _Segment, _boundaries_for, _candidate_score,
    _first_complete_row_edge, _artwork_content_center_y,
)
from doumao.core.grid_detector import GridDetectionError


def gallery(*, rows=2, full_header=False, third_partial=False, missing=None,
            shift_x=0, scheme='light', seed=9, tail_count=0, tail_missing=None):
    h,w = (1331,2047) if full_header else (1180,1450)
    bg=(247,250,253) if scheme=='light' else (34,38,41)
    ink=(69,83,97) if scheme=='light' else (201,208,213)
    image=np.full((h,w,3),bg,dtype=np.uint8)
    if full_header:
        xs = [233+294*i+shift_x for i in range(5)]
        ys = [578,936,1306]
        cv2.rectangle(image, (210,210),(1410+shift_x,290), ink, 1)  # search/filter
        cv2.rectangle(image, (210,438),(1410+shift_x,512), ink, 1)  # folder
        cv2.line(image, (210,358),(1410+shift_x,358),ink,2)
        cv2.line(image, (210,431),(1410+shift_x,431),ink,2)
        cv2.line(image, (210,511),(1410+shift_x,511),ink,2)
        cv2.line(image, (210,857),(1410+shift_x,857),ink,2)  # decorative
        cv2.line(image, (210,1221),(1410+shift_x,1221),ink,2)
    else:
        xs=[90+247*i+shift_x for i in range(5)]
        ys=[140+320*i for i in range(rows+1)]
    if rows==1 and full_header:
        ys=ys[:2]
    rng=np.random.default_rng(seed)
    for x in xs:
        cv2.line(image,(x,ys[0]),(x,ys[-1]),ink,2)
    for y in ys:
        cv2.line(image,(xs[0],y),(xs[-1],y),ink,2)
    for pos in range(rows*4):
        if pos == missing:continue
        r,c=divmod(pos,4)
        if r+1 >= len(ys):continue
        left,right=xs[c:c+2]
        top,bottom=ys[r:r+2]
        cx,cy=(left+right)//2,top+(bottom-top)*.43
        rad=min((right-left)*.25,(bottom-top)*.24)
        cv2.circle(image,(int(cx),int(cy)),int(rad), (30+pos*9,70+pos*7,170-pos*9),-1)
        cv2.rectangle(image,(int(cx-rad*.55),int(cy-rad*.22)),
                      (int(cx+rad*.45),int(cy+rad*.25)),
                      (180-pos*3,173-pos*5,60+pos*8),-1)
        for _ in range(40):
            x=int(rng.integers(left+30,right-30));y=int(rng.integers(top+30,bottom-65))
            cv2.rectangle(image,(x,y),(x+4,y+4), tuple(int(v) for v in rng.integers(30,220,3)),-1)
    if tail_count:
        assert not full_header and rows in (1,2) and 1 <= tail_count <= 3
        tail_top,tail_bottom=ys[-1],ys[-1]+320
        for c in range(tail_count):
            if c == tail_missing:
                continue
            left,right=xs[c:c+2]
            cv2.rectangle(image,(left,tail_top),(right,tail_bottom),ink,2)
            cx=(left+right)//2
            cy=tail_top+145
            cv2.circle(image,(cx,cy),63,(70+c*30,95+c*15,180-c*40),-1)
            cv2.rectangle(image,(cx-30,cy-20),(cx+34,cy+25),(190,190-c*10,40+c*20),-1)
            cv2.line(image,(cx-42,cy+35),(cx+45,cy-38),ink,6)
    if third_partial and full_header:
        # Only upper fragments of the third row; not evidence of completed cards.
        for c in range(4):
            x=xs[c]+60
            cv2.rectangle(image, (x,1310), (x+80,1330), ink, 2)
    return image


class UnifiedGalleryTests(unittest.TestCase):
    def test_twelve_cards(self):
        cards=detect_gallery_layout(gallery(rows=3))
        self.assertEqual([c['col'] for c in cards],[0,1,2,3]*3)
        self.assertEqual(len(cards),12)

    def test_two_complete_rows_with_header_and_partial_third(self):
        image=gallery(full_header=True,third_partial=True)
        cards=detect_gallery_layout(image)
        self.assertEqual(len(cards),8)
        self.assertEqual([c['col'] for c in cards],[0,1,2,3]*2)
        self.assertGreater(cards[0]['click'][1],578)
        self.assertLess(cards[-1]['click'][1],1306)

    def test_one_row(self):
        self.assertEqual(len(detect_gallery_layout(gallery(rows=1))),4)

    def test_two_rows(self):
        self.assertEqual(len(detect_gallery_layout(gallery(rows=2))),8)

    def test_horizontal_translation(self):
        cards=detect_gallery_layout(gallery(rows=3,shift_x=120))
        self.assertEqual(len(cards),12)
        self.assertGreater(cards[0]['click'][0],250)

    def test_dark_theme_geometry(self):
        self.assertEqual(len(detect_gallery_layout(gallery(rows=3,scheme='dark'))),12)

    def test_missing_art(self):
        with self.assertRaises(GridDetectionError):
            detect_gallery_layout(gallery(rows=2,missing=6))

    def test_missing_first_card_does_not_shift_to_later_row(self):
        with self.assertRaises(GridDetectionError):
            detect_gallery_layout(gallery(rows=2,missing=0))

    def test_missing_card_from_three_rows_must_not_downgrade(self):
        with self.assertRaises(GridDetectionError):
            detect_gallery_layout(gallery(rows=3,missing=10))

    def test_header_with_unloaded_second_row_does_not_downgrade(self):
        with self.assertRaises(GridDetectionError):
            detect_gallery_layout(gallery(full_header=True, missing=5))

    def test_one_to_three_complete_trailing_cards(self):
        for extra in (1,2,3):
            with self.subTest(extra=extra):
                cards=detect_gallery_layout(gallery(rows=2,tail_count=extra))
                self.assertEqual(len(cards),8+extra)
                self.assertEqual([c['col'] for c in cards[-extra:]],list(range(extra)))

    def test_partial_second_row_after_one_full_row(self):
        for extra in (1,2,3):
            with self.subTest(extra=extra):
                cards=detect_gallery_layout(gallery(rows=1,tail_count=extra))
                self.assertEqual(len(cards),4+extra)

    def test_trailing_gap_must_stop(self):
        with self.assertRaises(GridDetectionError):
            detect_gallery_layout(gallery(rows=2,tail_count=3,tail_missing=1))

    def test_trailing_card_with_unverified_image_must_stop(self):
        # A real frame with an unreadable card cannot be interpreted as missing.
        frame=gallery(rows=2,tail_count=1)
        cv2.rectangle(frame,(130,822),(300,1013),(247,250,253),-1)
        with self.assertRaises(GridDetectionError):
            detect_gallery_layout(frame)

    def test_blank_rejected(self):
        with self.assertRaises(GridDetectionError):
            detect_gallery_layout(np.full((1180,1450,3),235,dtype=np.uint8))

    def test_bad_shape_rejected(self):
        with self.assertRaises(GridDetectionError):
            detect_gallery_layout(np.zeros((900,1450),dtype=np.uint8))

    def test_diagnostics(self):
        diag={}
        cards=detect_gallery_layout(gallery(rows=2),diagnostics=diag)
        self.assertEqual(len(diag['selected_columns']),5)
        self.assertEqual(len(diag['selected_rows']),3)
        self.assertEqual(diag['verified_cards'],len(cards))

class ThumbnailVisibilityTests(unittest.TestCase):
    def test_visibility_default_is_seventy_five_percent(self):
        self.assertEqual(MIN_VISIBLE_THUMBNAIL_FRACTION, .75)

    def test_trailing_artwork_above_threshold_without_caption_is_clickable(self):
        image = gallery(rows=3)[:975]
        diag = {}
        cards = detect_gallery_layout(image, diagnostics=diag)
        self.assertEqual(len(cards), 12)
        self.assertEqual(diag['verified_trailing'], 4)
        self.assertTrue(all(0 < c['click'][1] < image.shape[0] for c in cards))

    def test_trailing_artwork_below_threshold_is_ignored(self):
        image = gallery(rows=3)[:960]
        diag = {}
        cards = detect_gallery_layout(image, diagnostics=diag)
        self.assertEqual(len(cards), 8)
        self.assertEqual(diag['verified_trailing'], 0)

    def test_leading_artwork_above_threshold_is_clickable(self):
        image = gallery(rows=3)[225:]
        diag = {}
        cards = detect_gallery_layout(image, diagnostics=diag)
        self.assertEqual(len(cards), 12)
        self.assertEqual(diag['verified_leading'], 4)
        self.assertEqual([c['col'] for c in cards[:4]], [0,1,2,3])
        self.assertTrue(all(c['click'][1] > 0 for c in cards))

    def test_leading_artwork_below_threshold_is_ignored(self):
        image = gallery(rows=3)[245:]
        diag = {}
        cards = detect_gallery_layout(image, diagnostics=diag)
        self.assertEqual(len(cards), 8)
        self.assertEqual(diag['verified_leading'], 0)

    def test_both_ends_cropped_and_middle_full(self):
        image = gallery(rows=3)[225:975]
        diag = {}
        cards = detect_gallery_layout(image, diagnostics=diag)
        self.assertEqual(len(cards), 12)
        self.assertEqual(diag['verified_leading'], 4)
        self.assertEqual(diag['verified_trailing'], 4)

    def test_missing_artwork_in_cropped_tail_stops_not_downgrades(self):
        # Missing one thumbnail must not silently turn 12 positions into 8.
        image = gallery(rows=3,missing=10)[:975]
        with self.assertRaises(UnsafeGalleryLayout):
            detect_gallery_layout(image)

    def test_missing_artwork_in_cropped_leading_row_stops(self):
        image = gallery(rows=3,missing=1)[225:]
        with self.assertRaises(UnsafeGalleryLayout):
            detect_gallery_layout(image)

    def test_unrelated_filter_header_not_promoted(self):
        image = gallery(rows=2, full_header=True, third_partial=True)
        self.assertEqual(len(detect_gallery_layout(image)), 8)

    def test_borderline_coverage_does_not_use_guessed_outside_image(self):
        # Even when the click center remains on-screen, <75% fails.
        image = gallery(rows=3)[:960]
        cards = detect_gallery_layout(image)
        self.assertEqual(len(cards), 8)

class AnchoredCroppedBorderTests(unittest.TestCase):
    """Retina Hough cluster offsets must not hide real card borders."""

    def _lines(self, *, reference_x=333, cropped_x=333):
        edges = np.zeros((1912, 2940), dtype=np.uint8)
        if reference_x is not None:
            edges[1100:1400, reference_x] = 255
        if cropped_x is not None:
            edges[1566:1890, cropped_x] = 255
        return edges

    def test_real_border_offset_within_hough_cluster_is_accepted(self):
        self.assertTrue(_anchored_side_border(
            self._lines(), 320, (1566, 1890), (1100, 1400), 438))

    def test_cropped_border_absent_fails_closed(self):
        self.assertFalse(_anchored_side_border(
            self._lines(cropped_x=None), 320,
            (1566, 1890), (1100, 1400), 438))

    def test_reference_border_absent_fails_closed(self):
        self.assertFalse(_anchored_side_border(
            self._lines(reference_x=None), 320,
            (1566, 1890), (1100, 1400), 438))

    def test_different_edge_locations_cannot_be_combined(self):
        self.assertFalse(_anchored_side_border(
            self._lines(cropped_x=305), 320,
            (1566, 1890), (1100, 1400), 438))


class ObservedRowBoundaryContracts(unittest.TestCase):
    """Synthetic geometry representing high-DPI border and header ambiguity."""

    def test_real_row_border_may_start_inside_first_inner_divider(self):
        xs = tuple(_Segment(x, 320, 1880, 1000)
                   for x in (333, 763, 1188, 1625, 2067))
        border = _Segment(1192, 766, 2041, 1275)
        self.assertIn(border, _boundaries_for(xs, [border], 1912))

    def test_three_column_tail_cannot_be_full_width_row(self):
        xs = tuple(_Segment(x, 320, 1880, 1000)
                   for x in (333, 763, 1188, 1625, 2067))
        border = _Segment(1192, 333, 1625, 1292)
        self.assertNotIn(border, _boundaries_for(xs, [border], 1912))

    def test_uniform_gallery_rhythm_beats_nearby_toolbar_line(self):
        # First candidate picks a control line at y=512. The true gallery
        # boundaries are y=588,1120,1646. Both have similar anchor scores,
        # but the former has materially less regular row spacing.
        def rank(rows):
            diffs = np.diff(rows)
            cv = float(np.std(diffs) / np.mean(diffs))
            anchor = abs(322-rows[0]) / 430
            return _candidate_score(-.42, cv, anchor)
        self.assertLess(rank((588,1120,1646)), rank((512,1120,1646)) - .08)



class CompleteRowAndClickEvidenceTests(unittest.TestCase):
    """Synthetic counterparts of two false Hough row origins and sparse art."""

    def setUp(self):
        self.xs = tuple(_Segment(x, 322, 1911, 1589)
                        for x in (333, 763, 1195, 1628, 2043))

    def test_caption_rule_does_not_span_all_four_card_ends(self):
        false_edge = _Segment(509, 288, 1874, 1586)
        true_edge = _Segment(605, 307, 2035, 1726)
        self.assertFalse(_first_complete_row_edge(self.xs, false_edge))
        self.assertTrue(_first_complete_row_edge(self.xs, true_edge))

    def test_previous_row_label_border_does_not_span_first_column(self):
        xs = tuple(_Segment(x, 322, 1911, 1589)
                   for x in (320, 758, 1185, 1602, 2023))
        false_edge = _Segment(341, 761, 2020, 1259)
        true_edge = _Segment(454, 286, 2258, 1966)
        self.assertFalse(_first_complete_row_edge(xs, false_edge))
        self.assertTrue(_first_complete_row_edge(xs, true_edge))

    def test_bottom_row_click_follows_graphic_not_early_blank_area(self):
        frame = np.full((1100, 1100, 3), 255, dtype=np.uint8)
        # The trailing artwork starts well below the card top; a fixed
        # top+0.43*height click lands in an empty light thumbnail region.
        cv2.rectangle(frame, (180, 640), (420, 685), (35, 50, 85), -1)
        cy = _artwork_content_center_y(frame, 100, 500, 400, 800)
        self.assertIsNotNone(cy)
        self.assertGreaterEqual(cy, 640)
        self.assertLessEqual(cy, 685)

    def test_no_graphic_does_not_invent_content_center(self):
        frame = np.full((1100, 1100, 3), 255, dtype=np.uint8)
        self.assertIsNone(_artwork_content_center_y(frame, 100, 500, 400, 800))

if __name__ == "__main__":
    unittest.main()
