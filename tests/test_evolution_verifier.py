"""Mutate recorded evidence, without executing policies or altering the archive."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / 'examples/evolution-dedupe/verify_agent.py'
ARCHIVE = ROOT / 'docs/evals/agent-evolution/raw-run.tar.xz'


class EvolutionVerifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ARCHIVE.is_file():
            raise unittest.SkipTest('recorded evolution fixture archive unavailable')
        temporary = tempfile.TemporaryDirectory(prefix='goal-verifier-recording-')
        cls.addClassCleanup(temporary.cleanup)
        with tarfile.open(ARCHIVE) as archive:
            archive.extractall(temporary.name, filter='data')
        cls.source = Path(temporary.name) / 'goal-real-evolution-20261111'

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='goal-verifier-mutation-')
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name) / 'recorded-run'
        shutil.copytree(self.source, self.project, copy_function=os.link)

    def replace(self, path, value, json_lines=False):
        # The clone uses hardlinks. Replace an inode; never write through it.
        original = self.source / path.relative_to(self.project)
        before = hashlib.sha256(original.read_bytes()).hexdigest()
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.verifier-test-')
        with os.fdopen(fd, 'w') as stream:
            stream.write(''.join(json.dumps(row)+'\n' for row in value) if json_lines
                         else json.dumps(value, indent=2)+'\n')
        os.replace(temporary, path)
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), before)

    def report(self, evaluation):
        path = next(path for path in (self.project/'state').glob('*/report.json')
                    if json.loads(path.read_bytes()).get('holdout_evaluation') == evaluation)
        return path, json.loads(path.read_bytes())

    def run_verifier(self, error=None, *, optimization=None):
        command = [sys.executable, '-B']
        env = dict(os.environ)
        env.pop('PYTHONOPTIMIZE', None)
        if optimization == '-O':
            command.append('-O')
        elif optimization == 'PYTHONOPTIMIZE=1':
            env['PYTHONOPTIMIZE'] = '1'
        result = subprocess.run([*command, str(VERIFIER), str(self.project)], env=env,
                                capture_output=True, text=True, timeout=30)
        if error is not None:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(error, result.stderr)
            return
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def cost_mutation(self, path, report, phase, factors, *, regressed=False):
        pairs = report['phases'][phase]['pairs']
        for pair, factor in zip(pairs, factors):
            pair['candidate']['elapsed'] = pair['baseline']['elapsed'] * factor
        baseline = sum(pair['baseline']['elapsed'] for pair in pairs)
        candidate = sum(pair['candidate']['elapsed'] for pair in pairs)
        wins = sum(pair['candidate']['elapsed'] < pair['baseline']['elapsed'] for pair in pairs)
        losses = sum(pair['candidate']['elapsed'] > pair['baseline']['elapsed'] for pair in pairs)
        decision = report['phases'][phase]['decision']
        decision.update(cost_gain=(baseline-candidate)/baseline, baseline_seconds=baseline,
                        candidate_seconds=candidate, regressed=regressed, **{'pass': False},
                        reason='no-confirmed-benefit',
                        one_sided_sign_p=sum(math.comb(wins+losses, k) for k in range(wins, wins+losses+1))/2**(wins+losses),
                        paired_seconds_sd=statistics.stdev(pair['baseline']['elapsed']-pair['candidate']['elapsed']
                                                         for pair in pairs))
        ledger_path = path.parent / 'trials.jsonl'
        ledger = [json.loads(line) for line in ledger_path.read_text().splitlines()]
        for row in ledger:
            if row['phase'] == phase and row['side'] == 'candidate':
                row['result'] = pairs[row['index']]['candidate']
        self.replace(ledger_path, ledger, json_lines=True)
        return decision

    def test_original_98_pairs_reconstruct_both_directions_and_transitions(self):
        result = self.run_verifier()
        self.assertEqual((result['pairs'], result['raw_outputs']), (98, 196))
        self.assertEqual([row['status'] for row in result['transitions']],
                         ['enabled', 'withdrawn', 'enabled', 'enabled'])
        withdrawal = result['transitions'][1]['phases']['development']
        self.assertEqual(withdrawal['reverse_sign_p'], 1/64)
        self.assertTrue(withdrawal['regressed'])

    def test_candidate_identity_cannot_borrow_baseline_archive(self):
        path, report = self.report(2)
        report['policies']['candidate'] = report['policies']['baseline']
        self.replace(path, report)
        self.run_verifier('candidate policy does not match frozen program')

    def test_optimized_python_preserves_original_98_pair_verification(self):
        for optimization in ('-O', 'PYTHONOPTIMIZE=1'):
            with self.subTest(optimization=optimization):
                result = self.run_verifier(optimization=optimization)
                self.assertEqual((result['pairs'], result['raw_outputs']), (98, 196))

    def test_optimized_python_rejects_candidate_identity_substitution(self):
        path, report = self.report(2)
        report['policies']['candidate'] = report['policies']['baseline']
        self.replace(path, report)
        for optimization in ('-O', 'PYTHONOPTIMIZE=1'):
            with self.subTest(optimization=optimization):
                self.run_verifier('candidate policy does not match frozen program', optimization=optimization)

    def test_optimized_python_rejects_unjustified_withdrawal(self):
        path, report = self.report(None)
        self.cost_mutation(path, report, 'development', [1.1]*6)
        self.replace(path, report)
        for optimization in ('-O', 'PYTHONOPTIMIZE=1'):
            with self.subTest(optimization=optimization):
                self.run_verifier('policy transition mismatch: expected retained-insufficient-counterevidence',
                                  optimization=optimization)

    def test_grader_identity_is_bound_to_frozen_program(self):
        path, report = self.report(2)
        report['policies']['grader'] = report['policies']['baseline']
        self.replace(path, report)
        self.run_verifier('grader policy does not match frozen program')

    def test_protocol_metadata_cannot_change_frozen_threshold(self):
        path, _ = self.report(None)
        protocol_path = path.parent / 'protocol.json'
        frozen = json.loads(protocol_path.read_bytes())
        frozen['protocol']['minimum_cost_gain'] = .05
        self.replace(protocol_path, frozen)
        self.run_verifier('frozen protocol config mismatch')

    def test_ten_percent_slowdown_does_not_justify_withdrawal(self):
        path, report = self.report(None)
        self.cost_mutation(path, report, 'development', [1.1]*6)
        self.replace(path, report)
        self.run_verifier('policy transition mismatch: expected retained-insufficient-counterevidence')

    def test_regression_flag_cannot_override_frozen_cost_threshold(self):
        path, report = self.report(None)
        self.cost_mutation(path, report, 'development', [1.1]*6, regressed=True)
        self.replace(path, report)
        self.run_verifier('phase regression decision mismatch')

    def test_large_but_inconsistent_slowdown_is_not_confirmed_regression(self):
        path, report = self.report(None)
        decision = self.cost_mutation(path, report, 'development', [2]*3 + [.8]*3)
        self.assertLess(decision['cost_gain'], -.15)
        self.replace(path, report)
        self.run_verifier('policy transition mismatch: expected retained-insufficient-counterevidence')

    def test_inconclusive_holdout_retains_current_policy(self):
        path, report = self.report(3)
        self.cost_mutation(path, report, 'holdout', [1.1]*20)
        report['status'] = 'retained-insufficient-counterevidence'
        report['elapsed'] = sum(pair[side]['elapsed'] for phase in report['phases'].values()
                                for pair in phase['pairs'] for side in ('baseline', 'candidate')) + .1
        self.replace(path, report)
        result = self.run_verifier()
        self.assertEqual(result['transitions'][-1]['status'], 'retained-insufficient-counterevidence')
        self.assertEqual(result['transitions'][-1]['enabled'], result['transitions'][-1]['prior'])

    def test_missed_budget_retains_existing_policy_without_promotion(self):
        path, report = self.report(3)
        report.update(within_budget=False, elapsed=61, status='retained-insufficient-counterevidence')
        self.replace(path, report)
        self.assertEqual(self.run_verifier()['transitions'][-1]['status'], 'retained-insufficient-counterevidence')

    def test_successful_pairs_cannot_promote_outside_budget(self):
        path, report = self.report(2)
        report.update(within_budget=False, elapsed=61)
        self.replace(path, report)
        self.run_verifier('policy transition mismatch: expected run-budget')

    def test_report_cannot_forge_within_budget(self):
        path, report = self.report(2)
        report['elapsed'] = 61
        self.replace(path, report)
        self.run_verifier('run exceeds frozen budget')

    def test_final_pointer_identifies_the_run_that_selected_its_bytes(self):
        path, report = self.report(3)
        selected_path = self.project / 'state/enabled.json'
        selected = json.loads(selected_path.read_bytes())
        selected.update(run=path.parent.name, protocol=report['protocol'])
        self.replace(selected_path, selected)
        self.run_verifier('enabled pointer does not match reconstructed selection')


if __name__ == '__main__':
    unittest.main()
