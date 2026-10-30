"""Static checks for normalized module paths and absent historic cross-version dependencies."""
import ast, unittest
from pathlib import Path

ROOT=Path(__file__).parents[1]
class StructureTests(unittest.TestCase):
    def test_package_modules_syntax(self):
        for file in (ROOT/'doumao').rglob('*.py'):
            with self.subTest(name=str(file)):
                ast.parse(file.read_text(encoding='utf-8'))
    def test_no_old_import_names(self):
        for file in (ROOT/'doumao').rglob('*.py'):
            s=file.read_text(encoding='utf-8')
            for prefix in ('import doumao_v0','import doumao_v1'):
                with self.subTest(name=file.name): self.assertNotIn(prefix,s)

if __name__=='__main__': unittest.main()
