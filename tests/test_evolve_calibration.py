"""Known-answer graders must reject bad artifacts before spending trial budget."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('calibration_fixture', Path(__file__).with_name('test_evolve.py'))
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)
evolve = fixtures.evolve

GRADER = b'''import json,sys
v=json.load(sys.stdin)
ok=v['output'].strip()==v['expected'].strip()
print(json.dumps(dict(floor=ok,horizon=True,score=int(ok))))
'''


class Calibration(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.Evolution()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def protocol(self, name='calibrated', offset=0):
        path = self.f.protocol(name, offset)
        (path.parent/'grader.py').write_bytes(GRADER)
        for name, content in [('good.txt', 'correct'), ('bad.txt', 'WRONG'), ('gold.txt', 'correct')]:
            (path.parent/name).write_text(content)
        config = json.loads(path.read_bytes())
        config['calibration'] = {kind: [dict(output=kind+'.txt', expected='gold.txt')]
                                 for kind in ('good', 'bad')}
        path.write_text(json.dumps(config))
        return path

    def test_always_pass_grader_cannot_enable_incorrect_fast_policy(self):
        path = self.protocol()
        (path.parent/'grader.py').write_text('print(\'{"floor":true,"horizon":true,"score":1}\')')
        with mock.patch.object(evolve, 'trial', side_effect=AssertionError('must not dispatch policies')):
            report = evolve.experiment(path, self.f.state)
        self.assertEqual(report['status'], 'instrument-invalid')
        self.assertEqual(report['calibration']['status'], 'failed')
        self.assertEqual(report['calibration']['cases'][-1]['kind'], 'bad')
        self.assertFalse((self.f.state/'enabled.json').exists())
        self.assertFalse((self.f.state/'statistical-budget.json').exists())
        self.assertFalse((self.f.state/'used-holdout.json').exists())
        self.assertEqual(report['phases'], {})

    def test_omitting_calibration_cannot_qualify_even_a_legacy_shaped_protocol(self):
        path = self.protocol()
        value = json.loads(path.read_bytes())
        del value['calibration']
        path.write_text(json.dumps(value))
        with mock.patch.object(evolve, 'trial', side_effect=AssertionError('must not dispatch')):
            with self.assertRaisesRegex(evolve.ExperimentError, 'calibration-required'):
                evolve.experiment(path, self.f.state)
        self.assertFalse(self.f.state.exists())

    def test_expiry_before_calibration_preserves_selection_without_running_instruments(self):
        path = self.protocol()
        with mock.patch.object(evolve, 'trial', side_effect=self.f.telemetry):
            initial = evolve.experiment(path, self.f.state)
        fresh = self.protocol('expired', 1000)
        value = json.loads(fresh.read_bytes())
        value['budget_seconds'] = 1e-9
        fresh.write_text(json.dumps(value))
        pointer = (self.f.state/'enabled.json').read_bytes()
        testing = (self.f.state/'statistical-budget.json').read_bytes()
        with mock.patch.object(evolve, 'run_program', side_effect=AssertionError('must not run grader or worker')):
            report = evolve.experiment(fresh, self.f.state)
        self.assertEqual(report['status'], 'retained-insufficient-counterevidence')
        self.assertEqual(report['calibration']['status'], 'not-executed')
        self.assertEqual(report['enabled'], initial['enabled'])
        self.assertEqual((self.f.state/'enabled.json').read_bytes(), pointer)
        self.assertEqual((self.f.state/'statistical-budget.json').read_bytes(), testing)

    def test_always_fail_grader_is_detected_on_good_sample(self):
        path = self.protocol()
        (path.parent/'grader.py').write_text('print(\'{"floor":false,"horizon":true,"score":0}\')')
        report = evolve.experiment(path, self.f.state)
        self.assertEqual(report['status'], 'instrument-invalid')
        self.assertEqual(len(report['calibration']['cases']), 1)
        self.assertFalse(report['calibration']['cases'][0]['matched'])

    def test_good_and_bad_calibration_then_original_paired_qualification(self):
        path = self.protocol()
        with mock.patch.object(evolve, 'trial', side_effect=self.f.telemetry):
            report = evolve.experiment(path, self.f.state)
        self.assertEqual(report['status'], 'enabled')
        self.assertEqual(report['calibration']['status'], 'passed')
        self.assertTrue(all(row['matched'] for row in report['calibration']['cases']))
        run = self.f.state/report['run']
        for kind in ('good', 'bad'):
            self.assertEqual((run/'frozen'/(kind+'.txt')).read_bytes(), (path.parent/(kind+'.txt')).read_bytes())
            self.assertTrue((run/('calibration-'+kind+'-0.out')).is_file())
        self.assertEqual(json.loads((self.f.state/'statistical-budget.json').read_bytes())['evaluations'], 1)

    def test_bad_instrument_preserves_incumbent_and_sequential_budget(self):
        path = self.protocol()
        with mock.patch.object(evolve, 'trial', side_effect=self.f.telemetry):
            initial = evolve.experiment(path, self.f.state)
        pointer = (self.f.state/'enabled.json').read_bytes()
        budget = (self.f.state/'statistical-budget.json').read_bytes()
        fresh = self.protocol('broken-monitor', 1000)
        (fresh.parent/'grader.py').write_text('print(\'{"floor":true,"horizon":true,"score":1}\')')
        report = evolve.experiment(fresh, self.f.state)
        self.assertEqual(report['status'], 'instrument-invalid')
        self.assertEqual(report['enabled'], initial['enabled'])
        self.assertEqual((self.f.state/'enabled.json').read_bytes(), pointer)
        self.assertEqual((self.f.state/'statistical-budget.json').read_bytes(), budget)

    def test_calibration_timeout_is_bounded_and_never_a_product_regression(self):
        path = self.protocol()
        config = json.loads(path.read_bytes())
        config['trial_seconds'] = .1
        path.write_text(json.dumps(config))
        (path.parent/'grader.py').write_text('import time; time.sleep(10)')
        report = evolve.experiment(path, self.f.state)
        self.assertEqual(report['status'], 'instrument-invalid')
        self.assertLess(report['elapsed'], 2)
        self.assertEqual(report['phases'], {})

    def test_calibration_source_mutation_cannot_qualify(self):
        path = self.protocol()
        real = evolve.run_program
        def mutate(*args):
            result = real(*args)
            (path.parent/'bad.txt').write_text('changed fixture')
            return result
        with mock.patch.object(evolve, 'run_program', side_effect=mutate), \
                mock.patch.object(evolve, 'trial', side_effect=AssertionError('must not dispatch')):
            with self.assertRaisesRegex(evolve.ExperimentError, 'frozen experiment'):
                evolve.experiment(path, self.f.state)
        report = json.loads(next(self.f.state.glob('*/report.json')).read_bytes())
        self.assertEqual(report['status'], 'instrument-invalid')
        self.assertFalse((self.f.state/evolve.PENDING).exists())

    def test_malformed_or_escaping_calibration_refused_before_state_creation(self):
        path = self.protocol()
        config = json.loads(path.read_bytes())
        invalid = [{}, {'good': [], 'bad': []},
                   {'good': [{'output': '../outside', 'expected': 'gold.txt'}],
                    'bad': [{'output': 'bad.txt', 'expected': 'gold.txt'}]},
                   {'good': [{'output': 'good.txt', 'expected': 'gold.txt'}],
                    'bad': [{'output': 'good.txt', 'expected': 'gold.txt'}]}]
        for value in invalid:
            with self.subTest(value=value):
                path.write_text(json.dumps(dict(config, calibration=value)))
                with self.assertRaises(evolve.ExperimentError):
                    evolve.experiment(path, self.f.state)
                self.assertFalse(self.f.state.exists())

    def test_feedback_reports_real_failure_and_next_nonresetting_sample_requirement(self):
        path = self.protocol()
        with mock.patch.object(evolve, 'trial', side_effect=self.f.telemetry):
            initial = evolve.experiment(path, self.f.state)
        fresh = self.protocol('counterexample', 1000)
        def fail(*args):
            row, output = self.f.telemetry(*args)
            if b'candidate' in args[0]:
                row.update(ok=False, floor=False, regression=True, reason='floor-or-horizon', stderr='actual failure')
            return row, output
        with mock.patch.object(evolve, 'trial', side_effect=fail):
            report = evolve.experiment(fresh, self.f.state)
        feedback = evolve.feedback(self.f.state, report['run'])
        self.assertEqual(feedback['next_action'], 'repair-candidate')
        self.assertEqual(feedback['selection']['policy'], initial['policies']['baseline'])
        self.assertEqual(feedback['findings'][0]['stderr'], 'actual failure')
        self.assertTrue(Path(feedback['findings'][0]['output']).is_file())
        self.assertEqual(feedback['next_holdout']['minimum_pairs'], 7)
        self.assertEqual(feedback['next_holdout']['evaluation'], 2)
        historical = evolve.feedback(self.f.state, initial['run'])
        self.assertTrue(historical['selection_changed_since_run'])
        self.assertEqual(historical['next_action'], 'review-current-selection')
        result = subprocess.run([sys.executable, '-I', str(fixtures.SCRIPT), 'feedback',
                                 '--state', str(self.f.state), '--run', report['run']],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), feedback)

    def test_feedback_refuses_path_escape_and_pending_transition(self):
        path = self.protocol()
        with mock.patch.object(evolve, 'trial', side_effect=self.f.telemetry):
            report = evolve.experiment(path, self.f.state)
        with self.assertRaisesRegex(evolve.ExperimentError, 'run'):
            evolve.feedback(self.f.state, '../escape')
        (self.f.state/evolve.PENDING).write_text('{}')
        with self.assertRaisesRegex(evolve.ExperimentError, 'recovery-required'):
            evolve.feedback(self.f.state, report['run'])


if __name__ == '__main__':
    unittest.main()
