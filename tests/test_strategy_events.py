"""W4: repeated claims and new readings must not fabricate artifact gains."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StrategyEvents(unittest.TestCase):
    def run_kernel(self, log, scores, objective='maximize'):
        with tempfile.TemporaryDirectory(prefix='goal-events-') as tmp:
            root = Path(tmp)
            (root / 'log').write_text(log); (root / 'scores').write_text(scores)
            result = subprocess.run(['gawk', '-v', 'obj=' + objective, '-v', 'stalled=1',
                                     '-f', str(ROOT / 'scripts/goal_strategy.awk'),
                                     str(root / 'scores'), str(root / 'log')], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

    def blocks(self, identities, claims=None):
        result = ''
        for index, identity in enumerate(identities, 1):
            result += '## iteration %s\ntask=T1[crew:1]\nstrategy=A\n' % index
            result += 'exit_signal=%s\n' % ('yes' if claims and index in claims else 'no')
            if identity is not None:
                result += 'digest=%s\n' % ('v2-' + identity * 64)
        return result

    def test_actual_three_round_case_is_one_artifact_and_two_claims(self):
        raw = (ROOT / 'examples/case-jsonl-cli/results/repair-loop-log.md').read_text()
        output = self.run_kernel(raw, '', objective='none')
        self.assertIn('artifact-versions=1 acceptance-claims=2 unchanged-artifact-rounds=2', output)
        self.assertIn('artifact-stagnation=2', output)
        self.assertIn('digest-scope=legacy-unverified', output)
        self.assertNotIn('promote:', output)

    def test_same_artifact_score_changes_are_information_not_strategy_gain(self):
        output = self.run_kernel(self.blocks(['a', 'a', 'a'], {2, 3}), '1|0|none|A\n2|100|none|A\n3|200|none|A\n')
        self.assertIn('measurement-revisions=2', output)
        self.assertIn('artifact-stagnation=2', output)
        self.assertIn('STRATEGY-PICK prefer=none', output)
        self.assertNotIn('-> exploit', output)
        self.assertNotIn('eval-gap:', output)
        self.assertNotIn('promote:', output)

    def test_restoration_and_missing_identity_do_not_earn_fresh_gain(self):
        restored = self.run_kernel(self.blocks(['a', 'b', 'a']), '1|0|none|A\n2|1|none|A\n3|2|none|A\n')
        self.assertIn('restorations=1', restored)
        self.assertIn('strategy=A n=0 unmeasured', restored)
        missing = self.run_kernel(self.blocks(['a', None, 'b']), '1|0|none|A\n2|100|none|A\n3|200|none|A\n')
        self.assertIn('unknown-artifact-rounds=1', missing)
        self.assertNotIn('-> exploit', missing)

    def test_real_controller_same_artifact_claims_do_not_create_strategy_benefit(self):
        ctl = ROOT / 'scripts/goal_ctl.sh'
        with tempfile.TemporaryDirectory(prefix='goal-event-controller-') as tmp:
            project = Path(tmp)
            def call(*args):
                result = subprocess.run(['bash', str(ctl), *args, '--project', str(project)],
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout
            call('init')
            (project / '.goal/goal.md').write_text(
                '# Goal\n\nobjective: maximize AC-1\nhorizon-waived: deterministic telemetry fixture\n\n'
                '## Acceptance criteria\n\n'
                '- AC-1 | score | check: `cat .goal/evidence/score` | expected: maximize\n\n'
                '## Approval\n\napproved: PENDING\n')
            call('stamp', '--auto')
            (project / 'artifact.txt').write_text('one unchanged artifact\n')
            for iteration, score in enumerate((10, 20, 30), 1):
                (project / '.goal/evidence/score').write_text(str(score) + '\n')
                call('close-iteration', '--task', 'T1', '--files', 'artifact.txt',
                     '--checks-pass', '1', '--checks-fail', '0', '--checks-unverifiable', '0',
                     '--progress', 'yes', '--exit-signal', 'no' if iteration == 1 else 'yes',
                     '--score', str(score), '--strategy', 'A', '--no-gate')
            output = call('status')
            self.assertIn('artifact-versions=1 acceptance-claims=2 unchanged-artifact-rounds=2', output)
            self.assertIn('measurement-revisions=2', output)
            self.assertIn('artifact-stagnation=2', output)
            self.assertIn('STRATEGY-PICK prefer=none', output)


if __name__ == '__main__':
    unittest.main()
