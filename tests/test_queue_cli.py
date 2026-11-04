import subprocess
import sys
import unittest

class QueueCliTests(unittest.TestCase):
    def call(self,*args):
        return subprocess.run([sys.executable,'-m','doumao','search-queue',*args],
                   capture_output=True,text=True,check=False)
    def test_requires_confirm_for_write(self):
        p=self.call('--mode','remove-prefix','--prefix','TEMP:',
                    '--search','TEMP:','--auto-save','--limit','1')
        self.assertNotEqual(p.returncode,0)
        self.assertIn('--confirm-selection',p.stderr)
    def test_reject_invalid_limit_before_gui(self):
        p=self.call('--mode','remove-prefix','--prefix','TEMP:',
                    '--search','TEMP:','--limit','0')
        self.assertNotEqual(p.returncode,0)
        self.assertIn('--limit',p.stderr)
    def test_reject_missing_rule(self):
        p=self.call('--mode','replace','--search','TEMP:')
        self.assertNotEqual(p.returncode,0)
        self.assertIn('--old',p.stderr)
    def test_parse_dry_run_defaults_no_save(self):
        from doumao.__main__ import build_parser
        args=build_parser().parse_args(['search-queue','--mode','replace','--old','a',
                                        '--new','b','--search','a'])
        self.assertFalse(args.auto_save)
