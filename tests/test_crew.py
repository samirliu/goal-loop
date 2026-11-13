"""Crew observations: real clocks/checkers, graph constraints and raw failures."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('goal_crew', ROOT / 'scripts/goal_crew.py')
crew = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(crew)


class Crew(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='goal-crew-test-')
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.state = self.project / '.goal'
        self.ctl('init')
        (self.state / 'goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n'
                                          '- AC-1 | test host | check: `true` | expected: exit=0\n\n'
                                          '## Approval\n\napproved: PENDING\n')
        self.ctl('stamp', '--auto', '--time-budget=120')
        self.graph = self.state / 'proposals/crew.json'
        self.graph.parent.mkdir()
        # Platform boot supervision is independently exercised by lifecycle
        # integration tests. These tests isolate event/decision semantics.
        previous = crew.boot
        crew.boot = lambda: 'unit-test-boot'
        self.addCleanup(lambda: setattr(crew, 'boot', previous))
        self.write_graph()

    def ctl(self, *args):
        result = subprocess.run(['bash', str(ROOT / 'scripts/goal_ctl.sh'), *args, '--project', str(self.project)],
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def write_graph(self, latency='low', deps=False):
        check = lambda name, expected: [sys.executable, '-c',
                                        'from pathlib import Path; assert Path(%r).read_text()==%r' % (name, expected)]
        value = dict(version=1, context={'backend': 'test-observer', 'latency-profile': latency}, capacity=2,
                     jobs=[dict(id='T1', files=['a.out'], deps=[], check=check('a.out', 'A')),
                           dict(id='T2', files=['b.out'], deps=['T1'] if deps else [], check=check('b.out', 'B'))],
                     final_check=[sys.executable, '-c', 'from pathlib import Path; '
                                  'assert Path("a.out").read_text()=="A"; assert Path("b.out").read_text()=="B"'],
                     instruments=[], inputs=[])
        self.graph.write_text(json.dumps(value))
        return value

    def fresh(self, mode, trial):
        for name in ('a.out', 'b.out'):
            path = self.project / name
            if path.exists():
                path.unlink()
        return crew.Wave(self.project, crew.begin(self.project, self.graph, mode, trial))

    def work(self, wave, task):
        (self.project / ('a.out' if task == 'T1' else 'b.out')).write_text('A' if task == 'T1' else 'B')
        wave.event(task, 'returned', 0)
        self.assertEqual(wave.validate(task), 0)
        wave.event(task, 'adopt')

    def sample(self, mode, trial, startup=0.005, unknown_start=False, duration=0.25):
        wave = self.fresh(mode, trial)
        wave.stage('coordination', 'begin')
        wave.stage('coordination', 'end')
        if mode == 'inline':
            for task in ('T1', 'T2'):
                wave.event(task, 'dispatch')
                wave.event(task, 'started')
                time.sleep(duration)
                self.work(wave, task)
        else:
            for task in ('T1', 'T2'):
                wave.event(task, 'dispatch')
            time.sleep(startup)
            if not unknown_start:
                for task in ('T1', 'T2'):
                    wave.event(task, 'started')
            time.sleep(duration)
            # Both workers finish before serial controller validation begins.
            for task, name, value in [('T1', 'a.out', 'A'), ('T2', 'b.out', 'B')]:
                (self.project / name).write_text(value)
                wave.event(task, 'returned', 0)
            for task in ('T1', 'T2'):
                self.assertEqual(wave.validate(task), 0)
                wave.event(task, 'adopt')
        wave.stage('join', 'begin')
        wave.stage('join', 'end')
        result = wave.finish()
        self.assertTrue(result['quality'])
        return result

    def test_decision_flips_with_observed_startup_cost(self):
        for profile, startup, expected in [('low', 0.005, 'crew'), ('high', 0.8, 'serial')]:
            self.write_graph(profile)
            # Real validators run in planner_profile; timings are controlled
            # mechanism inputs. A busy runner's .25s sleep did not guarantee
            # the unchanged >10% cost margin (the CI counterexample was 8.5%).
            self.planner_profile(serial_elapsed=.8, crew_elapsed=.55+startup,
                                 crew_duration=.25+startup, startup=startup)
            choice = crew.plan(self.project, self.graph)
            self.assertEqual(choice['choice'], expected, choice)
            self.assertEqual(choice['observations'], 6)
            self.assertIsNone(choice['money'])
            self.assertIsNone(choice['tokens'])
            if profile == 'low':
                failed = self.fresh('crew', 'recent-failure')
                failed.event('T1', 'dispatch'); failed.event('T1', 'started')
                failed.event('T2', 'dispatch')
                self.work(failed, 'T1')
                failed.event('T2', 'fault', note='observed provider failure')
                failed.finish()
                (self.project / 'a.out').unlink()
                blocked = crew.plan(self.project, self.graph)
                self.assertEqual(blocked['choice'], 'serial')
                self.assertEqual(blocked['failures'], 1)

    def planner_profile(self, serial_elapsed, crew_elapsed, crew_duration, startup=.005):
        """Controlled advice inputs; actual checker/identity validation stays real."""
        import uuid
        originals = [self.sample('inline', 'controlled-serial-template', duration=.001),
                     self.sample('crew', 'controlled-crew-template', duration=.001)]
        folder = crew.folder(self.project)
        for path in folder.glob('*.json'):
            path.unlink()
        for original in originals:
            for index in range(3):
                row = json.loads(json.dumps(original))
                row['id'] = uuid.uuid4().hex
                row['trial'] = 'controlled-'+row['id']
                row['timing_provenance'] = 'controlled-mechanism-only; not empirical utility'
                elapsed = serial_elapsed if row['mode'] == 'inline' else crew_elapsed
                row.update(started=original['started']+index, elapsed=elapsed,
                           finished=original['started']+index+elapsed)
                duration = .25 if row['mode'] == 'inline' else crew_duration
                for offset, job in enumerate(row['jobs'].values()):
                    begin = offset*.27 if row['mode'] == 'inline' else 0
                    end = begin+duration
                    job.update(dispatch=begin, started=begin+(.001 if row['mode']=='inline' else startup),
                               returned=end, first_valid=end+.001, adopted=end+.002)
                    for check in job['validations']:
                        check.update(start=end, end=end+.001)
                row['worker_seconds'] = duration*len(row['jobs'])
                crew.save(folder/(row['id']+'.json'), row)
        for name in ('a.out', 'b.out'):
            (self.project/name).unlink()

    def test_recorded_marginal_gain_does_not_lower_ten_percent_gate(self):
        self.planner_profile(serial_elapsed=.786307209, crew_elapsed=.719544459, crew_duration=.35)
        advice = crew.plan(self.project, self.graph)
        print('CONTROLLED_MARGINAL_COST '+json.dumps(advice), flush=True)
        self.assertEqual(advice['choice'], 'serial', advice)
        self.assertLess(advice['serial_lower']-advice['crew_upper'], advice['serial_lower']*.1)
        self.assertEqual(advice['observations'], 6)

    def test_unknown_startup_cannot_become_zero_cost(self):
        for i in range(3):
            self.sample('inline', 'inline-' + str(i), duration=0.01)
            self.sample('crew', 'crew-' + str(i), unknown_start=True, duration=0.01)
        for name in ('a.out', 'b.out'):
            (self.project / name).unlink()
        choice = crew.plan(self.project, self.graph)
        self.assertEqual(choice['choice'], 'serial')
        self.assertEqual(choice['reason'], 'failure-or-unknown-startup-in-latest-window')

    def test_coupled_task_waits_for_adopted_dependency(self):
        self.write_graph(deps=True)
        wave = self.fresh('crew', 'coupled')
        wave.event('T1', 'dispatch')
        with self.assertRaisesRegex(ValueError, 'dependency not adopted'):
            wave.event('T2', 'dispatch')
        wave.event('T1', 'started')
        self.work(wave, 'T1')
        wave.event('T2', 'dispatch')
        wave.event('T2', 'started')
        self.work(wave, 'T2')
        self.assertTrue(wave.finish()['quality'])
        for name in ('a.out', 'b.out'):
            (self.project / name).unlink()
        self.assertEqual(crew.plan(self.project, self.graph)['reason'], 'dependency-or-scope-bound')

    def test_dropped_worker_preserves_adopted_output_and_fault_cost(self):
        wave = self.fresh('crew', 'dropped')
        wave.event('T1', 'dispatch'); wave.event('T1', 'started')
        wave.event('T2', 'dispatch')
        self.work(wave, 'T1')
        wave.event('T2', 'fault', note='provider stopped before any usable output')
        result = wave.finish()
        self.assertFalse(result['quality'])
        self.assertEqual((self.project / 'a.out').read_text(), 'A')
        self.assertIsNotNone(result['jobs']['T1']['adopted'])
        self.assertIsNotNone(result['jobs']['T2']['fault'])
        self.assertIsNone(result['jobs']['T2']['startup_queue_seconds'])
        self.assertGreater(result['worker_seconds'], 0)
        self.assertIsNone(result['stage_seconds']['conflict'])

    def test_changed_output_cannot_reuse_adoption(self):
        wave = self.fresh('inline', 'stale-adoption')
        wave.event('T1', 'dispatch'); wave.event('T1', 'started')
        (self.project / 'a.out').write_text('A')
        wave.event('T1', 'returned', 0)
        self.assertEqual(wave.validate('T1'), 0)
        (self.project / 'a.out').write_text('user edit')
        with self.assertRaisesRegex(ValueError, 'stale/failed'):
            wave.event('T1', 'adopt')
        self.assertEqual((self.project / 'a.out').read_text(), 'user edit')

    def test_frozen_instrument_cannot_be_swapped(self):
        value = json.loads(self.graph.read_bytes())
        grader = self.project / 'grade.py'; grader.write_text('raise SystemExit(1)\n')
        value['instruments'] = ['../../grade.py']
        value['jobs'][0]['check'] = [sys.executable, 'grade.py']
        self.graph.write_text(json.dumps(value))
        wave = self.fresh('inline', 'instrument-swap')
        wave.event('T1', 'dispatch'); wave.event('T1', 'started')
        grader.write_text('raise SystemExit(0)\n')
        with self.assertRaisesRegex(ValueError, 'frozen instrument changed'):
            wave.validate('T1')

    def test_overlap_adds_serial_precedence_and_invalid_graph_does_not_book(self):
        value = self.write_graph()
        value['jobs'][1]['files'] = ['a.out']
        self.graph.write_text(json.dumps(value))
        _, _, edges = crew.load_graph(self.graph)
        self.assertEqual(edges['T2'], {'T1'})
        value['jobs'][0]['deps'] = ['T2']
        value['jobs'][1]['deps'] = ['T1']
        self.graph.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            crew.begin(self.project, self.graph, 'crew', 'invalid')
        self.assertFalse((self.state / 'evidence/crew').exists())

    def test_absent_stage_is_unknown_and_explicit_no_operation_is_zero(self):
        wave = self.fresh('inline', 'stage-absence')
        for task in ('T1', 'T2'):
            wave.event(task, 'dispatch'); wave.event(task, 'started'); self.work(wave, task)
        wave.stage('conflict', 'skip')
        result = wave.finish()
        self.assertEqual(result['stage_seconds']['conflict'], 0)
        self.assertIsNone(result['stage_seconds']['recovery'])
        self.assertGreater(result['stage_seconds']['revalidation'], 0)

    def test_repeated_trial_identity_is_not_independent_replication(self):
        import uuid
        self.sample('inline', 'same-inline', duration=0.01)
        self.sample('crew', 'same-crew', duration=0.01)
        folder = crew.folder(self.project)
        for path in list(folder.glob('*.json')):
            original = crew.load(path)
            for _ in range(2):
                copy = json.loads(json.dumps(original))
                copy['id'] = uuid.uuid4().hex
                crew.save(folder / (copy['id'] + '.json'), copy)
        for name in ('a.out', 'b.out'):
            (self.project / name).unlink()
        result = crew.plan(self.project, self.graph)
        self.assertEqual(result['choice'], 'serial')
        self.assertEqual(result['reason'], 'duplicate-trial-identity')

    def test_after_adoption_changes_still_fail_even_if_final_checker_is_weak(self):
        value = json.loads(self.graph.read_bytes())
        value['final_check'] = ['true']
        self.graph.write_text(json.dumps(value))
        wave = self.fresh('inline', 'post-adoption-change')
        for task in ('T1', 'T2'):
            wave.event(task, 'dispatch'); wave.event(task, 'started'); self.work(wave, task)
        (self.project / 'a.out').write_text('user edit after adoption')
        self.assertFalse(wave.finish()['quality'])
        self.assertEqual((self.project / 'a.out').read_text(), 'user edit after adoption')

    def test_new_earlier_budget_is_used_before_dispatch_and_undispatched_work_is_booked(self):
        import contextlib
        import io
        import os
        from unittest import mock
        wave = self.fresh('crew', 'budget-tightened')
        now = str(int(time.time()))
        with mock.patch.object(crew.budget, 'boot_identity', return_value='0'*64), \
                mock.patch.dict(os.environ, {'GOAL_RUNNER_MONOTONIC_START': str(time.monotonic())}), \
                contextlib.redirect_stdout(io.StringIO()):
            crew.budget.budget(self.state, 'begin', now, '1', now)
            time.sleep(1.1)
            with self.assertRaisesRegex(ValueError, 'time-budget-exhausted'):
                wave.event('T1', 'dispatch')
            for task in ('T1', 'T2'):
                wave.event(task, 'cancel', note='total deadline expired before dispatch')
            result = wave.finish()
        self.assertFalse(result['quality'])
        self.assertEqual(result['worker_seconds'], 0)  # explicitly no worker was launched
        self.assertIsNone(result['jobs']['T1']['startup_queue_seconds'])
        self.assertIsNone(result['jobs']['T1']['first_valid'])
        self.assertEqual(result['jobs']['T1']['fault']['kind'], 'not-dispatched')

    def test_changed_input_cannot_reuse_frozen_trial(self):
        value = self.write_graph()
        value['inputs'] = ['fixture.json']
        (self.project / 'fixture.json').write_text('[1,2]\n')
        self.graph.write_text(json.dumps(value))
        wave = self.fresh('inline', 'changed-input')
        wave.event('T1', 'dispatch'); wave.event('T1', 'started')
        (self.project / 'fixture.json').write_text('[999]\n')
        with self.assertRaisesRegex(ValueError, 'frozen inputs changed'):
            wave.validate('T1')

    def single_sample(self):
        original = json.loads(self.graph.read_bytes())
        whole = json.loads(json.dumps(original))
        whole['jobs'] = [dict(id='T1', files=['a.out', 'b.out'], deps=[], check=whole['final_check'])]
        self.graph.write_text(json.dumps(whole))
        wave = self.fresh('inline', 'one-worker-fixture')
        wave.event('T1', 'dispatch'); wave.event('T1', 'started')
        (self.project/'a.out').write_text('A'); (self.project/'b.out').write_text('B')
        wave.event('T1', 'returned', 0)
        self.assertEqual(wave.validate('T1'), 0)
        wave.event('T1', 'adopt')
        result = wave.finish()
        self.assertTrue(result['quality'])
        self.graph.write_text(json.dumps(original))
        return result

    def cost_inputs(self, single_duration, include_inline=True):
        """Synthetic timing inputs for advice, never empirical eval evidence."""
        import uuid
        serial = self.sample('inline', 'serial-fixture', duration=.001)
        parallel = self.sample('crew', 'crew-fixture', duration=.001)
        single = self.single_sample()
        folder = crew.folder(self.project)
        for path in folder.glob('*.json'):
            path.unlink()
        sources = [(parallel, 20, 21), (single, single_duration, single_duration+1)]
        if include_inline:
            sources.append((serial, 40, 81))
        for source, duration, total in sources:
            for index in range(3):
                row = json.loads(json.dumps(source))
                row['id'] = uuid.uuid4().hex
                row['trial'] = 'synthetic-'+row['id']
                row.update(started=source['started']+index, elapsed=total,
                           finished=source['started']+index+total)
                for offset, job in enumerate(row['jobs'].values()):
                    begin = offset*duration if len(row['jobs'])>1 and row['mode']=='inline' else 0
                    end = begin+duration
                    job.update(dispatch=begin, started=begin+.1, returned=end,
                               first_valid=end+.1, adopted=end+.2)
                    for validation in job['validations']:
                        validation.update(start=end, end=end+.1)
                row['worker_seconds'] = duration*len(row['jobs'])
                crew.save(folder/(row['id']+'.json'), row)
        for name in ('a.out', 'b.out'):
            (self.project/name).unlink()

    def test_single_worker_baseline_prevents_false_crew_benefit_and_accounts_for_width(self):
        for duration, expected, reason in [(10, 'serial', 'startup-coordination-or-dependency-cost'),
                                           (30, 'serial', 'latency-gain-with-worker-cost-tradeoff'),
                                           (50, 'crew', 'observed-latency-benefit')]:
            with self.subTest(single_worker_seconds=duration):
                self.cost_inputs(duration)
                advice = crew.plan(self.project, self.graph)
                self.assertEqual(advice['choice'], expected, advice)
                self.assertEqual(advice['serial_basis'], 'single-worker')
                self.assertEqual(advice['reason'], reason)
                self.assertEqual(advice['single_observations'], 3)
                self.assertEqual(advice['crew_worker_seconds_upper'], 40)
                self.assertEqual(advice['serial_worker_seconds_lower'], duration)
                if duration == 30:
                    from unittest import mock
                    with mock.patch.object(crew.budget, 'gate_limit', return_value=(time.monotonic()+25, False)):
                        constrained = crew.plan(self.project, self.graph)
                    self.assertEqual(constrained['choice'], 'crew', constrained)
                    self.assertEqual(constrained['reason'], 'only-observed-deadline-fit')

    def test_single_baseline_cannot_cross_different_frozen_input_bytes(self):
        value = json.loads(self.graph.read_bytes())
        value['inputs'] = ['fixture.json']
        (self.project/'fixture.json').write_text('[1,2]')
        self.graph.write_text(json.dumps(value))
        self.cost_inputs(50, include_inline=False)
        before = crew.plan(self.project, self.graph)
        self.assertEqual(before['choice'], 'crew', before)
        (self.project/'fixture.json').write_text('[1000000]')
        after = crew.plan(self.project, self.graph)
        self.assertEqual(after['single_observations'], 0)
        self.assertEqual(after['choice'], 'serial')

    def test_all_cost_history_expires_when_frozen_input_bytes_change(self):
        value = json.loads(self.graph.read_bytes())
        value['inputs'] = ['fixture.json']
        (self.project/'fixture.json').write_text('[1,2]')
        self.graph.write_text(json.dumps(value))
        self.cost_inputs(50)
        before = crew.plan(self.project, self.graph)
        self.assertEqual(before['choice'], 'crew', before)
        self.assertEqual(before['observations'], 9)
        (self.project/'fixture.json').write_text('[999999,888888,777777]')
        after = crew.plan(self.project, self.graph)
        self.assertNotEqual(after['condition'], before['condition'])
        self.assertEqual(after['observations'], 0, after)
        self.assertEqual(after['single_observations'], 0, after)
        self.assertEqual(after['choice'], 'serial', after)

    def test_public_cli_reads_api_observations_without_changing_their_transport(self):
        self.cost_inputs(50)
        expected = crew.plan(self.project, self.graph)
        result = subprocess.run([sys.executable, '-I', str(ROOT/'scripts/goal_crew.py'),
                                 'plan', '--project', str(self.project), '--graph', str(self.graph)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        actual = json.loads(result.stdout)
        for field in ('choice', 'reason', 'condition', 'observations', 'single_observations',
                      'serial_lower', 'crew_upper'):
            self.assertEqual(actual[field], expected[field], (field, actual, expected))

    def test_different_producer_transports_cannot_be_pooled(self):
        self.cost_inputs(50)
        path = next(crew.folder(self.project).glob('*.json'))
        row = crew.load(path)
        row['observer_transport'] = 'cli'
        row['condition'] = crew.condition_key(row['graph'], row['baseline'], row['inputs'], self.state, 'cli')
        row['batch_condition'] = crew.batch_key(row['graph'], row['baseline'], row['inputs'], self.state, 'cli')
        crew.save(path, row)
        advice = crew.plan(self.project, self.graph)
        self.assertEqual(advice['choice'], 'serial', advice)
        self.assertEqual(advice['reason'], 'mixed-observer-transports')
        self.assertEqual(advice['observations'], 9)

    def test_cli_records_real_cross_process_lifecycle(self):
        def cli(*args):
            result = subprocess.run([sys.executable, '-I', str(ROOT / 'scripts/goal_crew.py'), *args,
                                     '--project', str(self.project)], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout
        identity = cli('begin', '--graph', str(self.graph), '--mode', 'inline', '--trial', 'native-cli-clock').strip()
        for task, name, text in [('T1', 'a.out', 'A'), ('T2', 'b.out', 'B')]:
            cli('event', '--wave', identity, '--task', task, '--event', 'dispatch')
            cli('event', '--wave', identity, '--task', task, '--event', 'started')
            (self.project / name).write_text(text)
            cli('event', '--wave', identity, '--task', task, '--event', 'returned', '--result', '0')
            cli('validate', '--wave', identity, '--task', task)
            cli('event', '--wave', identity, '--task', task, '--event', 'adopt')
        result = json.loads(cli('finish', '--wave', identity))
        self.assertTrue(result['quality'])
        self.assertEqual(len(result['boot']), 64)
        self.assertGreater(result['stage_seconds']['revalidation'], 0)
        self.assertTrue(all(row['first_valid'] >= row['dispatch'] for row in result['jobs'].values()))


if __name__ == '__main__':
    unittest.main()
