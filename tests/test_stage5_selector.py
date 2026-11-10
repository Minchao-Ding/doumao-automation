import unittest
from unittest.mock import Mock
from doumao.core.grid_detector import GridDetectionError
from doumao.core.gallery_layout import UnsafeGalleryLayout
from doumao.core.grid_selection import select_visible_card_candidates


class SelectorTests(unittest.TestCase):
    def setUp(self):
        self.full=Mock();self.partial=Mock();self.legacy=Mock();self.unified=Mock()

    def select(self):
        return select_visible_card_candidates(None,full_detector=self.full,
                    partial_detector=self.partial,legacy_detector=self.legacy,
                    layout_detector=self.unified)

    def test_unified_success_prevents_all_legacy_calls(self):
        expected=[{'col':c%4} for c in range(8)]
        self.unified.return_value=expected
        self.assertIs(self.select(),expected)
        self.full.assert_not_called();self.partial.assert_not_called();self.legacy.assert_not_called()

    def test_unified_unsafe_does_not_fallback(self):
        self.unified.side_effect=UnsafeGalleryLayout('missing card')
        with self.assertRaises(UnsafeGalleryLayout):self.select()
        self.full.assert_not_called();self.partial.assert_not_called();self.legacy.assert_not_called()

    def test_unified_unknown_falls_back_to_existing_full(self):
        self.unified.side_effect=GridDetectionError('unsupported geometry')
        self.full.return_value=[{'col':c%4} for c in range(12)]
        self.assertEqual(len(self.select()),12)
        self.partial.assert_not_called();self.legacy.assert_not_called()

    def test_legacy_partial_remains_supported(self):
        self.unified.side_effect=GridDetectionError('not proven')
        self.full.side_effect=GridDetectionError('not full')
        self.partial.side_effect=GridDetectionError('not partial')
        self.legacy.return_value=[{'col':0}]
        self.assertEqual(len(self.select()),1)

    def test_old_selector_behavior_unchanged_when_unified_not_supplied(self):
        self.full.return_value=[{'col':0}]
        selected=select_visible_card_candidates(None,full_detector=self.full,
                                partial_detector=self.partial,legacy_detector=self.legacy)
        self.assertEqual(selected,[{'col':0}]);self.unified.assert_not_called()

if __name__=='__main__':unittest.main()
