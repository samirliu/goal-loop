"""Exercise scoped rollback through the production gate and recovery command."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


class ProjectCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='goal-incumbent-')
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)
        self.state = self.project / '.goal'
        self.ctl('init')

    def run_entry(self, cmd, *args, expected=0, env=None, input=None):
        result = subprocess.run([*cmd, *args, '--project', str(self.project)],
                                capture_output=True, text=True, timeout=15, env=env, input=input)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout, result.stderr

    def ctl(self, *args, **kwargs):
        return self.run_entry(['bash', str(SCRIPTS / 'goal_ctl.sh')], *args, **kwargs)

    def gate(self, *args, **kwargs):
        return self.run_entry(['bash', str(SCRIPTS / 'goal_gate.sh')], *args, **kwargs)

    def checkpoint(self, *args, **kwargs):
        return self.run_entry([sys.executable, '-I', str(SCRIPTS / 'goal_store.py'), 'incumbent'],
                              *args, **kwargs)


class Incumbent(ProjectCase):
    def setUp(self):
        super().setUp()
        (self.state / 'goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | good bytes | check: `grep -qx good a.txt` | expected: exit=0\n\n'
            '## Approval\n\napproved: PENDING\n')
        self.a = self.project / 'a.txt'
        self.b = self.project / 'b.txt'
        self.new = self.project / 'new.txt'
        self.a.write_text('good\n')
        self.a.chmod(0o755)
        self.b.write_text('keep\n')
        self.ctl('stamp', '--auto')
        self.ctl('close-iteration', '--task', 'T1', '--files', 'a.txt,b.txt',
                 '--checks-pass', '1', '--checks-fail', '0', '--checks-unverifiable', '0',
                 '--progress', 'yes', '--exit-signal', 'yes', '--adversarial', 'clear',
                 '--adversarial-note', 'exact bytes checked', '--no-gate')

    def pair(self):
        base = self.checkpoint('save', '--file', 'a.txt', '--file', 'b.txt', '--file', 'new.txt')[0].strip()
        self.a.write_text('bad\n')
        self.a.chmod(0o600)
        self.b.unlink()
        self.new.write_text('candidate addition\n')
        candidate = self.checkpoint('candidate', '--base', base)[0].strip()
        return ('--base', base, '--candidate', candidate)

    def test_restored_bytes_and_permissions_reproduce_original_go(self):
        args = self.pair()
        self.gate('--verify', expected=2)
        head = (self.state / 'store/commits/current').read_bytes()
        self.checkpoint('restore', *args)
        self.assertEqual(self.a.read_text(), 'good\n')
        self.assertEqual(self.a.stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.b.read_text(), 'keep\n')
        self.assertFalse(self.new.exists())
        self.assertEqual((self.state / 'store/commits/current').read_bytes(), head)
        self.assertIn('GATE: GO', self.gate('--check')[0])
        self.checkpoint('restore', *args)

    def test_owned_user_edit_refuses_all_writes_unowned_edit_survives(self):
        args = self.pair()
        unrelated = self.project / 'user.txt'
        unrelated.write_text('user-owned\n')
        self.new.write_text('edited by user\n')
        self.checkpoint('restore', *args, expected=4)
        self.assertEqual(self.a.read_text(), 'bad\n')
        self.assertFalse(self.b.exists())
        self.assertFalse((self.state / 'store/pending').exists())
        self.new.write_text('candidate addition\n')
        self.checkpoint('restore', *args)
        self.assertEqual(unrelated.read_text(), 'user-owned\n')
        self.gate('--verify')

    def test_interrupted_restore_blocks_gate_and_recovery_preserves_conflicts(self):
        args = self.pair()
        self.checkpoint('restore', *args, expected=91,
                        env=dict(os.environ, GOAL_INCUMBENT_FAULT='first-file'))
        self.assertTrue((self.state / 'store/pending').exists())
        self.assertIn('recovery-required', self.gate('--check', expected=4)[1])
        self.assertEqual(self.a.read_text(), 'good\n')
        self.assertFalse(self.b.exists())
        self.new.write_text('new user content\n')
        self.assertIn('restore conflict', self.ctl('recover', expected=4)[1])
        self.assertFalse(self.b.exists())
        self.assertEqual(self.new.read_text(), 'new user content\n')
        self.new.write_text('candidate addition\n')
        self.ctl('recover')
        self.assertFalse((self.state / 'store/pending').exists())
        self.gate('--check')

    def test_failed_gate_or_unsafe_scope_cannot_be_saved_as_incumbent(self):
        self.checkpoint('save', '--file', '.goal/state.rec', expected=4)
        link = self.project / 'alias.txt'
        link.symlink_to(self.a)
        self.checkpoint('save', '--file', 'alias.txt', expected=4)
        link.unlink()
        self.a.write_text('bad\n')
        self.checkpoint('save', '--file', 'a.txt', expected=4)
        self.assertFalse((self.state / 'store/incumbents').exists())

    def test_evolution_rejects_unrelated_checkpoint_pair_before_dispatch(self):
        _, base, _, candidate = self.pair()
        protocol = dict(version=2, baseline=candidate, candidate=base, entry='a.txt',
                        grader='absent.py', development=[], holdout=[],
                        minimum_pairs=6, minimum_cost_gain=.15, quality_tolerance=0,
                        trial_seconds=1, budget_seconds=10,
                        calibration=dict(good=[dict(output='good.txt', expected='gold.txt')],
                                         bad=[dict(output='bad.txt', expected='gold.txt')]))
        # Pair preflight must reject before reading the absent grader/fixtures.
        path = self.project / 'protocol.json'
        path.write_text(json.dumps(protocol))
        trial_state = self.project / '.goal/proposals/test'
        _, error = self.run_entry([sys.executable, '-I', str(SCRIPTS / 'goal_evolve.py')],
                                  str(path), '--state', str(trial_state), expected=4)
        self.assertIn('scope, lineage or frozen contract changed', error)
        self.assertFalse(trial_state.exists())


class IntermediateCheckpoint(ProjectCase):
    def setUp(self):
        super().setUp()
        (self.state / 'goal.md').write_text(
            '# Goal\n\n## Objective\n\nexit: forge\nobjective: maximize AC-1\n\n'
            '## Acceptance criteria\n\n'
            '- AC-1 | score | check: `cat score.txt` | baseline: abs | expected: maximize\n'
            '- AC-2 | floor | check: `grep -qx ready artifact.txt` | expected: exit=0\n'
            '- AC-3 | horizon | check: `cat artifact.txt` | calib: good=good.txt bad=bad.txt | expected: judged\n\n'
            '## Approval\n\napproved: PENDING\n')
        self.artifact = self.project / 'artifact.txt'
        self.artifact.write_text('ready\n')
        (self.project / 'score.txt').write_text('10\n')
        (self.project / 'good.txt').write_text('ready\n')
        (self.project / 'bad.txt').write_text('broken\n')
        (self.project / 'probe-input.txt').write_text('ready\n')
        (self.project / 'probe.sh').write_text('#!/usr/bin/env bash\ntest "$(cat)" = ready\n')
        (self.state / 'forge-plan.json').write_text(json.dumps(
            dict(version=1, instruments=['probe.sh'], cases=[
                dict(id='ready', dimension='readiness', input='probe-input.txt', command=['bash', 'probe.sh'])],
                 blind_spots=['single readiness fixture'])))
        self.ctl('stamp', '--auto')
        (self.state / 'work-plan.md').write_text('- [ ] T2 further exploration | files=artifact.txt\n')
        self.book()

    def book(self):
        self.ctl('close-iteration', '--task', 'T1', '--files', 'artifact.txt,score.txt',
                 '--checks-pass', '2', '--checks-fail', '0', '--checks-unverifiable', '0',
                 '--progress', 'yes', '--exit-signal', 'no', '--adversarial', 'clear',
                 '--adversarial-note', 'reviewed raw floor results', '--no-gate', '--dry', 'no',
                 '--strategy', 'baseline', '--score', '10', '--judge-score', '1')

    def bind(self, horizon='PASS', calibrate=True):
        self.ctl('bind', input=self.bind_rows(horizon, calibrate))

    def bind_rows(self, horizon='PASS', calibrate=True):
        digest = self.gate('--digest')[0].strip()
        iteration = next(line.split('=')[1] for line in (self.state / 'state.rec').read_text().splitlines()
                         if line.startswith('iteration='))
        sha = hashlib.sha256(self.artifact.read_bytes()).hexdigest()
        evidence = f'artifact: artifact.txt digest: {sha}' if horizon == 'PASS' else 'PROBE=inspect REASON=missing'
        rows = [f'AC-3|{horizon}|{iteration}|{digest}|cat artifact.txt|{evidence}']
        if calibrate:
            rows.extend([f'AC-3#good|PASS|{iteration}|{digest}|cat good.txt|good.txt',
                         f'AC-3#bad|FAIL|{iteration}|{digest}|cat bad.txt|bad.txt'])
        return '\n'.join(rows) + '\n'

    def save(self, **kwargs):
        return self.checkpoint('save', '--intermediate', '--file', 'artifact.txt', '--file', 'score.txt', **kwargs)

    def test_intermediate_restore_requalifies_without_claiming_completion(self):
        self.assertIn('best_score=none\n', (self.state / 'state.rec').read_text())
        self.bind()
        self.assertIn('best_score=10\n', (self.state / 'state.rec').read_text())
        self.assertIn('not-claimed', self.gate('--check', expected=2)[1])
        self.checkpoint('save', '--file', 'artifact.txt', expected=4)
        base = self.save()[0].strip()
        proof = json.loads((self.state / 'store/incumbents' / (base + '.json')).read_bytes())['proof']
        self.assertIn(b'GATE: CHECKPOINT-OK', base64.b64decode(proof))
        self.assertNotIn(b'GATE: GO', base64.b64decode(proof))
        self.artifact.write_text('broken\n')
        candidate = self.checkpoint('candidate', '--base', base)[0].strip()
        self.checkpoint('restore', '--base', base, '--candidate', candidate)
        self.assertIn('GATE: CHECKPOINT-OK', self.gate('--checkpoint')[0])
        self.assertIn('not-claimed', self.gate('--check', expected=2)[1])

    def test_checkpoint_refuses_missing_uncalibrated_and_unverifiable_horizon(self):
        self.assertIn('not-covered:AC-3', self.save(expected=4)[1])
        self.bind(horizon='UNVERIFIABLE', calibrate=False)
        self.assertIn('checkpoint-unverifiable', self.save(expected=4)[1])
        self.book()
        self.bind(calibrate=False)
        self.assertIn('calibration-missing:AC-3/good', self.save(expected=4)[1])
        self.assertFalse((self.state / 'store/incumbents').exists())

    def test_checkpoint_reruns_floor_and_honors_inherited_deadline(self):
        self.artifact.write_text('broken\n')
        self.book()
        self.bind()
        self.assertIn('open-FAIL:AC-2', self.save(expected=4)[1])
        self.artifact.write_text('ready\n')
        self.book()
        self.bind()
        env = dict(os.environ, GOAL_RUNNER_MONOTONIC_END='0')
        self.assertIn('time-budget-exhausted', self.save(expected=4, env=env)[1])
        self.assertFalse((self.state / 'store/incumbents').exists())

    def test_failed_horizon_cannot_advance_an_otherwise_feasible_score(self):
        self.bind()
        (self.project / 'score.txt').write_text('100\n')
        self.book()
        self.bind(horizon='FAIL')
        self.assertIn('best_score=10\n', (self.state / 'state.rec').read_text())
        self.assertIn('2|100|', (self.state / 'scores.rec').read_text())
        self.assertIn('open-FAIL:AC-3', self.gate('--quality', expected=2)[1])

    def test_qualification_and_bind_recover_on_both_sides_of_commit(self):
        from test_mutation_commit import MutationCommit
        source = self.project
        for point in ('generation-published', 'pointer-published'):
            with self.subTest(point=point):
                self.project = source.parent / (source.name + '-' + point)
                self.addCleanup(shutil.rmtree, self.project)
                shutil.copytree(source, self.project)
                self.state = self.project / '.goal'
                control = Path(tempfile.mkdtemp(prefix='goal-bind-fault-'))
                self.addCleanup(shutil.rmtree, control)
                env = MutationCommit.fault_env(self, control, point)
                rows = self.bind_rows()
                killed = MutationCommit.call(self, self.project, ['bind', '--operation-id', 'qualify-once'],
                                             input=rows, env=env)
                self.assertNotEqual(killed.returncode, 0)
                self.ctl('recover')
                if point == 'generation-published':
                    self.assertIn('best_score=none\n', (self.state / 'state.rec').read_text())
                    self.ctl('bind', '--operation-id', 'qualify-once', input=rows)
                else:
                    self.assertIn('best_score=10\n', (self.state / 'state.rec').read_text())
                before = (self.state / 'state.rec').read_bytes()
                self.assertIn('REPLAY', self.ctl('bind', '--operation-id', 'qualify-once', input=rows)[0])
                self.assertEqual(before, (self.state / 'state.rec').read_bytes())
                self.gate('--checkpoint')


class QualifiedWatermark(ProjectCase):
    def setup_goal(self, direction='maximize', floor='grep -qx ready artifact.txt'):
        (self.state / 'goal.md').write_text(
            '# Goal\n\n## Objective\n\nobjective: ' + direction + ' AC-1\n'
            'horizon-waived: exact readiness floor for this focused counterexample\n\n'
            '## Acceptance criteria\n\n'
            '- AC-1 | score | check: `cat score.txt` | expected: ' + direction + '\n'
            '- AC-2 | floor | check: `' + floor + '` | expected: exit=0\n\n'
            '## Approval\n\napproved: PENDING\n')
        (self.project / 'artifact.txt').write_text('ready\n')
        (self.project / 'score.txt').write_text('10\n')
        self.ctl('stamp', '--auto')

    def book(self, score, judge=None):
        self.ctl('close-iteration', '--task', 'T1', '--files', 'artifact.txt,score.txt',
                 '--checks-pass', '2', '--checks-fail', '0', '--checks-unverifiable', '0',
                 '--progress', 'yes', '--exit-signal', 'yes', '--adversarial', 'clear',
                 '--adversarial-note', 'read actual floor result', '--no-gate',
                 '--strategy', 'baseline', '--score', str(score),
                 *(('--judge-score', str(judge)) if judge is not None else ()))

    def check_failed_candidate(self, direction, infeasible):
        self.setup_goal(direction)
        self.book(10, judge=1)
        base = self.checkpoint('save', '--file', 'artifact.txt', '--file', 'score.txt')[0].strip()
        (self.project / 'artifact.txt').write_text('broken\n')
        (self.project / 'score.txt').write_text(str(infeasible) + '\n')
        self.book(infeasible, judge=.2)
        self.assertIn('best_score=10\n', (self.state / 'state.rec').read_text())
        self.assertIn('2|' + str(infeasible) + '|', (self.state / 'scores.rec').read_text())
        candidate = self.checkpoint('candidate', '--base', base)[0].strip()
        self.checkpoint('restore', '--base', base, '--candidate', candidate)
        self.book(10, judge=1)
        self.assertIn('score=10 best=10', self.gate('--check')[0])
        self.assertIn('last_quality_judge=1\n', (self.state / 'state.rec').read_text())

    def test_infeasible_maximum_cannot_poison_restored_incumbent(self):
        self.check_failed_candidate('maximize', 100)

    def test_infeasible_minimum_cannot_poison_restored_incumbent(self):
        self.check_failed_candidate('minimize', -100)

    def test_feasible_lower_score_does_not_replace_qualified_best(self):
        self.setup_goal()
        self.book(10)
        (self.project / 'score.txt').write_text('7\n')
        self.book(7)
        self.assertIn('best_score=10\n', (self.state / 'state.rec').read_text())
        self.assertIn('score-regressed', self.gate('--check', expected=2)[1])
        self.assertIn('GATE: QUALITY-OK', self.gate('--quality')[0])

    def test_improving_objective_with_declining_judge_still_fails(self):
        self.setup_goal()
        self.book(10, judge=1)
        (self.project / 'score.txt').write_text('20\n')
        self.book(20, judge=.2)
        self.assertIn('best_score=10\n', (self.state / 'state.rec').read_text())
        self.assertIn('DIVERGENCE:score-vs-judge', self.gate('--check', expected=2)[1])

    def test_same_score_qualified_judge_is_used_for_next_comparison(self):
        self.setup_goal()
        self.book(10, judge=1)
        self.book(10, judge=2)
        self.assertIn('last_quality_judge=2\n', (self.state / 'state.rec').read_text())
        (self.project / 'score.txt').write_text('100\n')
        self.book(100, judge=1.5)
        self.assertIn('best_score=10\n', (self.state / 'state.rec').read_text())
        self.assertIn('DIVERGENCE:score-vs-judge', self.gate('--check', expected=2)[1])

    def test_lower_minimize_score_with_declining_judge_still_fails(self):
        self.setup_goal('minimize')
        (self.project / 'score.txt').write_text('20\n')
        self.book(20, judge=8)
        (self.project / 'score.txt').write_text('10\n')
        self.book(10, judge=3)
        self.assertIn('best_score=20\n', (self.state / 'state.rec').read_text())
        failure = self.gate('--check', expected=2)[1]
        self.assertIn('DIVERGENCE:score-vs-judge', failure)
        self.assertIn('dir=minimize', failure)

    def test_unfrozen_prose_cannot_reset_a_qualified_watermark(self):
        self.setup_goal()
        (self.project / 'score.txt').write_text('100\n')
        self.book(100)
        basis = next(line for line in (self.state / 'state.rec').read_text().splitlines()
                     if line.startswith('best_score_basis='))
        with (self.state / 'goal.md').open('a') as stream:
            stream.write('\n## Notes\nReviewed on Wednesday.\n')
        (self.project / 'score.txt').write_text('10\n')
        self.book(10)
        self.assertIn(basis, (self.state / 'state.rec').read_text())
        self.assertIn('best_score=100\n', (self.state / 'state.rec').read_text())
        self.assertIn('score-regressed', self.gate('--check', expected=2)[1])

    def test_temporary_contract_tamper_cannot_erase_prior_qualification(self):
        self.setup_goal()
        (self.project / 'score.txt').write_text('100\n')
        self.book(100)
        original = (self.state / 'goal.md').read_bytes()
        (self.state / 'goal.md').write_bytes(original.replace(b'floor |', b'altered floor |'))
        (self.project / 'score.txt').write_text('10\n')
        self.book(10)
        self.assertIn('best_score=100\n', (self.state / 'state.rec').read_text())
        (self.state / 'goal.md').write_bytes(original)
        self.book(10)
        self.assertIn('score-regressed', self.gate('--check', expected=2)[1])

    def check_corrupting_qualifier(self, target):
        floor = 'if test -e .goal/evidence/trip; then echo contamination >> .goal/' + target + '; fi; grep -qx ready artifact.txt'
        self.setup_goal(floor=floor)
        self.book(10)
        names = ['state.rec', 'loop-log.md', 'verdicts.rec', 'evidence/raw/1.txt', 'store/commits/current']
        before = {name: (self.state / name).read_bytes() for name in names}
        (self.state / 'evidence/trip').touch()
        failure = self.ctl('bind', input='AC-1|PASS|1|unused|cat score.txt|observed\n', expected=4)
        self.assertIn('corrupted its input', failure[1])
        self.assertTrue((self.state / 'store/pending').exists())
        self.assertEqual(before['store/commits/current'], (self.state / 'store/commits/current').read_bytes())
        self.ctl('recover')
        self.assertEqual(before, {name: (self.state / name).read_bytes() for name in names})
        (self.state / 'evidence/trip').unlink()
        self.gate('--check')

    def test_bind_qualifier_cannot_publish_log_mutation(self):
        self.check_corrupting_qualifier('loop-log.md')

    def test_bind_qualifier_cannot_publish_verdict_mutation_in_its_own_scope(self):
        self.check_corrupting_qualifier('verdicts.rec')

    def test_bind_qualifier_cannot_publish_state_mutation_in_its_own_scope(self):
        self.check_corrupting_qualifier('state.rec')

    def test_bind_qualifier_cannot_publish_historical_raw_mutation(self):
        self.check_corrupting_qualifier('evidence/raw/1.txt')


if __name__ == '__main__':
    unittest.main()
