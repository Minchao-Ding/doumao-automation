"""Phase 4: shared visual predicate must not alter workflow policies."""
import unittest

import numpy as np

from doumao.core import artwork, queue_state, visible_order_state


def sample(seed):
    return np.random.default_rng(seed).integers(0, 256, (70, 60, 3), dtype=np.uint8)


class SharedArtworkTests(unittest.TestCase):
    def test_queue_legacy_symbol_is_same_function(self):
        # Existing callers importing from queue_state continue to work.
        self.assertIs(queue_state.looks_like_same_art, artwork.looks_like_same_art)

    def test_visible_order_uses_shared_function_not_queue_state(self):
        self.assertIs(visible_order_state.looks_like_same_art, artwork.looks_like_same_art)

    def test_exact_copy_matches(self):
        a = sample(1)
        self.assertTrue(artwork.looks_like_same_art(a, a.copy()))

    def test_different_art_does_not_match(self):
        self.assertFalse(artwork.looks_like_same_art(sample(1), sample(2)))

    def test_invalid_image_fails_closed(self):
        a = sample(1)
        self.assertFalse(artwork.looks_like_same_art(a, None))
        self.assertFalse(artwork.looks_like_same_art(a, np.zeros((10, 10, 3), np.uint8)))

    def test_queue_transition_policy_unchanged(self):
        a, b = sample(1), sample(2)
        old = [{'fp': a}, {'fp': b}]
        self.assertEqual(queue_state.queue_transition(old, [{'fp': b.copy()}]), 'advanced')
        self.assertEqual(queue_state.queue_transition(old, [{'fp': a.copy()}]), 'uncertain')

    def test_visible_order_matching_policy_unchanged(self):
        a, b = sample(1), sample(2)
        self.assertTrue(visible_order_state.artwork_matches_with_small_drift(a, a.copy()))
        self.assertFalse(visible_order_state.artwork_matches_with_small_drift(a, b))


if __name__ == '__main__':
    unittest.main()
