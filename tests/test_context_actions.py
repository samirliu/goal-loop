"""Consume only emitted maps through the real controller, recovery and Gate."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('context_commit_fault', ROOT/'tests/test_close_commit.py')
faults = importlib.util.module_from_spec(spec); spec.loader.exec_module(faults)


class ContextActions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='goal-context-actions-')
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.state = self.project/'.goal'

    def view(self):
        result = subprocess.run(['bash', str(ROOT/'scripts/goal_ctl.sh'), 'context', '--project', str(self.project), '--auto'],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        return json.loads(result.stdout)

    def execute(self, view, action, expected=0, env=None):
        command = view['actions'][action]['command']
        self.assertIsNotNone(command, view['actions'][action])
        result = subprocess.run(shlex.split(command), capture_output=True, text=True, env=env, timeout=20)
        if expected is not None:
            self.assertEqual(result.returncode, expected, result.stdout+result.stderr)
        return result

    def initialize(self):
        first = self.view()
        self.assertEqual(first['next'], 'initialize-ledger')
        self.execute(first, 'init')
        initial = self.view()
        self.assertEqual(initial['next'], 'author-contract-and-smoke')
        self.assertFalse((self.state/'goal.md').exists())
        contract = initial['author_contract']['template'].replace('<outcome>', 'deliver the answer').replace(
            '<yes/no statement>', 'answer matches the independent expectation').replace('<command>', 'python3 check.py')
        (self.state/'goal.md').write_text(contract)
        (self.project/'check.py').write_text('from pathlib import Path\nraise SystemExit(0 if Path("answer").read_bytes()==b"correct" else 1)\n')
        (self.project/'answer').write_bytes(b'correct')
        (self.state/'work-plan.md').write_text('- [ ] T1 answer | owner=controller | files=answer\n')
        authored = self.view()
        self.execute(authored, 'verify')
        self.execute(self.view(), 'stamp')

    def request(self, *, claim='yes', correct=True):
        (self.project/'answer').write_bytes(b'correct' if correct else b'wrong')
        (self.state/'work-plan.md').write_text('- [x] T1 answer | owner=controller | files=answer\n')
        view = self.view()
        self.assertEqual(view['next'], 'close-unbooked-wave')
        self.assertIsNone(view['actions']['close']['command'])
        self.assertIsNone(view['close_input']['template']['checks_pass'])
        self.assertIsNone(view['close_input']['template']['adversarial'])
        check = self.execute(view, 'verify', expected=0 if correct else 2)
        request = view['close_input']['template']
        request.update(checks_pass=1 if correct else 0, checks_fail=0 if correct else 1, checks_unverifiable=0,
                       progress='yes', exit_signal=claim, adversarial='clear',
                       adversarial_note='Independent exact-byte check: '+check.stdout.strip())
        path = Path(view['close_input']['path']); path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(request))
        return self.view(), request

    def test_single_task_from_empty_project_through_fresh_final_receipt(self):
        self.initialize()
        view, request = self.request()
        before = {str(p): p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        repeated = self.view()
        self.assertEqual(view['revision'], repeated['revision'])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.state.rglob('*') if p.is_file()})
        result = self.execute(view, 'close')
        self.assertIn('GATE: GO ', result.stdout)
        final = self.view()
        self.assertEqual(final['next'], 'verify-gate-and-deliver')
        self.assertNotIn('close', final['actions'])
        replay = self.execute(final, 'retry-close')
        self.assertIn('CTL: REPLAY operation='+request['operation_id'], replay.stdout)
        self.assertNotIn('GATE: GO ', replay.stdout)
        receipt = json.loads(self.execute(self.view(), 'receipt').stdout)
        self.assertTrue(receipt['completion_verified'])
        self.assertEqual({k: v['result'] for k, v in receipt['checks'].items()}, {'audit': 0, 'gate': 0})

    def test_claims_without_evidence_or_with_bad_product_cannot_go(self):
        self.initialize()
        view, request = self.request(correct=False)
        # Even dishonest submitted counts cannot bypass the real named check.
        request.update(checks_pass=999, checks_fail=0)
        Path(view['close_input']['path']).write_text(json.dumps(request))
        result = self.execute(self.view(), 'close', expected=2)
        self.assertNotIn('GATE: GO ', result.stdout)
        self.assertIn('open-FAIL:AC-1', result.stderr)
        final = self.view()
        self.execute(final, 'receipt', expected=2)

    def test_changed_product_request_and_evidence_reject_old_actions(self):
        self.initialize()
        view, request = self.request()
        (self.project/'answer').write_bytes(b'changed')
        self.assertIn('stale-context', self.execute(view, 'close', expected=4).stderr)
        (self.project/'answer').write_bytes(b'correct')
        fresh = self.view()
        request['adversarial_note'] += ' changed after map'
        Path(fresh['close_input']['path']).write_text(json.dumps(request))
        self.assertIn('stale-context', self.execute(fresh, 'close', expected=4).stderr)
        self.execute(self.view(), 'close')
        final = self.view()
        (self.state/'evidence/raw/1.txt').write_text('invented PASS')
        self.assertIn('ledger-view-mismatch', self.execute(final, 'receipt', expected=4).stderr)

    def recover_case(self, point, committed):
        self.initialize()
        view, request = self.request(claim='yes' if committed else 'no')
        env = faults.CloseCommit.fault_env(self, point)
        # Installing the fault instrument changes the artifact inventory.
        view = self.view()
        interrupted = self.execute(view, 'close', expected=None, env=env)
        self.assertNotEqual(interrupted.returncode, 0)
        recovery = self.view()
        self.assertEqual(recovery['next'], 'recover-ledger')
        self.assertEqual(set(recovery['actions']), {'recover'})
        self.assertEqual(recovery['recovery']['operation_id'], request['operation_id'])
        original = recovery['recovery']['original_arguments']
        self.assertIn(request['adversarial_note'], original)
        self.execute(view, 'close', expected=4)
        self.execute(recovery, 'recover')
        recovered = self.view()
        if committed:
            result = self.execute(recovered, 'retry-close')
            self.assertIn('CTL: REPLAY', result.stdout)
            self.assertEqual(recovered['actions']['retry-close']['parameters']['original_arguments'], original)
            self.assertIn('iteration=1\n', (self.state/'state.rec').read_text())
        else:
            self.assertEqual(recovered['close_input']['values'], request)
            # An unclaimed close returns the original NO-GO, but books once.
            self.execute(recovered, 'close', expected=2)
            self.assertIn('iteration=1\n', (self.state/'state.rec').read_text())

    def test_interruption_before_commit_recovers_original_request(self):
        self.recover_case('generation-published', False)

    def test_interruption_after_commit_replays_original_id_and_arguments(self):
        self.recover_case('pointer-published', True)

    def test_expiry_cannot_consume_an_old_work_or_close_map(self):
        self.initialize()
        view, _ = self.request()
        env = dict(os.environ, GOAL_RUNNER_MONOTONIC_END='1')
        self.assertIn('time-budget-exhausted', self.execute(view, 'close', expected=4, env=env).stderr)
        result = subprocess.run(['bash', str(ROOT/'scripts/goal_ctl.sh'), 'context', '--project', str(self.project), '--auto'],
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0, 'an expired inherited cap granted a fresh settlement')

    def test_recorded_wave_maps_plan_begin_prepare_and_missing_native_receipt(self):
        self.initialize()
        entered = subprocess.run([sys.executable, '-I', str(ROOT/'scripts/goal_host.py'), 'begin',
                                  str(self.project), 'codex', 'explicit-test-fixture', '120'],
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(entered.returncode, 0, entered.stdout+entered.stderr)
        proposals = self.state/'proposals'; proposals.mkdir(exist_ok=True)
        graph = dict(version=1, context={'test': 'action-binding'}, capacity=1, inputs=[], instruments=[],
                     jobs=[dict(id='T1', files=['answer'], deps=[], check=[sys.executable, 'check.py'])],
                     final_check=[sys.executable, 'check.py'])
        (proposals/'crew.json').write_text(json.dumps(graph))
        view = self.view()
        self.assertIsNone(view['actions']['begin-wave']['command'])
        self.assertEqual(json.loads(self.execute(view, 'plan').stdout)['choice'], 'serial')
        request = view['execution_input']['template']; request['mode'] = 'inline'
        Path(view['execution_input']['path']).write_text(json.dumps(request))
        starting = self.view()
        wave = self.execute(starting, 'begin-wave').stdout.strip()
        prepared_view = self.view()
        self.assertEqual(prepared_view['actions']['prepare-T1']['parameters']['wave'], wave)
        self.assertIn('explicit-test-fixture', prepared_view['actions']['prepare-T1']['executes'])
        prepared = json.loads(self.execute(prepared_view, 'prepare-T1').stdout)
        ticket = prepared['ticket']
        next_view = self.view()
        self.assertEqual(next_view['actions']['attach-T1']['parameters']['ticket'], ticket)
        self.assertIsNone(next_view['actions']['attach-T1']['command'], 'missing native evidence was guessed')
        self.assertIn('stale-context', self.execute(starting, 'begin-wave', expected=4).stderr)
        agent = '/root/context-test-fixture/T1'
        launch, terminal = proposals/'launch.json', proposals/'terminal.json'
        launch.write_text(json.dumps({'task_name':agent}))
        request['receipts'] = {'T1':{'launch':str(launch)}}
        Path(view['execution_input']['path']).write_text(json.dumps(request))
        attach = self.view()
        launch.write_text(json.dumps({'task_name':'/root/changed-fixture/T1'}))
        self.assertIn('stale-context', self.execute(attach, 'attach-T1', expected=4).stderr)
        launch.write_text(json.dumps({'task_name':agent}))
        self.execute(self.view(), 'attach-T1')
        ready = subprocess.run(shlex.split(prepared['ready_command']), capture_output=True, text=True, timeout=10)
        self.assertEqual(ready.returncode, 0, ready.stdout+ready.stderr)
        terminal.write_text(json.dumps({'agents':[{'agent_name':agent, 'agent_status':{'completed':'controlled test receipt'}}]}))
        request['receipts']['T1']['terminal'] = str(terminal)
        Path(view['execution_input']['path']).write_text(json.dumps(request))
        self.execute(self.view(), 'reconcile-T1')
        self.execute(self.view(), 'validate-T1')
        self.execute(self.view(), 'adopt-T1')
        self.execute(self.view(), 'finish-wave')
        self.assertEqual(self.view()['next'], 'close-unbooked-wave')
        self.assertNotIn('begin-wave', self.view()['actions'])

    def test_expired_map_can_settle_passing_work_without_dispatch_or_new_budget(self):
        self.initialize()
        self.request()
        result = subprocess.run([sys.executable, '-I', str(ROOT/'scripts/goal_host.py'), 'begin',
                                 str(self.project), 'codex', 'expiry-test-fixture', '1'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        deadline = json.loads((self.state/'runner.json').read_text())['deadline']
        time.sleep(1.1)
        view = self.view()
        self.assertTrue(view['expired'])
        self.assertFalse({'plan', 'begin-wave', 'prepare-T1', 'stamp'} & set(view['actions']))
        # Charge deterministic map preparation without slowing the original
        # controller's later batches. Mapping must preserve their envelopes,
        # rather than inventing a stricter aggregate close deadline.
        bindir = self.state/'map-probe'; bindir.mkdir()
        marker = self.state/'evidence/map-digest-delayed'
        shim = bindir/'python3'
        shim.write_text('#!/bin/bash\ncase "${2:-}" in */goal_tree_digest.py)\n'
                        ' if [ ! -e "$MAP_DELAY_MARKER" ]; then touch "$MAP_DELAY_MARKER"; sleep 1; fi ;;\nesac\n'
                        'exec '+shlex.quote(sys.executable)+' "$@"\n')
        shim.chmod(0o755)
        env = dict(os.environ, PATH=str(bindir)+os.pathsep+os.environ['PATH'], MAP_DELAY_MARKER=str(marker))
        self.execute(view, 'close', env=env)
        self.assertTrue(marker.exists(), 'controlled map preparation never ran')
        self.assertEqual(json.loads((self.state/'runner.json').read_text())['deadline'], deadline)
        receipt = json.loads(self.execute(self.view(), 'receipt').stdout)
        self.assertTrue(receipt['completion_verified'])


if __name__ == '__main__':
    unittest.main()
