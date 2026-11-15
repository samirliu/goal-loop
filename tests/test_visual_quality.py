"""Visual quality cannot be replaced by mechanical greens or a bare clear.

Bound PASS rows below are controlled seat fixtures, not a claim that the tiny
test images are good architecture. Actual Hagia evidence is replayed separately.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import select
import subprocess
import struct
import sys
import tempfile
import time
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT/'scripts'


def module(name):
    spec = importlib.util.spec_from_file_location('visual_'+name, SCRIPTS/(name+'.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


quality, host = module('goal_quality'), module('goal_host')


def png(content):
    def chunk(kind, data):
        return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    rgb=hashlib.sha256(content).digest()[:3]
    raw=b''.join(b'\0'+rgb*32 for _ in range(24))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',32,24,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')


class VisualQuality(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='goal-visual-quality-')
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.state = self.project/'.goal'
        self.ctl('init')
        (self.project/'answer').write_text('delivered\n')
        (self.project/'check.py').write_text('from pathlib import Path\nraise SystemExit(0 if Path("answer").read_text()=="delivered\\n" else 1)\n')
        (self.project/'good.png').write_bytes(png(b'controlled good anchor'))
        (self.project/'bad.png').write_bytes(png(b'controlled different anchor'))
        (self.state/'work-plan.md').write_text('- [x] T1 | deliver answer | files=answer\n')

    def ctl(self, *arguments, expected=0, input=None):
        result = subprocess.run(['bash', str(SCRIPTS/'goal_ctl.sh'), *arguments, '--project', str(self.project)],
                                input=input, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout+result.stderr)
        return result

    def author(self, objective='Build a photorealistic reconstruction', visual=True):
        self.state.joinpath('goal.md').write_text('# Goal\n\n## Objective\n\n'+objective+'\n\n'
            + ('quality: visual AC-2 views=exterior,gallery\n\n' if visual else '')
            + '## Acceptance criteria\n\n- AC-1 | delivered | check: `python3 check.py` | expected: exit=0\n'
            + ('- AC-2 | compare all promised views to reference anchors; no missing masses, blocked views or exposed interiors | '
               'check: `python3 check.py` | calib: good=good.png bad=bad.png | expected: judged\n' if visual else '')
            + '\n## Approval\n\napproved: PENDING\n')

    def image(self, name, content):
        path = self.state/'evidence'/name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(png(content))
        return dict(artifact=path.relative_to(self.project).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    def evidence(self):
        value = dict(version=1, views=dict(exterior=self.image('exterior.png', b'controlled exterior'),
            gallery=self.image('gallery.png', b'controlled gallery')), findings=[], summary='Controlled review fixture; no real image quality claim.')
        self.record = self.state/'evidence/quality-review.json'
        self.record.write_text(json.dumps(value))
        return value

    def bind(self, verdict='PASS'):
        digest = subprocess.run(['bash', str(SCRIPTS/'goal_gate.sh'), '--digest', '--project', str(self.project)],
                                capture_output=True, text=True, check=True).stdout.strip()
        def row(identity, status, path):
            evidence = 'PROBE=read REASON=controlled unavailable seat' if status=='UNVERIFIABLE' else (
                'controlled seat fixture artifact: '+path.relative_to(self.project).as_posix()+' digest: '+hashlib.sha256(path.read_bytes()).hexdigest())
            return '|'.join([identity,status,'1',digest,'controlled-seat',evidence])+'\n'
        rows = row('AC-2',verdict,self.record)
        for suffix,status in [('good','PASS'),('bad','FAIL')]:
            rows += row('AC-2#'+suffix,status,self.project/(suffix+'.png'))
        self.ctl('bind', input=rows)

    def close(self, expected=0, unverifiable=0):
        return self.ctl('close-iteration', '--task', 'T1', '--files', 'answer', '--checks-pass', '2',
            '--checks-fail', '0', '--checks-unverifiable', str(unverifiable), '--progress', 'yes', '--exit-signal', 'yes',
            '--adversarial', 'clear', '--adversarial-note', 'Controller clear cannot override cold quality findings.', expected=expected)

    def prepared(self):
        self.author(); self.ctl('stamp', '--auto'); value=self.evidence();return value

    def test_original_visual_intent_cannot_stamp_an_all_mechanical_contract(self):
        self.author('用 THREE.JS 构建尽可能逼真的圣索菲亚大教堂，并交付可信的自我验证系统。', False)
        before={p.relative_to(self.state):p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        result=self.ctl('stamp','--auto',expected=2)
        self.assertIn('quality-contract-required', result.stderr)
        self.assertEqual(before,{p.relative_to(self.state):p.read_bytes() for p in self.state.rglob('*') if p.is_file()})

    def test_original_host_request_survives_rewording_and_prompt_reentry(self):
        prompt='/goal-loop Build a photorealistic reconstruction and trustworthy verifier'
        payload=dict(hook_event_name='UserPromptSubmit', session_id='visual-session', cwd=str(self.project), prompt=prompt)
        host.hook(payload, 'claude', str(self.project))
        host.hook(dict(payload,prompt='continue'), 'claude', str(self.project))
        host.begin(self.project,'claude','visual-session',120)
        self.author('deliver a page with passing tests',False)
        result=self.ctl('stamp','--auto',expected=2)
        self.assertIn('quality-contract-required',result.stderr)
        view=json.loads(self.ctl('context','--auto').stdout)
        self.assertEqual(view['quality']['original_requests'][0]['text'],prompt)
        self.assertEqual(view['next'],'repair-quality-contract')
        self.assertNotIn('stamp',view.get('submissions',{}))

    def test_deterministic_threejs_maintenance_keeps_fast_lane(self):
        self.author('Fix the THREE.JS import and add a deterministic regression test',False)
        self.ctl('stamp','--auto')
        view=json.loads(self.ctl('context','--auto').stdout)
        self.assertNotIn('quality',view)
        self.assertIsNotNone(view['close_input']['measured_template'])

    def test_manual_cli_captures_original_request_and_cannot_replace_it_on_resume(self):
        prompt='Build a photorealistic reconstruction and trustworthy verifier'
        command=[sys.executable,'-I',str(SCRIPTS/'goal_host.py'),'begin',str(self.project),'claude','manual-session','120','--request-stdin']
        result=subprocess.run(command,input=prompt,text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        before=(self.state/'runner.json').read_bytes()
        changed=subprocess.run(command,input='deliver only passing tests',text=True,capture_output=True,timeout=15)
        self.assertEqual(changed.returncode,4);self.assertIn('original request changed',changed.stderr)
        self.assertEqual((self.state/'runner.json').read_bytes(),before)
        host.hook(dict(hook_event_name='UserPromptSubmit',session_id='manual-session',cwd=str(self.project),prompt='continue'), 'claude',str(self.project))
        host.begin(self.project,'claude','manual-session',120)
        self.author('deliver a page with passing tests',False)
        self.assertIn('quality-contract-required',self.ctl('stamp','--auto',expected=2).stderr)
        self.assertEqual(quality.context(self.project)['original_requests'][0]['text'],prompt)

    def test_mentioning_photorealistic_classifier_is_not_a_visual_deliverable(self):
        self.author('Repair the photorealistic classifier and test its false positive',False)
        self.ctl('stamp','--auto')
        self.assertFalse(quality.context(self.project)['required'])

    def test_maintaining_a_3d_scene_module_is_not_a_new_visual_delivery(self):
        self.author('修复 3D 场景模块的类型错误，并增加单元测试。',False)
        self.ctl('stamp','--auto')
        self.assertFalse(quality.context(self.project)['required'])

    def test_open_request_pipe_cannot_hang_entry_or_start_a_new_budget(self):
        command=[sys.executable,'-I',str(SCRIPTS/'goal_host.py'),'begin',str(self.project),'claude','open-pipe','.15','--request-stdin']
        child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            child.stdin.write(b'Build a photorealistic reconstruction');child.stdin.flush()
            child.wait(timeout=3)
            self.assertEqual(child.returncode,4)
            self.assertIn(b'request stdin timed out',child.stderr.read())
            self.assertFalse((self.state/'runner.json').exists())
        finally:
            if child.poll() is None:child.kill();child.wait()
            child.stdin.close();child.stdout.close();child.stderr.close()

    def test_request_reading_time_is_part_of_the_first_manual_budget(self):
        wrapper='''import importlib.util,sys
spec=importlib.util.spec_from_file_location('actual_entry',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
original=m.request_stdin
def ready(seconds):
 print('REQUEST_READY',file=sys.stderr,flush=True)
 return original(seconds)
m.request_stdin=ready
sys.argv=sys.argv[1:]
m.main()
'''
        command=[sys.executable,'-I','-c',wrapper,str(SCRIPTS/'goal_host.py'),'begin',str(self.project),'claude','delayed-input','5','--request-stdin']
        child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            self.assertTrue(select.select([child.stderr],[],[],3)[0]);self.assertEqual(child.stderr.readline(),b'REQUEST_READY\n')
            time.sleep(.2);sent=time.time()
            output,error=child.communicate(b'Build a photorealistic reconstruction',timeout=5)
            self.assertEqual(child.returncode,0,error)
            value=json.loads((self.state/'runner.json').read_bytes())
            self.assertLess(value['origin']['epoch'],sent-.1)
        finally:
            if child.poll() is None:child.kill();child.wait()

    def test_quality_declaration_in_a_comment_does_not_change_nonvisual_judgment(self):
        self.author('deliver a checked answer')
        path=self.state/'goal.md';path.write_text(path.read_text().replace('quality: visual AC-2 views=exterior,gallery',
            '<!--\nquality: visual AC-2 views=exterior,gallery\n-->').replace('\n## Approval',
            '\n- AC-3 | checked answer | check: `python3 check.py` | expected: exit=0\n\n## Approval'))
        self.ctl('stamp','--auto');self.evidence();self.bind('UNVERIFIABLE')
        # One of three criteria may use the existing UNVERIFIABLE allowance;
        # comments must not silently turn it into a mandatory visual floor.
        result=self.close(unverifiable=1)
        self.assertIn('GATE: GO ',result.stdout)

    def test_incomplete_visual_review_cannot_advance_intermediate_quality_watermark(self):
        self.author();path=self.state/'goal.md'
        path.write_text(path.read_text().replace('quality: visual', 'objective: maximize AC-1\n\nquality: visual').replace(
            'check: `python3 check.py` | expected: exit=0','check: `python3 score.py` | baseline: abs | expected: maximize'))
        (self.project/'score.py').write_text('print(1)\n')
        self.ctl('stamp','--auto');value=self.evidence();value['views'].pop('gallery');self.record.write_text(json.dumps(value));self.bind()
        self.ctl('close-iteration','--task','T1','--files','answer','--checks-pass','2','--checks-fail','0',
            '--checks-unverifiable','0','--progress','yes','--exit-signal','no','--score','1','--strategy','observed',expected=2)
        result=subprocess.run(['bash',str(SCRIPTS/'goal_gate.sh'),'--quality','--project',str(self.project)],capture_output=True,text=True)
        self.assertEqual(result.returncode,2,result.stdout+result.stderr);self.assertIn('quality-review-invalid',result.stderr)
        self.assertIn('best_score=none\n',(self.state/'state.rec').read_text())

    def test_additional_cold_review_observations_are_preserved_and_accepted(self):
        value=self.prepared();value.update(verdict='PASS',completion_eligible=True,validation_limits=['Controlled test only'])
        value['views']['gallery']['observations']=['Controlled independent seat fixture']
        self.record.write_text(json.dumps(value));self.bind()
        self.assertIn('GATE: GO ',self.close().stdout)

    def test_recorded_fail_cannot_be_hidden_by_empty_findings_and_pass_binding(self):
        value=self.prepared();value.update(verdict='FAIL',completion_eligible=False)
        self.record.write_text(json.dumps(value));self.bind()
        self.assertIn('quality-review-conflict',self.close(expected=2).stderr)

    def test_view_fail_cannot_be_hidden_by_overall_pass_and_empty_findings(self):
        value=self.prepared();value['verdict']='PASS';value['views']['gallery']['verdict']='FAIL'
        self.record.write_text(json.dumps(value));self.bind()
        self.assertIn('declared view did not pass: gallery',self.close(expected=2).stderr)

    def test_view_unverifiable_cannot_be_hidden_by_overall_pass(self):
        value=self.prepared();value['verdict']='PASS';value['views']['gallery']['verdict']='UNVERIFIABLE'
        self.record.write_text(json.dumps(value));self.bind()
        self.assertIn('declared view did not pass: gallery',self.close(expected=2).stderr)

    def test_removing_a_promised_view_after_stamp_is_contract_tampering(self):
        self.prepared();path=self.state/'goal.md';path.write_text(path.read_text().replace('views=exterior,gallery','views=exterior'))
        result=subprocess.run(['bash',str(SCRIPTS/'goal_gate.sh'),'--check','--project',str(self.project)],capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertIn('contract-tampered',result.stderr)

    def test_proxy_and_identical_calibration_anchors_do_not_qualify(self):
        self.author()
        path=self.state/'goal.md';path.write_text(path.read_text().replace('expected: judged','expected: exit=0').replace('calib: good=good.png bad=bad.png | ',''))
        self.assertIn('quality AC must be judged',self.ctl('stamp','--auto',expected=2).stderr)
        self.author();(self.project/'bad.png').write_bytes((self.project/'good.png').read_bytes())
        self.assertIn('identical bytes',self.ctl('stamp','--auto',expected=2).stderr)

    def test_bound_complete_review_can_complete_with_original_gate(self):
        self.prepared();self.bind();result=self.close()
        self.assertIn('GATE: GO ',result.stdout)
        self.assertEqual(subprocess.run(['bash',str(SCRIPTS/'goal_audit.sh'),'--project',str(self.project)],capture_output=True).returncode,0)

    def test_known_core_defect_blocks_even_with_all_pass_rows_and_clear(self):
        value=self.prepared();value['findings']=['Exterior mass below the semi-domes is not modelled; gold interiors are exposed.']
        self.record.write_text(json.dumps(value));self.bind()
        self.assertIn('quality-open-findings',self.close(expected=2).stderr)

    def test_missing_gallery_is_not_hidden_by_two_other_green_views(self):
        value=self.prepared();value['views'].pop('gallery');self.record.write_text(json.dumps(value));self.bind()
        self.assertIn('every declared view',self.close(expected=2).stderr)

    def test_ignored_screenshot_change_invalidates_otherwise_bound_review(self):
        value=self.prepared();self.bind();self.image('gallery.png',b'changed after review')
        self.assertIn('changed view evidence gallery',self.close(expected=2).stderr)

    def test_same_image_copied_under_another_filename_is_not_view_coverage(self):
        value=self.prepared();value['views']['gallery']=self.image('gallery.png',b'controlled exterior')
        self.record.write_text(json.dumps(value));self.bind()
        self.assertIn('one image cannot stand in',self.close(expected=2).stderr)

    def test_review_json_change_cannot_reuse_the_seat_pass(self):
        self.prepared();self.bind();self.record.write_text(self.record.read_text()+' ')
        self.assertIn('verdict-unbound:AC-2',self.close(expected=2).stderr)

    def test_visual_judgment_cannot_be_waived_as_unverifiable(self):
        self.prepared();self.bind('UNVERIFIABLE')
        self.assertIn('quality-judgment-required:AC-2',self.close(expected=2,unverifiable=1).stderr)

    def test_original_objective_and_anchor_bytes_are_frozen(self):
        self.prepared();path=self.state/'goal.md';original=path.read_text()
        path.write_text(original.replace('Build a photorealistic reconstruction','deliver a page'))
        result=subprocess.run(['bash',str(SCRIPTS/'goal_gate.sh'),'--check','--project',str(self.project)],capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertIn('check-script-tampered',result.stderr)
        path.write_text(original);(self.project/'good.png').write_bytes(b'changed anchor')
        result=subprocess.run(['bash',str(SCRIPTS/'goal_gate.sh'),'--check','--project',str(self.project)],capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertIn('check-script-tampered',result.stderr)

    def test_bad_declaration_remains_actionable_in_context(self):
        self.author();path=self.state/'goal.md';path.write_text(path.read_text().replace('exterior,gallery','exterior,exterior'))
        view=json.loads(self.ctl('context','--auto').stdout)
        self.assertIn('unique named views',view['quality']['error']);self.assertNotIn('stamp',view.get('submissions',{}))

    def test_quality_evidence_cannot_escape_project_via_symlink(self):
        value=self.prepared();source=self.state/'evidence/gallery.png';source.unlink();source.symlink_to(self.project/'good.png')
        value['views']['gallery']['sha256']=hashlib.sha256((self.project/'good.png').read_bytes()).hexdigest()
        self.record.write_text(json.dumps(value));self.bind()
        self.assertIn('symlink refused',self.close(expected=2).stderr)


if __name__=='__main__':
    unittest.main()
