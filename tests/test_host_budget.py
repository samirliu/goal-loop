"""Host entry charges planning time to the runner's existing transaction."""
import contextlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CTL = ROOT / 'scripts/goal_ctl.sh'
LOOP = ROOT / 'devtools/goal_loop.sh'
RUNNER = ROOT / 'scripts/goal_runner.py'
spec = importlib.util.spec_from_file_location('host_budget_runner', RUNNER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class HostBudget(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='goal-host-budget-')
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.state = self.project / '.goal'
        self.ctl('init')
        (self.state / 'goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | output | check: `true` | expected: exit=0\n\n'
            '## Approval\n\napproved: PENDING\n')
        self.ctl('stamp', '--auto')

    def ctl(self, *args):
        result = subprocess.run(['bash', str(CTL), *args, '--project', str(self.project)],
                                capture_output=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def origin(self, kind='prompt'):
        return dict(backend='test-host', session='real-entry', kind=kind,
                    epoch=time.time(), monotonic=time.monotonic(), boot=runner.boot_identity())

    def value(self):
        return runner.runner_data((self.state / 'runner.json').read_bytes())

    def ledger_bytes(self):
        return {str(path.relative_to(self.state)): path.read_bytes()
                for path in self.state.rglob('*') if path.is_file()}

    def budget(self, action='observe', seconds=200, started=None):
        # A new owner starts now. Its local clock must not replace host entry.
        now = int(time.time())
        env = dict(GOAL_RUNNER_MONOTONIC_START=str(time.monotonic()))
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            runner.budget(self.state, action, str(now if started is None else started), str(seconds), str(now))
        return self.value(), err.getvalue()

    def cli(self, command, *args, fault=None):
        env = os.environ.copy()
        env.pop('GOAL_RUNNER_FAULT', None)
        if fault:
            env['GOAL_RUNNER_FAULT'] = fault
        return subprocess.run([sys.executable, '-I', str(RUNNER), command, str(self.state), *map(str, args)],
                              env=env, capture_output=True, timeout=12)

    def test_real_planning_delay_and_gate_elapsed_survive_owner_restart(self):
        origin = self.origin()
        time.sleep(0.18)  # Real host reading/planning, before runner ownership.
        adopted = runner.adopt_host(self.state, origin, 20)
        cap, expired = runner.gate_limit(self.state)
        self.assertFalse(expired)
        self.assertLess(cap - time.monotonic(), 19.85)
        self.assertLessEqual(cap, origin['monotonic'] + 20)
        self.assertEqual(adopted['scope'], 'host-prompt-entry')
        time.sleep(0.08)
        observed, _ = self.budget()
        self.assertEqual(observed['origin'], origin)
        time.sleep(0.08)  # Independent gate work also belongs to total elapsed.
        delivered, report = self.budget('delivered')
        self.assertEqual(delivered['run'], adopted['run'])
        self.assertEqual(delivered['origin'], origin)
        self.assertGreaterEqual(delivered['result']['elapsed'], 0.34)
        self.assertTrue(delivered['result']['timely'])
        self.assertIn('scope=host-prompt-entry', report)

    def test_reentry_and_larger_allowance_never_extend_either_clock(self):
        origin = self.origin('tool')
        first = runner.adopt_host(self.state, origin, 30)
        duplicate = runner.adopt_host(self.state, origin, 300)
        later = runner.adopt_host(self.state, self.origin(), 600)
        observed, _ = self.budget('begin')
        for value in (duplicate, later, observed):
            self.assertEqual(value['run'], first['run'])
            self.assertEqual(value['origin'], origin)
            self.assertEqual(value['scope'], 'host-tool-entry')
            self.assertLessEqual(value['deadline'], first['deadline'])
            self.assertLessEqual(value['monotonic']['deadline'], first['monotonic']['deadline'])

    def test_actual_loop_resume_preserves_origin_and_run(self):
        origin = self.origin()
        first = runner.adopt_host(self.state, origin, 30)
        result = subprocess.run(['bash', str(LOOP), '--continue', '--resume', '--dry-run',
                                 '--wallclock=200', '--max-iterations=1', '--project', str(self.project)],
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        value = self.value()
        self.assertEqual(value['run'], first['run'])
        self.assertEqual(value['origin'], origin)
        self.assertEqual(value['deadline'], first['deadline'])
        self.assertLessEqual(value['monotonic']['deadline'], first['monotonic']['deadline'])
        self.assertGreaterEqual(value['result']['elapsed'], time.monotonic() - origin['monotonic'] - 0.2)
        self.assertIn(b'scope=host-prompt-entry', result.stderr)

    def test_earlier_observed_entry_is_preserved_when_adopted_later(self):
        early = self.origin()
        time.sleep(0.04)
        later = self.origin('tool')
        first = runner.adopt_host(self.state, later, 30)
        second = runner.adopt_host(self.state, early, 30)
        self.assertEqual(second['run'], first['run'])
        self.assertEqual(second['origin'], early)
        self.assertEqual(second['scope'], 'host-prompt-entry')
        self.assertLessEqual(second['deadline'], first['deadline'])
        self.assertLessEqual(second['monotonic']['deadline'], first['monotonic']['deadline'])
        self.assertEqual(second['deadline'], math.floor(early['epoch'] + 30))
        self.assertEqual(runner.adopt_host(self.state, later, 300)['origin'], early)

    def test_script_entry_remains_accurate_and_v1_api_still_works(self):
        old, _ = self.budget('begin', 30)
        self.assertEqual(old['version'], 1)
        self.assertEqual(old['scope'], 'script-entry')
        self.assertNotIn('origin', old)
        origin = self.origin('tool')
        value = runner.adopt_host(self.state, origin, 300)
        self.assertEqual(value['version'], 2)
        self.assertEqual(value['run'], old['run'])
        self.assertEqual(value['scope'], 'script-entry')
        self.assertEqual(value['started'], old['started'])
        self.assertLessEqual(value['deadline'], old['deadline'])
        delivered, report = self.budget('delivered')
        self.assertEqual(delivered['origin'], origin)
        self.assertIn('scope=script-entry', report)
        self.assertGreaterEqual(delivered['result']['elapsed'], int(time.time()) - old['started'])

    def test_invalid_receipts_and_budgets_do_not_write(self):
        valid = self.origin()
        invalid = [dict(valid, epoch=valid['epoch'] + 100),
                   dict(valid, monotonic=valid['monotonic'] + 100),
                   dict(valid, boot='0' * 64), dict(valid, boot='bad'),
                   dict(valid, epoch=math.nan), dict(valid, epoch='today'),
                   dict(valid, monotonic=math.inf), dict(valid, epoch=True),
                   dict(valid, kind='script'), dict(valid, surprise='extra')]
        for receipt in invalid:
            with self.subTest(receipt=receipt):
                before = self.ledger_bytes()
                with self.assertRaises(runner.store.StoreError):
                    runner.adopt_host(self.state, receipt, 30)
                self.assertEqual(self.ledger_bytes(), before)
        for seconds in (0, -1, math.inf, math.nan, True, '30'):
            with self.subTest(seconds=seconds):
                before = self.ledger_bytes()
                with self.assertRaises(runner.store.StoreError):
                    runner.adopt_host(self.state, valid, seconds)
                self.assertEqual(self.ledger_bytes(), before)

    def test_clock_regression_and_uncommitted_views_fail_without_writes(self):
        origin = self.origin()
        runner.adopt_host(self.state, origin, 30)
        before = self.ledger_bytes()
        with mock.patch.object(runner.time, 'time', return_value=origin['epoch'] - 5):
            # Use a valid older receipt so the highwater check is exercised.
            older = dict(origin, epoch=origin['epoch'] - 10, monotonic=origin['monotonic'] - 10)
            with self.assertRaisesRegex(runner.store.StoreError, 'clock-regressed'):
                runner.adopt_host(self.state, older, 30)
        self.assertEqual(self.ledger_bytes(), before)
        (self.state / 'runner.deadline').write_text('9999999999\n')
        tampered = self.ledger_bytes()
        with self.assertRaisesRegex(runner.store.StoreError, 'ledger-view-mismatch'):
            runner.adopt_host(self.state, origin, 30)
        self.assertEqual(self.ledger_bytes(), tampered)

    def test_host_observation_requires_exclusive_ledger_ownership(self):
        origin = self.origin()
        before = self.ledger_bytes()
        with runner.ledger(self.state):
            with self.assertRaisesRegex(runner.store.StoreError, 'ledger-busy'):
                runner.adopt_host(self.state, origin, 30)
        self.assertEqual(self.ledger_bytes(), before)

    def test_reboot_keeps_origin_and_rejects_nonadvancing_wall_clock(self):
        origin = self.origin()
        first = runner.adopt_host(self.state, origin, 30)
        next_boot = 'f' * 64 if origin['boot'] != 'f' * 64 else 'e' * 64
        next_origin = dict(origin, boot=next_boot, epoch=float(first['clock']), monotonic=4.0)
        before = self.ledger_bytes()
        # This models a reboot; the real initial boot receipt above remains
        # mandatory, including under the macOS sandbox.
        with mock.patch.object(runner, 'boot_identity', return_value=next_boot), \
                mock.patch.object(runner.time, 'time', return_value=next_origin['epoch']), \
                mock.patch.object(runner.time, 'monotonic', return_value=4.0):
            with self.assertRaisesRegex(runner.store.StoreError, 'clock-regressed-across-reboot'):
                runner.adopt_host(self.state, next_origin, 300)
        self.assertEqual(self.ledger_bytes(), before)
        next_origin['epoch'] += 2
        with mock.patch.object(runner, 'boot_identity', return_value=next_boot), \
                mock.patch.object(runner.time, 'time', return_value=next_origin['epoch']), \
                mock.patch.object(runner.time, 'monotonic', return_value=4.0):
            resumed = runner.adopt_host(self.state, next_origin, 300)
            delivered, _ = self.budget('delivered')
        for value in (resumed, delivered):
            self.assertEqual(value['run'], first['run'])
            self.assertEqual(value['origin'], origin)
            self.assertEqual(value['deadline'], first['deadline'])
            self.assertEqual(value['monotonic']['boot'], next_boot)
        self.assertGreaterEqual(delivered['result']['elapsed'], next_origin['epoch'] - origin['epoch'])

    def test_host_faults_use_same_pointer_commit_and_exact_recovery(self):
        origin = self.origin()
        receipt = self.project / 'entry.json'
        receipt.write_text(json.dumps(origin))
        pointer = self.state / 'store/commits/current'
        before = pointer.read_bytes()
        failed = self.cli('adopt-host', receipt, 30, fault='generation-published')
        self.assertEqual(failed.returncode, 91, failed.stdout + failed.stderr)
        self.assertEqual(pointer.read_bytes(), before)
        self.assertFalse((self.state / 'runner.json').exists())
        self.ctl('status')
        self.ctl('recover')
        failed = self.cli('adopt-host', receipt, 30, fault='pointer-published')
        self.assertEqual(failed.returncode, 91, failed.stdout + failed.stderr)
        self.assertNotEqual(pointer.read_bytes(), before)
        self.assertFalse((self.state / 'runner.json').exists())
        with self.assertRaisesRegex(runner.store.StoreError, 'ledger-view-mismatch'):
            runner.store.verify_views(self.state)
        self.ctl('recover')
        value = self.value()
        self.assertEqual(value['origin'], origin)
        self.assertEqual(value['deadline'], math.floor(origin['epoch'] + 30))
        self.assertEqual(int((self.state / 'runner.clock').read_text()), value['clock'])
        self.assertEqual(int((self.state / 'runner.deadline').read_text()), value['deadline'])
        runner.store.verify_views(self.state)
        retried = self.cli('adopt-host', receipt, 300)
        self.assertEqual(retried.returncode, 0, retried.stdout + retried.stderr)
        repeated = json.loads(retried.stdout)
        self.assertEqual(repeated['run'], value['run'])
        self.assertEqual(repeated['origin'], origin)
        self.assertEqual(repeated['deadline'], value['deadline'])
        self.assertLessEqual(repeated['monotonic']['deadline'], value['monotonic']['deadline'])

    def test_late_real_gate_go_is_not_timely(self):
        (self.project / 'artifact.txt').write_text('delivered\n')
        self.ctl('close-iteration', '--task', 'T1', '--files', 'artifact.txt',
                 '--checks-pass', '1', '--checks-fail', '0', '--checks-unverifiable', '0',
                 '--progress', 'yes', '--exit-signal', 'yes', '--adversarial', 'clear',
                 '--adversarial-note', 'reviewed', '--no-gate')
        origin = self.origin()
        time.sleep(1.12)
        first = runner.adopt_host(self.state, origin, 1)
        _, expired = runner.gate_limit(self.state, settlement=False)
        self.assertTrue(expired, 'planning before adoption was given a fresh allowance')
        result = subprocess.run(['bash', str(LOOP), '--continue', '--resume', '--wallclock=200',
                                 '--max-iterations=1', '--project', str(self.project)],
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(b'GATE: GO', result.stdout + result.stderr)
        self.assertIn(b'timing=after-deadline', result.stderr)
        value = self.value()
        self.assertEqual(value['run'], first['run'])
        self.assertEqual(value['origin'], origin)
        self.assertEqual(value['result']['outcome'], 'delivered')
        self.assertFalse(value['result']['timely'])
        self.assertGreaterEqual(value['result']['elapsed'], 1.12)


if __name__ == '__main__':
    unittest.main()
