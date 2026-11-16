"""Maintained instructions must resolve and match the distributed release."""
import json
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Documentation(unittest.TestCase):
    def test_current_version_agrees_across_discovery_and_usage(self):
        version = (ROOT/'VERSION').read_text().strip()
        self.assertRegex(version, r'^\d+\.\d+\.\d+$')
        for name in ['README.md', 'docs/README.md']:
            self.assertIn('**'+version+'**' if name.startswith('docs/') else '**v'+version+'**',
                          (ROOT/name).read_text(), name)
        for name in ['SKILL.md', 'skills/goal-loop/SKILL.md']:
            self.assertIn('# Goal Loop (v'+version+')', (ROOT/name).read_text(), name)
        self.assertEqual(json.loads((ROOT/'.claude-plugin/plugin.json').read_text())['version'], version)

    def test_maintained_document_links_resolve_inside_the_repository(self):
        files = [ROOT/'README.md', ROOT/'SKILL.md', ROOT/'docs/README.md', ROOT/'docs/history.md',
                 ROOT/'docs/evals/README.md', ROOT/'docs/transaction-state.md',
                 *sorted((ROOT/'references').rglob('*.md')), *sorted((ROOT/'examples').rglob('README.md'))]
        missing = []
        for path in files:
            text = re.sub(r'^```[^\n]*\n.*?^```[^\n]*$', '', path.read_text(), flags=re.M | re.S)
            for target in re.findall(r'\[[^\]\n]*\]\(([^\)\n]+)\)', text):
                parsed = urlsplit(target.strip('<>').split(' "')[0])
                if parsed.scheme or not parsed.path:
                    continue
                resolved = (path.parent/unquote(parsed.path)).resolve()
                if not resolved.is_relative_to(ROOT) or not resolved.exists():
                    missing.append((str(path.relative_to(ROOT)), target))
        self.assertEqual(missing, [])

    def test_installation_ships_license_and_current_documentation(self):
        names = json.loads((ROOT/'assets/install-files.json').read_text())
        for name in ['LICENSE', 'README.md', 'docs/README.md', 'docs/history.md', 'assets/history-files.json',
                     'docs/transaction-state.md', 'scripts/goal_install.py', 'skills/goal-loop/SKILL.md']:
            self.assertIn(name, names)
            self.assertTrue((ROOT/name).is_file(), name)

    def test_runtime_document_links_resolve_without_historical_evidence(self):
        spec=importlib.util.spec_from_file_location('documentation_install',ROOT/'scripts/goal_install.py')
        install=importlib.util.module_from_spec(spec);spec.loader.exec_module(install)
        with tempfile.TemporaryDirectory(prefix='goal-runtime-docs-') as tmp:
            package=Path(tmp).resolve()/'runtime';install.install('plugin',package)
            files=[package/'README.md',package/'SKILL.md',*sorted((package/'docs').glob('*.md')),
                   *sorted((package/'references').rglob('*.md')),*sorted((package/'examples').rglob('README.md'))]
            missing=[]
            for path in files:
                text=re.sub(r'^```[^\n]*\n.*?^```[^\n]*$', '', path.read_text(), flags=re.M|re.S)
                for target in re.findall(r'\[[^\]\n]*\]\(([^\)\n]+)\)',text):
                    parsed=urlsplit(target.strip('<>').split(' "')[0])
                    if parsed.scheme or not parsed.path:continue
                    resolved=(path.parent/unquote(parsed.path)).resolve()
                    if not resolved.is_relative_to(package) or not resolved.exists():
                        missing.append((str(path.relative_to(package)),target))
            self.assertEqual(missing,[])


if __name__ == '__main__':
    unittest.main()
