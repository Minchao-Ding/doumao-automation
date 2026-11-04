import unittest
from doumao.title_rules import proposal, transform_text

class GenericRules(unittest.TestCase):
    def test_remove_one_prefix_without_touching_rest(self):
        spec={'rule_type':'remove_prefix','prefix':'TEMP:','search_must_disappear':'TEMP:'}
        self.assertEqual(proposal('TEMP: Card｜Alt',spec),' Card｜Alt')
        self.assertIsNone(proposal('Already clean',spec))
    def test_still_matches_search_rejected(self):
        spec={'rule_type':'remove_prefix','prefix':'TEMP:','search_must_disappear':'TEMP:'}
        with self.assertRaises(ValueError):proposal('TEMP: TEMP: Card',spec)
    def test_replace_all_matches_preserves_separators(self):
        spec={'rule_type':'replace_text','old':'draft','new':'final',
              'search_must_disappear':'draft'}
        self.assertEqual(proposal('draft｜B｜draft',spec),'final｜B｜final')
    def test_invalid_postcondition_rejected(self):
        spec={'rule_type':'replace_text','old':'A','new':'AA','search_must_disappear':'A'}
        with self.assertRaises(ValueError):proposal('A｜card',spec)
    def test_no_match_does_not_write(self):
        self.assertIsNone(proposal('final',['not a rule'] if False else
                 {'rule_type':'replace_text','old':'draft','new':'final'}))
    def test_empty_rejected(self):
        with self.assertRaises(ValueError):proposal('TEMP:',{'rule_type':'remove_prefix','prefix':'TEMP:'})
    def test_append_suffix_idempotent(self):
        spec={'rule_type':'append_suffix','suffix':'Person','delimiter':'｜',
              'forbid_other':['Other']}
        self.assertEqual(proposal('Portrait',spec),'Portrait｜Person')
        self.assertIsNone(proposal('Portrait｜Person',spec))
        self.assertIsNone(proposal('Portrait｜Other',spec))
    def test_no_fixed_collection_constant_in_queue_engine(self):
        from pathlib import Path
        root = Path(__file__).parents[1]/'doumao'
        for rel in ('core/queue_state.py','workflows/search_queue_rename.py'):
            code=(root/rel).read_text(encoding='utf-8')
            self.assertNotIn('TARGET_FOLDER =',code)
            self.assertNotIn('PREFIX =',code)
