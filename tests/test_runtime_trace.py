"""Real supervised commands leave cost evidence without changing acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
SPEC = importlib.util.spec_from_file_location('runtime_trace', SCRIPTS / 'goal_trace.py')
trace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trace)


class RuntimeTrace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='goal-runtime-trace-')
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.state = self.project / '.goal'
        self.call('goal_ctl.sh', 'init', expected=0)

    def call(self, script, *args, expected=None):
        result = subprocess.run(['bash', str(SCRIPTS / script), *args, '--project', str(self.project)],
                                capture_output=True, timeout=15)
        if expected is not None:
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_measurement_conditions_and_nested_wall_time_are_observed(self):
        (self.state / 'goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n'
                                          '- AC-1 | output | check: `sleep 0.05` | expected: exit=0\n\n'
                                          '## Approval\n\napproved: PENDING\n')
        self.call('goal_ctl.sh', 'stamp', '--auto', expected=0)
        before = {r['id'] for r in trace.records(self.project)}
        result = self.call('goal_gate.sh', '--verify', expected=0)
        self.assertIn(b'AC-1|PASS', result.stdout)
        rows = [r for r in trace.records(self.project) if r['id'] not in before]
        self.assertEqual(len(rows), 2)
        batch = next(r for r in rows if r['kind'] == 'verification')
        check = next(r for r in rows if r['kind'] == 'measurement')
        self.assertEqual(check['parent'], batch['id'])
        self.assertEqual(check['label'], 'check:AC-1')
        self.assertRegex(check['artifact'], '^v2-[0-9a-f]{64}$')
        self.assertEqual(check['contract_sha256'], trace.file_hash(self.state / 'goal.md'))
        self.assertGreaterEqual(check['elapsed'], 0.05)
        self.assertGreater(batch['elapsed'], check['elapsed'])
        self.assertEqual(check['result'], 0)
        self.assertIsNone(check['tokens'])
        self.assertIsNone(check['money'])
        status = self.call('goal_ctl.sh', 'status', expected=0)
        self.assertIn(b'wall=not-summed tokens=unknown money=unknown', status.stdout)

    def test_timed_out_executor_is_retained_with_nonzero_cost(self):
        env = dict(os.environ, GOAL_TRACE_PROJECT=str(self.project))
        result = subprocess.run([sys.executable, '-I', str(SCRIPTS / 'goal_bounded.py'),
                                 '--owner', str(os.getpid()), '--seconds', '0.2', '--kind', 'executor',
                                 '--label', 'timeout-case', '--', 'bash', '-c', 'sleep 3'],
                                env=env, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
        rows = trace.records(self.project)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['result'], 124)
        self.assertEqual(rows[0]['state'], 'complete')
        self.assertGreaterEqual(rows[0]['elapsed'], 0.15)

    def test_handled_supervisor_setup_failure_finishes_cost_without_dispatch(self):
        marker = self.project/'must-not-run'
        bootstrap = ('import importlib.util,os,sys\n'
            'spec=importlib.util.spec_from_file_location("bounded",sys.argv[1])\n'
            'bounded=importlib.util.module_from_spec(spec);spec.loader.exec_module(bounded)\n'
            'def unavailable(owner): raise bounded.watch.WatchError("injected kernel subscription failure")\n'
            'bounded.watch._process_events=unavailable\n'
            'sys.argv=[sys.argv[1],"--owner",str(os.getppid()),"--seconds","1","--",sys.executable,"-c",'
            + repr('from pathlib import Path; Path(%r).touch()' % str(marker)) + ']\n'
            'try: bounded.main()\n'
            'except bounded.watch.WatchError: sys.exit(4)\n')
        result = subprocess.run([sys.executable, '-I', '-c', bootstrap, str(SCRIPTS/'goal_bounded.py')],
            env=dict(os.environ, GOAL_TRACE_PROJECT=str(self.project)), start_new_session=True,
            capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 4, result.stdout+result.stderr)
        self.assertFalse(marker.exists(), 'setup failure released user work')
        rows = trace.records(self.project)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['state'], 'complete')
        self.assertEqual(rows[0]['result'], 4)
        self.assertGreater(rows[0]['elapsed'], 0)

    def test_unfinished_span_is_unknown_not_zero(self):
        trace.Trace(self.project, 'executor', 'incomplete-case', ['bash', '-c', 'work'])
        result = self.call('goal_ctl.sh', 'status', expected=0)
        self.assertIn(b'unfinished=1 executor-span-seconds=unknown', result.stdout)

    def test_damaged_cost_evidence_does_not_turn_into_zero_or_a_go(self):
        item = trace.Trace(self.project, 'executor', 'damaged-case', ['bash'])
        item.finish(1)
        value = json.loads(item.path.read_bytes())
        value['payload']['elapsed'] = 0  # retain the old checksum
        item.path.write_text(json.dumps(value))
        result = self.call('goal_ctl.sh', 'status', expected=0)
        self.assertIn(b'costs=unknown', result.stderr)
        self.assertNotIn(b'executor-span-seconds=0', result.stdout)
        self.assertNotIn(b'GATE: GO', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
