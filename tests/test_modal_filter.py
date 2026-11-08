import unittest
import numpy as np
import cv2
from doumao.core.navigation import find_detail_modal

class ModalRegressionTests(unittest.TestCase):
    def test_one_pale_blue_card_is_not_detail(self):
        f=np.zeros((1000,1600,3),np.uint8)
        f[230:660,180:600]=(255,252,246)
        self.assertIsNone(find_detail_modal(f))
    def test_real_white_dialog_still_detected(self):
        f=np.zeros((1000,1600,3),np.uint8)
        f[210:720,450:1190]=(255,255,255)
        self.assertEqual(find_detail_modal(f),(450,210,740,510))
    def test_card_and_real_dialog_dont_block_one_another(self):
        f=np.zeros((1000,1600,3),np.uint8)
        f[250:650,180:570]=(255,252,246)
        f[190:740,600:1260]=(255,255,255)
        self.assertEqual(find_detail_modal(f),(600,190,660,550))
