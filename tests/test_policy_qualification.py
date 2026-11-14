"""Only calibrated, evidence-bound selections can affect later execution.

Trial costs are controlled in these state-machine tests. Known-answer grader
processes, immutable archives, production consumers and legacy recovery are real.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('qualification_fixture', Path(__file__).with_name('test_evolve.py'))
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)
evolve = fixtures.evolve
ROOT = Path(__file__).resolve().parents[1]


class Qualification(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.Evolution()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def enable(self):
        path = self.f.protocol('initial')
        with mock.patch.object(evolve, 'trial', side_effect=self.f.telemetry):
            report = evolve.experiment(path, self.f.state)
        return report, evolve.enabled_policy(self.f.state)

    def test_selection_binds_actual_report_and_runs_exact_archive(self):
        report, selected = self.enable()
        run = self.f.state/report['run']
        self.assertEqual(selected['qualification'], evolve.digest((run/'report.json').read_bytes()))
        output, rc, reason, _ = evolve.run_enabled(self.f.state, 2, b'{}')
        self.assertEqual((output, rc, reason), (b'candidate\n', 0, None))

    def test_missing_binding_requires_requalification_before_execution(self):
        report, selected = self.enable()
        del selected['qualification']
        evolve.atomic(self.f.state/'enabled.json', selected)
        before = {p.relative_to(self.f.state):p.read_bytes() for p in self.f.state.rglob('*') if p.is_file()}
        with mock.patch.object(evolve, 'run_program', side_effect=AssertionError('must not execute legacy selection')):
            with self.assertRaisesRegex(evolve.ExperimentError, 'requalification-required'):
                evolve.run_enabled(self.f.state, 2, b'{}')
        feedback = evolve.feedback(self.f.state, report['run'])
        self.assertEqual(feedback['next_action'], 'requalify-policy')
        self.assertFalse(feedback['qualification']['verified'])
        after = {p.relative_to(self.f.state):p.read_bytes() for p in self.f.state.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_report_or_frozen_evidence_changes_stop_before_program(self):
        report, _ = self.enable()
        run = self.f.state/report['run']
        for name in ('report.json', 'protocol.json', 'frozen/grader.py', 'frozen/good.txt', 'calibration-bad-0.out'):
            with self.subTest(name=name):
                path = run/name
                original = path.read_bytes()
                path.write_bytes(original+b'changed')
                try:
                    with mock.patch.object(evolve, 'run_program', side_effect=AssertionError('must not execute')):
                        with self.assertRaisesRegex(evolve.ExperimentError, 'qualification-invalid'):
                            evolve.run_enabled(self.f.state, 2, b'{}')
                finally:
                    path.write_bytes(original)

    def test_resealed_incomplete_phase_is_not_a_valid_qualification(self):
        report, selected = self.enable()
        report['phases']['holdout']['pairs'].pop()
        path = self.f.state/report['run']/'report.json'
        evolve.atomic(path, report)
        selected['qualification'] = evolve.digest(path.read_bytes())
        evolve.atomic(self.f.state/'enabled.json', selected)
        with self.assertRaisesRegex(evolve.ExperimentError, 'incomplete or ineligible pairs'):
            evolve.run_enabled(self.f.state, 2, b'{}')

    def test_same_bytes_can_requalify_without_resetting_history_and_stale_feedback_is_marked(self):
        initial, legacy = self.enable()
        del legacy['qualification']
        evolve.atomic(self.f.state/'enabled.json', legacy)
        fresh = self.f.protocol('fresh', 1000)
        config = json.loads(fresh.read_bytes())
        for index in (6, 7):
            name = 'holdout-%s.json' % index
            (fresh.parent/name).write_text(json.dumps({'task': 1100+index}))
            config['holdout'].append(dict(input=name, expected=name))
        fresh.write_text(json.dumps(config))
        with mock.patch.object(evolve, 'trial', side_effect=self.f.telemetry):
            report = evolve.experiment(fresh, self.f.state)
        selected = evolve.enabled_policy(self.f.state)
        self.assertEqual(report['status'], 'enabled')
        self.assertEqual(selected['policy'], legacy['policy'])
        self.assertEqual(selected['run'], report['run'])
        self.assertIn('qualification', selected)
        self.assertEqual(evolve.testing_budget(self.f.state)['evaluations'], 2)
        self.assertEqual(evolve.run_enabled(self.f.state, 2, b'{}')[0], b'candidate\n')
        old = evolve.feedback(self.f.state, initial['run'])
        self.assertTrue(old['selection_changed_since_run'])
        self.assertEqual(old['next_action'], 'review-current-selection')

    def test_real_legacy_record_and_pending_recover_without_replaying_or_granting_execution(self):
        folder = self.f.root/'restored'
        folder.mkdir()
        with tarfile.open(ROOT/'docs/evals/execution-evolution-20261114/raw-evolution.tar.gz') as archive:
            archive.extractall(folder, members=[item for item in archive if item.name.startswith('bad-grader-before/state/')], filter='data')
        state = folder/'bad-grader-before/state'
        selected = evolve.enabled_policy(state)
        self.assertNotIn('qualification', selected)
        run = state/selected['run']
        report_bytes = (run/'report.json').read_bytes()
        report = json.loads(report_bytes)
        self.assertNotIn('calibration', report)
        # Original transition schema, with an already published pointer and
        # all archived materials. Recovery must finish without running code.
        materials = {p.relative_to(run).as_posix():evolve.digest(p.read_bytes())
                     for p in run.rglob('*') if p.is_file() and p.name != 'report.json'}
        guard = dict(version=1, phase='transition', run=selected['run'], before=None,
                     after=evolve.blob((state/'enabled.json').read_bytes()), report_before=evolve.blob(report_bytes),
                     report=report, materials=materials)
        evolve.publish_pending(state, guard)
        budget = (state/'statistical-budget.json').read_bytes()
        trials = (run/'trials.jsonl').read_bytes()
        with mock.patch.object(evolve, 'run_program', side_effect=AssertionError('recovery must not replay')):
            self.assertEqual(evolve.recover_policy(state)['status'], 'recovered')
        self.assertEqual((state/'statistical-budget.json').read_bytes(), budget)
        self.assertEqual((run/'trials.jsonl').read_bytes(), trials)
        result = subprocess.run([sys.executable, '-I', str(fixtures.SCRIPT), 'run-enabled',
                                 '--state', str(state), '--seconds', '2'], input=b'{}',
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertEqual(result.stdout, b'')
        self.assertIn(b'policy-requalification-required', result.stderr)


if __name__ == '__main__':
    unittest.main()
