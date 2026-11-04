"""Configuration is parsed before any GUI import, with no private sample data."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from doumao.__main__ import build_parser

class ConfigTests(unittest.TestCase):
    def call(self,*args):
        return subprocess.run([sys.executable,'-m','doumao','search-queue',*args],
                   capture_output=True,text=True,check=False)
    def test_example_config_is_fictional(self):
        p=Path(__file__).parents[1]/'examples'/'queue_rename.example.json'
        conf=json.loads(p.read_text())
        self.assertEqual(conf['prefix'],'DRAFT-')
    def test_auto_save_in_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'s.json'
            path.write_text('{"mode":"remove-prefix","search":"DRAFT-","prefix":"DRAFT-","auto-save":true}')
            r=self.call('--config',str(path))
            self.assertNotEqual(r.returncode,0)
            self.assertIn('配置 JSON',r.stderr)
    def test_config_without_write_still_checks_gui_only_after_parse(self):
        r=self.call('--config','/file/that/does/not/exist')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('配置文件无法读取',r.stderr)
    def test_config_write_still_needs_explicit_confirmation(self):
        p=Path(__file__).parents[1]/'examples'/'queue_rename.example.json'
        r=self.call('--config',str(p),'--auto-save')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('--confirm-selection',r.stderr)
