"""Visible-order soft visual check; artwork safety without pixel-exact crops.

Tests use generated fictional patterns; no user's private screenshots in Git.
"""
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from doumao.core.visible_order_state import (
    VisibleOrderUncertain, artwork_matches_with_small_drift,
    ensure_stable, parse_line,
)
from doumao.workflows import visible_order_rename as workflow


def sample_art(seed):
    canvas = np.full((70, 60, 3), (245, 248, 250), np.uint8)
    rng = np.random.default_rng(seed)
    for _ in range(24):
        x, y = int(rng.integers(7, 52)), int(rng.integers(8, 58))
        color = tuple(int(x) for x in rng.integers(20, 205, 3))
        cv2.rectangle(canvas, (x, y), (min(x+5, 58), min(y+5, 68)), color, -1)
    return canvas


def shifted(image, dx=2, dy=-2):
    matrix = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(image, matrix, (image.shape[1], image.shape[0]),
                          flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def twelve_cards():
    cards = []
    for slot in range(12):
        row, col = divmod(slot, 4)
        cards.append({'col':col, 'top':140+row*290,
                      'click':(220+col*235, 280+row*290),
                      'fp':sample_art(slot+100)})
    return cards


class ArtworkToleranceTests(unittest.TestCase):
    def test_small_shift_is_not_treated_as_new_card(self):
        art = sample_art(62)
        for offset in (-3, -2, -1, 1, 2, 3):
            with self.subTest(offset=offset):
                self.assertTrue(artwork_matches_with_small_drift(art,shifted(art,offset,offset)))

    def test_obvious_other_artwork_still_rejected(self):
        self.assertFalse(artwork_matches_with_small_drift(sample_art(70),sample_art(71)))

    def test_missing_or_bad_image_rejected(self):
        art=sample_art(1)
        self.assertFalse(artwork_matches_with_small_drift(art,np.zeros((12,12,3),np.uint8)))
        self.assertFalse(artwork_matches_with_small_drift(art,None))

    def test_bounded_grid_with_shifted_target_passes(self):
        before=twelve_cards()
        after=[dict(c) for c in before]
        after[4]=dict(after[4],fp=shifted(before[4]['fp']))
        ensure_stable(before,after,fingerprint_positions=[5])

    def test_obvious_wrong_target_still_stops(self):
        before=twelve_cards()
        after=[dict(c) for c in before]
        after[4]=dict(after[4],fp=sample_art(999))
        with self.assertRaisesRegex(VisibleOrderUncertain,'第 5 张图像'):
            ensure_stable(before,after,fingerprint_positions=[5])

    def test_geometry_still_fails_even_when_art_matches(self):
        before=twelve_cards()
        after=[dict(c) for c in before]
        after[4]=dict(after[4],top=after[4]['top']+40)
        with self.assertRaisesRegex(VisibleOrderUncertain,'第 5 张卡片的位置'):
            ensure_stable(before,after,fingerprint_positions=[5])

    def test_batch_process_uses_tolerant_check_and_writes_only_requested(self):
        before=twelve_cards()
        slightly_different=[dict(c,fp=shifted(c['fp'],2,2)) for c in before]
        seen=[]
        class UI:
            def shot(self): return np.zeros((1250, 1600, 3),np.uint8)
            def check_list(self,frame): return None
            def handle_card(self,target,frame,pos,save,rule):
                seen.append((pos,rule['new']))
                return 'saved', 'old',rule['new']
            diagnostics=Mock()
        counter={'n':0}
        def detector(frame):
            counter['n']+=1
            return before if counter['n']==1 else slightly_different
        with patch.object(workflow,'detect_visible_grid',side_effect=detector), \
             patch.object(workflow,'emit'), \
             patch.object(workflow.time,'sleep',return_value=None):
            result=workflow.process_batch(UI(),parse_line('2: 甲 乙'))
        self.assertEqual(result.completed,[2,3])
        self.assertEqual(seen,[(2,'甲'),(3,'乙')])

if __name__=='__main__': unittest.main()
