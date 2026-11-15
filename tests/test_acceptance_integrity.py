"""Acceptance requirements cannot disappear between declaration and completion.

Seat rows are controlled protocol fixtures, never claimed independent grades.
Every outcome below goes through the production controller and Gate.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'


class AcceptanceIntegrity(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='goal-acceptance-integrity-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root/'.goal'
        self.ctl('init')
        (self.root/'answer.txt').write_text('ready\n')
        (self.root/'good.txt').write_text('known good\n')
        (self.root/'bad.txt').write_text('known bad\n')
        (self.state/'work-plan.md').write_text('- [x] T1 | deliver answer | files=answer.txt\n')

    def entry(self, script, *args, expected=0, input=None):
        result = subprocess.run(['bash', str(SCRIPTS/script), *args, '--project', str(self.root)],
                                input=input, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout+result.stderr)
        return result

    def ctl(self, *args, **kw):
        return self.entry('goal_ctl.sh', *args, **kw)

    def gate(self, *args, **kw):
        return self.entry('goal_gate.sh', *args, **kw)

    def author(self, rows=None, extra='', heading='Objective'):
        self.goal = self.state/'goal.md'
        rows = rows or ['- AC-1 | report present | check: `test -s answer.txt` | expected: exit=0']
        self.goal.write_text('# Goal\n\n## '+heading+'\n\nDeliver the complete original report.\n\n'
                             +extra+'\n## Acceptance criteria\n\n'+'\n'.join(rows)
                             +'\n\n## Approval\n\napproved: PENDING\n')

    def judged(self, identity='AC-1', bad='bad.txt', external=False, window=3600):
        return '- '+identity+' | original report correctness | check: `cat answer.txt` | '+(
            'external: `python3 external.py` | window: '+str(window)+' | ' if external else ''
        )+'calib: good=good.txt bad='+bad+' | expected: judged'

    def sha(self, path):
        return hashlib.sha256((self.root/path).read_bytes()).hexdigest()

    def bind(self, identity='AC-1', status='PASS', bad='bad.txt', evidence=None, initial=()):
        digest = self.gate('--digest').stdout.strip()
        iteration = int(dict(line.split('=',1) for line in (self.state/'state.rec').read_text().splitlines())['iteration'])+1
        def row(label, verdict, path, override=None):
            text = override or ('PROBE=read REASON=controlled unavailable judgment' if verdict=='UNVERIFIABLE' else
                                'controlled seat fixture artifact: '+path+' digest: '+self.sha(path))
            return '|'.join([label,verdict,str(iteration),digest,'controlled-seat-fixture',text])+'\n'
        rows = ''.join(row(*item) for item in initial)+row(identity,status,'answer.txt')
        if status=='PASS':
            rows += ''.join(row(identity+'#'+side, verdict, path, (evidence or {}).get(side))
                            for side,verdict,path in [('good','PASS','good.txt'),('bad','FAIL',bad)])
        self.ctl('bind',input=rows)

    def close(self, expected=0, passes=1, unverified=0, score=None):
        args = ['close-iteration','--task','T1','--files','answer.txt','--checks-pass',str(passes),
                '--checks-fail','0','--checks-unverifiable',str(unverified),'--progress','yes',
                '--exit-signal','yes','--adversarial','clear','--adversarial-note',
                'Controlled protocol fixture; clear cannot waive declared requirements.','--receipt']
        if score is not None:
            args += ['--score',str(score),'--strategy','observed']
        return self.ctl(*args,expected=expected)

    def external(self, status=0):
        (self.state/'evidence/status').write_text(str(status))
        (self.root/'external.py').write_text("from pathlib import Path\n"
            "p=Path('.goal/evidence/calls')\np.write_text(str(int(p.read_text())+1) if p.exists() else '1')\n"
            "raise SystemExit(int(Path('.goal/evidence/status').read_text()))\n")

    def test_ordinary_objective_is_frozen_before_any_visual_classification(self):
        self.author();self.ctl('stamp','--auto')
        self.goal.write_text(self.goal.read_text().replace('complete original report','placeholder'))
        self.assertIn('check-script-tampered',self.close(expected=2).stderr)

    def test_alternate_goal_heading_preserves_the_same_intent_binding(self):
        self.author(heading='Goal');self.ctl('stamp','--auto')
        self.goal.write_text(self.goal.read_text().replace('complete original report','placeholder'))
        self.assertIn('check-script-tampered',self.close(expected=2).stderr)

    def test_nonvisual_captured_request_cannot_be_rewritten_with_a_new_checksum(self):
        result = subprocess.run([sys.executable,'-I',str(SCRIPTS/'goal_host.py'),'begin',str(self.root),
                                 'claude','controlled-request-fixture','120','--request-stdin'],
                                input='Generate a complete regional report from the supplied data.',
                                text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.author();self.ctl('stamp','--auto')
        receipt = next((self.state/'evidence/host').glob('session-*.json'))
        envelope = json.loads(receipt.read_bytes());envelope['payload']['request']='Generate a placeholder.'
        encoded = json.dumps(envelope['payload'],sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
        envelope['sha256']=hashlib.sha256(encoded).hexdigest();receipt.write_text(json.dumps(envelope))
        self.assertIn('check-script-tampered',self.close(expected=2).stderr)

    def test_valid_calibrated_nonvisual_judgment_still_gets_original_receipt(self):
        self.author([self.judged()]);self.ctl('stamp','--auto');self.bind()
        self.assertIn('"completion_verified":true',self.close().stdout.replace(' ',''))

    def test_identical_anchor_bytes_refuse_stamp_without_ledger_mutation(self):
        self.author([self.judged()]);(self.root/'bad.txt').write_bytes((self.root/'good.txt').read_bytes())
        head = (self.state/'store/commits/current').read_bytes()
        self.assertIn('calibration-identical',self.ctl('stamp','--auto',expected=2).stderr)
        self.assertEqual(head,(self.state/'store/commits/current').read_bytes())
        self.assertFalse((self.state/'store/pending').exists())
        view = json.loads(self.ctl('context','--auto').stdout)
        self.assertEqual(view['next'],'repair-acceptance-contract')
        self.assertNotIn('stamp',view.get('submissions',{}))

    def test_regrading_a_changed_anchor_does_not_move_the_frozen_yardstick(self):
        self.author([self.judged()]);self.ctl('stamp','--auto')
        (self.root/'bad.txt').write_text('different unapproved anchor\n');self.bind()
        self.assertIn('check-script-tampered',self.close(expected=2).stderr)

    def test_calibration_symlink_is_not_an_in_tree_frozen_anchor(self):
        self.author([self.judged()]);(self.root/'bad.txt').unlink()
        (self.root/'bad.txt').symlink_to(self.root/'answer.txt')
        self.assertIn('symlink refused',self.ctl('stamp','--auto',expected=2).stderr)

    def test_quoted_anchor_name_cannot_substitute_for_hash_binding(self):
        self.author([self.judged()]);self.ctl('stamp','--auto');self.bind(evidence={'good':'observed good.txt'})
        self.assertIn('calibration-unbound:AC-1/good',self.close(expected=2).stderr)

    def test_incorrect_anchor_hash_cannot_be_hidden_by_correct_name(self):
        self.author([self.judged()]);self.ctl('stamp','--auto')
        self.bind(evidence={'bad':'artifact: bad.txt digest: '+'0'*64})
        self.assertIn('calibration-unbound:AC-1/bad',self.close(expected=2).stderr)

    def test_anchor_binding_requires_full_hash_not_a_short_prefix(self):
        self.author([self.judged()]);self.ctl('stamp','--auto')
        self.bind(evidence={'good':'artifact: good.txt digest: '+self.sha('good.txt')[:8]})
        self.assertIn('calibration-unbound:AC-1/good',self.close(expected=2).stderr)

    def test_unrelated_artifact_cannot_calibrate_a_named_anchor(self):
        self.author([self.judged()]);self.ctl('stamp','--auto')
        self.bind(evidence={'good':'good.txt observed; artifact: answer.txt digest: '+self.sha('answer.txt')})
        self.assertIn('calibration-unbound:AC-1/good',self.close(expected=2).stderr)

    def test_conflicting_bad_anchor_grades_are_not_resolved_by_last_row(self):
        self.author([self.judged()]);self.ctl('stamp','--auto')
        self.bind(initial=[('AC-1#bad','PASS','bad.txt')])
        self.assertIn('verdict-conflict:AC-1#bad',self.close(expected=2).stderr)

    def test_conflicting_good_anchor_grades_are_not_resolved_by_last_row(self):
        self.author([self.judged()]);self.ctl('stamp','--auto')
        self.bind(initial=[('AC-1#good','FAIL','good.txt')])
        self.assertIn('verdict-conflict:AC-1#good',self.close(expected=2).stderr)

    def test_overlapping_fixture_names_use_exact_binding_not_substring_exclusion(self):
        (self.root/'bad-good.txt').write_text('known bad\n')
        self.author([self.judged(bad='bad-good.txt')]);self.ctl('stamp','--auto');self.bind(bad='bad-good.txt')
        self.close()

    def objective(self, waive=False):
        self.author(['- AC-1 | speed | check: `echo 10` | expected: maximize',
                     '- AC-2 | local floor | check: `test -s answer.txt` | expected: exit=0',self.judged('AC-3')],
                    extra='objective: maximize AC-1\n'+('horizon-waived: controlled single metric fixture\n' if waive else ''))
        self.ctl('stamp','--auto')

    def test_unverifiable_quota_cannot_waive_the_declared_optimization_horizon(self):
        self.objective();self.bind('AC-3','UNVERIFIABLE')
        self.assertIn('horizon-unverified',self.close(expected=2,passes=2,unverified=1,score=10).stderr)
        self.assertIn('best_score=none\n',(self.state/'state.rec').read_text())

    def test_calibrated_pass_horizon_can_qualify_and_deliver_an_objective(self):
        self.objective();self.bind('AC-3');self.close(passes=3,score=10)
        self.assertIn('best_score=10\n',(self.state/'state.rec').read_text())

    def test_explicit_frozen_horizon_waiver_preserves_the_ordinary_quota(self):
        self.objective(waive=True);self.bind('AC-3','UNVERIFIABLE');self.close(passes=2,unverified=1,score=10)

    def test_judged_external_pending_is_actually_measured_and_never_go(self):
        self.external(75);self.author([self.judged(external=True)]);self.ctl('stamp','--auto');self.bind()
        self.assertIn('deferred-pending:AC-1',self.close(expected=2).stderr)
        self.assertEqual((self.state/'evidence/calls').read_text(),'1')
        self.assertIn('false_completes=0\n',(self.state/'state.rec').read_text())

    def test_judged_external_failure_is_decisive(self):
        self.external(1);self.author([self.judged(external=True)]);self.ctl('stamp','--auto');self.bind()
        self.assertIn('open-FAIL:AC-1',self.close(expected=2).stderr)

    def test_judged_external_pass_can_go_and_reuses_cache_for_same_artifact(self):
        self.external();self.author([self.judged(external=True)]);self.ctl('stamp','--auto');self.bind();self.close()
        self.gate('--check');self.assertEqual((self.state/'evidence/calls').read_text(),'1')

    def test_verify_reports_external_state_without_fabricating_a_judged_pass(self):
        self.external(75);self.author([self.judged(external=True)]);self.ctl('stamp','--auto')
        result = self.gate('--verify')
        self.assertIn('VERIFY AC-1|SKIP|judged',result.stdout)
        self.assertIn('EXTERNAL AC-1|DEFERRED|',result.stdout)
        self.assertIn('pending=1',result.stdout)
        self.assertNotIn('VERIFY AC-1|PASS|',result.stdout)

    def test_zero_window_always_requeries_the_external_source(self):
        self.external();self.author([self.judged(external=True,window=0)]);self.ctl('stamp','--auto')
        self.gate('--verify');self.gate('--verify')
        self.assertEqual((self.state/'evidence/calls').read_text(),'2')

    def external_floor(self):
        self.external();self.author(['- AC-1 | reviewed report version | check: `test -s answer.txt` | '
                                    'external: `python3 external.py` | window: 3600 | expected: exit=0'])
        self.ctl('stamp','--auto')

    def test_external_approval_for_previous_artifact_cannot_approve_new_bytes(self):
        self.external_floor();self.close()
        (self.root/'answer.txt').write_text('new version awaiting approval\n')
        (self.state/'evidence/status').write_text('75')
        self.assertIn('deferred-pending:AC-1',self.close(expected=2).stderr)
        self.assertEqual((self.state/'evidence/calls').read_text(),'2')

    def test_unbound_legacy_external_cache_is_requeried(self):
        self.external_floor();(self.state/'evidence/status').write_text('75')
        (self.state/'evidence/deferred.rec').write_text('AC-1|PASS|'+str(int(time.time()))+'|legacy\n')
        self.assertIn('deferred-pending:AC-1',self.close(expected=2).stderr)

    def test_other_project_cannot_reuse_a_same_bytes_external_approval(self):
        self.external_floor();self.close()
        other = AcceptanceIntegrity();other.setUp();self.addCleanup(other.doCleanups)
        other.external_floor()
        (other.state/'evidence/deferred.rec').write_bytes((self.state/'evidence/deferred.rec').read_bytes())
        (other.state/'evidence/status').write_text('75')
        self.assertIn('deferred-pending:AC-1',other.close(expected=2).stderr)

    def test_future_external_cache_does_not_grant_an_indefinite_pass(self):
        self.external_floor();self.close()
        cache = self.state/'evidence/deferred.rec';columns=cache.read_text().strip().split('|')
        columns[2]=str(int(time.time())+3600);cache.write_text('|'.join(columns)+'\n')
        (self.state/'evidence/status').write_text('75')
        self.assertIn('deferred-pending:AC-1',self.gate('--check',expected=2).stderr)

    def test_replacing_external_checker_cannot_change_a_frozen_requirement(self):
        self.external_floor();(self.root/'external.py').write_text('raise SystemExit(0)\n')
        self.assertIn('check-script-tampered',self.close(expected=2).stderr)

    def test_mjs_instrument_bytes_are_frozen_like_js(self):
        (self.root/'check.mjs').write_text('exit 1\n')
        self.author(['- AC-1 | floor | check: `bash check.mjs` | expected: exit=0']);self.ctl('stamp','--auto')
        (self.root/'check.mjs').write_text('exit 0\n')
        self.assertIn('check-script-tampered',self.close(expected=2).stderr)

    def test_quoted_script_path_with_spaces_cannot_bypass_freeze(self):
        (self.root/'check script.sh').write_text('exit 1\n')
        self.author(['- AC-1 | floor | check: `bash "check script.sh"` | expected: exit=0'])
        self.ctl('stamp','--auto');(self.root/'check script.sh').write_text('exit 0\n')
        self.assertIn('check-script-tampered',self.close(expected=2).stderr)

    def test_bad_shell_quoting_refuses_stamp_before_mutation(self):
        self.author(['- AC-1 | floor | check: `bash "broken.sh` | expected: exit=0'])
        head=(self.state/'store/commits/current').read_bytes()
        self.assertIn('invalid instrument command',self.ctl('stamp','--auto',expected=2).stderr)
        self.assertEqual(head,(self.state/'store/commits/current').read_bytes())
        self.assertFalse((self.state/'store/pending').exists())

    def metric(self, value, expected, token='metric', regex='value=(.*)'):
        (self.root/'value.txt').write_text('value='+value+'\n')
        self.author(['- AC-1 | measured value | check: `cat value.txt` | '+token+': `'+regex+'` | expected: '+expected])
        self.ctl('stamp','--auto')

    def test_fractional_capture_is_not_promoted_from_point_five_to_five(self):
        self.metric('.5','>=1');self.assertIn('observed=0.5',self.gate('--verify',expected=2).stdout)

    def test_fractional_capture_can_pass_its_actual_floor(self):
        self.metric('.5','>=0.5');self.close()

    def test_negative_fractional_capture_preserves_sign_and_magnitude(self):
        self.metric('-.5','<=-0.4');self.assertIn('observed=-0.5',self.gate('--verify').stdout)

    def test_scientific_capture_is_reported_unsupported_instead_of_truncated(self):
        self.metric('1e3','<=2');self.assertIn('BROKEN',self.gate('--verify',expected=2).stdout)

    def test_nonnumeric_capture_does_not_become_a_numeric_prefix(self):
        self.metric('1junk','<=2');self.assertIn('BROKEN',self.gate('--verify',expected=2).stdout)

    def test_negative_standard_deviation_breaks_the_instrument(self):
        self.metric('-100','>=0','sd');self.assertIn('negative standard deviation',self.gate('--verify',expected=2).stdout)

    def test_negative_variance_breaks_the_instrument(self):
        self.metric('-100','>=0','var');self.assertIn('negative variance',self.gate('--verify',expected=2).stdout)

    def test_small_spread_notation_does_not_expand_the_noise_band(self):
        (self.root/'value.txt').write_text('score=10\nspread=0.0000000001\n')
        self.author(['- AC-1 | speed | check: `cat value.txt` | metric: `score=([0-9]+)` | '
                     'sd: `spread=([0-9.]+)` | expected: maximize'],
                    extra='objective: maximize AC-1\nhorizon-waived: controlled single metric fixture\n')
        self.ctl('stamp','--auto');self.close(score=10)
        (self.root/'value.txt').write_text('score=9\nspread=0.0000000001\n')
        self.assertIn('score-regressed',self.close(expected=2,score=9).stderr)


if __name__ == '__main__':
    unittest.main()
