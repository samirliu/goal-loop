"""Policy switch crashes use real processes, directory locks and archive execution.

Trial telemetry is controlled, so these tests claim transition correctness,
not policy quality or measured cost benefit. Write failures are injected without
bypassing directory locks, transition validation, compare-and-swap or recovery.
"""
import base64
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('evolution_fixture', Path(__file__).with_name('test_evolve.py'))
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)
evolve = fixtures.evolve
SCRIPT = Path(evolve.__file__)


def observations(program, grader, task, expected, seconds, deadline, failure=False):
    candidate = (any(b'candidate' in base64.b64decode(value['bytes']) for value in program.files.values() if value)
                 if isinstance(program, evolve.Bundle) else b'candidate' in program)
    failed = failure and candidate
    return {'ok': not failed, 'elapsed': 1 if candidate else 2, 'score': 1,
            'floor': not failed, 'horizon': not failed, 'regression': failed}, b'observed-output'


class PolicyTransition(unittest.TestCase):
    def case(self, sleeping=False):
        fixture = fixtures.Evolution()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        initial = fixture.protocol('initial')
        if sleeping:
            (initial.parent / 'candidate.py').write_text('import time\nfrom pathlib import Path\n'
                'Path(%r).write_text("running")\ntime.sleep(1)\nprint("candidate")\n' %
                str(fixture.root / 'policy-started'))
        result = self.evaluate(fixture, initial)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        fixture.initial = json.loads((fixture.state / 'enabled.json').read_bytes())
        return fixture

    def evaluate(self, fixture, protocol, failure=False, fault=None, project=None):
        env = os.environ.copy()
        env.pop('GOAL_EVOLVE_FAULT', None)
        if fault:
            env['GOAL_EVOLVE_FAULT'] = fault
        args = [sys.executable, '-I', str(Path(__file__).resolve()), '--evaluate', str(protocol),
                str(fixture.state), 'failure' if failure else 'benefit']
        if project is not None:
            args.append(str(project))
        return subprocess.run(args,
                              env=env, capture_output=True, timeout=15)

    def cli(self, fixture, *args):
        return subprocess.run([sys.executable, '-I', str(SCRIPT), *args, '--state', str(fixture.state)],
                              input=b'{}', capture_output=True, timeout=10)

    def executable(self, fixture, expected=None, blocked='policy-recovery-required'):
        result = self.cli(fixture, 'run-enabled', '--seconds', '5')
        if expected is None:
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertIn(blocked.encode(), result.stderr)
            self.assertEqual(result.stdout, b'')
        else:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout, expected)

    def history(self, fixture):
        paths = [fixture.state / name for name in ('used-holdout.json', 'statistical-budget.json')]
        paths.extend(fixture.state.glob('*/trials.jsonl'))
        paths.extend((fixture.state / 'policies').iterdir())
        return {str(path.relative_to(fixture.state)): path.read_bytes() for path in paths}

    def recover(self, fixture, *args):
        result = self.cli(fixture, 'recover', *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_process_crashes_before_after_switch_report_and_ack_recover_without_replay(self):
        for stage in ('transition-prepared', 'selection-published', 'report-published', 'acknowledgement'):
            with self.subTest(stage=stage):
                fixture = self.case()
                fresh = fixture.protocol('monitor', offset=1000)
                crashed = self.evaluate(fixture, fresh, failure=True, fault=stage)
                self.assertEqual(crashed.returncode, 91, crashed.stdout + crashed.stderr)
                history = self.history(fixture)
                pointer = evolve.enabled_policy(fixture.state)
                if stage == 'transition-prepared':
                    self.assertEqual(pointer, fixture.initial)
                else:
                    self.assertNotEqual(pointer['policy'], fixture.initial['policy'])
                if stage == 'acknowledgement':
                    self.assertFalse((fixture.state / evolve.PENDING).exists())
                    self.executable(fixture, b'baseline\n')
                else:
                    pending = evolve.pending_policy(fixture.state)
                    before_report = json.loads((fixture.state / pending['run'] / 'report.json').read_bytes())
                    if stage != 'report-published':
                        self.assertNotEqual(before_report['status'], 'withdrawn')
                    self.executable(fixture)
                result = self.recover(fixture)
                self.assertEqual(result['status'], 'clean' if stage == 'acknowledgement' else 'recovered')
                self.executable(fixture, b'baseline\n')
                self.assertEqual(self.history(fixture), history)
                self.assertEqual(self.recover(fixture)['status'], 'clean')

    def test_pointer_write_failure_blocks_old_policy_until_real_recovery(self):
        fixture = self.case()
        fresh = fixture.protocol('monitor-write-error', offset=2000)
        atomic = evolve.atomic_bytes

        def fail_pointer(path, data):
            if path.name == 'enabled.json':
                raise OSError('injected pointer write failure')
            atomic(path, data)

        with mock.patch.object(evolve, 'trial', side_effect=lambda *a: observations(*a, failure=True)), \
                mock.patch.object(evolve, 'atomic_bytes', side_effect=fail_pointer):
            with self.assertRaisesRegex(OSError, 'pointer write failure'):
                evolve.experiment(fresh, fixture.state)
        self.assertEqual(evolve.enabled_policy(fixture.state), fixture.initial)
        pending = evolve.pending_policy(fixture.state)
        report = json.loads((fixture.state / pending['run'] / 'report.json').read_bytes())
        self.assertNotEqual(report['status'], 'withdrawn')
        history = self.history(fixture)
        self.executable(fixture)
        self.recover(fixture)
        self.executable(fixture, b'baseline\n')
        self.assertEqual(self.history(fixture), history)

    def test_first_promotion_recovers_without_a_previous_pointer(self):
        fixture = fixtures.Evolution()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        protocol = fixture.protocol('first-promotion')
        crashed = self.evaluate(fixture, protocol, fault='transition-prepared')
        self.assertEqual(crashed.returncode, 91, crashed.stdout + crashed.stderr)
        self.assertFalse((fixture.state / 'enabled.json').exists())
        self.assertIsNone(evolve.pending_policy(fixture.state)['before'])
        history = self.history(fixture)
        self.executable(fixture)
        self.recover(fixture)
        self.executable(fixture, b'candidate\n')
        self.assertEqual(self.history(fixture), history)

    def test_checkpoint_bundle_transition_recovers_from_archives_without_project_reexecution(self):
        fixture = fixtures.Evolution()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        path = fixture.protocol('checkpoint-protocol')
        project = fixture.root / 'project'; project.mkdir()

        def entry(script, *args):
            result = subprocess.run([*script, *args, '--project', str(project)], capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout.decode().strip()

        ctl = ['bash', str(SCRIPT.with_name('goal_ctl.sh'))]
        checkpoint = [sys.executable, '-I', str(SCRIPT.with_name('goal_store.py')), 'incumbent']
        entry(ctl, 'init')
        (project / '.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | runnable | check: `python3 -B policy.py` | expected: exit=0\n\n'
            '## Approval\n\napproved: PENDING\n')
        (project / 'policy.py').write_text('from helper import label\nprint(label)\n')
        (project / 'helper.py').write_text('label="baseline"\n')
        entry(ctl, 'stamp', '--auto')
        entry(ctl, 'close-iteration', '--task', 'T1', '--files', 'policy.py,helper.py', '--checks-pass', '1',
              '--checks-fail', '0', '--checks-unverifiable', '0', '--exit-signal', 'yes',
              '--adversarial', 'clear', '--adversarial-note', 'archive execution fixture', '--no-gate')
        baseline = entry(checkpoint, 'save', '--file', 'policy.py', '--file', 'helper.py')
        (project / 'helper.py').write_text('label="candidate"\n')
        candidate = entry(checkpoint, 'candidate', '--base', baseline)
        protocol = json.loads(path.read_bytes())
        protocol.update(version=2, baseline=baseline, candidate=candidate, entry='policy.py')
        path.write_text(json.dumps(protocol))
        crashed = self.evaluate(fixture, path, project=project, fault='selection-published')
        self.assertEqual(crashed.returncode, 91, crashed.stdout + crashed.stderr)
        self.assertEqual(evolve.enabled_policy(fixture.state)['version'], 2)
        history = self.history(fixture)
        self.executable(fixture)
        project.rename(fixture.root / 'project-retained-for-review')
        self.recover(fixture)
        self.executable(fixture, b'candidate\n')
        self.assertEqual(self.history(fixture), history)

    def test_final_report_write_failure_leaves_committed_switch_pending(self):
        fixture = self.case()
        fresh = fixture.protocol('monitor-report-error', offset=3000)
        atomic = evolve.atomic

        def fail_final_report(path, value):
            if path.name == 'report.json' and value.get('status') == 'withdrawn':
                raise OSError('injected final report failure')
            atomic(path, value)

        with mock.patch.object(evolve, 'trial', side_effect=lambda *a: observations(*a, failure=True)), \
                mock.patch.object(evolve, 'atomic', side_effect=fail_final_report):
            with self.assertRaisesRegex(OSError, 'final report failure'):
                evolve.experiment(fresh, fixture.state)
        self.assertNotEqual(evolve.enabled_policy(fixture.state)['policy'], fixture.initial['policy'])
        history = self.history(fixture)
        self.executable(fixture)
        self.recover(fixture)
        self.executable(fixture, b'baseline\n')
        self.assertEqual(self.history(fixture), history)

    def test_guard_creation_failure_never_dispatches_a_trial(self):
        fixture = self.case()
        fresh = fixture.protocol('guard-error', offset=4000)
        history = self.history(fixture)
        atomic = evolve.atomic

        def fail_guard(path, value):
            if path.name == evolve.PENDING:
                raise OSError('injected guard failure')
            atomic(path, value)

        with mock.patch.object(evolve, 'trial') as trial, mock.patch.object(evolve, 'atomic', side_effect=fail_guard):
            with self.assertRaisesRegex(OSError, 'guard failure'):
                evolve.experiment(fresh, fixture.state)
            trial.assert_not_called()
        self.assertFalse((fixture.state / evolve.PENDING).exists())
        self.assertEqual(self.history(fixture), history)
        self.executable(fixture, b'candidate\n')

    def test_normal_budget_exhaustion_retains_enabled_policy_and_clears_guard(self):
        fixture = self.case()
        fresh = fixture.protocol('monitor-budget', offset=4500)
        protocol = json.loads(fresh.read_bytes()); protocol['budget_seconds'] = 1e-9
        fresh.write_text(json.dumps(protocol))
        history = self.history(fixture)
        with mock.patch.object(evolve, 'trial') as trial:
            result = evolve.experiment(fresh, fixture.state)
            trial.assert_not_called()
        self.assertEqual(result['status'], 'retained-insufficient-counterevidence')
        self.assertFalse(result['within_budget'])
        self.assertEqual(evolve.enabled_policy(fixture.state), fixture.initial)
        self.assertFalse((fixture.state / evolve.PENDING).exists())
        self.assertEqual(self.history(fixture), history)
        self.executable(fixture, b'candidate\n')

    def quarantine(self, fixture):
        history = self.history(fixture)
        self.executable(fixture)
        refused = self.cli(fixture, 'recover')
        self.assertEqual(refused.returncode, 4, refused.stdout + refused.stderr)
        self.assertIn(b'unfinished-policy-evaluation', refused.stderr)
        recovered = self.recover(fixture, '--abort-incomplete')
        report = json.loads(Path(recovered['report']).read_bytes())
        self.assertEqual(report['status'], 'interrupted-uncertain')
        self.assertIsNone(report['enabled'])
        self.assertEqual(report['recovery']['previous_pointer'], fixture.initial)
        archived = Path(recovered['report']).parent / report['recovery']['incomplete_report']
        self.assertEqual(evolve.digest(archived.read_bytes()), report['recovery']['incomplete_report_sha256'])
        self.assertEqual(self.history(fixture), history)
        self.executable(fixture, blocked='no qualified policy enabled')
        self.assertEqual(self.recover(fixture, '--abort-incomplete')['status'], 'clean')
        return history

    def test_evaluating_crash_can_be_quarantined_in_same_state_without_claiming_withdrawal(self):
        fixture = self.case()
        fresh = fixture.protocol('monitor-interrupted', offset=5000)
        crashed = self.evaluate(fixture, fresh, failure=True, fault='evaluating-published')
        self.assertEqual(crashed.returncode, 91, crashed.stdout + crashed.stderr)
        pending = evolve.pending_policy(fixture.state)
        self.assertEqual(pending['phase'], 'evaluating')
        self.assertFalse((fixture.state / pending['run'] / 'trials.jsonl').exists())
        history = self.quarantine(fixture)
        retry = fixture.protocol('new-inputs-after-quarantine', offset=10000)
        protocol = json.loads(retry.read_bytes())
        for phase in ('development', 'holdout'):
            for index in range(6, 20):
                name = '%s-%s.json' % (phase, index)
                (retry.parent / name).write_text(json.dumps({'task': 'fresh-' + phase + '-' + str(index)}))
                protocol[phase].append({'input': name, 'expected': name})
        retry.write_text(json.dumps(protocol))
        repeated = self.evaluate(fixture, retry)
        self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
        self.executable(fixture, b'candidate\n')
        self.assertEqual(json.loads((fixture.state / 'statistical-budget.json').read_bytes())['evaluations'], 2)
        for name, data in history.items():
            if name not in ('used-holdout.json', 'statistical-budget.json'):
                self.assertEqual((fixture.state / name).read_bytes(), data)

    def test_intent_creation_failure_after_regression_retains_evaluation_guard(self):
        fixture = self.case()
        fresh = fixture.protocol('intent-error', offset=6000)
        atomic = evolve.atomic

        def fail_intent(path, value):
            if path.name == evolve.PENDING and value['payload']['phase'] == 'transition':
                raise OSError('injected intent failure')
            atomic(path, value)

        with mock.patch.object(evolve, 'trial', side_effect=lambda *a: observations(*a, failure=True)), \
                mock.patch.object(evolve, 'atomic', side_effect=fail_intent):
            with self.assertRaisesRegex(OSError, 'intent failure'):
                evolve.experiment(fresh, fixture.state)
        pending = evolve.pending_policy(fixture.state)
        self.assertEqual(pending['phase'], 'evaluating')
        raw = fixture.state / pending['run'] / 'trials.jsonl'
        self.assertEqual(len(raw.read_text().splitlines()), 2)
        self.quarantine(fixture)

    def test_quarantine_itself_recovers_on_both_sides_of_pointer_switch(self):
        for stage in ('transition-prepared', 'selection-published'):
            with self.subTest(stage=stage):
                fixture = self.case()
                fresh = fixture.protocol('interrupted-quarantine', offset=6500)
                self.assertEqual(self.evaluate(fixture, fresh, fault='evaluating-published').returncode, 91)
                history = self.history(fixture)
                with mock.patch.dict(os.environ, {'GOAL_EVOLVE_FAULT': stage}):
                    crashed = self.cli(fixture, 'recover', '--abort-incomplete')
                self.assertEqual(crashed.returncode, 91, crashed.stdout + crashed.stderr)
                self.assertEqual(evolve.pending_policy(fixture.state)['phase'], 'transition')
                self.executable(fixture)
                recovered = self.recover(fixture)
                report = json.loads(Path(recovered['report']).read_bytes())
                self.assertEqual(report['status'], 'interrupted-uncertain')
                self.assertEqual(report['recovery']['previous_pointer'], fixture.initial)
                self.executable(fixture, blocked='no qualified policy enabled')
                self.assertEqual(self.history(fixture), history)

    def test_recovery_detects_checksum_pointer_report_material_and_archive_edits(self):
        for changed in ('checksum', 'pointer', 'report', 'material', 'archive'):
            with self.subTest(changed=changed):
                fixture = self.case()
                fresh = fixture.protocol('monitor-conflict', offset=7000)
                self.assertEqual(self.evaluate(fixture, fresh, failure=True, fault='transition-prepared').returncode, 91)
                pending = evolve.pending_policy(fixture.state)
                if changed == 'checksum':
                    path = fixture.state / evolve.PENDING
                elif changed == 'pointer':
                    path = fixture.state / 'enabled.json'
                elif changed == 'report':
                    path = fixture.state / pending['run'] / 'report.json'
                elif changed == 'material':
                    path = fixture.state / pending['run'] / 'runner.py'
                else:
                    path = fixture.state / fixture.initial['program']
                before = path.read_bytes()
                if changed == 'checksum':
                    value = json.loads(before); value['sha256'] = '0' * 64
                    edited = json.dumps(value).encode()
                elif changed == 'pointer':
                    value = json.loads(before); value['run'] = '0' * 32
                    edited = json.dumps(value).encode()
                else:
                    edited = before + b'\n# user edit\n'
                path.write_bytes(edited)
                refused = self.cli(fixture, 'recover')
                self.assertEqual(refused.returncode, 4, refused.stdout + refused.stderr)
                self.assertEqual(path.read_bytes(), edited)
                self.executable(fixture)
                path.write_bytes(before)
                self.recover(fixture)
                self.executable(fixture, b'baseline\n')

    def test_execution_and_recovery_obey_same_directory_writer_lock(self):
        fixture = self.case()
        descriptor = os.open(fixture.state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for args in (('recover',), ('run-enabled', '--seconds', '5')):
                refused = self.cli(fixture, *args)
                self.assertEqual(refused.returncode, 4, refused.stdout + refused.stderr)
            fresh = fixture.protocol('writer-refused', offset=8000)
            with mock.patch.object(evolve, 'trial') as trial:
                with self.assertRaises(BlockingIOError):
                    evolve.experiment(fresh, fixture.state)
                trial.assert_not_called()
        finally:
            os.close(descriptor)
        self.executable(fixture, b'candidate\n')

    def test_execution_keeps_reader_lock_through_owned_process_cleanup(self):
        fixture = self.case(sleeping=True)
        process = subprocess.Popen([sys.executable, '-I', str(SCRIPT), 'run-enabled', '--state', str(fixture.state),
                                    '--seconds', '5'], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not (fixture.root / 'policy-started').exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue((fixture.root / 'policy-started').exists(), 'archived policy did not start')
            self.assertIsNone(process.poll())
            descriptor = os.open(fixture.state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(descriptor)
            self.assertEqual(self.cli(fixture, 'recover').returncode, 4)
            output, error = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, error)
            self.assertEqual(output, b'candidate\n')
        finally:
            if process.poll() is None:
                process.kill(); process.communicate(timeout=5)


if __name__ == '__main__':
    if sys.argv[1:2] == ['--evaluate']:
        protocol, state, kind, *project = sys.argv[2:]
        with mock.patch.object(evolve, 'trial', side_effect=lambda *a: observations(*a, failure=kind == 'failure')):
            print(json.dumps(evolve.experiment(protocol, state, project[0] if project else None)))
    else:
        unittest.main()
