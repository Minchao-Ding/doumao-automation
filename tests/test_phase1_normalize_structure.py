"""Cross-platform AST protection: title workflows do not import one another."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'doumao'


class DependencyTests(unittest.TestCase):
    def test_title_workflows_do_not_depend_on_each_other(self):
        for name in ('normalize_titles', 'search_queue_rename', 'visible_order_rename'):
            with self.subTest(workflow=name):
                path = ROOT / 'workflows' / (name + '.py')
                tree = ast.parse(path.read_text(encoding='utf-8'))
                imported = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
                self.assertFalse(any(n in ('.normalize_titles', '.search_queue_rename',
                                           '.visible_order_rename') for n in imported))
                self.assertNotIn('handle_card', path.read_text(encoding='utf-8'))

    def test_core_title_editor_is_not_a_workflow(self):
        path = ROOT / 'core' / 'title_editor.py'
        source = path.read_text(encoding='utf-8')
        self.assertNotIn('from ..workflows', source)
        self.assertNotIn('LOG =', source)
        self.assertNotIn('CLICK =', source)

    def test_normalizer_does_not_own_copy_of_title_gui(self):
        path = ROOT / 'workflows' / 'normalize_titles.py'
        source = path.read_text(encoding='utf-8')
        for forbidden in ('def handle_card(', 'def wait_for_title_editor(',
                          'def find_title_only(', 'def read_title_only(',
                          'def card_rows('):
            with self.subTest(function=forbidden):
                self.assertNotIn(forbidden, source)

    def test_cli_resolver_is_shared(self):
        path = ROOT / 'core' / 'title_editor.py'
        self.assertIn('def resolve_click_command()', path.read_text(encoding='utf-8'))
        for name in ('normalize_titles', 'search_queue_rename', 'visible_order_rename'):
            with self.subTest(workflow=name):
                source = (ROOT / 'workflows' / (name + '.py')).read_text(encoding='utf-8')
                self.assertIn('resolve_click_command', source)
                self.assertNotIn('shutil.which(', source)


if __name__ == '__main__':
    unittest.main()
