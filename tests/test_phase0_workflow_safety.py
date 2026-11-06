"""Phase 0 regression specifications against EXISTING v3.5 workflows.

Run from the root of an actual v3.5 checkout. The tests use only mocks and
synthetic thumbnails: no macOS automation, no real items, no clicks or writes.
This file CANNOT be executed standalone without the existing project modules.
"""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch
import numpy as np

from doumao.core.queue_state import QueueUncertain
from doumao.core.visible_order_state import VisibleOrderUncertain, parse_line
from doumao.workflows import search_queue_rename as queue
from doumao.workflows import visible_order_rename as visible


def fake_card(index: int):
    return {
        "col": index % 4,
        "top": 100 + (index // 4) * 300,
        "click": (100 + (index % 4) * 120, 200),
        "fp": np.full((30, 30, 3), index, dtype=np.uint8),
    }


class SearchQueueSaveBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.pyautogui = Mock()
        self.pyautogui.FailSafeException = type("FakeFailSafe", (Exception,), {})
        self.ui = Mock()
        self.events = []
        self.rule = {
            "rule_type": "remove_prefix",
            "prefix": "TEMP:",
            "search_must_disappear": "TEMP:",
        }

    def invoke(self, *, card_results, queue_results, first_cards=None, auto_save=True):
        self.ui.handle_card.side_effect = card_results
        cards = first_cards if first_cards is not None else [fake_card(0)]
        with patch.dict("sys.modules", {"pyautogui": self.pyautogui}), \
             patch.object(queue, "_frontend", return_value=self.ui), \
             patch.object(queue, "snapshot", return_value=(None, cards)), \
             patch.object(queue, "await_advance", side_effect=queue_results), \
             patch.object(queue, "emit", side_effect=lambda event, **kw: self.events.append((event, kw))), \
             patch.object(queue.shutil, "which", return_value="/usr/bin/cliclick"), \
             patch.object(queue.time, "sleep", return_value=None):
            queue.run(rule=self.rule, limit=4, auto_save=auto_save, search="TEMP:")

    def test_confirmed_save_and_queue_advance(self):
        self.invoke(card_results=[("saved", "TEMP: Item", "Item")],
                    queue_results=[(None, [], "empty")])
        self.ui.handle_card.assert_called_once()
        self.assertTrue(any(name == "queue_advance_verified" for name, _ in self.events))

    def test_failure_before_handle_card_returns_never_retries(self):
        with self.assertRaises(QueueUncertain):
            self.invoke(card_results=[RuntimeError("save action possibly dispatched")],
                        queue_results=[])
        self.ui.handle_card.assert_called_once()
        stop = next(data for name, data in self.events if name == "stopped")
        self.assertTrue(stop["pending"])
        # v3.5 has no way to know whether the nested editor already clicked.
        self.assertFalse(stop["save_returned"])

    def test_returned_save_but_unconfirmed_queue_never_retries(self):
        with self.assertRaises(QueueUncertain):
            self.invoke(card_results=[("saved", "TEMP: Item", "Item")],
                        queue_results=[QueueUncertain("queue did not advance")])
        self.ui.handle_card.assert_called_once()
        stop = next(data for name, data in self.events if name == "stopped")
        self.assertTrue(stop["pending"])
        self.assertTrue(stop["save_returned"])
        self.assertFalse(any(name == "queue_advance_verified" for name, _ in self.events))

    def test_cancellation_during_advance_never_starts_next_item(self):
        with self.assertRaises(KeyboardInterrupt):
            self.invoke(card_results=[("saved", "TEMP: Item", "Item")],
                        queue_results=[KeyboardInterrupt()])
        self.ui.handle_card.assert_called_once()
        stop = next(data for name, data in self.events if name == "stopped")
        self.assertEqual(stop["reason"], "user_interrupted")
        self.assertTrue(stop["pending"])

    def test_preview_does_not_start_a_second_item(self):
        self.invoke(card_results=[("preview", "TEMP: Item", "Item")],
                    queue_results=[], auto_save=False)
        self.ui.handle_card.assert_called_once()


class VisibleOrderSaveBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((1200, 1000, 3), dtype=np.uint8)
        self.cards = [fake_card(0), fake_card(1)]
        self.ui = Mock()
        self.events = []

    def invoke(self, card_results, line="A B"):
        self.ui.handle_card.side_effect = card_results
        with patch.object(visible, "capture", return_value=(self.frame, self.cards)), \
             patch.object(visible, "check_snapshot", return_value=(self.frame, self.cards)), \
             patch.object(visible, "emit", side_effect=lambda event, **kw: self.events.append((event, kw))):
            return visible.process_batch(self.ui, parse_line(line), sleep=lambda _: None)

    def test_confirmed_two_items(self):
        state = self.invoke([("saved", "old-1", "A"), ("saved", "old-2", "B")])
        self.assertEqual(state.completed, [1, 2])
        self.assertEqual(self.ui.handle_card.call_count, 2)

    def test_save_error_first_item_stops_without_second_attempt(self):
        with self.assertRaises(VisibleOrderUncertain):
            self.invoke([RuntimeError("save may have been clicked")])
        self.ui.handle_card.assert_called_once()
        stop = next(data for name, data in self.events if name == "batch_stopped")
        self.assertEqual(stop["pending"], 1)
        self.assertEqual(stop["completed"], [])

    def test_failure_second_item_preserves_first_verified_result(self):
        with self.assertRaises(VisibleOrderUncertain):
            self.invoke([("saved", "old-1", "A"), RuntimeError("uncertain")])
        self.assertEqual(self.ui.handle_card.call_count, 2)
        stop = next(data for name, data in self.events if name == "batch_stopped")
        self.assertEqual(stop["pending"], 2)
        self.assertEqual(stop["completed"], [1])

    def test_skipped_unchanged_title_does_not_require_save(self):
        state = self.invoke([("skipped", "A", "A")], line="A")
        self.assertEqual(state.completed, [1])
        self.ui.handle_card.assert_called_once()

    def test_keyboard_interrupt_propagates_without_reopening_first_item(self):
        # Known v3.5 limitation: the process_batch Exception handler does not
        # catch BaseException/KeyboardInterrupt, so no batch_stopped JSONL is
        # emitted here. The exception nevertheless stops without retrying.
        with self.assertRaises(KeyboardInterrupt):
            self.invoke([KeyboardInterrupt()])
        self.ui.handle_card.assert_called_once()
        self.assertFalse(any(name == "batch_stopped" for name, _ in self.events))


if __name__ == "__main__":
    unittest.main()
