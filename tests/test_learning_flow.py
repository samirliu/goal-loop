"""Production-path counterexamples for dependency reuse and learned routing."""
import importlib.util
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('learning_fixtures', Path(__file__).with_name('test_crew.py'))
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)
crew, ROOT = fixtures.crew, fixtures.ROOT


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


context = module('learning_context', ROOT / 'scripts/goal_context.py')
host = module('learning_host', ROOT / 'scripts/goal_host.py')
policies = module('learning_policy_fixture', ROOT / 'tests/test_evolve.py')


class LearningFlow(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.Crew()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_changed_adopted_parent_cannot_authorize_child(self):
        f = self.fixture
        f.write_graph(deps=True)
        wave = f.fresh('crew', 'stale-parent')
        wave.event('T1', 'dispatch')
        f.work(wave, 'T1')
        (f.project / 'a.out').write_text('changed after adoption')
        with self.assertRaisesRegex(ValueError, 'dependency evidence is stale'):
            wave.event('T2', 'dispatch')

    def test_installed_entry_cannot_launch_harness(self):
        f = self.fixture
        marker = f.project / 'invoked'
        fake = f.project / 'fake-cli'
        fake.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\n')
        fake.chmod(0o755)
        result = subprocess.run(['bash', str(ROOT / 'scripts/goal_loop.sh'), '--continue',
                                 '--max-iterations=1', '--wallclock=3', '--project', str(f.project)],
                                env=dict(os.environ, CLAUDE_BIN=str(fake)), capture_output=True, timeout=10)
        self.assertFalse(marker.exists(), result.stdout + result.stderr)
        self.assertEqual(result.returncode, 4)

    def graph_v2(self, dependency=False):
        f = self.fixture
        value = f.write_graph(deps=dependency)
        value['version'] = 2
        for j in value['jobs']:
            j['inputs'] = ['a.out'] if j['deps'] else []
        f.graph.write_text(json.dumps(value))
        return value

    def test_repair_dispatches_only_failed_unit_and_preserves_good_bytes(self):
        f = self.fixture
        self.graph_v2()
        first = crew.Wave(f.project, crew.begin(f.project, f.graph, 'crew', 'first'))
        first.event('T1', 'dispatch'); f.work(first, 'T1')
        first.event('T2', 'dispatch'); first.event('T2', 'fault', note='provider died')
        self.assertFalse(first.finish()['quality'])
        before = (f.project/'a.out').read_bytes()
        second = crew.Wave(f.project, crew.begin(f.project, f.graph, 'crew', 'repair', retry_note='fresh worker after observed death'))
        rows = crew.load(second.path)['jobs']
        self.assertEqual(rows['T1']['reused_from']['wave'], first.path.stem)
        self.assertEqual(rows['T2']['repair']['attempts'], 1)
        with self.assertRaisesRegex(ValueError, 'accepted unit is reused'):
            second.event('T1', 'dispatch')
        second.event('T2', 'dispatch'); f.work(second, 'T2')
        self.assertTrue(second.finish()['quality'])
        self.assertEqual((f.project/'a.out').read_bytes(), before)

    def test_related_inputs_interfaces_and_outputs_invalidate_reuse(self):
        f = self.fixture
        value = self.graph_v2(dependency=True)
        (f.project/'source').write_text('one')
        value['inputs'] = ['source']; value['jobs'][0]['inputs'] = ['source']
        f.graph.write_text(json.dumps(value))
        first = crew.Wave(f.project, crew.begin(f.project, f.graph, 'crew', 'accepted'))
        for t in ('T1', 'T2'):
            first.event(t, 'dispatch'); f.work(first, t)
        self.assertTrue(first.finish()['quality'])
        same = crew.load(crew.Wave(f.project, crew.begin(f.project, f.graph, 'crew', 'same')).path)
        self.assertTrue(all(r.get('reused_from') for r in same['jobs'].values()))
        (f.project/'source').write_text('two')
        changed = crew.load(crew.Wave(f.project, crew.begin(f.project, f.graph, 'crew', 'changed')).path)
        self.assertTrue(all(not r.get('reused_from') for r in changed['jobs'].values()))
        (f.project/'source').write_text('one')
        (f.state/'interfaces.md').write_text('new interface')
        changed = crew.load(crew.Wave(f.project, crew.begin(f.project, f.graph, 'crew', 'interface')).path)
        self.assertTrue(all(not r.get('reused_from') for r in changed['jobs'].values()))

    def test_task_rename_cannot_reset_retry_cap(self):
        f = self.fixture
        value = self.graph_v2()
        # One owned unit; task ids are presentation, not retry identities.
        value['jobs'] = value['jobs'][:1]
        f.graph.write_text(json.dumps(value))
        for n in range(3):
            value['jobs'][0]['id'] = 'T'+str(n+1)
            f.graph.write_text(json.dumps(value))
            wave = crew.Wave(f.project, crew.begin(f.project, f.graph, 'inline', 'failure-'+str(n), retry_note='revised brief '+str(n)))
            wave.event(value['jobs'][0]['id'], 'dispatch')
            wave.event(value['jobs'][0]['id'], 'fault', note='observed failure')
            wave.finish()
        value['jobs'][0]['id'] = 'T9'; f.graph.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'unit retry limit'):
            crew.begin(f.project, f.graph, 'inline', 'renamed', retry_note='try again')

    def test_v2_rejects_wait_without_a_consumed_artifact(self):
        f = self.fixture
        value = self.graph_v2(dependency=True)
        value['jobs'][1]['inputs'] = []
        f.graph.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'no consumed artifact'):
            crew.load_graph(f.graph)

    def test_context_rejects_stale_artifact_and_corrupt_ledger(self):
        f = self.fixture
        value = context.show(f.project)
        self.assertEqual(value['binding']['head'], crew.store.verify_views(f.state))
        (f.project/'new-artifact').write_text('not in the old context')
        command = [sys.executable, '-I', str(ROOT/'scripts/goal_context.py'), 'run', str(f.project), value['revision'], 'status']
        result = subprocess.run(command, capture_output=True, timeout=12)
        self.assertEqual(result.returncode, 4, result.stdout+result.stderr)
        self.assertIn(b'stale-context', result.stderr)
        (f.state/'state.rec').write_text('iteration=999\n')
        with self.assertRaisesRegex(context.store.StoreError, 'ledger-view-mismatch'):
            context.show(f.project)

    def test_unique_prompt_enter_preserves_earliest_origin_and_rejects_ambiguity(self):
        f = self.fixture
        payload = dict(hook_event_name='UserPromptSubmit', cwd=str(f.project), session_id='actual-one', prompt='/goal-loop do the task')
        host.hook(payload, 'claude')
        first = host.enter(f.project, 60)
        later = host.enter(f.project, 120)
        self.assertEqual(first['session'], 'actual-one')
        self.assertLessEqual(later['deadline_epoch'], first['deadline_epoch'])
        view=context.show(f.project)
        self.assertEqual(view['budget_scope'],'host-prompt-entry')
        self.assertLessEqual(view['deadline_epoch'],first['deadline_epoch']+.01)
        payload['session_id'] = 'actual-two'; host.hook(payload, 'claude')
        with self.assertRaisesRegex(ValueError, 'ambiguous recorded host identity'):
            host.enter(f.project, 60)

    def test_context_stamp_consumes_revision_under_original_writer_lock(self):
        with tempfile.TemporaryDirectory(prefix='context-stamp-') as directory:
            root = Path(directory)
            ctl = ['bash', str(ROOT/'scripts/goal_ctl.sh')]
            init = subprocess.run(ctl+['init', '--project', str(root)], capture_output=True, timeout=12)
            self.assertEqual(init.returncode, 0)
            (root/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n'
                '- AC-1 | example | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
            view = context.show(root)
            self.assertNotIn('--auto',view['actions']['stamp']['executes'])
            authorized = context.show(root,auto=True)
            self.assertIn('--auto',authorized['actions']['stamp']['executes'])
            self.assertNotEqual(view['revision'],authorized['revision'])
            command = [sys.executable, '-I', str(ROOT/'scripts/goal_context.py'), 'run', str(root), view['revision'], 'stamp']
            stamped = subprocess.run(command, capture_output=True, timeout=15)
            self.assertEqual(stamped.returncode, 0, stamped.stdout+stamped.stderr)
            self.assertTrue(context.show(root)['stamped'])
            self.assertNotIn(' auto',(root/'.goal/goal.md').read_text().split('approved: ',1)[1])
            stale = subprocess.run(command, capture_output=True, timeout=15)
            self.assertEqual(stale.returncode, 4)
            self.assertIn(b'stale-context', stale.stderr)

    def test_expired_context_offers_no_dispatch_and_receipt_does_not_invent_go(self):
        f = self.fixture
        with mock.patch.object(context.budget, 'gate_limit', return_value=(time.monotonic()-1, True)):
            value = context.show(f.project)
        self.assertTrue(value['expired'])
        self.assertEqual(set(value['actions']), {'status'})
        report = context.receipt(f.project)
        self.assertFalse(report['completion_verified'])
        self.assertNotEqual(report['checks']['gate']['result'], 0)

    def test_changed_interface_between_validation_and_adoption_is_rejected(self):
        f = self.fixture
        self.graph_v2()
        wave = crew.Wave(f.project, crew.begin(f.project, f.graph, 'crew', 'stale-check'))
        wave.event('T1', 'dispatch')
        (f.project/'a.out').write_text('A'); wave.event('T1', 'returned', 0)
        self.assertEqual(wave.validate('T1'), 0)
        (f.state/'interfaces.md').write_text('changed after validation')
        with self.assertRaisesRegex(ValueError, 'validation evidence is stale'):
            wave.event('T1', 'adopt')

    def test_prepare_is_stable_until_the_actual_budget_changes(self):
        f = self.fixture
        host.begin(f.project, 'codex', 'stable-budget', 90)
        wave = host.crew.begin(f.project, f.graph, 'crew', 'stable-budget')
        original = host.limits
        ticks = []
        def rounded(root, with_identity=False):
            end, cap, key = original(root, with_identity=True)
            ticks.append(1)
            return end, cap-len(ticks)*.000001, key
        with mock.patch.object(host, 'limits', side_effect=rounded):
            first = host.prepare(f.project, wave, 'T1')
            again = host.prepare(f.project, wave, 'T1')
        self.assertEqual(first, again)
        host.begin(f.project, 'codex', 'stable-budget', 30)
        tightened = host.prepare(f.project, wave, 'T1')
        self.assertLess(tightened['deadline_monotonic'], first['deadline_monotonic']-40)

    def test_context_cannot_relabel_a_borrowed_reader_as_writer(self):
        with tempfile.TemporaryDirectory(prefix='context-borrowed-lock-') as directory:
            root=Path(directory)
            subprocess.run(['bash',str(ROOT/'scripts/goal_ctl.sh'),'init','--project',str(root)],check=True,capture_output=True)
            (root/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n'
                '- AC-1 | example | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
            view=context.show(root)
            fd=os.open(root/'.goal',os.O_RDONLY|os.O_DIRECTORY)
            try:
                fcntl.flock(fd,fcntl.LOCK_SH)
                env=dict(os.environ,GOAL_ACCESS_FD=str(fd),GOAL_ACCESS_MODE='write',GOAL_ACCESS_OWNER_PID=str(os.getpid()))
                result=subprocess.run([sys.executable,'-I',str(ROOT/'scripts/goal_context.py'),'run',str(root),view['revision'],'stamp'],
                                      env=env,pass_fds=(fd,),capture_output=True,timeout=12)
            finally:os.close(fd)
            self.assertEqual(result.returncode,4,result.stdout+result.stderr)
            self.assertIn(b'nested-writer',result.stderr)
            self.assertIn('approved: PENDING',(root/'.goal/goal.md').read_text())

    def test_context_does_not_send_an_unbooked_or_claimed_wave_back_to_work(self):
        f=self.fixture
        (f.project/'a.out').write_text('A')
        (f.state/'work-plan.md').write_text('- [x] T1 landed | owner=controller | files=a.out\n')
        self.assertEqual(context.show(f.project)['next'],'close-unbooked-wave')
        f.ctl('close-iteration','--operation-id','context-final-001','--task','T1','--files','a.out',
              '--checks-pass','1','--checks-fail','0','--checks-unverifiable','0','--exit-signal','yes',
              '--adversarial','clear','--adversarial-note','fixture check and file verified')
        self.assertEqual(context.show(f.project)['next'],'verify-gate-and-deliver')

    def test_first_real_hook_entry_has_a_usable_map_before_contract_exists(self):
        with tempfile.TemporaryDirectory(prefix='context-first-entry-') as directory:
            root=Path(directory)
            payload=dict(hook_event_name='UserPromptSubmit',cwd=str(root),session_id='fixture-first-entry',
                         prompt='/goal-loop-host:goal-loop --auto --time-budget=90 implement the task')
            host.hook(payload,'claude')
            host.enter(root,90)
            command=['bash',str(ROOT/'scripts/goal_ctl.sh'),'context','--project',str(root),'--auto']
            result=subprocess.run(command,capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            view=json.loads(result.stdout)
            self.assertFalse((root/'.goal/goal.md').exists(),'a view silently authored/approved a contract')
            self.assertEqual(view['next'],'author-contract-and-smoke')
            self.assertIsNone(view['binding']['contract'])
            self.assertNotIn('stamp',view['actions'])
            template=view['author_contract']['template']
            (root/'answer.txt').write_text('valid')
            (root/'check.py').write_text('from pathlib import Path\nraise SystemExit(0 if Path("answer.txt").read_text()=="valid" else 1)\n')
            contract=template.replace('<outcome>','deliver the verified answer').replace('<yes/no statement>','answer is valid').replace('<command>','python3 check.py')
            (root/'.goal/goal.md').write_text(contract)
            smoke=subprocess.run([sys.executable,str(root/'check.py')],cwd=root,capture_output=True)
            self.assertEqual(smoke.returncode,0)
            refreshed=subprocess.run(command,capture_output=True,timeout=15)
            self.assertEqual(refreshed.returncode,0,refreshed.stdout+refreshed.stderr)
            ready=json.loads(refreshed.stdout)
            import shlex
            stamp=subprocess.run(shlex.split(ready['actions']['stamp']['command']),capture_output=True,timeout=15)
            self.assertEqual(stamp.returncode,0,stamp.stdout+stamp.stderr)
            self.assertTrue(context.show(root)['stamped'])

    def qualified_policy(self):
        f = self.fixture
        p = policies.Evolution(); p.setUp(); self.addCleanup(p.doCleanups)
        p.state = f.state/'proposals/routing'
        protocol = p.protocol('routing')
        (protocol.parent/'baseline.py').write_text('import json\nprint(json.dumps(dict(match=False,choice="baseline",reason="baseline")))\n')
        (protocol.parent/'candidate.py').write_text('# candidate\nimport json,sys\nv=json.load(sys.stdin)\n'
            'm=v["context"].get("profile")=="small"\nprint(json.dumps(dict(match=m,choice="serial" if m else "baseline",reason="measured small-unit startup")))\n')
        engine = crew.evolution()
        with mock.patch.object(engine, 'trial', side_effect=p.telemetry):
            result = engine.experiment(protocol, p.state)
        self.assertEqual(result['status'], 'enabled')
        return p, protocol, result

    def test_qualified_policy_changes_dispatch_and_mismatch_retains_baseline(self):
        f = self.fixture
        p, _, result = self.qualified_policy()
        value = f.write_graph(); value['context']['profile'] = 'small'; f.graph.write_text(json.dumps(value))
        report = crew.plan(f.project, f.graph, policy_state=p.state)
        self.assertEqual(report['policy']['selection']['policy'], result['enabled'])
        self.assertEqual(report['reason'], 'qualified-routing-policy')
        wave = crew.Wave(f.project, crew.begin(f.project, f.graph, 'crew', 'policy', p.state))
        self.assertEqual(crew.load(wave.path)['mode'], 'inline')
        wave.event('T1', 'dispatch')
        with self.assertRaisesRegex(ValueError, 'host capacity'):
            wave.event('T2', 'dispatch')
        value['context']['profile'] = 'other'; f.graph.write_text(json.dumps(value))
        other = crew.Wave(f.project, crew.begin(f.project, f.graph, 'crew', 'outside', p.state))
        self.assertFalse(crew.load(other.path)['policy']['decision']['match'])
        self.assertEqual(crew.load(other.path)['mode'], 'crew')

    def test_withdrawal_and_pending_transition_block_stale_dispatch(self):
        f = self.fixture
        p, _, initial = self.qualified_policy()
        value = f.write_graph(); value['context']['profile'] = 'small'; f.graph.write_text(json.dumps(value))
        wave = crew.Wave(f.project, crew.begin(f.project, f.graph, 'crew', 'before-withdrawal', p.state))
        fresh = p.protocol('regression', offset=1000)
        (fresh.parent/'candidate.py').write_bytes((p.state/('policies/'+initial['enabled']+'.py')).read_bytes())
        (fresh.parent/'baseline.py').write_text('import json\nprint(json.dumps(dict(match=False,choice="baseline",reason="baseline")))\n')
        def bad(*args):
            row, output = p.telemetry(*args)
            if b'# candidate' in args[0]:
                row.update(ok=False, floor=False, regression=True)
            return row, output
        engine = crew.evolution()
        with mock.patch.object(engine, 'trial', side_effect=bad):
            withdrawn = engine.experiment(fresh, p.state)
        self.assertEqual(withdrawn['status'], 'withdrawn')
        with self.assertRaisesRegex(ValueError, 'policy changed'):
            wave.event('T1', 'dispatch')
        next_wave = crew.Wave(f.project, crew.begin(f.project, f.graph, 'crew', 'after-withdrawal', p.state))
        self.assertEqual(crew.load(next_wave.path)['mode'], 'crew')
        (p.state/'policy-pending.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'recovery-required'):
            next_wave.event('T1', 'dispatch')

    def test_holdout_rejection_preserves_the_consumed_routing_version(self):
        f = self.fixture
        p, _, initial = self.qualified_policy()
        value = f.write_graph(); value['context']['profile'] = 'small'; f.graph.write_text(json.dumps(value))
        before = crew.begin(f.project, f.graph, 'crew', 'before-holdout', p.state)
        fresh = p.protocol('holdout-rejection', offset=2000)
        (fresh.parent/'baseline.py').write_bytes((p.state/('policies/'+initial['enabled']+'.py')).read_bytes())
        (fresh.parent/'candidate.py').write_text('# candidate-next\nimport json\nprint(json.dumps(dict(match=True,choice="serial",reason="new hypothesis")))\n')
        config = json.loads(fresh.read_bytes())
        for n in (6,7):
            name='holdout-'+str(n)+'.json';(fresh.parent/name).write_text(json.dumps({'task':2100+n}))
            config['holdout'].append({'input':name,'expected':name})
        fresh.write_text(json.dumps(config))
        pointer = (p.state/'enabled.json').read_bytes()
        def observed(program, grader, task, expected, seconds, deadline):
            new = b'# candidate-next' in program
            held = json.loads(task)['task'] >= 2100
            cost = (3 if held else 1) if new else 2
            return dict(ok=True,elapsed=cost,score=1,floor=True,horizon=True),b'controlled full-path holdout'
        with mock.patch.object(crew.evolution(), 'trial', side_effect=observed):
            retained=crew.evolution().experiment(fresh,p.state)
        self.assertEqual(retained['status'],'holdout-rejected')
        self.assertEqual((p.state/'enabled.json').read_bytes(),pointer)
        crew.Wave(f.project,before).event('T1','dispatch')
        self.assertEqual(crew.plan(f.project,f.graph,policy_state=p.state)['policy']['selection']['policy'],initial['enabled'])


if __name__ == '__main__':
    unittest.main()
