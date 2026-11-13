"""A standalone gate shares one run deadline across all its work."""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
CTL, GATE = (ROOT / 'scripts' / name for name in ('goal_ctl.sh', 'goal_gate.sh'))


class GateBudget(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='goal-gate-budget-')
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.state = self.project / '.goal'
        self.call(CTL, 'init', expected=0)
        checks = []
        for i in range(1, 6):
            checks.append('- AC-%s | output | check: `if test -f .goal/evidence/slow; then '
                          'sleep 1; echo %s >> .goal/evidence/completed; fi; true` | expected: exit=0' % (i, i))
        (self.state / 'goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n' + '\n'.join(checks) +
                                          '\n\n## Budgets\n\ncheck_timeout=10\n\n## Approval\n\napproved: PENDING\n')
        self.call(CTL, 'stamp', '--auto', '--time-budget=1', expected=0)
        # Always enter final settlement after the contract deadline, regardless
        # of epoch rounding or how long the stamp smoke checks took.
        time.sleep(1.1)
        (self.state / 'evidence/slow').touch()

    def call(self, script, *args, expected=None, env=None):
        result = subprocess.run(['bash', str(script), *args, '--project', str(self.project)],
                                capture_output=True, env=env, timeout=12)
        if expected is not None:
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def ledger_bytes(self):
        return {str(p.relative_to(self.state)): p.read_bytes() for p in self.state.rglob('*')
                if p.is_file() and 'evidence' not in p.relative_to(self.state).parts}

    def test_expired_standalone_batch_does_not_give_every_ac_new_time(self):
        before = self.ledger_bytes()
        started = time.monotonic()
        result = self.call(GATE, '--verify')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertLess(time.monotonic() - started, 4.2)
        lines = (self.state / 'evidence/completed').read_text().splitlines()
        self.assertLess(len(lines), 5, 'each AC received a new settlement')
        self.assertEqual(before, self.ledger_bytes(), 'read-only gate changed ledger state')

    def test_ambient_supervision_marker_cannot_skip_the_bound(self):
        result = self.call(GATE, '--verify', env=dict(os.environ, GOAL_GATE_SUPERVISED='1'))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertLess(len((self.state / 'evidence/completed').read_text().splitlines()), 5)

    def test_hash_preparation_is_inside_the_same_bound(self):
        bindir = self.project / 'bin'
        bindir.mkdir()
        python = bindir / 'python3'
        python.write_text('#!/bin/bash\ncase "${2:-}" in */goal_tree_digest.py) '
                          'touch "$HASH_READY"; sleep 5 ;; esac\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
        python.chmod(0o755)
        marker = self.state / 'evidence/hash-ready'
        env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ['PATH'], HASH_READY=str(marker))
        started = time.monotonic()
        result = self.call(GATE, '--verify', env=env)
        self.assertTrue(marker.exists(), 'slow hashing was never reached')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertLess(time.monotonic() - started, 4.2)
        self.assertFalse((self.state / 'evidence/completed').exists())


if __name__ == '__main__':
    unittest.main()
