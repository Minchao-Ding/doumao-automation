"""Parser guards must reject accidental write commands before importing GUI modules."""
import subprocess
import sys
import unittest


class SafeCliTests(unittest.TestCase):
    def call(self, *args):
        return subprocess.run([sys.executable, '-m', 'doumao', *args],
                              capture_output=True, text=True, check=False)

    def test_clean_requires_explicit_save(self):
        p=self.call('clean','--limit','1')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('--auto-save', p.stderr)

    def test_clean_requires_folder_confirmation(self):
        p=self.call('clean','--auto-save','--limit','1')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('--confirm-folder drinks', p.stderr)

    def test_titles_requires_folder_confirmation_for_writing(self):
        p=self.call('titles','--auto-save','--limit','1')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('--confirm-folder drinks', p.stderr)

    def test_title_dry_run_defaults_to_no_save(self):
        from doumao.__main__ import build_parser
        args=build_parser().parse_args(['titles','--limit','1'])
        self.assertFalse(args.auto_save)

if __name__=='__main__': unittest.main()
