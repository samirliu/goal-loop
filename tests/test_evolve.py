"""Decision/registry tests use controlled telemetry; subprocess tests use real code."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/goal_evolve.py'
SPEC = importlib.util.spec_from_file_location('goal_evolve', SCRIPT)
evolve = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evolve)


class Evolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='goal-evolve-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / 'state'
        self.config = {'version': 1, 'baseline': 'baseline.py', 'candidate': 'candidate.py', 'grader': 'grader.py',
                       'minimum_pairs': 6, 'minimum_cost_gain': 0.15, 'quality_tolerance': 0,
                       'trial_seconds': 1, 'budget_seconds': 10}

    def protocol(self, suffix, offset=0):
        root = self.root / suffix; root.mkdir()
        for name, code in (('baseline.py', b'print("baseline")\n'), ('candidate.py', b'print("candidate")\n'),
                           ('grader.py', b'import json;print(json.dumps({"floor":False,"horizon":False,"score":0}))\n')):
            (root / name).write_bytes(code)
        config = dict(self.config)
        for phase, base in (('development', 0), ('holdout', 100)):
            config[phase] = []
            for index in range(6):
                name = '%s-%s.json' % (phase, index)
                (root / name).write_text(json.dumps({'task': base + index + offset}))
                config[phase].append({'input': name, 'expected': name})
        path = root / 'protocol.json'; path.write_text(json.dumps(config))
        return path

    def telemetry(self, program, grader, task, expected, seconds, deadline):
        candidate = b'candidate' in program
        return {'ok': True, 'elapsed': 1 if candidate else 2, 'score': 1}, b'observed-output'

    def test_only_replicated_eligible_cost_improvement_passes(self):
        def pairs(differences):
            return [{'baseline': {'ok': True, 'score': 1, 'elapsed': 2},
                     'candidate': {'ok': True, 'score': 1, 'elapsed': 2 - difference}} for difference in differences]
        positive = pairs([1] * 6)
        decision = evolve.compare(positive, self.config)
        self.assertTrue(decision['pass'])
        self.assertEqual(decision['one_sided_sign_p'], 1 / 64)
        self.assertFalse(evolve.compare(pairs([0] * 6), self.config)['pass'])
        self.assertFalse(evolve.compare(pairs([1.9, -.01, -.01, -.01, -.01, -.01]), self.config)['pass'])
        self.assertFalse(evolve.compare(positive[:1], self.config)['pass'])
        positive[0]['candidate']['ok'] = False
        self.assertFalse(evolve.compare(positive, self.config)['pass'])
        positive[0]['candidate'].update(ok=True, score=0)
        self.assertFalse(evolve.compare(positive, self.config)['pass'])

    def test_registry_promotes_and_withdraws_without_reusing_holdout(self):
        protocol = self.protocol('first')
        with mock.patch.object(evolve, 'trial', side_effect=self.telemetry):
            result = evolve.experiment(protocol, self.state)
        self.assertEqual(result['status'], 'enabled')
        selected = json.loads((self.state / 'enabled.json').read_bytes())
        self.assertEqual(selected['policy'], result['policies']['candidate'])
        self.assertEqual(evolve.digest((self.state / selected['program']).read_bytes()), selected['policy'])
        self.assertTrue((self.state / result['run'] / 'frozen/grader.py').is_file())
        with self.assertRaisesRegex(evolve.ExperimentError, 'already exposed'):
            evolve.experiment(protocol, self.state)
        fresh = self.protocol('fresh', offset=1000)
        def failure(*args):
            row, output = self.telemetry(*args)
            if b'candidate' in args[0]:
                row.update(ok=False, floor=False)
            return row, output
        with mock.patch.object(evolve, 'trial', side_effect=failure):
            withdrawn = evolve.experiment(fresh, self.state)
        self.assertEqual(withdrawn['status'], 'withdrawn')
        self.assertNotIn('holdout', withdrawn['phases'])
        self.assertEqual(len(withdrawn['phases']['development']['pairs']), 1)
        self.assertEqual(withdrawn['enabled'], withdrawn['policies']['baseline'])
        self.assertTrue((self.state / selected['program']).is_file())  # rollback preserves candidate history

    def test_development_gain_then_complete_holdout_regression_keeps_incumbent(self):
        first = self.protocol('incumbent')
        with mock.patch.object(evolve, 'trial', side_effect=self.telemetry):
            initial = evolve.experiment(first, self.state)
        pointer = (self.state / 'enabled.json').read_bytes()
        selected = json.loads(pointer)
        old_program = (self.state / selected['program']).read_bytes()
        preserved = {path: path.read_bytes() for path in (
            self.state / initial['run'] / 'report.json',
            self.state / initial['run'] / 'trials.jsonl', self.state / selected['program'])}
        exposed = set(json.loads((self.state / 'used-holdout.json').read_bytes()))

        fresh = self.protocol('new-candidate', offset=1000)
        (fresh.parent / 'baseline.py').write_bytes(old_program)
        (fresh.parent / 'candidate.py').write_bytes(b'print("candidate-v2")\n')
        config = json.loads(fresh.read_bytes())
        # The second alpha is .00833: keep the original budget/thresholds,
        # and provide enough fresh pairs to execute the entire holdout.
        for index in (6, 7):
            name = 'holdout-%s.json' % index
            (fresh.parent / name).write_text(json.dumps({'task': 1100 + index}))
            config['holdout'].append({'input': name, 'expected': name})
        fresh.write_text(json.dumps(config))

        def split_telemetry(program, grader, task, expected, seconds, deadline):
            # Controlled branch evidence; this does not measure policy utility.
            candidate = program != old_program
            held_out = json.loads(task)['task'] >= 1100
            elapsed = (3 if held_out else 1) if candidate else 2
            return {'ok': True, 'floor': True, 'horizon': True, 'score': 1,
                    'regression': False, 'elapsed': elapsed}, b'observed-output'

        with mock.patch.object(evolve, 'trial', side_effect=split_telemetry):
            result = evolve.experiment(fresh, self.state)
        development, holdout = (result['phases'][name] for name in ('development', 'holdout'))
        self.assertTrue(development['decision']['pass'])
        self.assertEqual(len(holdout['pairs']), holdout['scheduled_pairs'])
        self.assertEqual(len(holdout['pairs']), 8)
        self.assertFalse(holdout['decision']['pass'])
        self.assertTrue(holdout['decision']['regressed'])
        self.assertEqual(result['status'], 'holdout-rejected')
        self.assertEqual(result['enabled'], initial['enabled'])
        self.assertNotEqual(result['enabled'], result['policies']['candidate'])
        self.assertEqual((self.state / 'enabled.json').read_bytes(), pointer)
        self.assertEqual(json.loads((self.state / result['run'] / 'report.json').read_bytes()),
                         json.loads(evolve.encode(result)))
        self.assertEqual(json.loads((self.state / 'statistical-budget.json').read_bytes())['evaluations'], 2)
        self.assertTrue(exposed.issubset(json.loads((self.state / 'used-holdout.json').read_bytes())))
        self.assertEqual({path: path.read_bytes() for path in preserved}, preserved)
        self.assertFalse((self.state / evolve.PENDING).exists())
        executed = subprocess.run([sys.executable, '-I', str(SCRIPT), 'run-enabled',
                                   '--state', str(self.state), '--seconds', '2'],
                                  input=b'{}', capture_output=True, timeout=5)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertEqual(executed.stdout, b'candidate\n')
        print('EVOLVE_HOLDOUT_REJECTION ' + json.dumps(dict(
            status=result['status'], development_gain=development['decision']['cost_gain'],
            holdout_gain=holdout['decision']['cost_gain'], holdout_pairs=len(holdout['pairs']),
            holdout_alpha=result['holdout_alpha'], pointer_unchanged=True,
            incumbent_sha256=evolve.digest(old_program), history_preserved=True,
            run_enabled_exit=executed.returncode, run_enabled_stdout=executed.stdout.decode())))

    def test_noop_or_overlapping_tasks_refused_before_state_creation(self):
        protocol = self.protocol('bad')
        (protocol.parent / 'candidate.py').write_bytes((protocol.parent / 'baseline.py').read_bytes())
        with self.assertRaisesRegex(evolve.ExperimentError, 'no behavioral'):
            evolve.experiment(protocol, self.state)
        self.assertFalse(self.state.exists())
        protocol = self.protocol('overlap')
        config = json.loads(protocol.read_bytes())
        config['holdout'][0]['input'] = config['development'][0]['input']
        protocol.write_text(json.dumps(config))
        with self.assertRaisesRegex(evolve.ExperimentError, 'distinct'):
            evolve.experiment(protocol, self.state)

    def test_inconclusive_monitor_retains_incumbent_and_does_not_reset_testing_budget(self):
        first = self.protocol('first-monitor')
        with mock.patch.object(evolve, 'trial', side_effect=self.telemetry):
            initial = evolve.experiment(first, self.state)
        fresh = self.protocol('next-monitor', offset=2000)
        with mock.patch.object(evolve, 'trial', side_effect=self.telemetry):
            monitored = evolve.experiment(fresh, self.state)
        # Six positive pairs meet the first alpha=.025 but do not meet the
        # second alpha=.00833. Skip an unwinnable holdout before dispatch.
        holdout = monitored['phases']['holdout']
        self.assertEqual(holdout['decision']['reason'], 'holdout-underpowered')
        self.assertEqual(holdout['pairs'], [])
        self.assertEqual(json.loads((self.state / 'statistical-budget.json').read_bytes())['evaluations'], 1)
        self.assertEqual(monitored['status'], 'retained-insufficient-counterevidence')
        self.assertEqual(monitored['enabled'], initial['enabled'])

    def test_changed_grader_leaves_failed_trace_and_preserves_enabled_policy(self):
        protocol = self.protocol('changed')
        def tamper(*args):
            (protocol.parent / 'grader.py').write_text('changed')
            return self.telemetry(*args)
        with mock.patch.object(evolve, 'trial', side_effect=tamper):
            with self.assertRaisesRegex(evolve.ExperimentError, 'frozen experiment'):
                evolve.experiment(protocol, self.state)
        reports = list(self.state.glob('*/report.json'))
        self.assertEqual(len(reports), 1)
        report = json.loads(reports[0].read_bytes())
        self.assertEqual(report['status'], 'instrument-invalid')
        self.assertEqual(len(report['phases']['development']['pairs']), 1)
        self.assertFalse((self.state / 'enabled.json').exists())

    def test_broken_grader_does_not_withdraw_an_enabled_policy(self):
        first = self.protocol('initial')
        with mock.patch.object(evolve, 'trial', side_effect=self.telemetry):
            initial = evolve.experiment(first, self.state)
        next_protocol = self.protocol('monitor-broken-grader', offset=4000)
        (next_protocol.parent / 'grader.py').write_text('raise RuntimeError("broken instrument")')
        monitored = evolve.experiment(next_protocol, self.state)
        self.assertEqual(monitored['enabled'], initial['enabled'])
        self.assertEqual(monitored['status'], 'instrument-invalid')
        self.assertNotIn('holdout', monitored['phases'])

    def test_former_development_inputs_cannot_be_used_as_holdout(self):
        first = self.protocol('initial')
        with mock.patch.object(evolve, 'trial', side_effect=self.telemetry):
            evolve.experiment(first, self.state)
        second = self.protocol('bad-holdout', offset=-100)
        with self.assertRaisesRegex(evolve.ExperimentError, 'already exposed'):
            evolve.experiment(second, self.state)

    def test_trial_budget_covers_worker_and_grader_together(self):
        import time
        worker = b'import time;time.sleep(.30);print("ok")'
        grader = b'import time;time.sleep(.30);print(\'{"floor":true,"horizon":true,"score":1}\')'
        record, _ = evolve.trial(worker, grader, b'{}', b'{}', .50, time.monotonic() + 5)
        self.assertFalse(record['ok'])
        self.assertIsNone(record['floor'])
        self.assertGreater(record['elapsed'], .30)

    def test_enough_pairs_before_deadline_does_not_qualify_a_partial_phase(self):
        protocol = self.protocol('partial')
        config = json.loads(protocol.read_bytes())
        extra = protocol.parent / 'seventh.json'
        extra.write_text('{"task": 7}')
        config['development'].append({'input': extra.name, 'expected': extra.name})
        protocol.write_text(json.dumps(config))
        clock = [0]
        calls = []

        def advance(*args):
            calls.append(args)
            if len(calls) == 12:
                clock[0] = 11
            return self.telemetry(*args)

        with mock.patch.object(evolve.time, 'monotonic', side_effect=lambda: clock[0]), \
                mock.patch.object(evolve, 'trial', side_effect=advance):
            result = evolve.experiment(protocol, self.state)
        phase = result['phases']['development']
        self.assertEqual(len(phase['pairs']), 6)
        self.assertEqual(phase['decision']['reason'], 'incomplete-phase')
        self.assertNotIn('holdout', result['phases'])
        self.assertNotEqual(result['enabled'], result['policies']['candidate'])

    def test_real_worker_failure_and_timeout_are_measured_not_dropped(self):
        grader = b'import json;print(json.dumps({"floor":True,"horizon":True,"score":1}))\n'
        import time
        failed, output = evolve.trial(b'import sys;sys.exit(9)\n', grader, b'{}', b'{}', 1, time.monotonic() + 3)
        self.assertFalse(failed['ok']); self.assertIn('9', failed['reason'])
        self.assertGreater(failed['elapsed'], 0)
        timed, output = evolve.trial(b'import time;time.sleep(5)\n', grader, b'{}', b'{}', .05, time.monotonic() + 3)
        self.assertFalse(timed['ok']); self.assertEqual(timed['reason'], 'timeout')
        self.assertIsNone(timed['tokens']); self.assertIsNone(timed['money'])


if __name__ == '__main__':
    unittest.main()
