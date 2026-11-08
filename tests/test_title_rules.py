"""Pure-Python tests: no macOS / screenshot required."""
import unittest
from doumao.title_rules import proposal, load_rule, DEFAULT_RULE
from pathlib import Path

class TitleRuleTests(unittest.TestCase):
    def test_examples(self):
        examples={
           'Sample Alpha':'Sample｜Alpha',
           'Sample Beta':'Sample｜Beta',
           'Sticker Pattern':'Sticker｜Pattern',
           'Plain':None,
           'Sample｜Alpha':None,
           'A B C':None,
           ' 前缀':None,
           '后缀 ':None,
           'A\tB':None,
           'A　B':None,
           'A\nB':None,
           'A  B':None,
        }
        for old,expected in examples.items():
            with self.subTest(old=old): self.assertEqual(proposal(old),expected)
    def test_rule_file(self):
        p=Path(__file__).parents[1]/'doumao'/'rules'/'drinks.json'
        spec=load_rule(p)
        self.assertEqual(proposal('Draft Sample',spec),'Draft｜Sample')
    def test_no_mutation(self):
        self.assertEqual(DEFAULT_RULE['old_separator'],' ')

if __name__=='__main__': unittest.main()
