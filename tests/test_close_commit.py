"""End-to-end commit-point and lost-acknowledgement tests for real closes."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CTL = ROOT / 'scripts/goal_ctl.sh'
STORE = ROOT / 'scripts/goal_store.py'


class CloseCommit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='goal-commit-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.state = self.project / '.goal'
        self.call('init', expected=0)
        (self.project / 'artifact.txt').write_text('artifact\n')
        (self.project / 'check.sh').write_text(
            'n=$(cat .goal/evidence/check-count 2>/dev/null || echo 0)\n'
            'echo $((n+1)) > .goal/evidence/check-count\ntrue\n')
        (self.state / 'goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | pass | check: `bash check.sh` | expected: exit=0\n\n'
            '## Approval\n\napproved: PENDING\n')
        self.call('stamp', '--auto', expected=0)
        self.args = ['close-iteration', '--task', 'T1', '--files', 'artifact.txt',
                     '--checks-pass', '1', '--checks-fail', '0', '--checks-unverifiable', '0',
                     '--false-complete', 'yes', '--no-gate']

    def call(self, *args, expected=None, env=None):
        result = subprocess.run(['bash', str(CTL), *args, '--project', str(self.project)],
                                capture_output=True, text=True, timeout=20, env=env)
        if expected is not None:
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def snapshot(self):
        return {str(p.relative_to(self.state)): p.read_bytes() for p in self.state.rglob('*') if p.is_file()}

    def assert_iteration(self, expected):
        self.assertIn('iteration=%s\n' % expected, (self.state / 'state.rec').read_text())

    def fault_env(self, point):
        bindir = self.project / 'fault-bin'
        bindir.mkdir()
        shim = bindir / 'python3'
        shim.write_text('#!' + sys.executable + '\n' + '''
import importlib.util, os, signal, sys
sys.dont_write_bytecode = True
args = sys.argv[1:]
if len(args) >= 5 and args[0] == '-I' and args[1] == os.environ['TEST_STORE'] and args[2] == 'close-journal' and args[4] == 'finish':
    spec = importlib.util.spec_from_file_location('commit_fault_store', args[1])
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    point = os.environ['TEST_COMMIT_POINT']
    def die():
        os.kill(int(os.environ['GOAL_ACCESS_OWNER_PID']), signal.SIGKILL)
        os._exit(73)
    if point != 'ack':
        original = mod.Store.commit
        def fault(where):
            if where == point: die()
        def commit(self, *a, **kw):
            kw['fault'] = fault
            return original(self, *a, **kw)
        mod.Store.commit = commit
    mod.close_journal(args[3], 'finish', int(args[5]) if len(args) > 5 else 0)
    die()
os.execv(sys.executable, [sys.executable] + args)
''')
        shim.chmod(0o755)
        return dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ['PATH'],
                    TEST_STORE=str(STORE), TEST_COMMIT_POINT=point)

    def test_retry_is_read_only_even_after_newer_commit(self):
        self.call(*self.args, '--operation-id', 'wave-1', expected=0)
        self.assert_iteration(1)
        self.assertIn('false_completes=1\n', (self.state / 'state.rec').read_text())
        before = self.snapshot()
        retry = self.call(*self.args, '--operation-id', 'wave-1', expected=0)
        self.assertIn('CTL: REPLAY', retry.stdout)
        self.assertNotIn('GATE: GO', retry.stdout)
        self.assertEqual(before, self.snapshot())
        self.call(*self.args, '--operation-id', 'wave-2', expected=0)
        self.assert_iteration(2)
        before = self.snapshot()
        self.call(*self.args, '--operation-id', 'wave-1', expected=0)
        self.assertEqual(before, self.snapshot())
        conflict = self.call(*self.args, '--checks-pass', '2', '--operation-id', 'wave-1', expected=4)
        self.assertIn('different arguments', conflict.stderr)
        self.assertEqual(before, self.snapshot())

    def test_default_id_is_unique_and_invalid_id_does_not_write(self):
        before = self.snapshot()
        for invalid in ('', '../escape', 'bad|id', 'x' * 129):
            self.call(*self.args, '--operation-id', invalid, expected=4)
            self.assertEqual(before, self.snapshot())
        results = [self.call(*self.args, expected=0) for _ in range(2)]
        identities = [re.search(r'operation=([0-9a-f]+)', result.stdout).group(1) for result in results]
        self.assertNotEqual(*identities)
        self.assert_iteration(2)

    def test_crash_before_pointer_rolls_back_then_same_id_can_retry(self):
        killed = self.call(*self.args, '--operation-id', 'before', env=self.fault_env('generation-published'))
        self.assertNotEqual(killed.returncode, 0)
        self.assertTrue((self.state / 'store/pending').is_file())
        stale_pending = (self.state / 'store/pending').read_bytes()
        self.call('recover', expected=0)
        self.assert_iteration(0)
        self.assertEqual((self.state / 'evidence/check-count').read_text().strip(), '1')
        self.call(*self.args, '--operation-id', 'before', expected=0)
        self.assert_iteration(1)
        self.assertEqual((self.state / 'evidence/check-count').read_text().strip(), '2')
        (self.state / 'store/pending').write_bytes(stale_pending)
        # The same identity has since committed: restoring its earlier pending
        # marker must retain that committed version rather than roll it back.
        self.call('recover', expected=0)
        self.assert_iteration(1)
        self.assertEqual((self.state / 'evidence/check-count').read_text().strip(), '2')

    def test_uncommitted_old_journal_cannot_rollback_newer_version(self):
        self.call(*self.args, '--operation-id', 'base', expected=0)
        self.call(*self.args, '--operation-id', 'aborted', env=self.fault_env('generation-published'))
        stale_pending = (self.state / 'store/pending').read_bytes()
        self.call('recover', expected=0)
        self.call(*self.args, '--operation-id', 'new-version', expected=0)
        (self.state / 'store/pending').write_bytes(stale_pending)
        before = self.snapshot()
        refused = self.call('recover', expected=4)
        self.assertIn('baseline', refused.stderr)
        self.assertEqual(before, self.snapshot())

    def test_crash_after_pointer_rolls_forward_and_retry_does_not_rerun(self):
        killed = self.call(*self.args, '--operation-id', 'after', env=self.fault_env('pointer-published'))
        self.assertNotEqual(killed.returncode, 0)
        pending = (self.state / 'store/pending').read_bytes()
        self.call('status', expected=4)
        (self.state / 'state.rec').write_text('iteration=999\n')
        (self.state / 'evidence/raw/1.txt').unlink()
        self.call('recover', expected=0)
        self.assert_iteration(1)
        self.assertTrue((self.state / 'evidence/raw/1.txt').is_file())
        self.call(*self.args, '--operation-id', 'after', expected=0)
        self.assertEqual((self.state / 'evidence/check-count').read_text().strip(), '1')
        # A stale pending journal must never rewind a newer committed version.
        self.call(*self.args, '--operation-id', 'newer', expected=0)
        (self.state / 'store/pending').write_bytes(pending)
        before = self.snapshot()
        refused = self.call('recover', expected=4)
        self.assertIn('not the current committed version', refused.stderr)
        self.assertEqual(before, self.snapshot())

    def test_lost_acknowledgement_does_not_consume_a_second_iteration(self):
        killed = self.call(*self.args, '--operation-id', 'lost-ack', env=self.fault_env('ack'))
        self.assertNotEqual(killed.returncode, 0)
        self.assertFalse((self.state / 'store/pending').exists())
        before = self.snapshot()
        self.call(*self.args, '--operation-id', 'lost-ack', expected=0)
        self.assertEqual(before, self.snapshot())
        self.assert_iteration(1)


if __name__ == '__main__':
    unittest.main()
