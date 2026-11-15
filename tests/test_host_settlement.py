"""Native hook -> emitted command integration, including expired controllers."""
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


host = module(ROOT/'scripts/goal_host.py', 'settlement_host')
fixtures = module(ROOT/'tests/test_context_actions.py', 'settlement_context_fixture')


class HostSettlement(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ContextActions()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.project = self.f.project.resolve()
        self.f.state = self.f.project/'.goal'
        self.f.initialize()
        self.project, self.state = self.f.project, self.f.state
        self.backend, self.session = 'claude', 'native-settlement-fixture'
        host.begin(self.project, self.backend, self.session, 120)

    def expire(self):
        host.budget.adopt_host(self.state, host.capture(self.backend, self.session, 'tool'), .1)
        time.sleep(.12)
        return json.loads((self.state/'runner.json').read_bytes())

    def hook(self, command=None, *, tool='Bash', agent=None, event='PreToolUse'):
        payload = dict(hook_event_name=event, session_id=self.session, cwd=str(self.project),
                       tool_name=tool, tool_input={'command': command})
        if agent:
            payload['agent_id'] = agent
        result = subprocess.run([sys.executable, '-I', str(ROOT/'scripts/goal_host.py'),
                                 'hook', '--backend', self.backend],
                                input=json.dumps(payload), text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        return json.loads(result.stdout)

    def execute(self, command, expected=0):
        self.assertEqual(self.hook(command), {}, command)
        result = subprocess.run(command, shell=True, cwd=self.project,
                                capture_output=True, text=True, timeout=40)
        self.assertEqual(result.returncode, expected, result.stdout+result.stderr)
        return result

    def test_expired_native_controller_books_and_gets_actual_go_without_new_budget(self):
        (self.state/'work-plan.md').write_text('- [x] T1 answer | files=answer\n')
        runner = self.expire()
        for tool in ('Read', 'Grep', 'Glob', 'AskUserQuestion'):
            self.assertEqual(self.hook(tool=tool), {})
        view = self.f.view()
        self.assertTrue(view['expired'])
        self.execute(view['actions']['status']['command'])
        self.execute(view['actions']['receipt']['command'], expected=2)
        view = self.f.view()
        request = dict(progress='yes', exit_signal='yes', adversarial='clear',
                       adversarial_note='Actual exact-byte comparison to the independent expectation.')
        command = view['submissions']['close']['command'] + " <<'GOAL_CLOSE'\n" + json.dumps(request) + '\nGOAL_CLOSE\n'
        result = self.execute(command)
        self.assertIn('GATE: GO ', result.stdout)
        final = self.f.view()
        receipt = json.loads(self.execute(final['actions']['receipt']['command']).stdout)
        self.assertTrue(receipt['completion_verified'])
        self.assertEqual(json.loads((self.state/'runner.json').read_bytes()), runner)
        self.execute(self.f.view()['actions']['end']['command'])
        self.assertEqual(self.hook('echo ordinary-follow-up'), {})
        self.assertIn('iteration=1\n', (self.state/'state.rec').read_text())

    def test_expired_allowance_does_not_accept_work_shell_injection_or_other_project(self):
        self.expire()
        view = self.f.view()
        allowed = view['actions']['status']['command']
        submission = view['submissions']['close']['command']
        other = allowed.replace(str(self.project), '/tmp')
        commands = ['touch should-not-exist', allowed+'; touch should-not-exist',
                    allowed+' && true', 'env '+allowed, other,
                    allowed+'\necho extra', allowed+' > redirected',
                    submission+" <<GOAL_CLOSE\n{}\nGOAL_CLOSE",
                    submission+" <<'GOAL_CLOSE'\n{}\nGOAL_CLOSE\ntouch should-not-exist",
                    submission+" <<'GOAL_CLOSE'\n$(touch should-not-exist)\nGOAL_CLOSE",
                    shlex.join([sys.executable, '-c', 'print("unbounded work")'])]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.hook(command)['hookSpecificOutput']['permissionDecision'], 'deny')
        for tool in ('Agent', 'Task', 'Write', 'Edit'):
            self.assertEqual(self.hook(tool=tool)['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(self.hook(allowed, agent='worker')['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(self.hook(tool='Read', agent='worker')['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertFalse((self.project/'should-not-exist').exists())

    def test_expired_stale_submission_still_rejects_before_booking(self):
        (self.state/'work-plan.md').write_text('- [x] T1 answer | files=answer\n')
        self.expire()
        view = self.f.view()
        (self.project/'answer').write_text('changed after the map')
        command = view['submissions']['close']['command'] + " <<'JUDGMENT'\n{}\nJUDGMENT"
        self.assertIn('stale-context', self.execute(command, expected=4).stderr)
        self.assertIn('iteration=0\n', (self.state/'state.rec').read_text())

    def test_end_retains_budget_fences_workers_and_accepts_real_terminal_receipt(self):
        graph = self.project/'graph.json'
        graph.write_text(json.dumps(dict(version=1, context={}, capacity=1, inputs=[], instruments=[],
            jobs=[dict(id='T1', files=['answer'], deps=[], check=['true'])], final_check=['true'])))
        wave = host.crew.begin(self.project, graph, 'crew', 'end-fixture')
        item = host.prepare(self.project, wave, 'T1')
        host.attach(self.project, item['ticket'], {'agentId': 'owned-worker'})
        runner = json.loads((self.state/'runner.json').read_bytes())
        self.execute(self.f.view()['actions']['end']['command'])
        _, path = host.folder(self.project)
        row = host.get(path, item['ticket'])[1]
        self.assertTrue(Path(row['cancel_file']).exists())
        self.assertEqual(row['phase'], 'prepared')
        self.assertIsNone(host.crew.load(host.crew.Wave(self.project, wave).path)['jobs']['T1']['returned'])
        self.assertEqual(self.hook('echo user-follow-up'), {})
        self.assertEqual(self.hook(tool='Read', agent='owned-worker')['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(self.hook(item['owned_ready_command'], agent='owned-worker')['hookSpecificOutput']['permissionDecision'], 'deny')
        owned = subprocess.run(shlex.split(item['owned_ready_command']), capture_output=True, text=True, timeout=10)
        self.assertEqual(owned.returncode, 4, owned.stdout+owned.stderr)
        with self.assertRaisesRegex(ValueError, 'session ended'):
            host.begin(self.project, self.backend, self.session, 7200)
        host.reconcile(self.project, {'agentId': 'owned-worker', 'status': 'interrupted'}, self.session, self.backend)
        self.assertEqual(host.get(path, item['ticket'])[1]['phase'], 'cancelled')
        self.assertEqual(json.loads((self.state/'runner.json').read_bytes()), runner)

    def test_stop_keeps_goal_active_but_session_end_releases_it(self):
        self.assertEqual(self.hook(event='Stop'), {})
        self.assertTrue(host.active(host.folder(self.project)[1], self.project, self.session)['active'])
        self.assertEqual(self.hook(event='SessionEnd'), {})
        self.assertFalse(host.active(host.folder(self.project)[1], self.project, self.session, include_ended=True)['active'])
        self.assertEqual(self.hook('echo user-follow-up'), {})

    def test_ended_session_history_does_not_ambiguous_current_reconciliation(self):
        host.begin(self.project, self.backend, 'previous-session', 90)
        host.end(self.project, 'previous-session', self.backend)
        graph = self.project/'graph.json'
        graph.write_text(json.dumps(dict(version=1, context={}, capacity=1, inputs=[], instruments=[],
            jobs=[dict(id='T1', files=['answer'], deps=[], check=['true'])], final_check=['true'])))
        wave = host.crew.begin(self.project, graph, 'crew', 'current-session')
        item = host.prepare(self.project, wave, 'T1')
        host.attach(self.project, item['ticket'], {'agentId': 'current-worker'})
        observed = host.reconcile(self.project, {'agentId': 'current-worker', 'status': 'completed'})
        self.assertEqual(observed, [dict(ticket=item['ticket'], outcome='returned')])
        self.assertEqual(host.end(self.project)['session'], self.session)

    def pending_expired_close(self):
        self.f.request(claim='no')
        env = fixtures.faults.CloseCommit.fault_env(self.f, 'generation-published')
        self.expire()
        view = self.f.view()
        command = view['actions']['close']['command']
        self.assertEqual(self.hook(command), {})
        interrupted = subprocess.run(shlex.split(command), capture_output=True, text=True, env=env, timeout=30)
        self.assertNotEqual(interrupted.returncode, 0)
        self.assertTrue((self.state/'store/pending').exists())
        return (self.state/'runner.json').read_bytes()

    def test_expired_native_controller_can_recover_a_pending_transaction(self):
        runner = self.pending_expired_close()
        show = shlex.join([sys.executable, '-I', str(ROOT/'scripts/goal_context.py'), 'show', str(self.project)])
        recovery = json.loads(self.execute(show).stdout)
        self.assertEqual(recovery['next'], 'recover-ledger')
        self.assertIn('end', recovery['actions'])
        self.execute(recovery['actions']['recover']['command'])
        self.assertFalse((self.state/'store/pending').exists())
        self.assertEqual((self.state/'runner.json').read_bytes(), runner)

    def test_end_is_available_during_pending_recovery_without_erasing_it(self):
        runner = self.pending_expired_close()
        recovery = self.f.view()
        self.execute(recovery['actions']['end']['command'])
        self.assertTrue((self.state/'store/pending').exists())
        self.assertEqual((self.state/'runner.json').read_bytes(), runner)
        self.assertEqual(self.hook('echo ordinary-follow-up'), {})

    def test_context_exposes_freeze_drift_before_further_dispatch(self):
        script = self.project/'check.py'
        saved = script.read_bytes()
        script.write_bytes(saved+b'\n# changed after stamp\n')
        view = self.f.view()
        self.assertEqual(view['next'], 'repair-instrument-freeze')
        self.assertEqual(view['instruments']['changed'], ['check.py'])
        self.assertNotIn('verify', view['actions'])
        self.assertIn('end', view['actions'])
        script.write_bytes(saved)
        self.assertIsNone(self.f.view()['instruments']['error'])

    def test_nested_graph_reports_path_error_without_losing_control_actions(self):
        proposals = self.state/'proposals'
        proposals.mkdir(exist_ok=True)
        graph = dict(version=1, context={}, capacity=1, inputs=[], instruments=['check.py'],
                     jobs=[dict(id='T1', files=['answer'], deps=[], check=['true'])], final_check=['true'])
        path = proposals/'crew.json'
        path.write_text(json.dumps(graph))
        invalid = self.f.view()
        self.assertIn('error', invalid['execution_input'])
        self.assertIn('end', invalid['actions'])
        self.assertEqual(invalid['execution_input']['graph_path'], str(path))
        graph['instruments'] = [str(self.project/'check.py')]
        path.write_text(json.dumps(graph))
        valid = self.f.view()
        self.assertNotIn('error', valid['execution_input'])
        self.assertIn('plan', valid['actions'])

    def test_native_review_retry_requires_booking_and_a_fresh_ticket(self):
        proposals = self.state/'proposals'
        proposals.mkdir(exist_ok=True)
        graph = proposals/'crew.json'
        graph.write_text(json.dumps(dict(version=1, context={}, capacity=1, inputs=[], instruments=[],
            jobs=[dict(id='T1', files=['answer'], deps=[], check=['true'])], final_check=['true'])))
        wave = host.crew.begin(self.project, graph, 'crew', 'first-review')
        item = host.prepare(self.project, wave, 'T1')
        host.attach(self.project, item['ticket'], {'agentId': 'first-reviewer'})
        host.reconcile(self.project, {'agentId': 'first-reviewer', 'status': 'completed'})
        denied = self.hook('true', agent='first-reviewer')
        self.assertIn('fresh ticket/worker', denied['hookSpecificOutput']['permissionDecisionReason'])
        second = host.crew.begin(self.project, graph, 'crew', 'changed-evidence-review')
        with self.assertRaisesRegex(ValueError, 'unbooked host wave'):
            host.prepare(self.project, second, 'T1')
        view = self.f.view()
        self.assertIn('multiple active waves', view['execution_input']['error'])
        self.assertIn('end', view['actions'])
        request = dict(progress='yes', exit_signal='no')
        command = view['submissions']['close']['command']+" <<'BOOK'\n"+json.dumps(request)+'\nBOOK'
        self.execute(command, expected=2)
        fresh = host.prepare(self.project, second, 'T1')
        self.assertNotEqual(fresh['ticket'], item['ticket'])
        third = host.crew.begin(self.project, graph, 'crew', 'must-book-second-review')
        with self.assertRaisesRegex(ValueError, 'unbooked host wave'):
            host.prepare(self.project, third, 'T1')
        with self.assertRaisesRegex(ValueError, 'already terminal'):
            host.prepare(self.project, wave, 'T1')


if __name__ == '__main__':
    unittest.main()
