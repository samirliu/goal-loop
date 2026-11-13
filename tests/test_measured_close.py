"""Derive mechanical counts from the original verifier, keep actual review required."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('measured_context_fixture',ROOT/'tests/test_context_actions.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)


class MeasuredClose(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ContextActions();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.initialize()
        (self.f.state/'work-plan.md').write_text('- [x] T1 answer | owner=controller | files=answer\n')

    def close(self,review=True,extra=(),env=None):
        command=['bash',str(ROOT/'scripts/goal_ctl.sh'),'close-iteration','--project',str(self.f.project),
                 '--operation-id','measured-close-001','--task','T1','--files','answer',
                 '--progress','yes','--exit-signal','yes','--checks-from-verify','--receipt']
        if review:command+=['--adversarial','clear','--adversarial-note','Exact-byte independent review of answer and check.py.']
        return subprocess.run(command+list(extra),capture_output=True,text=True,timeout=30,env=env)

    def receipt(self,result):
        rows=[]
        for line in result.stdout.splitlines():
            try:value=json.loads(line)
            except ValueError:continue
            if isinstance(value,dict) and 'completion_verified' in value:rows.append(value)
        self.assertEqual(len(rows),1,result.stdout+result.stderr)
        return rows[0]

    def test_one_call_derives_counts_books_and_runs_original_fresh_acceptance(self):
        result=self.close()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        log=(self.f.state/'loop-log.md').read_text()
        for line in ('checks_pass=1\n','checks_fail=0\n','checks_unverifiable=0\n'):self.assertIn(line,log)
        self.assertIn('GATE: VERIFY AC-1|PASS|',(self.f.state/'evidence/raw/1.txt').read_text())
        receipt=self.receipt(result)
        self.assertTrue(receipt['completion_verified'])
        self.assertEqual({k:v['result'] for k,v in receipt['checks'].items()},{'audit':0,'gate':0})

    def test_bad_product_is_measured_failed_not_auto_passed(self):
        (self.f.project/'answer').write_bytes(b'wrong')
        result=self.close()
        self.assertEqual(result.returncode,2,result.stdout+result.stderr)
        log=(self.f.state/'loop-log.md').read_text()
        self.assertIn('checks_pass=0\n',log);self.assertIn('checks_fail=1\n',log)
        self.assertFalse(self.receipt(result)['completion_verified'])

    def test_successful_checks_never_supply_missing_adversarial_clear(self):
        result=self.close(review=False)
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse((self.f.state/'evidence/adversarial.rec').exists())
        self.assertFalse(self.receipt(result)['completion_verified'])

    def test_explicit_counts_cannot_be_mixed_with_measured_mode(self):
        before=(self.f.state/'state.rec').read_bytes()
        result=self.close(extra=['--checks-pass','999'])
        self.assertEqual(result.returncode,4,result.stdout+result.stderr)
        self.assertEqual(before,(self.f.state/'state.rec').read_bytes())
        self.assertFalse((self.f.state/'store/pending').exists())

    def test_replay_preserves_original_intent_and_gets_fresh_gate(self):
        first=self.close();self.assertEqual(first.returncode,0,first.stdout+first.stderr)
        replay=self.close();self.assertEqual(replay.returncode,0,replay.stdout+replay.stderr)
        self.assertIn('CTL: REPLAY',replay.stdout)
        self.assertTrue(self.receipt(replay)['completion_verified'])
        self.assertEqual((self.f.state/'loop-log.md').read_text().count('## iteration'),1)
        (self.f.project/'answer').write_bytes(b'changed')
        stale=self.close()
        self.assertNotEqual(stale.returncode,0,stale.stdout+stale.stderr)
        self.assertFalse(self.receipt(stale)['completion_verified'])
        self.assertEqual((self.f.state/'loop-log.md').read_text().count('## iteration'),1)

    def measured_request(self):
        view=self.f.view()
        request=view['close_input']['measured_template']
        self.assertNotIn('checks_pass',request)
        self.assertEqual(request['checks_source'],'verify')
        request.update(progress='yes',exit_signal='yes',adversarial='clear',
                       adversarial_note='Actual review of answer bytes and the independent check.')
        path=Path(view['close_input']['path']);path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(request))
        return self.f.view(),request

    def test_version_bound_map_consumes_measured_request(self):
        view,request=self.measured_request()
        self.assertIn('--checks-from-verify',view['actions']['close']['executes'])
        changed=dict(request,adversarial_note='Different review after map compilation.')
        Path(view['close_input']['path']).write_text(json.dumps(changed))
        self.assertIn('stale-context',self.f.execute(view,'close',expected=4).stderr)
        result=self.f.execute(self.f.view(),'close')
        self.assertTrue(self.receipt(result)['completion_verified'])

    def test_interruption_recovers_and_reuses_original_measured_arguments(self):
        view,request=self.measured_request()
        env=fixtures.faults.CloseCommit.fault_env(self.f,'generation-published')
        view=self.f.view()
        self.assertNotEqual(self.f.execute(view,'close',expected=None,env=env).returncode,0)
        pending=self.f.view()
        self.assertEqual(pending['next'],'recover-ledger')
        original=pending['recovery']['original_arguments']
        self.assertIn('--checks-from-verify',original);self.assertIn('--receipt',original)
        self.f.execute(pending,'recover')
        self.assertEqual(self.f.view()['close_input']['values'],request)
        result=self.f.execute(self.f.view(),'close')
        self.assertTrue(self.receipt(result)['completion_verified'])
        self.assertEqual((self.f.state/'loop-log.md').read_text().count('## iteration'),1)

    def test_partial_pass_from_mutating_check_is_never_committed(self):
        before=(self.f.state/'state.rec').read_bytes()
        (self.f.project/'check.py').write_text('from pathlib import Path\nPath("answer").write_bytes(b"changed")\n')
        result=self.close()
        self.assertEqual(result.returncode,4,result.stdout+result.stderr)
        self.assertIn('check-mutated-tree',result.stderr)
        self.assertIn('measured-close-incomplete',result.stderr)
        self.assertTrue((self.f.state/'store/pending').exists())
        self.assertNotIn('completion_verified',result.stdout)
        self.f.execute(self.f.view(),'recover')
        self.assertEqual((self.f.state/'state.rec').read_bytes(),before)
        self.assertNotIn('checks_pass=1',(self.f.state/'loop-log.md').read_text())

    def test_expired_close_cannot_gain_a_fresh_receipt_budget(self):
        result=self.close(env=dict(os.environ,GOAL_RUNNER_MONOTONIC_END='1'))
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertNotIn('"completion_verified": true',result.stdout)


if __name__=='__main__':unittest.main()
