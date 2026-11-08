"""Regression: placeholder text must not split the metadata note field.

These are generated screenshots, not real GUI clicks or user artwork.
"""
from __future__ import annotations

import unittest

import numpy as np

from doumao.core.metadata_editor import form_rects


class MetadataFormTextRegression(unittest.TestCase):
    def setUp(self):
        self.save = (300, 920, 520, 50)
        self.frame = np.full((1000, 1500, 3), 225, dtype=np.uint8)
        self.pale_bgr = (254, 252, 248)

    def field(self, y, height):
        sx, _, sw, _ = self.save
        self.frame[y:y + height, sx:sx + sw] = self.pale_bgr

    def test_placeholder_in_note_does_not_split_valid_pair(self):
        self.field(480, 40)
        self.field(530, 60)
        # Simulate an unusually wide gray placeholder in the middle of the
        # note: the old .30-.80 stripe was interrupted through this row.
        sx, _, sw, _ = self.save
        self.frame[544:561, sx + round(sw*.29):sx + round(sw*.68)] = (180, 180, 180)
        self.assertEqual(form_rects(self.frame, self.save),
                         ((300, 480, 520, 40), (300, 530, 520, 60)))

    def test_missing_note_stops(self):
        self.field(480, 40)
        self.assertIsNone(form_rects(self.frame, self.save))

    def test_wrong_spacing_stops(self):
        self.field(380, 40)
        self.field(530, 60)
        self.assertIsNone(form_rects(self.frame, self.save))

    def test_ambiguous_two_pairs_stops(self):
        self.field(350, 40)
        self.field(402, 60)
        self.field(480, 40)
        self.field(530, 60)
        self.assertIsNone(form_rects(self.frame, self.save))

    def test_missing_save_anchor_stops(self):
        self.field(480, 40)
        self.field(530, 60)
        self.assertIsNone(form_rects(self.frame, None))


if __name__ == '__main__':
    unittest.main()
