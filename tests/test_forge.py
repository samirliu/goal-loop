"""Forge exit uses executed, frozen probes and reports its bounded coverage."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
CTL, GATE = (ROOT / 'scripts' / name for name in ('goal_ctl.sh', 'goal_gate.sh'))


class ForgeCoverage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='goal-forge-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / '.goal'
        self.call(CTL, 'init')
        (self.state / 'goal.md').write_text(
            '# Goal\n\n## Objective\n\nexit: forge\n\n'
            '## Acceptance criteria\n\n'
            '- AC-1 | function exists | check: `grep -q dedupe algorithm.py` | expected: exit=0\n\n'
            '## Budget\n\ncheck_timeout=1\n\n## Approval\n\napproved: PENDING\n')
        (self.root / 'algorithm.py').write_text('def dedupe(items):\n    return sorted(set(items))\n')
        (self.root / 'probe.py').write_text(
            'import json,sys,time\nfrom pathlib import Path\nfrom algorithm import dedupe\n'
            'if Path(".goal/evidence/slow").exists(): time.sleep(5)\n'
            'items=json.load(sys.stdin)\nexpected=[]\n'
            'for value in sorted(items):\n'
            '    if value not in expected: expected.append(value)\n'
            'actual=dedupe(items)\n'
            'print(json.dumps(dict(expected=expected,actual=actual)))\n'
            'sys.exit(0 if expected == actual else 1)\n')
        cases = []
        for name, data in (('positive', [4, 2, 4]), ('negative', [-3, 2, -3])):
            (self.root / (name + '.json')).write_text(json.dumps(data))
            cases.append(dict(id=name, dimension='integer-sign', input=name + '.json',
                              command=[sys.executable, '-B', 'probe.py']))
        self.plan = dict(version=1, instruments=['probe.py'], cases=cases,
                         blind_spots=['non-integer inputs and lists over three elements'])
        self.plan_path = self.state / 'forge-plan.json'
        self.plan_path.write_text(json.dumps(self.plan))

    def call(self, script, *args, expected=0, env=None):
        result = subprocess.run(['bash', str(script), *args, '--project', str(self.root)],
                                capture_output=True, text=True, env=env, timeout=15)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def stamp(self):
        self.call(CTL, 'stamp', '--auto')

    def critic(self, findings=''):
        iteration = int(next(line.split('=')[1] for line in (self.state / 'state.rec').read_text().splitlines()
                             if line.startswith('iteration='))) + 1
        artifact = self.call(GATE, '--digest').stdout.strip()
        frozen = (self.state / 'check_freeze').read_text().split('forge=')[1].split(';')[0]
        (self.state / ('evidence/critic-iter-%s.md' % iteration)).write_text(
            'ITERATION|' + str(iteration) + '\nARTIFACT|' + artifact + '\nPLAN|' + frozen + '\n'
            + findings + 'CLEAR|reviewed the declared finite scope\n')

    def close(self, dry='yes', env=None, findings='', refresh_critic=True):
        if dry == 'yes' and refresh_critic:
            self.critic(findings)
        return self.call(CTL, 'close-iteration', '--task', 'T1', '--files', 'algorithm.py',
                         '--checks-pass', '1', '--checks-fail', '0', '--checks-unverifiable', '0',
                         '--progress', 'yes', '--exit-signal', 'yes', '--adversarial', 'clear',
                         '--adversarial-note', 'checked finite input domain against independent reference',
                         '--dry', dry, '--no-gate', env=env)

    def report(self, iteration):
        rows = [line[7:] for line in (self.state / ('evidence/raw/%s.txt' % iteration)).read_text().splitlines()
                if line.startswith('FORGE: ')]
        self.assertEqual(len(rows), 1)
        return json.loads(rows[0])

    def test_stamp_requires_a_declared_probe_scope_before_any_commit(self):
        self.plan_path.unlink()
        before = (self.state / 'store/commits/current').read_bytes()
        self.call(CTL, 'stamp', '--auto', expected=2)
        self.assertEqual(before, (self.state / 'store/commits/current').read_bytes())

    def test_repeated_clear_records_stability_and_explicit_blind_spots(self):
        self.stamp()
        scope = (self.state / 'evidence/raw/0.txt').read_text()
        self.assertTrue(scope.startswith('FORGE-SCOPE: '))
        frozen = json.loads(scope[13:])
        self.assertEqual(frozen['definition'], self.plan)
        self.assertIn('negative.json', frozen['files'])
        for _ in range(3):
            self.close()
        first, repeated = self.report(1), self.report(3)
        self.assertEqual(first['new_cases'], 2)
        self.assertEqual(repeated['new_cases'], 0)
        self.assertEqual(repeated['repeated_cases'], 2)
        self.assertEqual(repeated['remaining'], [])
        self.assertEqual(repeated['blind_spots'], self.plan['blind_spots'])
        gate = self.call(GATE, '--check')
        self.assertIn('coverage=declared', gate.stdout)

    def test_clear_receipts_without_dry_probes_never_complete_forge(self):
        self.stamp()
        for _ in range(3):
            self.close(dry='no')
        self.assertIn('not-dry', self.call(GATE, '--check', expected=2).stderr)
        self.assertFalse(any('FORGE: ' in p.read_text() for p in (self.state / 'evidence/raw').glob('*.txt')))

    def test_open_critic_finding_and_stale_critic_cannot_earn_dry_credit(self):
        self.stamp()
        self.close(findings='FINDING|size|large instances remain unproven|probe five items\n')
        report = self.report(1)
        self.assertFalse(report['qualified'])
        self.assertEqual(report['reason'], 'critic-has-findings')
        self.assertEqual(report['cases'], [])
        self.assertIn('dry_streak=0', (self.state / 'state.rec').read_text())
        self.critic()
        stale = self.state / 'evidence/critic-iter-2.md'
        stale.write_text(stale.read_text().replace('ITERATION|2', 'ITERATION|1'))
        self.close(refresh_critic=False)
        self.assertEqual(self.report(2)['reason'], 'critic evidence is stale or unbound')
        self.close(refresh_critic=False)
        self.assertEqual(self.report(3)['reason'], 'critic-evidence-missing')

    def test_declared_new_input_exposes_a_defect_missed_by_positive_only_probe(self):
        (self.root / 'algorithm.py').write_text('def dedupe(items):\n    return sorted({x for x in items if x >= 0})\n')
        self.stamp()
        for _ in range(3):
            self.close()
        report = self.report(3)
        self.assertFalse(report['qualified'])
        self.assertEqual(report['cases'][0]['result'], 0)
        self.assertEqual(report['cases'][1]['result'], 1)
        self.assertIn('expected', report['cases'][1]['stdout'])
        self.assertIn('dry_streak=0', (self.state / 'state.rec').read_text())
        self.call(GATE, '--check', expected=2)

    def test_plan_input_and_checker_edits_invalidate_the_frozen_probe_scope(self):
        self.stamp()
        before = (self.state / 'store/commits/current').read_bytes()
        (self.root / 'negative.json').write_text('[2]')
        self.close()
        self.assertFalse(self.report(1)['qualified'])
        self.assertIn('dry_streak=0', (self.state / 'state.rec').read_text())
        self.assertNotEqual(before, (self.state / 'store/commits/current').read_bytes())
        self.call(GATE, '--check', expected=2)

    def test_exhausted_budget_preserves_unprobed_scope_and_cannot_earn_dry_credit(self):
        self.stamp()
        (self.state / 'evidence/slow').touch()
        self.close(env=dict(os.environ, GOAL_RUNNER_MONOTONIC_END=str(time.monotonic() + .8)))
        report = self.report(1)
        self.assertFalse(report['qualified'])
        self.assertTrue(report['remaining'])
        self.assertIn('dry_streak=0', (self.state / 'state.rec').read_text())

    def test_failed_floor_skips_probe_spend_and_cannot_become_dry(self):
        self.stamp()
        (self.root / 'algorithm.py').write_text('x = 1\n')
        self.close()
        report = self.report(1)
        self.assertFalse(report['qualified'])
        self.assertEqual(report['cases'], [])
        self.assertEqual(report['reason'], 'floor-verification-incomplete')
        self.assertIn('dry_streak=0', (self.state / 'state.rec').read_text())

    def test_renamed_duplicate_probe_does_not_earn_new_coverage(self):
        duplicate = dict(self.plan['cases'][0], id='renamed', dimension='renamed-dimension')
        self.plan['cases'][1] = duplicate
        self.plan_path.write_text(json.dumps(self.plan))
        self.stamp()
        self.close()
        report = self.report(1)
        self.assertTrue(report['qualified'])
        self.assertEqual(report['new_cases'], 1)
        self.assertEqual(report['repeated_cases'], 1)

    def test_probe_ledger_mutation_leaves_a_recoverable_pending_transaction(self):
        probe = self.root / 'probe.py'
        probe.write_text(probe.read_text() + '\n')  # actual mutating instrument must be frozen
        source = probe.read_text().replace('sys.exit(0 if expected == actual else 1)',
                                          'Path(".goal/state.rec").write_text("corrupted\\n")')
        probe.write_text(source)
        self.stamp()
        self.critic()
        head = (self.state / 'store/commits/current').read_bytes()
        result = self.call(CTL, 'close-iteration', '--task', 'T1', '--files', 'algorithm.py',
                           '--checks-pass', '1', '--checks-fail', '0', '--checks-unverifiable', '0',
                           '--progress', 'yes', '--exit-signal', 'no', '--adversarial', 'clear',
                           '--adversarial-note', 'read raw results', '--dry', 'yes', '--no-gate', expected=4)
        self.assertTrue((self.state / 'store/pending').exists(), result.stdout + result.stderr)
        self.assertEqual(head, (self.state / 'store/commits/current').read_bytes())
        self.assertEqual(self.report(1)['reason'], 'probe-changed-ledger')
        self.call(CTL, 'recover')
        self.assertIn('iteration=0', (self.state / 'state.rec').read_text())
        self.assertFalse((self.state / 'store/pending').exists())

    def test_legacy_forge_migration_retains_history_and_requires_new_probe_evidence(self):
        self.stamp()
        for _ in range(3):
            self.close()
        # Create an unversioned legacy fixture with the old raw evidence shape.
        # Existing history remains readable, but has no executed probe receipts.
        archive = tempfile.TemporaryDirectory(prefix='goal-forge-legacy-')
        self.addCleanup(archive.cleanup)
        legacy = Path(archive.name) / 'state'
        self.state.rename(legacy)
        shutil.copytree(legacy, self.state, ignore=shutil.ignore_patterns('store', 'runner.lock'))
        freeze = (self.state / 'check_freeze').read_text()
        (self.state / 'check_freeze').write_text(freeze.split('forge=')[0] + '\n')
        for number in range(4):
            path = self.state / ('evidence/raw/%s.txt' % number)
            if path.exists():
                rows = [line for line in path.read_text().splitlines() if not line.startswith(('FORGE: ', 'FORGE-SCOPE: '))]
                path.write_text('\n'.join(rows) + '\n')
        history = (self.state / 'loop-log.md').read_bytes()
        self.call(CTL, 'migrate')
        self.assertEqual(history, (self.state / 'loop-log.md').read_bytes())
        self.assertIn('dry_streak=0', (self.state / 'state.rec').read_text())
        self.call(GATE, '--check', expected=2)
        for _ in range(3):
            self.close()
        self.assertIn('coverage=declared', self.call(GATE, '--check').stdout)
        head = (self.state / 'store/commits/current').read_bytes()
        self.plan['blind_spots'] = []
        self.plan_path.write_text(json.dumps(self.plan))
        self.call(CTL, 'migrate', expected=4)
        self.assertEqual(head, (self.state / 'store/commits/current').read_bytes())

    def test_coverage_can_grow_without_dropping_earlier_cases_or_failures(self):
        self.stamp()
        self.close()
        old_history = (self.state / 'loop-log.md').read_bytes()
        (self.root / 'zero.json').write_text('[0,0,0]')
        self.plan['cases'].append(dict(id='zero', dimension='integer-sign', input='zero.json',
                                       command=[sys.executable, '-B', 'probe.py']))
        self.plan_path.write_text(json.dumps(self.plan))
        self.call(CTL, 'migrate')
        self.assertEqual(old_history, (self.state / 'loop-log.md').read_bytes())
        self.assertIn('dry_streak=0', (self.state / 'state.rec').read_text())
        self.close()
        report = self.report(2)
        self.assertEqual(len(report['cases']), 3)
        self.assertEqual(report['new_cases'], 1)
        self.assertEqual(report['repeated_cases'], 2)
        self.assertTrue(report['qualified'])

    def test_acceptance_check_cannot_replace_the_archived_scope_during_close(self):
        goal = self.state / 'goal.md'
        text = goal.read_text().replace('grep -q dedupe algorithm.py',
            'if test -f .goal/evidence/tamper; then echo corrupted > .goal/evidence/raw/0.txt; fi; grep -q dedupe algorithm.py')
        goal.write_text(text)
        self.stamp()
        self.critic()
        head = (self.state / 'store/commits/current').read_bytes()
        archive = (self.state / 'evidence/raw/0.txt').read_bytes()
        (self.state / 'evidence/tamper').touch()
        self.call(CTL, 'close-iteration', '--task', 'T1', '--files', 'algorithm.py',
                  '--checks-pass', '1', '--checks-fail', '0', '--checks-unverifiable', '0',
                  '--progress', 'yes', '--exit-signal', 'no', '--dry', 'yes', '--no-gate', expected=4)
        self.assertEqual(head, (self.state / 'store/commits/current').read_bytes())
        self.assertTrue((self.state / 'store/pending').exists())
        self.call(CTL, 'recover')
        self.assertEqual(archive, (self.state / 'evidence/raw/0.txt').read_bytes())


if __name__ == '__main__':
    unittest.main()
