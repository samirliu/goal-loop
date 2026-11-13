"""Direct production entrypoints: committed views, migration and corruption."""
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CTL, GATE, AUDIT = (ROOT / 'scripts' / name for name in ('goal_ctl.sh', 'goal_gate.sh', 'goal_audit.sh'))
SPEC = importlib.util.spec_from_file_location('view_store', ROOT / 'scripts/goal_store.py')
store = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(store)


class ViewAuthority(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='goal-view-authority-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.state = self.project / '.goal'
        self.call(CTL, 'init', expected=0)
        (self.state / 'goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | artifact | check: `test -s a.txt` | expected: exit=0\n\n'
            '## Approval\n\napproved: PENDING\n')
        self.call(CTL, 'stamp', '--auto', expected=0)
        (self.project / 'a.txt').write_text('artifact\n')
        self.call(CTL, 'close-iteration', '--task', 'T1', '--files', 'a.txt',
                  '--checks-pass', '1', '--checks-fail', '0', '--checks-unverifiable', '0',
                  '--exit-signal', 'yes', '--adversarial', 'clear', '--no-gate', expected=0)
        self.call(GATE, '--check', expected=0)

    def call(self, script, *args, expected=None, **kw):
        result = subprocess.run(['bash', str(script), *args, '--project', str(self.project)],
                                capture_output=True, text=True, timeout=15, **kw)
        if expected is not None:
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_all_managed_views_refuse_even_harmless_uncommitted_changes(self):
        names = sorted(store._VIEW_FILES) + ['evidence/raw/1.txt']
        for name in names:
            with self.subTest(name=name):
                path = self.state / name
                original = path.read_bytes() if path.exists() else None
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((original or b'') + b'\n')
                pointer = (self.state / 'store/commits/current').read_bytes()
                for script, args in ((GATE, ('--check',)), (GATE, ('--verify',)),
                                     (CTL, ('status',)), (AUDIT, ())):
                    result = self.call(script, *args, expected=4)
                    self.assertIn('ledger-view-mismatch', result.stderr)
                self.assertEqual((self.state / 'store/commits/current').read_bytes(), pointer)
                self.call(CTL, 'bind', expected=4, input='AC-1|PASS|1|x|x|x\n')
                self.call(CTL, 'recover', expected=0)
                self.assertEqual(path.read_bytes() if path.exists() else None, original)
                self.call(GATE, '--check', expected=0)

    def test_missing_or_truncated_pointer_never_falls_back_to_legacy(self):
        pointer = self.state / 'store/commits/current'
        original = pointer.read_bytes()
        for broken in (None, b'{"version":1,'):
            if broken is None:
                pointer.unlink()
            else:
                pointer.write_bytes(broken)
            self.call(GATE, '--check', expected=4)
            self.call(CTL, 'migrate', expected=4)
            self.call(CTL, 'recover', expected=4)
            pointer.write_bytes(original)
        self.call(GATE, '--check', expected=0)

    def test_generation_checksum_is_verified_by_all_readers(self):
        pointer = json.loads((self.state / 'store/commits/current').read_bytes())
        generation = self.state / 'store/commits/generations' / pointer['head']
        original = generation.read_bytes(); generation.write_bytes(original[:-5])
        for script, args in ((GATE, ('--check',)), (CTL, ('status',)), (AUDIT, ())):
            self.call(script, *args, expected=4)
        generation.write_bytes(original)
        self.call(GATE, '--check', expected=0)

    def test_no_pending_recovery_restores_exact_latest_committed_version(self):
        pointer = (self.state / 'store/commits/current').read_bytes()
        (self.state / 'state.rec').write_text('iteration=0\n')
        (self.state / 'scores.rec').unlink()
        (self.state / 'evidence/raw/99.txt').write_text('uncommitted evidence')
        self.call(CTL, 'recover', expected=0)
        self.assertIn('iteration=1\n', (self.state / 'state.rec').read_text())
        self.assertTrue((self.state / 'scores.rec').is_file())
        self.assertFalse((self.state / 'evidence/raw/99.txt').exists())
        self.assertEqual((self.state / 'store/commits/current').read_bytes(), pointer)
        self.call(GATE, '--check', expected=0)

    def test_unversioned_legacy_requires_explicit_read_only_migration(self):
        shutil.rmtree(self.state / 'store')
        before = {str(p.relative_to(self.state)): p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        result = self.call(GATE, '--check', expected=4)
        self.assertIn('ledger-migration-required', result.stderr)
        self.assertEqual(before, {str(p.relative_to(self.state)): p.read_bytes() for p in self.state.rglob('*') if p.is_file()})
        self.call(CTL, 'migrate', expected=0)
        self.call(GATE, '--check', expected=0)
        pointer = (self.state / 'store/commits/current').read_bytes()
        self.call(CTL, 'migrate', expected=0)
        self.assertEqual(pointer, (self.state / 'store/commits/current').read_bytes())

    def test_migration_refuses_legacy_history_view_disagreement(self):
        values = store._capture_files(self.state, store._view_names(self.state))
        shutil.rmtree(self.state / 'store')
        legacy = store.Store(self.state / 'store/commits')
        legacy.commit('legacy', b'legacy snapshot', {name: data for name, data in values.items() if data is not None})
        (self.state / 'state.rec').write_bytes(values['state.rec'] + b'\n')
        refused = self.call(CTL, 'migrate', expected=4)
        self.assertIn('disagree', refused.stderr)
        (self.state / 'state.rec').write_bytes(values['state.rec'])
        self.call(CTL, 'migrate', expected=0)
        self.call(GATE, '--check', expected=0)

    def test_migration_refuses_duplicate_or_truncated_legacy_iteration_rows(self):
        shutil.rmtree(self.state / 'store')
        log = self.state / 'loop-log.md'
        log.write_bytes(log.read_bytes() + log.read_bytes())
        refused = self.call(CTL, 'migrate', expected=4)
        self.assertIn('iteration mismatch', refused.stderr)
        self.assertFalse((self.state / 'store/commits/current').exists())

    def test_invalid_init_identity_creates_no_goal_directory(self):
        project = self.project / 'fresh'; project.mkdir()
        result = subprocess.run(['bash', str(CTL), 'init', '--project', str(project), '--operation-id', '../bad'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 4)
        self.assertFalse((project / '.goal').exists())

    def test_ambient_mode_without_inherited_descriptor_cannot_bypass_view_check(self):
        state = self.state / 'state.rec'
        state.write_bytes(state.read_bytes() + b'\n')
        (self.state / 'store/pending').write_text('pending transaction')
        env = dict(os.environ, GOAL_ACCESS_MODE='write', GOAL_ACCESS_OWNER_PID=str(os.getpid()))
        env.pop('GOAL_ACCESS_FD', None)
        env.pop('GOAL_ACCESS_EXEC_PID', None)
        self.call(GATE, '--check', expected=4, env=env)

    def test_resetting_approval_marker_cannot_reapprove_a_weaker_contract(self):
        goal = self.state / 'goal.md'
        goal.write_text(re.sub(r'^approved: .*$', 'approved: PENDING', goal.read_text(), flags=re.M)
                        .replace('test -s a.txt', 'true'))
        pointer = (self.state / 'store/commits/current').read_bytes()
        self.call(CTL, 'stamp', '--auto', expected=4)
        self.assertEqual(pointer, (self.state / 'store/commits/current').read_bytes())

    def test_unknown_legacy_command_kind_is_not_silently_migrated(self):
        values = store._capture_files(self.state, store._view_names(self.state))
        shutil.rmtree(self.state / 'store')
        snapshot = {name: data for name, data in values.items() if data is not None}
        snapshot[store._MUTATION_META] = store._encode({'version': 1, 'operation': 'unknown',
                                                       'intent': '0' * 64, 'missing': [], 'kind': 'future-command'})
        commits = store.Store(self.state / 'store/commits')
        head = commits.commit('unknown', b'future schema', snapshot)
        refused = self.call(CTL, 'migrate', expected=4)
        self.assertIn('unknown legacy', refused.stderr)
        self.assertEqual(commits.read()[0], head)


if __name__ == '__main__':
    unittest.main()
