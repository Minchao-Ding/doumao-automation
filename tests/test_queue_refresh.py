"""Queue refresh timing tests; patch screenshot layer, never touch GUI."""
import unittest
from unittest.mock import Mock, patch
import numpy as np
from doumao.core.queue_state import QueueUncertain
from doumao.workflows import search_queue_rename as workflow

A=np.random.default_rng(10).integers(0,255,(60,70,3),dtype=np.uint8)
B=np.random.default_rng(11).integers(0,255,(60,70,3),dtype=np.uint8)
C=np.random.default_rng(12).integers(0,255,(60,70,3),dtype=np.uint8)

def item(a):return {'fp':a,'col':0}

class RefreshTests(unittest.TestCase):
    def test_delayed_refresh_rechecks_without_reediting(self):
        ui=Mock()
        source=[item(A),item(B)]
        with patch.object(workflow,'snapshot',side_effect=[
                (None,source),(None,[item(B)]),(None,[item(B)])]), \
             patch.object(workflow.time,'sleep',return_value=None):
            _, cards, state=workflow.await_advance(ui,source,attempts=3)
        self.assertEqual(state,'advanced')
        self.assertTrue(workflow.looks_like_same_art(cards[0]['fp'],B))
    def test_stable_empty_requires_recheck(self):
        ui=Mock()
        with patch.object(workflow,'snapshot',side_effect=[(None,[]),(None,[])]), \
             patch.object(workflow.time,'sleep',return_value=None):
            _, cards, state=workflow.await_advance(ui,[item(A)])
        self.assertEqual((cards,state),([], 'empty'))
    def test_transient_empty_does_not_complete(self):
        ui=Mock()
        with patch.object(workflow,'snapshot',side_effect=[(None,[]),(None,[item(A)])]), \
             patch.object(workflow.time,'sleep',return_value=None):
            with self.assertRaises(QueueUncertain):
                workflow.await_advance(ui,[item(A)],attempts=1)
    def test_visual_ambiguity_is_safety_stop(self):
        ui=Mock()
        with patch.object(workflow,'snapshot',return_value=(None,[item(A),item(B)])), \
             patch.object(workflow.time,'sleep',return_value=None):
            with self.assertRaises(QueueUncertain):
                workflow.await_advance(ui,[item(A),item(B)],attempts=2)
    def test_snapshot_stable_empty(self):
        ui=Mock()
        ui.card_rows.return_value=[]
        screen = np.zeros((900, 1500, 3), dtype=np.uint8)
        with patch.object(workflow,'scroll_to_top',return_value=screen), \
             patch.object(workflow,'_list',return_value=screen), \
             patch.object(workflow.time,'sleep',return_value=None):
            _, result=workflow.snapshot(ui)
        self.assertEqual(result,[])
        self.assertEqual(ui.card_rows.call_count,5)
    def test_snapshot_loading_change_is_not_exhaustion(self):
        ui=Mock()
        ui.card_rows.return_value=[]
        before = np.zeros((900, 1500, 3), dtype=np.uint8)
        loading = np.full_like(before, 255)
        with patch.object(workflow,'scroll_to_top',return_value=before), \
             patch.object(workflow,'_list',return_value=loading), \
             patch.object(workflow.time,'sleep',return_value=None):
            with self.assertRaises(QueueUncertain):workflow.snapshot(ui)
