"""Compose improvement with the controller's real writer-locked acceptance.

Policy trial costs are controlled by the shared fixture. Verification, claim,
receipt, recovery and competing access all execute their production entrypoints.
"""
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('acceptance_improvement_fixture', ROOT/'tests/test_improvement.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
improve, host = fixtures.improve, fixtures.host
spec = importlib.util.spec_from_file_location('acceptance_improvement_context', ROOT/'scripts/goal_context.py')
context = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context)


class ImprovementAcceptance(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.Improvement()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.start()
        self.case.evaluate()
        self.f, self.root = self.case.f, self.case.root

    def receipt(self, view):
        result = json.loads(self.f.execute(view, 'receipt').stdout)
        self.assertTrue(result['completion_verified'], result)
        return result

    def test_live_campaign_does_not_block_mapped_verify_claim_and_receipt(self):
        self.f.execute(self.f.view(), 'verify')
        (self.root/'.goal/work-plan.md').write_text('- [x] T1 answer | files=answer\n')
        view = self.f.view()
        request = dict(progress='yes', exit_signal='yes', adversarial='clear',
                       adversarial_note='Actual check.py independently compares the delivered exact answer bytes.')
        result = subprocess.run(shlex.split(view['submissions']['close']['command']),
                                input=json.dumps(request), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('GATE: GO ', result.stdout)
        self.receipt(self.f.view())
        self.assertIn('iteration=1\n', (self.root/'.goal/state.rec').read_text())

    def test_expired_live_campaign_can_close_through_actual_native_hook(self):
        self.f.request()
        host.budget.adopt_host(self.root/'.goal', host.capture('claude', 'improvement-test-session', 'tool'), .1)
        time.sleep(.12)
        runner = (self.root/'.goal/runner.json').read_bytes()
        view = self.f.view()
        self.assertTrue(view['expired'])
        command = view['actions']['close']['command']
        payload = dict(hook_event_name='PreToolUse', session_id='improvement-test-session', cwd=str(self.root),
                       tool_name='Bash', tool_input={'command':command})
        self.assertEqual(host.hook(payload, 'claude'), {})
        self.f.execute(view, 'close')
        self.receipt(self.f.view())
        self.assertEqual((self.root/'.goal/runner.json').read_bytes(), runner)

    def test_live_campaign_still_rejects_a_bad_product_at_final_acceptance(self):
        view, _ = self.f.request(correct=False)
        result = self.f.execute(view, 'close', expected=2)
        self.assertNotIn('GATE: GO ', result.stdout)
        receipt = self.f.execute(self.f.view(), 'receipt', expected=2)
        self.assertFalse(json.loads(receipt.stdout)['completion_verified'])

    def test_claim_recovery_with_campaign_retains_original_request_and_books_once(self):
        self.f.request()
        env = fixtures.contexts.faults.CloseCommit.fault_env(self.f, 'generation-published')
        interrupted = self.f.execute(self.f.view(), 'close', expected=None, env=env)
        self.assertNotEqual(interrupted.returncode, 0)
        self.assertTrue((self.root/'.goal/store/pending').exists())
        self.f.execute(self.f.view(), 'recover')
        self.f.execute(self.f.view(), 'close')
        self.receipt(self.f.view())
        self.assertIn('iteration=1\n', (self.root/'.goal/state.rec').read_text())

    def test_borrowed_read_keeps_writer_exclusion_and_refuses_other_project(self):
        with context.access(self.root, write=True) as (_, _, fd):
            self.assertIsNotNone(improve.view(self.root, ledger_fd=fd)[0]['selected'])
            blocked = subprocess.run(['bash', str(ROOT/'scripts/goal_ctl.sh'), 'status', '--project', str(self.root)],
                                     capture_output=True, text=True, timeout=10)
            self.assertEqual(blocked.returncode, 4, blocked.stdout+blocked.stderr)
            self.assertIn('ledger-busy', blocked.stderr)
            with tempfile.TemporaryDirectory(prefix='improve-foreign-ledger-') as directory:
                other = Path(directory).resolve()
                (other/'.goal').mkdir()
                with self.assertRaisesRegex(ValueError, 'lock target mismatch'):
                    with improve.crew.read_ledger(other, ledger_fd=fd):
                        self.fail('foreign descriptor was accepted')
                with self.assertRaisesRegex(improve.engine.ExperimentError, 'lock target mismatch'):
                    improve.engine.checkpoint_programs(dict(baseline='0'*64,candidate='1'*64,entry='worker.py'), other, ledger_fd=fd)
        self.f.execute(self.f.view(), 'verify')


if __name__ == '__main__':
    unittest.main()
