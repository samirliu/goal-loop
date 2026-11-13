"""Offline evaluator calibration. All native receipts here are synthetic fixtures."""
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
spec=importlib.util.spec_from_file_location('delivery_verifier',ROOT/'devtools/verify_delivery.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
d=v.records

GOOD='''def merge_ranges(ranges):
    out=[]
    for pair in ranges:
        if not isinstance(pair,(list,tuple)) or len(pair)!=2 or any(type(x) is not int for x in pair) or pair[0]>pair[1]:
            raise ValueError()
    for a,b in sorted(ranges):
        if a==b: continue
        if out and a<=out[-1][1]: out[-1][1]=max(out[-1][1],b)
        else: out.append([a,b])
    return out
'''


class DeliveryEvaluation(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);source=self.base/'source';source.mkdir();(source/'SKILL.md').write_text('fixture')
        self.root=self.base/'trial';d.freeze(self.root,source,source)
        self.protocol=d.read(self.root/'protocol.json')
        self.protocol['order']=self.protocol['order'][:1];self.protocol['scheduled_positions']=1
        d.save(self.root/'protocol.json',self.protocol)
        d.begin(self.root,1);self.folder=self.root/'1';self.manifest=d.read(self.folder/'manifest.json')
        (self.folder/'work/solution.py').write_text(GOOD)
        now=time.time()
        self.events=[dict(type='session_meta',payload={'id':'offline-fixture'}),
                     dict(type='turn_context',payload={'model':'gpt-6.1-sol','effort':'max'}),
                     dict(type='response_item',timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(now)),
                          payload=dict(type='message',role='assistant',phase='final_answer',content=[dict(type='output_text',text='offline final fixture')]))]
        self.write_events()
        command=[sys.executable,'-B',str(self.root/'frozen/grade.py'),'--project',str(self.folder/'work'),'--family','small','--seed','131101']
        checked=subprocess.run(command,capture_output=True,text=True,timeout=10)
        self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
        self.report=dict(session='offline-fixture',checks={'independent':dict(result=0,started=self.manifest['entry'],finished=time.monotonic(),stdout=checked.stdout)},
                         finished=time.monotonic(),events_sha256=d.sha(self.folder/'events.jsonl'),human_interventions=0)
        self.status=dict(agents=[dict(agent_name='/root/delivery_1',agent_status='completed')])
        self.write_report()

    def write_events(self):
        (self.folder/'events.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in self.events))

    def write_report(self):
        d.save(self.folder/'report.json',self.report);d.save(self.folder/'host-terminal.json',self.status)

    def test_correct_bare_delivery_needs_no_goal_loop_metadata(self):
        result=v.verify(self.root)
        self.assertTrue(result['rows'][0]['qualified'])
        self.assertFalse((self.folder/'work/.goal').exists())

    def test_reserved_validation_positions_keep_global_identity(self):
        protocol=copy.deepcopy(self.protocol);protocol['order'][0]['position']=7
        d.save(self.root/'protocol.json',protocol)
        d.begin(self.root,7)
        self.assertEqual(d.read(self.root/'7/manifest.json')['position'],7)

    def test_no_final_late_final_and_cancel_are_not_deliveries(self):
        for mutation in ('missing','late','cancelled'):
            events=copy.deepcopy(self.events)
            if mutation=='missing':events=events[:-1]
            if mutation=='late':events[-1]['timestamp']='2099-01-01T00:00:00Z'
            status='interrupted' if mutation=='cancelled' else 'completed'
            result=v.classify(self.protocol,self.manifest,self.report,events,status)
            self.assertFalse(result['qualified'],mutation)

    def test_false_green_bad_product_and_changed_grader_are_rejected(self):
        (self.folder/'work/solution.py').write_text('def merge_ranges(x): return []\n')
        with self.assertRaisesRegex(RuntimeError,'independent replay'):v.verify(self.root)
        (self.root/'frozen/grade.py').write_text('raise SystemExit(0)\n')
        with self.assertRaisesRegex(RuntimeError,'evaluator/task bytes'):v.verify(self.root)

    def test_deadline_model_source_and_missing_positions_are_rejected(self):
        report=copy.deepcopy(self.report);report['checks']['independent']['finished']=self.manifest['deadline']+1
        self.assertFalse(v.classify(self.protocol,self.manifest,report,self.events,'completed')['qualified'])
        events=copy.deepcopy(self.events);events[1]['payload']['model']='other'
        with self.assertRaisesRegex(RuntimeError,'model/effort'):v.classify(self.protocol,self.manifest,self.report,events,'completed')
        (self.root/'sources/current/SKILL.md').write_text('changed')
        with self.assertRaisesRegex(RuntimeError,'source changed'):v.verify(self.root)
        (self.root/'sources/current/SKILL.md').write_text('fixture')
        (self.folder/'report.json').unlink()
        with self.assertRaisesRegex(RuntimeError,'missing scheduled'):v.verify(self.root)

    def test_goal_loop_cannot_reuse_bare_acceptance_or_fake_gate(self):
        manifest=dict(self.manifest,variant='current')
        self.assertFalse(v.classify(self.protocol,manifest,self.report,self.events,'completed')['qualified'])
        report=copy.deepcopy(self.report)
        for name in ('audit','gate'):report['checks'][name]=dict(report['checks']['independent'])
        with self.assertRaisesRegex(RuntimeError,'missing original GO'):v.classify(self.protocol,manifest,report,self.events,'completed')

    def test_filter_does_not_save_thinking_or_credentials(self):
        source=self.base/'native.jsonl';target=self.base/'filtered.jsonl'
        source.write_text('\n'.join(json.dumps(x) for x in [
            dict(type='response_item',payload=dict(type='reasoning',text='private-thought')),
            dict(type='response_item',payload=dict(type='custom_tool_call_output',output='sk-'+'x'*25)),
            dict(type='event_msg',payload=dict(type='token_count',text='ignored'))]))
        d.transcript(source,target)
        self.assertNotIn('private-thought',target.read_text());self.assertNotIn('x'*25,target.read_text())


if __name__=='__main__':unittest.main()
