"""Offline regression for unchanged full/partial/legacy grid precedence."""
import unittest
from unittest.mock import Mock

from doumao.core.grid_detector import GridDetectionError
from doumao.core.grid_selection import select_visible_card_candidates


class GridSelectionTests(unittest.TestCase):
    def setUp(self):
        self.frame = object()  # No screenshot, app connection, or GUI operation.
        self.full = Mock()
        self.partial = Mock()
        self.legacy = Mock()

    def choose(self):
        return select_visible_card_candidates(
            self.frame,
            full_detector=self.full,
            partial_detector=self.partial,
            legacy_detector=self.legacy,
        )

    def test_full_detector_wins_without_other_scanners(self):
        cards = [{'col': i % 4} for i in range(12)]
        self.full.return_value = cards
        self.assertIs(self.choose(), cards)
        self.full.assert_called_once_with(self.frame)
        self.partial.assert_not_called()
        self.legacy.assert_not_called()

    def test_partial_detector_runs_only_after_known_full_failure(self):
        self.full.side_effect = GridDetectionError('full failed')
        cards = [{'col': i % 4} for i in range(8)]
        self.partial.return_value = cards
        self.assertIs(self.choose(), cards)
        self.partial.assert_called_once_with(self.frame)
        self.legacy.assert_not_called()

    def test_legacy_scanner_runs_only_after_both_known_failures(self):
        self.full.side_effect = GridDetectionError('full failed')
        self.partial.side_effect = GridDetectionError('partial failed')
        cards = [{'col': i % 4} for i in range(4)]
        self.legacy.return_value = cards
        self.assertIs(self.choose(), cards)
        self.legacy.assert_called_once_with(self.frame)

    def test_legacy_accepts_existing_incomplete_counts(self):
        self.full.side_effect = GridDetectionError('full failed')
        self.partial.side_effect = GridDetectionError('partial failed')
        for count in (1, 6, 11):
            with self.subTest(count=count):
                cards = [{} for _ in range(count)]
                self.legacy.return_value = cards
                self.assertIs(self.choose(), cards)

    def test_bad_legacy_counts_rethrow_original_full_error(self):
        original = GridDetectionError('original structural failure')
        self.full.side_effect = original
        self.partial.side_effect = GridDetectionError('partial failed')
        for count in (0, 12, 13):
            with self.subTest(count=count):
                self.legacy.return_value = [{} for _ in range(count)]
                with self.assertRaises(GridDetectionError) as caught:
                    self.choose()
                self.assertIs(caught.exception, original)

    def test_unexpected_full_error_does_not_trigger_fallback(self):
        self.full.side_effect = RuntimeError('unexpected full error')
        with self.assertRaisesRegex(RuntimeError, 'unexpected full error'):
            self.choose()
        self.partial.assert_not_called()
        self.legacy.assert_not_called()

    def test_unexpected_partial_error_does_not_trigger_legacy(self):
        self.full.side_effect = GridDetectionError('full failed')
        self.partial.side_effect = ValueError('unexpected partial error')
        with self.assertRaisesRegex(ValueError, 'unexpected partial error'):
            self.choose()
        self.legacy.assert_not_called()

    def test_legacy_failure_is_not_masked(self):
        self.full.side_effect = GridDetectionError('full failed')
        self.partial.side_effect = GridDetectionError('partial failed')
        self.legacy.side_effect = RuntimeError('legacy scanner failed')
        with self.assertRaisesRegex(RuntimeError, 'legacy scanner failed'):
            self.choose()

    def test_partial_empty_result_does_not_guess_or_retry(self):
        # The old workflow passes this through to ordered_cards(), which
        # rejects an empty list. Preserve that boundary and do not try legacy.
        self.full.side_effect = GridDetectionError('full failed')
        self.partial.return_value = []
        self.assertEqual(self.choose(), [])
        self.legacy.assert_not_called()




class WorkflowLazyLegacyTests(unittest.TestCase):
    """Existing workflow test UIs need not implement an unused fallback."""

    @staticmethod
    def cards(count):
        import numpy as np
        return [
            {
                'col': slot % 4,
                'top': 180 + (slot // 4) * 250,
                'click': (200 + (slot % 4) * 220, 260 + (slot // 4) * 250),
                'fp': np.full((70, 60, 3), slot + 1, dtype=np.uint8),
            }
            for slot in range(count)
        ]

    @staticmethod
    def ui():
        import numpy as np

        class NoLegacyUI:
            def shot(self):
                return np.zeros((1000, 1450, 3), dtype=np.uint8)

            def check_list(self, frame):
                pass

        return NoLegacyUI()

    def test_workflow_full_grid_without_legacy_method(self):
        from unittest.mock import patch
        from doumao.workflows import visible_order_rename as workflow
        cards = self.cards(12)
        with patch.object(workflow, 'detect_visible_grid', return_value=cards), \
             patch.object(workflow, 'detect_partial_grid', side_effect=AssertionError('partial must not run')):
            _, detected = workflow.capture(self.ui())
        self.assertEqual(len(detected), 12)

    def test_workflow_partial_grid_without_legacy_method(self):
        from unittest.mock import patch
        from doumao.workflows import visible_order_rename as workflow
        cards = self.cards(8)
        with patch.object(workflow, 'detect_visible_grid', side_effect=GridDetectionError('three rows unavailable')), \
             patch.object(workflow, 'detect_partial_grid', return_value=cards):
            _, detected = workflow.capture(self.ui())
        self.assertEqual(len(detected), 8)


if __name__ == '__main__':
    unittest.main()
