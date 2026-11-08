"""Regression: HoughLinesP may return (N,4) or (N,1,4) on different builds."""
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from doumao.core.grid_detector import _extract_lines


class HoughShapeTests(TestCase):
    def test_hough_2d_n_by_4(self):
        frame = np.zeros((1000, 1400, 3), dtype=np.uint8)
        segments = np.array([[100, 100, 100, 800], [100, 200, 1200, 200]], dtype=np.int32)
        with patch('doumao.core.grid_detector.cv2.HoughLinesP', return_value=segments):
            vertical, horizontal = _extract_lines(frame)
        self.assertEqual(len(vertical), 1)
        self.assertEqual(len(horizontal), 1)
        self.assertEqual(vertical[0].axis, 100)
        self.assertEqual(horizontal[0].axis, 200)

    def test_hough_3d_n_by_1_by_4(self):
        frame = np.zeros((1000, 1400, 3), dtype=np.uint8)
        segments = np.array([[[100, 100, 100, 800]], [[100, 200, 1200, 200]]], dtype=np.int32)
        with patch('doumao.core.grid_detector.cv2.HoughLinesP', return_value=segments):
            vertical, horizontal = _extract_lines(frame)
        self.assertEqual((len(vertical), len(horizontal)), (1, 1))
