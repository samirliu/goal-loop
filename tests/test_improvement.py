"""Recursive policy lifecycle. Controlled trial costs test decisions, not utility.

Calibration, archive consumption, native maps and controller execution are real.
The runnable example separately measures actual policy work without mocked costs.
"""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


improve = module(ROOT/'scripts/goal_improve.py', 'test_improvement_runtime')
contexts = module(ROOT/'tests/test_context_actions.py', 'improvement_context_fixture')
policies = module(ROOT/'tests/test_evolve.py', 'improvement_policy_fixture')
host = module(ROOT/'scripts/goal_host.py', 'improvement_host_fixture')
checkpoints = module(ROOT/'tests/test_incumbent.py', 'improvement_checkpoint_fixture')


class Improvement(unittest.TestCase):
    def setUp(self):
        self.f = contexts.ContextActions()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.project = self.f.project.resolve()
        self.f.state = self.f.project/'.goal'
        self.f.initialize()
        self.root = self.f.project
        host.begin(self.root, 'claude', 'improvement-test-session', 120)
        self.p = policies.Evolution()
        self.p.setUp()
        self.addCleanup(self.p.doCleanups)
        self.p.root = self.root/'.goal/proposals'
        self.p.root.mkdir(exist_ok=True)
        self.state = self.p.root/'policy'
        trigger = self.root/'.goal/evidence/observed-failure.txt'
        trigger.write_text('Observed repeated work in the local tool workflow; inspect this raw trace.')
        self.value = dict(version=1, scope='local tool workflow', consumer='tool',
            state=self.state.relative_to(self.root).as_posix(), protocol=None, max_attempts=4,
            reserve_fraction=.25, intent='improve', hypothesis='Reuse verified work to reduce repeated local tool cost.',
            trigger=dict(artifact=trigger.relative_to(self.root).as_posix(),
                         sha256=improve.engine.digest(trigger.read_bytes()), observation='Repeated work was observed.'))
        self.source = self.root/improve.CONFIG
        self.proposal('first')

    def proposal(self, name, offset=0, baseline=None, candidate=None, pairs=8, intent='improve'):
        source = self.p.protocol(name, offset)
        value = json.loads(source.read_bytes())
        for phase, base in [('development', 0), ('holdout', 100)]:
            for index in range(6, pairs):
                path = source.parent/(phase+'-'+str(index)+'.json')
                path.write_text(json.dumps(dict(task=offset+base+index)))
                value[phase].append(dict(input=path.name, expected=path.name))
        source.write_text(json.dumps(value))
        if baseline is not None:
            (source.parent/'baseline.py').write_bytes(baseline)
        if candidate is not None:
            (source.parent/'candidate.py').write_bytes(candidate)
        self.value.update(protocol=source.relative_to(self.root).as_posix(), intent=intent)
        self.source.write_text(json.dumps(self.value))
        self.protocol = source
        return source

    def evaluate(self, *, failure=False):
        baseline = (self.protocol.parent/'baseline.py').read_bytes()
        def observed(program, grader, task, expected, seconds, end):
            failed = failure and program != baseline
            return dict(ok=not failed, elapsed=2 if program == baseline else 1, score=1,
                        floor=not failed, horizon=not failed, regression=failed), b'observed'
        with mock.patch.object(improve.engine, 'trial', side_effect=observed):
            return improve.evaluate(self.root)

    def start(self):
        return improve.initialize(self.root)

    def selected_bytes(self):
        selected = improve.engine.enabled_policy(self.state)
        return (self.state/selected['program']).read_bytes()

    def test_two_generations_use_the_qualified_parent_and_preserve_evidence(self):
        self.start()
        first = self.evaluate()
        self.assertEqual(first['status'], 'enabled')
        first_report = (self.state/first['run']/'report.json').read_bytes()
        parent = improve.engine.enabled_policy(self.state)
        baseline = self.selected_bytes()
        self.proposal('second', 1000, baseline, b'print("candidate-two")\n')
        with self.assertRaisesRegex(ValueError, 'consume the qualified parent'):
            self.evaluate()
        output, rc, reason, _ = improve.consume(self.root, 2, b'actual later task')
        self.assertEqual((output, rc, reason), (b'candidate\n', 0, None))
        second = self.evaluate()
        self.assertEqual(second['status'], 'enabled')
        self.assertEqual(second['improvement']['parent'], parent)
        self.assertEqual(second['improvement']['candidate_depth'], 2)
        view, _ = improve.view(self.root)
        self.assertEqual(view['generation_depth'], 2)
        self.assertEqual(view['attempts'], 2)
        self.assertEqual((self.state/first['run']/'report.json').read_bytes(), first_report)
        self.assertEqual(improve.engine.testing_budget(self.state)['evaluations'], 2)
        self.assertEqual(len(json.loads((self.state/'used-holdout.json').read_bytes())), 32)

    def test_fresh_counterexample_withdraws_and_repair_keeps_testing_budget(self):
        self.start()
        first = self.evaluate()
        old = self.selected_bytes()
        improve.consume(self.root, 2, b'production one')
        self.proposal('second', 1000, old, b'print("candidate-two")\n')
        second = self.evaluate()
        newer = self.selected_bytes()
        improve.consume(self.root, 2, b'production two')
        self.proposal('counterexample', 2000, old, newer, intent='monitor')
        monitored = self.evaluate(failure=True)
        self.assertEqual(monitored['status'], 'withdrawn')
        self.assertEqual(self.selected_bytes(), old)
        improve.consume(self.root, 2, b'actual fallback task')
        self.proposal('repair', 3000, old, b'print("candidate-repair")\n')
        repaired = self.evaluate()
        self.assertEqual(repaired['status'], 'enabled')
        self.assertEqual(repaired['improvement']['attempt'], 4)
        self.assertEqual(repaired['improvement']['candidate_depth'], 2)
        self.assertEqual(improve.engine.testing_budget(self.state)['evaluations'], 3)
        for row in (first, second, monitored):
            self.assertTrue((self.state/row['run']/'report.json').exists())

    def test_attempt_limit_stops_experiments_but_keeps_actual_delivery_consumable(self):
        self.value['max_attempts'] = 1
        self.source.write_text(json.dumps(self.value))
        self.start()
        self.evaluate()
        view, commands = improve.view(self.root)
        self.assertEqual(view['next'], 'finish-original-goal')
        self.assertNotIn('evaluate-improvement', commands)
        self.assertIsNotNone(view['consume_command'])
        self.assertEqual(improve.consume(self.root, 2, b'later work')[1], 0)
        with self.assertRaisesRegex(ValueError, 'attempt limit'):
            self.evaluate()

    def test_changing_allocation_or_state_cannot_reset_attempts(self):
        original = self.start()
        again = self.start()
        self.assertEqual(original['cutoff'], again['cutoff'])
        self.value['state'] = '.goal/proposals/relabelled'
        self.source.write_text(json.dumps(self.value))
        with self.assertRaisesRegex(ValueError, 'allocation is fixed'):
            self.start()
        self.value['state'] = '.goal/proposals/policy'
        self.value['max_attempts'] += 1
        self.source.write_text(json.dumps(self.value))
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.start()

    def test_grader_or_threshold_replacement_never_dispatches_a_candidate(self):
        self.start()
        for key in ('grader', 'minimum_cost_gain'):
            with self.subTest(key=key):
                config = json.loads(self.protocol.read_bytes())
                original = self.protocol.read_bytes()
                grader = self.protocol.parent/'grader.py'
                saved = grader.read_bytes()
                if key == 'grader':
                    grader.write_bytes(saved+b'\n# replaced instrument\n')
                else:
                    config[key] = .01
                    self.protocol.write_text(json.dumps(config))
                with mock.patch.object(improve.engine, 'trial') as trial:
                    with self.assertRaisesRegex(ValueError, 'cannot change the grader'):
                        improve.evaluate(self.root)
                    trial.assert_not_called()
                self.protocol.write_bytes(original)
                grader.write_bytes(saved)
        self.assertFalse(list(self.state.glob('*/report.json')))

    def test_stale_parent_and_exposed_holdout_cannot_restart_learning(self):
        self.start()
        self.evaluate()
        improve.consume(self.root, 2, b'actual use')
        self.proposal('stale-parent', 1000, candidate=b'print("new-candidate")\n')
        with self.assertRaisesRegex((ValueError, improve.engine.ExperimentError), 'descend from the active|currently enabled'):
            self.evaluate()
        baseline = self.selected_bytes()
        self.proposal('reused-holdout', 0, baseline, b'print("new-candidate")\n')
        with self.assertRaisesRegex(improve.engine.ExperimentError, 'already exposed'):
            self.evaluate()
        self.assertEqual(len(list(self.state.glob('*/report.json'))), 1)

    def test_reserve_stops_new_trials_without_renewing_the_goal_budget(self):
        record = self.start()
        runner = (self.root/'.goal/runner.json').read_bytes()
        with mock.patch.object(improve.time, 'monotonic', return_value=record['cutoff']+.01):
            with mock.patch.object(improve.engine, 'trial') as trial:
                with self.assertRaisesRegex(ValueError, 'reserve reached'):
                    improve.evaluate(self.root)
                trial.assert_not_called()
        self.assertEqual((self.root/'.goal/runner.json').read_bytes(), runner)

    def test_monitor_cannot_nominate_an_unverified_fallback(self):
        self.start()
        self.evaluate()
        active = self.selected_bytes()
        self.proposal('monitor', 1000, b'print("unknown fallback")\n', active, intent='monitor')
        with self.assertRaisesRegex(ValueError, 'qualified fallback'):
            self.evaluate()

    def test_candidate_cannot_rewrite_its_trigger_during_comparison(self):
        self.start()
        evidence = self.root/self.value['trigger']['artifact']
        def tamper(*args):
            evidence.write_text('rewritten after seeing the result')
            return dict(ok=True, elapsed=1, score=1, floor=True, horizon=True), b'observed'
        with mock.patch.object(improve.engine, 'trial', side_effect=tamper):
            with self.assertRaisesRegex(improve.engine.ExperimentError, 'frozen experiment material changed'):
                improve.evaluate(self.root)
        report = json.loads(next(self.state.glob('*/report.json')).read_bytes())
        self.assertEqual(report['status'], 'instrument-invalid')
        self.assertFalse((self.state/'enabled.json').exists())

    def test_expired_native_context_recovers_interrupted_improvement_with_bad_next_input(self):
        self.start()
        with mock.patch.object(improve.engine, 'transition_fault', side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                self.evaluate()
        self.protocol.write_text('{broken next proposal')
        host.budget.adopt_host(self.root/'.goal', host.capture('claude', 'improvement-test-session', 'tool'), .1)
        time.sleep(.12)
        view = self.f.view()
        command = view['actions']['recover-improvement']['command']
        payload = dict(hook_event_name='PreToolUse', session_id='improvement-test-session', cwd=str(self.root),
                       tool_name='Bash', tool_input={'command':command})
        self.assertEqual(host.hook(payload, 'claude'), {})
        result = subprocess.run(shlex.split(command), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertFalse((self.state/improve.engine.PENDING).exists())
        self.assertIsNone(improve.engine.enabled_policy(self.state)['policy'])
        report = json.loads(next(self.state.glob('*/report.json')).read_bytes())
        self.assertEqual(report['status'], 'interrupted-uncertain')

    def test_bad_next_proposal_does_not_disable_qualified_archive_consumption(self):
        self.start()
        self.evaluate()
        self.protocol.write_text('{incomplete proposal')
        view, commands = improve.view(self.root)
        self.assertIn('proposal_error', view)
        self.assertNotIn('evaluate-improvement', commands)
        self.assertEqual(improve.consume(self.root, 2, b'actual work')[1], 0)

    def test_context_binds_proposal_bytes_and_preserves_completion_authority(self):
        view = self.f.view()
        self.assertIn('start-improvement', view['actions'])
        self.f.execute(view, 'start-improvement')
        before = self.f.view()
        source = self.protocol.parent/'candidate.py'
        source.write_bytes(source.read_bytes()+b'\n# changed candidate\n')
        changed = self.f.execute(before, 'evaluate-improvement', expected=4)
        self.assertIn('stale-context', changed.stderr)
        self.assertIn('iteration=0\n', (self.root/'.goal/state.rec').read_text())
        self.assertFalse((self.state/'enabled.json').exists())

    def test_after_actual_use_map_requires_fresh_next_generation_proposal(self):
        self.start()
        self.evaluate()
        improve.consume(self.root, 2, b'actual later work')
        view, commands = improve.view(self.root)
        self.assertEqual(view['next'], 'prepare-next-generation')
        self.assertNotIn('evaluate-improvement', commands)
        self.assertIsNotNone(view['parent_archive'])
        self.proposal('next', 1000, self.selected_bytes(), b'print("next-candidate")\n')
        self.assertIn('evaluate-improvement', improve.view(self.root)[1])

    def test_qualified_proposer_generates_its_own_next_version_from_feedback(self):
        proposer = b'''import json,sys
GENERATION = 1
request=json.load(sys.stdin)
assert request['feedback']['run']
assert 'holdout' not in request
source=request['parent_program'].replace('GENERATION = 1','GENERATION = 2')
print(json.dumps(dict(hypothesis='Refine the bounded proposal operator from actual feedback.',files={'candidate.py':source})))
'''
        (self.protocol.parent/'candidate.py').write_bytes(proposer)
        self.value['consumer'] = 'proposer'
        self.source.write_text(json.dumps(self.value))
        self.start()
        first = self.evaluate()
        view, commands = improve.view(self.root)
        self.assertEqual(view['next'], 'generate-next-proposal')
        self.assertIn('suggest-improvement', commands)
        proposed = improve.suggest(self.root)
        self.assertEqual(proposed['parent']['policy'], first['enabled'])
        generated = proposed['proposal']['files']['candidate.py'].encode()
        self.assertIn(b'GENERATION = 2', generated)
        self.assertEqual(self.selected_bytes(), proposer, 'a generated proposal was applied without independent evaluation')
        self.proposal('recursive-proposer', 1000, proposer, generated)
        second = self.evaluate()
        self.assertEqual(second['status'], 'enabled')
        self.assertEqual(second['improvement']['candidate_depth'], 2)
        self.assertEqual(self.selected_bytes(), generated)

    def test_proposer_cannot_write_goal_state_and_invalid_output_is_not_usage(self):
        (self.protocol.parent/'candidate.py').write_text('print(\'{"hypothesis":"bad","files":{".goal/goal.md":"waived"}}\')\n')
        self.value['consumer'] = 'proposer'
        self.source.write_text(json.dumps(self.value))
        self.start()
        self.evaluate()
        original = (self.root/'.goal/goal.md').read_bytes()
        with self.assertRaisesRegex(ValueError, 'invalid proposer file scope'):
            improve.suggest(self.root)
        self.assertEqual(improve.view(self.root)[0]['actual_uses'], [])
        self.assertEqual((self.root/'.goal/goal.md').read_bytes(), original)

    def test_consumption_refuses_a_stale_selected_parent(self):
        self.start()
        self.evaluate()
        parent = improve.engine.enabled_policy(self.state)
        improve.consume(self.root, 2, b'actual use')
        self.proposal('new-selected-parent', 1000, self.selected_bytes(), b'print("candidate-new")\n')
        self.evaluate()
        with self.assertRaisesRegex(ValueError, 'selected policy changed'):
            improve.consume(self.root, 2, b'stale request', expected=parent)

    def test_ending_the_goal_stops_recursive_work_without_deleting_the_archive(self):
        self.start()
        self.evaluate()
        archived = self.selected_bytes()
        runner = (self.root/'.goal/runner.json').read_bytes()
        host.end(self.root, 'improvement-test-session', 'claude')
        for action in (lambda:improve.evaluate(self.root), lambda:improve.consume(self.root, 2, b'late work')):
            with self.assertRaisesRegex(ValueError, 'session ended'):
                action()
        self.assertEqual(self.selected_bytes(), archived)
        self.assertEqual((self.root/'.goal/runner.json').read_bytes(), runner)

    def test_qualified_routing_is_consumed_by_existing_native_planner(self):
        decision = b'print(\'{"match":true,"choice":"serial","reason":"qualified local workflow"}\')\n'
        (self.protocol.parent/'baseline.py').write_bytes(decision)
        (self.protocol.parent/'candidate.py').write_bytes(decision+b'# candidate\n')
        self.value['consumer'] = 'routing'
        self.source.write_text(json.dumps(self.value))
        self.start()
        self.evaluate()
        graph = dict(version=1, context={}, capacity=2, inputs=[], instruments=[],
                     jobs=[dict(id='T1', files=['answer'], deps=[], check=['true'])], final_check=['true'])
        (self.root/'.goal/proposals/crew.json').write_text(json.dumps(graph))
        view = self.f.view()
        self.assertIn('--policy-state', view['actions']['plan']['executes'])
        self.assertEqual(view['execution_input']['template']['policy_state'], str(self.state))
        planned = json.loads(self.f.execute(view, 'plan').stdout)
        self.assertEqual(planned['reason'], 'qualified-routing-policy')
        self.assertEqual(planned['policy']['selection'], improve.engine.enabled_policy(self.state))
        # Printing advice alone is deliberately insufficient as actual work.
        self.assertEqual(improve.view(self.root)[0]['actual_uses'], [])
        source = self.root/'.goal/proposals/execution.json'
        source.write_text(json.dumps(dict(mode='inline', policy_state=None)))
        self.assertNotIn('--policy-state', self.f.view()['actions']['plan']['executes'])
        graph['jobs'][0]['check'] = [sys.executable, 'check.py']
        graph_path = self.root/'.goal/proposals/crew.json'
        graph_path.write_text(json.dumps(graph))
        wave = improve.crew.Wave(self.root, improve.crew.begin(self.root, graph_path, 'inline', 'actual-routing-use', self.state))
        wave.event('T1', 'dispatch')
        wave.event('T1', 'started')
        (self.root/'answer').write_bytes(b'correct')
        checked = subprocess.run([sys.executable, '-I', str(self.root/'check.py')],cwd=self.root)
        wave.event('T1', 'returned', result=checked.returncode)
        self.assertEqual(wave.validate('T1'), 0)
        wave.event('T1', 'adopt')
        self.assertTrue(wave.finish()['quality'])
        self.assertEqual(improve.view(self.root)[0]['actual_uses'], ['crew:'+wave.path.stem])

    def test_multifile_worker_instructions_use_archived_checkpoint_bytes(self):
        fixture = checkpoints.IntermediateCheckpoint()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.project = fixture.project.resolve()
        fixture.state = fixture.project/'.goal'
        root = fixture.project
        (root/'worker.py').write_text('from pathlib import Path\nprint(Path("rules.md").read_text())\n')
        (root/'rules.md').write_text('baseline-playbook')
        fixture.book()
        fixture.bind()
        base = fixture.checkpoint('save', '--intermediate', '--file', 'worker.py', '--file', 'rules.md')[0].strip()
        (root/'rules.md').write_text('candidate-playbook')
        candidate = fixture.checkpoint('candidate', '--base', base)[0].strip()
        host.begin(root, 'claude', 'checkpoint-improvement', 120)
        protocol = root/'.goal/proposals/bundle/protocol.json'
        shutil.copytree(self.protocol.parent, protocol.parent)
        value = json.loads(protocol.read_bytes())
        value.update(version=2, baseline=base, candidate=candidate, entry='worker.py')
        protocol.write_text(json.dumps(value))
        config = dict(self.value, protocol=protocol.relative_to(root).as_posix(), scope='owned worker instruction bundle')
        evidence = root/'.goal/evidence/observed-profile.txt'
        evidence.write_text('Owned instruction bundle profile fixture; no claim of model benefit.')
        config['trigger'] = dict(artifact=evidence.relative_to(root).as_posix(),
                                sha256=improve.engine.digest(evidence.read_bytes()), observation='Profile fixture')
        (root/improve.CONFIG).write_text(json.dumps(config))
        improve.initialize(root)
        baseline = improve.engine.program_bytes(improve.engine.load_protocol(protocol, root)[1]['baseline'])
        def observed(program, *args):
            return dict(ok=True, elapsed=2 if improve.engine.program_bytes(program)==baseline else 1,
                        score=1, floor=True, horizon=True), b'controlled instruction evidence'
        with mock.patch.object(improve.engine, 'trial', side_effect=observed):
            self.assertEqual(improve.evaluate(root)['status'], 'enabled')
        (root/'rules.md').write_text('later live edit')
        actual, code, reason, _ = improve.consume(root, 2, b'actual input')
        self.assertEqual((actual, code, reason), (b'candidate-playbook\n', 0, None))


if __name__ == '__main__':
    unittest.main()
