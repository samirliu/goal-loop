"""Submit real judgments against one observed version, without a refresh hop."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts/goal_context.py'
spec = importlib.util.spec_from_file_location('submit_context_fixture', ROOT/'tests/test_context_actions.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class ContextSubmit(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ContextActions()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.initialize()
        (self.f.state/'work-plan.md').write_text('- [x] T1 answer | owner=controller | files=answer\n')

    def judgment(self):
        return dict(progress='yes', exit_signal='yes', adversarial='clear',
                    adversarial_note='Actual second pass: answer bytes are correct and check.py independently compares them.')

    def submit(self, view, request=None, env=None):
        return subprocess.run([sys.executable, '-I', str(SCRIPT), 'submit', str(self.f.project),
                               view['revision'], 'close', '--auto', '--input', '-'],
                              input=json.dumps(self.judgment() if request is None else request),
                              capture_output=True, text=True, timeout=30, env=env)

    def receipt(self, result):
        values=[]
        for line in result.stdout.splitlines():
            try: value=json.loads(line)
            except ValueError: continue
            if isinstance(value, dict) and 'completion_verified' in value: values.append(value)
        self.assertEqual(len(values), 1, result.stdout+result.stderr)
        return values[0]

    def test_one_observed_version_accepts_judgments_and_runs_fresh_original_gate(self):
        view=self.f.view()
        self.assertFalse((self.f.state/'proposals/close-iteration.json').exists())
        result=self.submit(view)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue(self.receipt(result)['completion_verified'])
        log=(self.f.state/'loop-log.md').read_text()
        self.assertIn('checks_pass=1\n', log)
        self.assertEqual(log.count('## iteration'), 1)
        request=json.loads((self.f.state/'proposals/close-iteration.json').read_text())
        self.assertEqual(request['operation_id'], view['close_input']['template']['operation_id'])
        self.assertEqual(request['checks_source'], 'verify')
        self.assertNotIn('checks_pass', request)

    def test_emitted_submission_requires_only_actual_judgments(self):
        view=self.f.view(); entry=view['submissions']['close']
        self.assertIn(' submit ', entry['command'])
        self.assertEqual(set(entry['template']), set(self.judgment()))
        self.assertTrue(all(value is None for value in entry['template'].values()))

    def test_artifact_change_rejects_before_writing_request_or_booking(self):
        view=self.f.view(); before=(self.f.state/'state.rec').read_bytes()
        (self.f.project/'answer').write_bytes(b'changed')
        result=self.submit(view)
        self.assertEqual(result.returncode, 4, result.stdout+result.stderr)
        self.assertIn('stale-context', result.stderr)
        self.assertFalse((self.f.state/'proposals/close-iteration.json').exists())
        self.assertEqual(before, (self.f.state/'state.rec').read_bytes())

    def test_replaced_proposal_invalidates_observed_version(self):
        view=self.f.view(); path=self.f.state/'proposals/close-iteration.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(view['close_input']['measured_template']))
        before=path.read_bytes(); result=self.submit(view)
        self.assertEqual(result.returncode, 4, result.stdout+result.stderr)
        self.assertIn('stale-context', result.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_contract_and_plan_changes_reject_old_judgments(self):
        view=self.f.view()
        for path in [self.f.state/'goal.md', self.f.state/'work-plan.md']:
            before=path.read_bytes(); path.write_bytes(before+b'\nchanged after review\n')
            result=self.submit(view)
            self.assertEqual(result.returncode, 4, result.stdout+result.stderr)
            self.assertIn('stale-context', result.stderr)
            self.assertFalse((self.f.state/'proposals/close-iteration.json').exists())
            path.write_bytes(before)

    def test_missing_review_is_not_inferred_from_passing_checks(self):
        request=self.judgment(); del request['adversarial']
        result=self.submit(self.f.view(), request)
        self.assertEqual(result.returncode, 4, result.stdout+result.stderr)
        self.assertIn('adversarial', result.stderr)
        self.assertFalse((self.f.state/'proposals/close-iteration.json').exists())
        self.assertFalse((self.f.state/'evidence/adversarial.rec').exists())

    def test_manual_counts_cannot_override_automatic_evidence(self):
        result=self.submit(self.f.view(), dict(self.judgment(), checks_pass=999))
        self.assertEqual(result.returncode, 4, result.stdout+result.stderr)
        self.assertFalse((self.f.state/'proposals/close-iteration.json').exists())

    def test_derived_protocol_controls_cannot_be_overridden(self):
        view=self.f.view()
        for key, value in [('receipt', 'no'), ('operation_id', 'another-id'), ('checks_source', None)]:
            result=self.submit(view, dict(self.judgment(), **{key:value}))
            self.assertEqual(result.returncode, 4, result.stdout+result.stderr)
            self.assertIn('are derived', result.stderr)
            self.assertFalse((self.f.state/'proposals/close-iteration.json').exists())

    def test_actual_business_failure_stays_failed_and_charges_false_claim(self):
        (self.f.project/'answer').write_bytes(b'wrong')
        result=self.submit(self.f.view())
        self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
        self.assertFalse(self.receipt(result)['completion_verified'])
        self.assertIn('checks_fail=1\n', (self.f.state/'loop-log.md').read_text())
        self.assertIn('false_completes=1\n', (self.f.state/'state.rec').read_text())

    def test_expired_inherited_budget_is_not_renewed(self):
        view=self.f.view(); result=self.submit(view, env=dict(os.environ, GOAL_RUNNER_MONOTONIC_END='1'))
        self.assertEqual(result.returncode, 4, result.stdout+result.stderr)
        self.assertFalse((self.f.state/'proposals/close-iteration.json').exists())

    def test_precommit_crash_retains_exact_request_for_original_recovery(self):
        env=fixtures.faults.CloseCommit.fault_env(self.f, 'generation-published')
        view=self.f.view(); result=self.submit(view, env=env)
        self.assertNotEqual(result.returncode, 0)
        saved=(self.f.state/'proposals/close-iteration.json').read_bytes()
        recovery=self.f.view(); args=recovery['recovery']['original_arguments']
        self.assertIn('--checks-from-verify', args); self.assertIn('--receipt', args)
        self.f.execute(recovery, 'recover')
        restored=self.f.view()
        self.assertEqual((self.f.state/'proposals/close-iteration.json').read_bytes(), saved)
        self.assertEqual(restored['close_input']['values']['adversarial_note'], self.judgment()['adversarial_note'])
        result=self.f.execute(restored, 'close')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue(self.receipt(result)['completion_verified'])

    def test_committed_request_cannot_be_booked_again_with_old_revision(self):
        view=self.f.view(); first=self.submit(view)
        self.assertEqual(first.returncode, 0, first.stdout+first.stderr)
        stale=self.submit(view)
        self.assertEqual(stale.returncode, 4, stale.stdout+stale.stderr)
        current=self.f.view(); replay=self.f.execute(current, 'retry-close')
        self.assertIn('CTL: REPLAY', replay.stdout)
        self.assertTrue(self.receipt(replay)['completion_verified'])
        self.assertEqual((self.f.state/'loop-log.md').read_text().count('## iteration'), 1)

    def test_postcommit_crash_recovers_original_arguments_without_rebooking(self):
        env=fixtures.faults.CloseCommit.fault_env(self.f, 'pointer-published')
        result=self.submit(self.f.view(), env=env)
        self.assertNotEqual(result.returncode, 0)
        pending=self.f.view()
        self.assertIn('--receipt', pending['recovery']['original_arguments'])
        self.f.execute(pending, 'recover')
        replay=self.f.execute(self.f.view(), 'retry-close')
        self.assertIn('CTL: REPLAY', replay.stdout)
        self.assertTrue(self.receipt(replay)['completion_verified'])
        self.assertEqual((self.f.state/'loop-log.md').read_text().count('## iteration'), 1)


class ContextEntry(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ContextActions(); self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def entry(self, auto=True, seconds=120):
        command=[sys.executable, '-I', str(ROOT/'scripts/goal_host.py'), 'begin', str(self.f.project),
                 'codex', 'explicit-submit-test-fixture', str(seconds), '--context']
        result=subprocess.run(command+(['--auto'] if auto else []), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        return json.loads(result.stdout)

    def author(self, value, check='python3 check.py'):
        template=value['context']['author_contract']['template']
        template=template.replace('<outcome>', 'deliver answer').replace('<yes/no statement>', 'answer is correct').replace('<command>', check)
        (self.f.state/'goal.md').write_text(template)
        (self.f.project/'check.py').write_text('from pathlib import Path\nraise SystemExit(0 if Path("answer").read_bytes()==b"correct" else 1)\n')
        (self.f.project/'answer').write_bytes(b'correct')
        (self.f.state/'work-plan.md').write_text('- [ ] T1 answer | owner=controller | files=answer\n')

    def stamp(self, view):
        import shlex
        return subprocess.run(shlex.split(view['submissions']['stamp']['command']),
                              input='', capture_output=True, text=True, timeout=20)

    def test_one_entry_initializes_binds_and_returns_current_map(self):
        result=self.entry()
        self.assertEqual(result['host']['session'], 'explicit-submit-test-fixture')
        self.assertEqual(result['context']['budget_scope'], 'host-tool-entry')
        self.assertEqual(result['context']['next'], 'author-contract-and-smoke')
        self.assertTrue((self.f.state/'runner.json').exists())
        self.assertFalse((self.f.state/'goal.md').exists())
        deadline=json.loads((self.f.state/'runner.json').read_text())['deadline']
        resumed=self.entry(seconds=600)
        self.assertEqual(resumed['host']['deadline_epoch'], deadline)

    def test_single_submission_smokes_then_stamps_original_contract(self):
        self.author(self.entry()); view=self.f.view(); result=self.stamp(view)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('GATE: VERIFY AC-1|PASS|', result.stdout)
        self.assertRegex((self.f.state/'goal.md').read_text(), r'approved: [0-9a-f]+')
        self.assertTrue(self.f.view()['stamped'])

    def test_failing_business_criterion_can_be_stamped_before_its_repair(self):
        self.author(self.entry()); (self.f.project/'answer').write_bytes(b'wrong')
        result=self.stamp(self.f.view())
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('GATE: VERIFY AC-1|FAIL|', result.stdout)
        self.assertRegex((self.f.state/'goal.md').read_text(), r'approved: [0-9a-f]+')
        self.assertNotIn('GATE: GO ', result.stdout)

    def test_broken_smoke_does_not_stamp(self):
        self.author(self.entry(), check='missing_smoke_executable_379d9')
        result=self.stamp(self.f.view())
        self.assertNotEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('|BROKEN|', result.stdout)
        self.assertIn('approved: PENDING', (self.f.state/'goal.md').read_text())

    def test_mutating_smoke_does_not_stamp(self):
        self.author(self.entry())
        (self.f.project/'check.py').write_text('from pathlib import Path\nPath("answer").write_bytes(b"changed")\n')
        result=self.stamp(self.f.view())
        self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
        self.assertIn('check-mutated-tree', result.stdout+result.stderr)
        self.assertIn('approved: PENDING', (self.f.state/'goal.md').read_text())

    def test_entry_preserves_manual_approval_marker_without_auto_flag(self):
        entered=self.entry(auto=False); self.author(entered)
        result=subprocess.run(['bash', str(ROOT/'scripts/goal_ctl.sh'), 'context', '--project', str(self.f.project)],
                              capture_output=True, text=True, timeout=15)
        view=json.loads(result.stdout)
        self.assertNotIn('--auto', view['submissions']['stamp']['command'])
        self.assertIn('approved: PENDING', (self.f.state/'goal.md').read_text())
        manual=self.stamp(view)
        self.assertEqual(manual.returncode, 0, manual.stdout+manual.stderr)
        approved=next(line for line in (self.f.state/'goal.md').read_text().splitlines() if line.startswith('approved:'))
        self.assertNotIn(' auto', approved)

    def test_numeric_contract_keeps_explicit_observed_counts(self):
        self.author(self.entry(), check='printf 1')
        path=self.f.state/'goal.md'
        path.write_text(path.read_text().replace('expected: exit=0', 'probe: `true` | expected: >=1'))
        stamped=self.stamp(self.f.view())
        self.assertEqual(stamped.returncode, 0, stamped.stdout+stamped.stderr)
        (self.f.state/'work-plan.md').write_text('- [x] T1 answer | owner=controller | files=answer\n')
        view=self.f.view()
        self.assertIsNone(view['close_input']['measured_template'])
        self.assertIn('checks_pass', view['submissions']['close']['template'])
        request=dict(progress='yes', exit_signal='yes', adversarial='clear',
                     adversarial_note='Actual printf check returned1; reviewed fixed numeric expectation and probe.',
                     checks_pass=1, checks_fail=0, checks_unverifiable=0)
        result=subprocess.run([sys.executable, '-I', str(SCRIPT), 'submit', str(self.f.project),
                               view['revision'], 'close', '--auto', '--input', '-'],
                              input=json.dumps(request), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('"completion_verified": true', result.stdout)

    def test_enter_from_real_shaped_prompt_keeps_earliest_origin(self):
        host_spec=importlib.util.spec_from_file_location('submit_host_fixture', ROOT/'scripts/goal_host.py')
        host=importlib.util.module_from_spec(host_spec); host_spec.loader.exec_module(host)
        host.hook(dict(hook_event_name='UserPromptSubmit', session_id='explicit-prompt-fixture',
                       cwd=str(self.f.project), prompt='/goal-loop deliver answer'), 'codex')
        result=subprocess.run([sys.executable, '-I', str(ROOT/'scripts/goal_host.py'), 'enter',
                               str(self.f.project), '120', '--context'], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        value=json.loads(result.stdout)
        self.assertEqual(value['host']['session'], 'explicit-prompt-fixture')
        self.assertEqual(value['context']['budget_scope'], 'host-prompt-entry')

    def test_entry_reports_context_store_errors_through_normal_host_error_path(self):
        from unittest import mock
        host_spec=importlib.util.spec_from_file_location('submit_host_error_fixture', ROOT/'scripts/goal_host.py')
        host=importlib.util.module_from_spec(host_spec); host_spec.loader.exec_module(host)
        context=host.module('goal_context')
        argv=['goal_host.py', 'begin', str(self.f.project), 'codex', 'explicit-error-fixture', '120', '--context']
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(host, 'module', return_value=context), \
             mock.patch.object(context, 'show', side_effect=context.store.StoreError('ledger-view-mismatch')):
            with self.assertRaisesRegex(ValueError, 'ledger-view-mismatch'):
                host.main()


if __name__ == '__main__': unittest.main()
