"""Synthetic cohort calibration, including actual independent subprocess checks."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj)
    return obj


v=module('cohort_verifier',ROOT/'devtools/verify_delivery.py')
d,m=v.records,v.metrics
fixtures=module('cohort_native_fixtures',ROOT/'tests/test_native_eval_capture.py')
delivery=module('cohort_delivery_fixtures',ROOT/'tests/test_delivery_evaluation.py')


def configuration(**kwargs):
    value=dict(families=['small'],instances=1,seed_base=441001,model='fixture-model',effort='max',
               seconds=120,execution_seconds=100,calibration=True)
    value.update(kwargs)
    return value


class CohortPlan(unittest.TestCase):
    def test_changed_source_stops_before_creating_an_attempt(self):
        with tempfile.TemporaryDirectory(prefix='goal-cohort-source-') as tmp:
            root=Path(tmp)/'cohort';d.freeze(root,ROOT,None,configuration())
            path=root/'sources/current/SKILL.md';path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'source changed'):
                d.native_capture(root,1,'/root/cohort_1','fixture-parent',Path(tmp)/'sessions')
            self.assertFalse((root/'1').exists())

    def test_four_families_have_fixed_seeds_balanced_arms_and_runtime_only_sources(self):
        with tempfile.TemporaryDirectory(prefix='goal-cohort-plan-') as tmp:
            root=Path(tmp)/'cohort'
            d.freeze(root,ROOT,None,configuration(families=['small','medium','optimization','recovery'],instances=3))
            p=d.read(root/'protocol.json')
            self.assertEqual(p['scheduled_positions'],24)
            self.assertEqual(p['maximum_scheduled_wall_seconds'],24*120)
            self.assertEqual(len(p['cases']),12)
            for i,case in enumerate(p['cases']):
                arms=[r['variant'] for r in p['order'] if r['case']==case['id']]
                self.assertEqual(arms,['bare','current'] if i%2==0 else ['current','bare'])
            self.assertFalse((root/'sources/current/docs/evals').exists())
            self.assertTrue((root/'frozen/native-harness/devtools/native_eval_capture.py').is_file())
            with self.assertRaisesRegex(ValueError,'requires capture'):
                d.begin(root,1)
            with self.assertRaisesRegex(ValueError,'serial cohort'):
                d.native_capture(root,2,'/root/cohort_2','fixture-parent',Path(tmp)/'sessions')
            self.assertFalse((root/'2').exists())

    def test_invalid_budget_duplicate_family_and_instance_count_create_no_cohort(self):
        for bad in (dict(seconds=100,execution_seconds=100),dict(families=['small','small']),
                    dict(instances=0),dict(instances=True),dict(model=''),dict(seconds=601)):
            with self.subTest(bad=bad),tempfile.TemporaryDirectory() as tmp:
                output=Path(tmp)/'invalid'
                with self.assertRaises(ValueError):d.freeze(output,ROOT,None,configuration(**bad))
                self.assertFalse(output.exists())


class DeliveryMetrics(unittest.TestCase):
    def row(self,**kwargs):
        value=dict(qualified=True,seconds=10,tokens=None,money=None,currency=None,human_interventions=None)
        value.update(kwargs);return value

    def test_failed_attempt_costs_and_zero_deliveries_are_preserved(self):
        value=m.aggregate([self.row(),self.row(qualified=False,seconds=30)])
        self.assertEqual(value['success_rate'],.5)
        self.assertEqual(value['wall_seconds_per_qualified'],40)
        self.assertIsNone(value['tokens']);self.assertIsNone(value['money'])
        self.assertEqual(value['money_coverage'],{'observed':0,'attempts':2})
        self.assertIsNone(m.aggregate([self.row(qualified=False)])['wall_seconds_per_qualified'])

    def test_partial_accounting_and_mixed_currencies_never_become_free_or_comparable(self):
        rows=[self.row(tokens=20,money=.1,currency='USD'),self.row()]
        self.assertIsNone(m.aggregate(rows)['tokens'])
        self.assertIsNone(m.aggregate(rows)['money'])
        rows[1]=self.row(tokens=30,money=.2,currency='EUR')
        self.assertEqual(m.aggregate(rows)['tokens'],50)
        self.assertIsNone(m.aggregate(rows)['money'])
        self.assertIsNone(m.aggregate(rows)['currency'])

    def test_accounting_requires_same_session_model_whole_attempt_and_finite_values(self):
        good=dict(model='fixture-model',session='actual-session',tokens=20,money=.1,
                  currency='USD',source='synthetic provider receipt',scope='whole-attempt')
        self.assertEqual(m.accounting(good,'fixture-model','actual-session')['tokens'],20)
        for patch in ({'tokens':True},{'tokens':-1},{'money':float('nan')},{'scope':'goal-only'},
                      {'session':'other'},{'model':'other'},{'currency':None}):
            with self.subTest(patch=patch),self.assertRaises(RuntimeError):
                m.accounting(dict(good,**patch),'fixture-model','actual-session')

    def test_paired_gain_cannot_hide_a_lost_delivery_or_use_calibration_as_utility(self):
        cases=[dict(id='c'+str(i),family='small') for i in range(3)]
        protocol=dict(cases=cases,minimum_pairs=3,minimum_cost_gain=.2,evidence_kind='live-native')
        rows=[dict(self.row(seconds=20 if arm=='bare' else 5),case=case['id'],variant=arm)
              for case in cases for arm in ('bare','current')]
        self.assertTrue(m.cohort(rows,protocol)['paired']['current']['criteria_met'])
        protocol['evidence_kind']='calibration-fixture'
        self.assertFalse(m.cohort(rows,protocol)['paired']['current']['criteria_met'])
        protocol['evidence_kind']='live-native';rows[1]['qualified']=False
        result=m.cohort(rows,protocol)['paired']['current']
        self.assertEqual(result['delivery_losses'],1)
        self.assertFalse(result['criteria_met'])


class CapturedCohort(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp=tempfile.TemporaryDirectory(prefix='goal-captured-cohort-');cls.addClassCleanup(tmp.cleanup)
        cls.base=Path(tmp.name).resolve();cls.root=cls.base/'cohort';cls.sessions=cls.base/'sessions';cls.sessions.mkdir()
        d.freeze(cls.root,ROOT,None,configuration())
        cls.protocol=d.read(cls.root/'protocol.json')
        for planned in cls.protocol['order']:
            position=planned['position'];agent='/root/cohort_'+str(position)
            argv=[sys.executable,'-I',str(cls.root/'frozen/evaluate_delivery.py'),'capture',str(cls.root),str(position),
                  '--agent-path',agent,'--parent-thread','fixture-parent','--sessions-root',str(cls.sessions)]
            process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                folder=cls.root/str(position);work=folder/'work';until=time.monotonic()+15
                while not (folder/'prompt.txt').is_file():
                    if process.poll() is not None:
                        out,err=process.communicate();raise AssertionError(out+err)
                    if time.monotonic()>until:raise AssertionError('capture ready timed out')
                    time.sleep(.02)
                (work/'solution.py').write_text(delivery.GOOD)
                if planned['variant']!='bare':
                    ctl=cls.root/'sources/current/scripts/goal_ctl.sh'
                    def invoke(*args):
                        r=subprocess.run(['bash',str(ctl),*args,'--project',str(work)],capture_output=True,text=True,timeout=20)
                        if r.returncode:raise AssertionError(r.stdout+r.stderr)
                    invoke('init')
                    (work/'.goal/goal.md').write_text('# Goal\n\n## Objective\n\nImplement the interval task.\n\n## Acceptance criteria\n\n'
                        '- AC-1 | public checks | check: `python3 public.py` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
                    (work/'.goal/work-plan.md').write_text('- [x] T1 implementation | files=solution.py\n')
                    invoke('stamp','--auto')
                    invoke('close-iteration','--task','T1','--files','solution.py','--checks-from-verify','--receipt',
                           '--progress','yes','--exit-signal','yes','--adversarial','clear',
                           '--adversarial-note','Synthetic calibration: independent interval checks verify exact output and rejection semantics.')
                start=time.time()
                rows=fixtures.native_rows(start,start+.01,sid='cohort-fixture-'+str(position),agent=agent)
                time.sleep(.02)
                (cls.sessions/(str(position)+'.jsonl')).write_text(''.join(json.dumps(row)+'\n' for row in rows))
                out,err=process.communicate(timeout=20)
                if process.returncode:raise AssertionError(out+err)
                d.save(folder/'host-terminal.json',{'agents':[{'agent_name':agent,'agent_status':'completed'}]})
            finally:
                if process.poll() is None:process.kill();process.communicate()

    def test_real_collector_and_independent_graders_reconstruct_both_arms(self):
        result=v.verify(self.root)
        self.assertTrue(all(row['qualified'] for row in result['rows']))
        self.assertEqual(result['totals']['bare']['qualified'],1)
        self.assertEqual(result['totals']['current']['qualified'],1)
        self.assertIsNone(result['totals']['current']['money'])
        self.assertFalse(result['paired']['current']['eligible_for_cohort_decision'])

    def test_observed_model_drift_stops_the_next_dispatch(self):
        path=self.root/'1/capture/report.json';before=path.read_bytes();report=json.loads(before)
        try:
            report['settings_drift']=True;d.save(path,report)
            with self.assertRaisesRegex(ValueError,'model/effort drift'):
                d.native_capture(self.root,2,'/root/cohort_2','fixture-parent',self.sessions)
        finally:path.write_bytes(before)

    def test_accounting_receipts_cover_all_attempts_and_remain_bound_to_original_bytes(self):
        try:
            for position in (1,2):
                folder=self.root/str(position);capture=d.read(folder/'capture/report.json')
                receipt=self.base/'usage.json'
                d.save(receipt,dict(model='fixture-model',session=capture['session_id'],tokens=position*20,
                    money=position*.1,currency='USD',source='synthetic provider receipt',scope='whole-attempt'))
                d.attach_accounting(self.root,position,receipt,0)
            result=v.verify(self.root)
            self.assertEqual(result['totals']['bare']['tokens'],20)
            self.assertEqual(result['totals']['current']['money'],.2)
            self.assertEqual(result['totals']['current']['human_interventions'],0)
            path=self.root/'1/host-accounting.json';path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaisesRegex(RuntimeError,'accounting receipt changed'):v.verify(self.root)
        finally:
            for position in (1,2):
                for name in ('accounting.json','host-accounting.json'):
                    (self.root/str(position)/name).unlink(missing_ok=True)

    def test_posthoc_good_product_cannot_rescue_an_original_rejection(self):
        path=self.root/'1/capture/report.json';before=path.read_bytes();report=json.loads(before)
        report.update(qualified=False,reasons=['controlled original rejection'])
        try:
            d.save(path,report)
            self.assertFalse(v.verify(self.root)['rows'][0]['qualified'])
        finally:path.write_bytes(before)

    def test_changed_artifact_is_rejected_even_when_business_tests_still_pass(self):
        path=self.root/'1/work/solution.py';before=path.read_bytes()
        try:
            path.write_bytes(before+b'\n# later change\n')
            with self.assertRaisesRegex(RuntimeError,'artifact changed'):v.verify(self.root)
        finally:path.write_bytes(before)

    def test_original_runtime_observations_cannot_be_rewritten(self):
        folder=self.root/'2';receipt=d.read(folder/'capture/report.json')
        names=receipt['artifacts'][str(folder/'work')]['entries']['.goal']['entries']['evidence']['entries']['runtime']['entries']
        path=folder/'work/.goal/evidence/runtime'/next(iter(names));before=path.read_bytes()
        try:
            path.write_bytes(before+b'\n')
            with self.assertRaisesRegex(RuntimeError,'artifact changed'):v.verify(self.root)
        finally:path.write_bytes(before)

    def test_weakened_capture_check_is_not_accepted_as_original_acceptance(self):
        path=self.root/'1/capture-manifest.json';report_path=self.root/'1/capture/report.json'
        before,original=path.read_bytes(),report_path.read_bytes()
        declaration=json.loads(before);declaration['checks'][0]['argv']=['true']
        try:
            d.save(path,declaration);report=json.loads(original);report['manifest_sha256']=d.sha(path);d.save(report_path,report)
            with self.assertRaisesRegex(RuntimeError,'acceptance/workspace'):v.verify(self.root)
        finally:path.write_bytes(before);report_path.write_bytes(original)

    def test_missing_scheduled_trial_is_never_dropped(self):
        path=self.root/'2/capture/report.json';before=path.read_bytes()
        try:
            path.unlink()
            with self.assertRaisesRegex(RuntimeError,'missing scheduled'):v.verify(self.root)
        finally:path.write_bytes(before)


if __name__=='__main__':unittest.main()
