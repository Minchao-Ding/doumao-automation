"""Offline-only queue tests; synthetic fictional cards, no GUI."""
import unittest
import numpy as np
from doumao.core.queue_state import (looks_like_same_art, queue_transition,
                                      QueueCounter, QueueUncertain)

rng=np.random.default_rng(21)
A=rng.integers(0,256,(60,70,3),dtype=np.uint8)
B=rng.integers(0,256,(60,70,3),dtype=np.uint8)
C=rng.integers(0,256,(60,70,3),dtype=np.uint8)

def card(image,title='same title'):
    return {'col':0,'fp':image.copy(),'title':title}

class QueueIdentityTests(unittest.TestCase):
    def test_same_title_different_art_advances(self):
        self.assertEqual(queue_transition([card(A),card(B)], [card(B)]), 'advanced')
    def test_same_title_same_art_is_ambiguous(self):
        self.assertEqual(queue_transition([card(A),card(A)], [card(A)]), 'uncertain')
    def test_same_head_after_save_stops(self):
        self.assertEqual(queue_transition([card(A),card(B)], [card(A),card(B)]), 'uncertain')
    def test_wrong_next_head_is_uncertain(self):
        self.assertEqual(queue_transition([card(A),card(B)], [card(C)]), 'uncertain')
    def test_one_card_first_changes(self):
        self.assertEqual(queue_transition([card(A)], [card(B)]), 'advanced')
    def test_empty_after_save(self):
        self.assertEqual(queue_transition([card(A)], []), 'empty')
    def test_exact_same_image_is_recognized(self):
        self.assertTrue(looks_like_same_art(A, A.copy()))
    def test_different_art_is_not_confused(self):
        self.assertFalse(looks_like_same_art(A,B))
    def test_tiny_shift_is_tolerated(self):
        shifted=np.roll(A,1,axis=0)
        self.assertTrue(looks_like_same_art(A,shifted))
    def test_nonimage_is_safe(self):
        self.assertFalse(looks_like_same_art(A,'not an image'))

class CounterTests(unittest.TestCase):
    def test_success_limit(self):
        c=QueueCounter(2)
        for _ in range(2):c.start();c.verified('advanced')
        self.assertEqual(c.finished(False).outcome,'limit_reached')
    def test_exhausted_before_requested_number(self):
        c=QueueCounter(10);c.start();c.verified('empty')
        self.assertEqual((c.finished(True).outcome,c.changed),('exhausted',1))
    def test_all_exhausted(self):
        c=QueueCounter(None);c.start();c.verified('empty')
        self.assertEqual(c.finished(True).outcome,'exhausted')
    def test_pending_save_never_counts(self):
        c=QueueCounter(1);c.start()
        with self.assertRaises(QueueUncertain):c.finished(True)
        self.assertEqual(c.changed,0)
    def test_second_edit_blocked_when_pending(self):
        c=QueueCounter(3);c.start()
        with self.assertRaises(QueueUncertain):c.start()
    def test_nonpositive_limit_rejected(self):
        for bad in (0,-1,True):
            with self.subTest(bad=bad),self.assertRaises(ValueError):QueueCounter(bad)
    def test_unverified_result_rejected(self):
        c=QueueCounter(3);c.start()
        with self.assertRaises(QueueUncertain):c.verified('uncertain')
