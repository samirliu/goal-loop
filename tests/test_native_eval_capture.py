"""Mechanism-only synthetic native fixtures. No models, native workers or clients."""
import contextlib
import datetime
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'devtools/native_eval_capture.py'
SPEC = importlib.util.spec_from_file_location('native_eval_capture', SCRIPT)
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


def iso(at):
    return datetime.datetime.fromtimestamp(at, datetime.timezone.utc).isoformat()


def native_rows(start, end, *, sid='fixture-evaluation', agent='/root/efficiency_001',
                parent='fixture-parent', final=True, terminal=True, model='fixture-model', effort='max'):
    """Use observed host field names; IDs and all content are synthetic."""
    turn = sid + '-turn'
    rows = [dict(type='session_meta', timestamp=iso(start), payload=dict(
        id=sid, session_id='fixture-runtime', timestamp=iso(start), cwd='/synthetic',
        agent_path=agent, parent_thread_id=parent,
        source=dict(subagent=dict(thread_spawn=dict(agent_path=agent, parent_thread_id=parent, depth=1))))),
        dict(type='event_msg', timestamp=iso(start + .001), payload=dict(
            type='task_started', turn_id=turn, root_turn_id='fixture-root-turn', started_at=int(start))),
        dict(type='turn_context', timestamp=iso(start + .002), payload=dict(
            turn_id=turn, root_turn_id='fixture-root-turn', model=model, effort=effort))]
    if final:
        rows.append(dict(type='response_item', timestamp=iso(end - .001), payload=dict(
            type='message', role='assistant', phase='final_answer', status='completed',
            content=[dict(type='output_text', text='Synthetic fixture final; no model effectiveness claim.')])) )
    if terminal:
        rows.append(dict(type='event_msg', timestamp=iso(end), payload=dict(
            type='task_complete', turn_id=turn, root_turn_id='fixture-root-turn',
            started_at=int(start), completed_at=int(end), duration_ms=round(1000 * (end-start)))))
    return rows


class ScriptedClock:
    """Simulate delayed process scheduling without waiting hundreds of seconds."""
    def __init__(self, end):
        self.elapsed, self.end, self.actions = 0., end, []
        self.base, self.monotonic_base = time.time(), time.monotonic()

    def monotonic(self):
        return self.monotonic_base + self.elapsed

    def time(self):
        return self.base + self.elapsed

    def sleep(self, seconds):
        target = min(self.actions[0][0], self.end) if self.actions else self.end
        self.elapsed = max(self.elapsed + seconds, target)
        while self.actions and self.actions[0][0] <= self.elapsed:
            _, action = self.actions.pop(0)
            action()


class CaptureFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='goal-native-capture-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.initial = self.base / 'frozen-initial'
        self.initial.mkdir()
        (self.initial / 'TASK.md').write_text('Synthetic mechanism fixture, not an evaluation task.\n')
        (self.initial / 'public.txt').write_text('immutable input\n')
        (self.initial / 'result.txt').write_text('incomplete\n')
        (self.initial / 'result.txt').chmod(0o640)
        self.product = self.base / 'frozen-product'
        self.product.mkdir()
        (self.product / 'version.txt').write_text('frozen source fixture\n')
        self.grader = self.base / 'frozen-grader.py'
        self.grader.write_text('from pathlib import Path\nimport sys\n'
                               'work=Path(sys.argv[1])\n'
                               'assert (work/"result.txt").read_text()=="complete\\n"\n'
                               '(work/"independently-checked").touch()\nprint("business PASS fixture")\n')
        self.sessions = self.base / 'sessions'
        self.sessions.mkdir()
        self.work, self.output = self.base / 'work', self.base / 'capture'
        self.manifest_path = self.base / 'manifest.json'
        self.manifest = dict(version=1, position=1, group='arbitrary-fixture-group', goal_loop=False,
            agent_path='/root/efficiency_001', parent_thread_id='fixture-parent',
            model='fixture-model', effort='max', seconds=360, execution_seconds=330,
            max_internal_workers=2, initial_workspace=str(self.initial), work=str(self.work),
            immutable_inputs=['TASK.md', 'public.txt'],
            frozen={str(p): c.fingerprint(p) for p in (self.initial, self.product, self.grader)},
            artifacts=[str(self.work)], checks=[dict(name='independent', argv=[sys.executable, '-B',
                str(self.grader), str(self.work)], cwd=str(self.work))])
        self.write_manifest()

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest))

    def log(self, rows, name='root.jsonl'):
        path = self.sessions / name
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        return path

    def complete_product(self):
        (self.work / 'result.txt').write_text('complete\n')

    def fake(self, actions, *, runner=None):
        self.write_manifest()
        clock = ScriptedClock(self.manifest['seconds'])
        capture = c.Capture(self.manifest_path, c.sha(self.manifest_path), self.output, self.sessions, clock=clock)
        clock.actions = [(at, lambda fn=fn: fn(clock)) for at, fn in actions]
        invocations = []
        def passing(check):
            invocations.append(check['name'])
            start, wall = clock.monotonic(), clock.time()
            self.assertEqual((self.work / 'result.txt').read_text(), 'complete\n')
            clock.elapsed += .2
            if runner:
                return runner(check, clock, start, wall)
            return dict(result=0, supervisor_returncode=0, stdout='GATE: GO fixture\n', stderr='',
                        command=check['argv'], started=start, finished=clock.monotonic(),
                        started_epoch=wall, finished_epoch=clock.time())
        with mock.patch.object(capture, 'run_check', side_effect=passing), contextlib.redirect_stdout(io.StringIO()):
            result = capture.run()
        return result, invocations, capture

    def emit(self, clock, **kwargs):
        self.complete_product()
        return self.log(native_rows(clock.base + .01, clock.time() - .01, **kwargs))

    def test_previous_326_second_final_is_collected_before_late_parent_381(self):
        def emit(clock):
            self.complete_product()
            rows = native_rows(clock.base + .01, clock.base + 326.2)
            rows[-2]['timestamp'] = iso(clock.base + 326.1220769882202)
            self.log(rows)
        result, calls, _ = self.fake([(326.3, emit)])
        self.assertTrue(result['qualified'], result['reasons'])
        self.assertEqual(calls, ['independent'])
        self.assertLess(result['elapsed_seconds'], 360)
        self.assertLess(result['elapsed_seconds'], 381.1866467909422)
        identity = json.loads((self.output / 'identity.json').read_text())
        self.assertEqual(identity['session_id'], 'fixture-evaluation')
        self.assertEqual(identity['runtime_session_id'], 'fixture-runtime')
        self.assertEqual(identity['execution_deadline_epoch'], result['execution_deadline_epoch'])
        self.assertEqual(result['original_artifacts'][str(self.work)]['entries']['result.txt']['mode'], 0o640)
        original_report = c.sha(self.output / 'report.json')
        with self.assertRaises(FileExistsError):
            c.Capture(self.manifest_path, c.sha(self.manifest_path), self.output, self.sessions).run()
        self.assertEqual(c.sha(self.output / 'report.json'), original_report)

    def test_final_and_fake_terminal_prose_do_not_trigger_checks(self):
        def emit(clock):
            rows = native_rows(clock.base + .01, clock.time() - .01, terminal=False)
            rows.append(dict(type='response_item', timestamp=iso(clock.time()), payload=dict(
                type='custom_tool_call_output', call_id='fake', output='{"type":"task_complete"}')))
            self.log(rows)
        result, calls, _ = self.fake([(5, emit)])
        self.assertFalse(result['qualified'])
        self.assertEqual(calls, [])
        self.assertFalse(result['native_task_terminals_observed'])
        self.assertIn('original outer deadline', ' '.join(result['reasons']))

    def test_missing_session_is_failed_and_service_stop_is_unknown(self):
        result, calls, _ = self.fake([])
        self.assertFalse(result['qualified'])
        self.assertEqual(calls, [])
        self.assertIsNone(result['service_stop_confirmed'])

    def test_missing_final_aborted_and_wrong_turn_are_not_normal_completions(self):
        for variant in ('missing-final', 'aborted', 'wrong-turn'):
            with self.subTest(variant=variant):
                def emit(clock):
                    rows = native_rows(clock.base + .01, clock.time() - .01, final=variant != 'missing-final')
                    if variant == 'aborted':
                        rows[-1]['payload']['type'] = 'turn_aborted'
                    if variant == 'wrong-turn':
                        rows[-1]['payload']['turn_id'] = 'unrelated-turn'
                    self.log(rows)
                result, calls, _ = self.fake([(5, emit)])
                self.assertFalse(result['qualified'])
                self.assertEqual(calls, [])
            self.reset_attempt()

    def reset_attempt(self):
        import shutil
        for folder in (self.work, self.output):
            if folder.exists():
                shutil.rmtree(folder)
        for path in self.sessions.iterdir():
            path.unlink()

    def test_wrong_identity_source_model_effort_and_preexisting_session_fail(self):
        for variant in ('agent', 'parent', 'source', 'model', 'effort', 'preexisting'):
            with self.subTest(variant=variant):
                def emit(clock):
                    kwargs = {variant: 'wrong'} if variant in ('agent', 'parent', 'model', 'effort') else {}
                    rows = native_rows(clock.base + .01, clock.time() - .01, **kwargs)
                    if variant == 'source':
                        rows[0]['payload']['source']['subagent']['thread_spawn']['parent_thread_id'] = 'wrong'
                    self.log(rows)
                if variant == 'preexisting':
                    self.log(native_rows(1794540000.01, 1794540001.))
                    actions = []
                else:
                    actions = [(5, emit)]
                result, calls, _ = self.fake(actions)
                self.assertFalse(result['qualified'])
                self.assertEqual(calls, [])
            self.reset_attempt()

    def test_late_terminal_and_delayed_observation_past_outer_fail(self):
        for when in (331, 361):
            with self.subTest(when=when):
                result, calls, _ = self.fake([(when, lambda clock: self.emit(clock))])
                self.assertFalse(result['qualified'])
                self.assertEqual(calls, [])
            self.reset_attempt()
        def late_terminal(clock):
            self.complete_product()
            rows = native_rows(clock.base + .01, clock.base + 331)
            rows[-2]['timestamp'] = iso(clock.base + 326.1220769882202)
            self.log(rows)
        result, calls, _ = self.fake([(331.1, late_terminal)])
        self.assertFalse(result['qualified'])
        self.assertEqual(calls, [])
        self.assertIn('native final/terminal after execution deadline', result['reasons'])

    def test_workspace_preparation_time_is_not_granted_back(self):
        self.write_manifest()
        clock = ScriptedClock(360)
        capture = c.Capture(self.manifest_path, c.sha(self.manifest_path), self.output, self.sessions, clock=clock)
        def slow_copy(*args):
            clock.elapsed += 331
            return dict(result=0, supervisor_returncode=0, started=clock.monotonic()-331,
                        finished=clock.monotonic(), finished_epoch=clock.time())
        with mock.patch.object(capture, 'bounded_command', side_effect=slow_copy), contextlib.redirect_stdout(io.StringIO()):
            result = capture.run()
        self.assertFalse(result['qualified'])
        self.assertFalse((self.output / 'ready.json').exists())
        self.assertIn('execution', ' '.join(result['reasons']))
        self.assertEqual(result['execution_deadline'], result['entry'] + 330)

    def test_copy_occurs_after_clock_start_and_immutable_inputs_are_checked(self):
        self.assertFalse(self.work.exists())
        def emit(clock):
            self.emit(clock)
            (self.work / 'public.txt').write_text('changed input\n')
        result, calls, _ = self.fake([(5, emit)])
        self.assertFalse(result['qualified'])
        self.assertEqual(calls, [])
        self.assertGreaterEqual(result['preparation']['started'], result['entry'])
        self.assertIn('immutable workspace input changed', result['reasons'])

    def test_precreated_work_and_manifest_hash_changes_cannot_be_reused(self):
        self.work.mkdir()
        result, calls, _ = self.fake([])
        self.assertFalse(result['qualified'])
        self.assertEqual(calls, [])
        self.assertIn('fresh path', ' '.join(result['reasons']))
        self.reset_attempt()
        def change(clock):
            self.emit(clock)
            self.manifest_path.write_text(self.manifest_path.read_text() + '\n')
        result, calls, _ = self.fake([(5, change)])
        self.assertFalse(result['qualified'])
        self.assertEqual(calls, [])
        self.assertIn('frozen manifest changed', result['reasons'])

    def test_changed_frozen_source_or_grader_fails_at_entry_or_after_checks(self):
        (self.product / 'version.txt').write_text('drift')
        result, calls, _ = self.fake([])
        self.assertFalse(result['qualified'])
        self.assertEqual(calls, [])
        self.assertFalse((self.output / 'ready.json').exists())
        self.reset_attempt()
        (self.product / 'version.txt').write_text('frozen source fixture\n')
        def runner(check, clock, start, wall):
            self.grader.write_text('raise SystemExit(0)\n')
            return dict(result=0, supervisor_returncode=0, stdout='fixture', started=start,
                        finished=clock.monotonic(), finished_epoch=clock.time())
        result, calls, _ = self.fake([(5, lambda clock: self.emit(clock))], runner=runner)
        self.assertFalse(result['qualified'])
        self.assertEqual(calls, ['independent'])
        self.assertIn('frozen input/source/grader changed', result['reasons'])

    def test_nested_descendants_must_be_terminal_before_checks(self):
        def emit(clock):
            self.emit(clock)
            self.log(native_rows(clock.base + 1, clock.base + 4, sid='child',
                agent='/root/efficiency_001/worker', parent='fixture-evaluation'), 'child.jsonl')
            self.log(native_rows(clock.base + 2, clock.base + 4.5, sid='grandchild',
                agent='/root/efficiency_001/worker/nested', parent='child', final=False, terminal=False), 'nested.jsonl')
        result, calls, _ = self.fake([(5, emit)])
        self.assertFalse(result['qualified'])
        self.assertTrue(result['normal_final'])
        self.assertEqual(calls, [])
        self.assertEqual(set(result['sessions']), {'fixture-evaluation', 'child', 'grandchild'})
        self.assertEqual(result['peak_internal_workers_observed'], 2)
        self.reset_attempt()
        def finish_child(clock):
            self.log(native_rows(clock.base + 2, clock.base + 6, sid='grandchild',
                agent='/root/efficiency_001/worker/nested', parent='child'), 'nested.jsonl')
        result, calls, _ = self.fake([(5, emit), (6.1, finish_child)])
        self.assertTrue(result['qualified'], result['reasons'])
        self.assertGreaterEqual(result['checks']['independent']['started'], result['entry']+6.)

    def test_three_concurrent_internal_workers_fail_even_if_all_finished(self):
        def emit(clock):
            self.emit(clock)
            for i in range(3):
                self.log(native_rows(clock.base + 1, clock.base + 3, sid='child-'+str(i),
                    agent='/root/efficiency_001/worker'+str(i), parent='fixture-evaluation'), 'child'+str(i)+'.jsonl')
        result, calls, _ = self.fake([(5, emit)])
        self.assertFalse(result['qualified'])
        self.assertEqual(calls, [])
        self.assertEqual(result['peak_internal_workers_observed'], 3)

    def test_failed_or_late_check_and_cancellation_never_qualify(self):
        for variant in ('failed', 'late', 'cancel'):
            with self.subTest(variant=variant):
                def runner(check, clock, start, wall):
                    if variant == 'late':
                        clock.elapsed = 361
                    if variant == 'cancel':
                        (self.output / 'cancel').touch()
                    return dict(result=1 if variant == 'failed' else 0, supervisor_returncode=0, stdout='fixture',
                                started=start, finished=clock.monotonic(), finished_epoch=clock.time())
                result, calls, _ = self.fake([(5, lambda clock: self.emit(clock))], runner=runner)
                self.assertFalse(result['qualified'])
                self.assertEqual(calls, ['independent'])
                self.assertIsNone(result['service_stop_confirmed'])
            self.reset_attempt()

    def test_goal_loop_requires_all_original_checks_and_gate_go(self):
        self.manifest['goal_loop'] = True
        result, calls, _ = self.fake([])
        self.assertFalse(result['qualified'])
        self.assertEqual(calls, [])
        self.reset_attempt()
        for name in ('audit', 'gate'):
            self.manifest['checks'].append(dict(name=name, argv=['fixture-only-'+name], cwd=str(self.work)))
        def no_go(check, clock, start, wall):
            return dict(result=0, supervisor_returncode=0, stdout='PASS prose is not Gate GO',
                        started=start, finished=clock.monotonic(), finished_epoch=clock.time())
        result, calls, _ = self.fake([(5, lambda clock: self.emit(clock))], runner=no_go)
        self.assertFalse(result['qualified'])
        self.assertEqual(calls, ['independent', 'audit', 'gate'])
        self.assertIn('original Gate GO receipt missing', result['reasons'])
        self.reset_attempt()
        result, calls, _ = self.fake([(5, lambda clock: self.emit(clock))])
        self.assertTrue(result['qualified'], result['reasons'])

    def test_reasoning_credentials_and_encrypted_bodies_are_never_copied(self):
        def emit(clock):
            self.complete_product()
            rows = native_rows(clock.base + .01, clock.time() - .01)
            rows[3:3] = [dict(type='response_item', timestamp=iso(clock.base + 1),
                payload=dict(type='reasoning', summary='PRIVATE THOUGHT', encrypted_content='PRIVATE CIPHERTEXT')),
                dict(type='response_item', timestamp=iso(clock.base + 2), payload=dict(
                    type='custom_tool_call', name='exec', call_id='opaque', input=dict(encrypted_content='HIDDEN BODY'))),
                dict(type='response_item', timestamp=iso(clock.base + 3), payload=dict(
                    type='custom_tool_call_output', call_id='visible', output=[dict(type='text', text=
                        'sk-'+'x'*30+' Authorization: Bearer fixture-secret api_key="fixture-key"')]))]
            self.log(rows)
        result, _, _ = self.fake([(5, emit)])
        self.assertTrue(result['qualified'], result['reasons'])
        contents = '\n'.join(p.read_text() for p in self.output.iterdir() if p.suffix in ('.json', '.jsonl'))
        for secret in ('PRIVATE THOUGHT', 'PRIVATE CIPHERTEXT', 'HIDDEN BODY', 'x'*30, 'fixture-secret', 'fixture-key'):
            self.assertNotIn(secret, contents)
        self.assertIn(c.UNKNOWN, contents)
        self.assertIsNone(result['tokens'])
        self.assertIsNone(result['fees'])
        self.assertEqual(result['sessions']['fixture-evaluation']['opaque_tool_receipts'], 1)

    def test_invalid_budget_and_worker_limit_are_rejected(self):
        for key, value in (('seconds', 901), ('execution_seconds', 781), ('max_internal_workers', 3)):
            previous = self.manifest[key]
            self.manifest[key] = value
            result, calls, _ = self.fake([])
            self.assertFalse(result['qualified'])
            self.assertEqual(calls, [])
            self.manifest[key] = previous
            self.reset_attempt()

    def test_invalid_artifact_shape_is_not_traversed_after_validation_failure(self):
        self.manifest['artifacts'] = '/'
        result, calls, _ = self.fake([])
        self.assertFalse(result['qualified'])
        self.assertEqual(result['artifacts'], {})
        self.assertEqual(calls, [])

    def test_native_malformed_row_is_recorded_as_failure(self):
        def emit(clock):
            path = self.emit(clock)
            with path.open('a') as stream:
                stream.write('{not valid JSON}\n')
        result, calls, _ = self.fake([(5, emit)])
        self.assertFalse(result['qualified'])
        self.assertEqual(calls, [])

    def start_cli(self, *, seconds=4, execution_seconds=3):
        self.manifest.update(seconds=seconds, execution_seconds=execution_seconds)
        self.write_manifest()
        proc = subprocess.Popen([sys.executable, '-B', str(SCRIPT), 'run', str(self.manifest_path),
            '--manifest-sha256', c.sha(self.manifest_path), '--output', str(self.output),
            '--sessions-root', str(self.sessions)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        def cleanup():
            if proc.poll() is None:
                proc.terminate()
            proc.communicate(timeout=5)
        self.addCleanup(cleanup)
        until = time.monotonic() + 3
        while not (self.output / 'ready.json').exists():
            if proc.poll() is not None:
                out, err = proc.communicate()
                self.fail('collector failed before ready: %r %r' % (out, err))
            self.assertLess(time.monotonic(), until, 'no collector ready receipt')
            time.sleep(.01)
        self.assertTrue(self.work.is_dir())
        return proc

    def cli_complete(self, terminal=True):
        ready = json.loads((self.output / 'ready.json').read_text())
        self.assertLessEqual(ready['ready_epoch'], time.time())
        self.complete_product()
        start = time.time()
        time.sleep(.025)
        return self.log(native_rows(start, time.time(), terminal=terminal))

    def test_real_cli_automatically_checks_only_after_host_task_complete(self):
        proc = self.start_cli()
        path = self.cli_complete(terminal=False)
        time.sleep(.15)
        self.assertIsNone(proc.poll())
        self.assertFalse((self.work / 'independently-checked').exists())
        now = time.time()
        with path.open('a') as stream:
            stream.write(json.dumps(native_rows(now-.01, now)[-1]) + '\n')
        out, err = proc.communicate(timeout=4)
        self.assertEqual(proc.returncode, 0, out + err)
        result = json.loads((self.output / 'report.json').read_text())
        self.assertTrue(result['qualified'], result['reasons'])
        self.assertTrue((self.work / 'independently-checked').exists())
        self.assertEqual(result['checks']['independent']['supervisor_returncode'], 0)
        self.assertEqual((self.output / 'independent.status').read_text(), '0')
        self.assertLessEqual(result['finished'], result['deadline'])
        self.assertLessEqual((self.output / 'report.json').stat().st_mtime, result['deadline_epoch'])

    def test_real_check_timeout_kills_group_and_cannot_run_after_deadline(self):
        late = self.base / 'late-descendant'
        child_code = 'import time; from pathlib import Path; time.sleep(1.2); Path(%r).touch()' % str(late)
        self.grader.write_text('import subprocess,sys,time\nsubprocess.Popen([sys.executable,"-B","-c",%r])\n'
                               'print("check started",flush=True)\ntime.sleep(30)\n' % child_code)
        self.manifest['frozen'][str(self.grader)] = c.fingerprint(self.grader)
        proc = self.start_cli(seconds=.9, execution_seconds=.6)
        self.cli_complete()
        out, err = proc.communicate(timeout=4)
        self.assertEqual(proc.returncode, 1, out + err)
        result = json.loads((self.output / 'report.json').read_text())
        self.assertFalse(result['qualified'])
        self.assertEqual(result['checks']['independent']['result'], 124)
        time.sleep(.65)
        self.assertFalse(late.exists(), 'supervised descendant continued after timeout')

    def test_real_local_check_cancellation_does_not_claim_service_stop(self):
        marker = self.base / 'check-started'
        self.grader.write_text('from pathlib import Path\nimport time\nPath(%r).touch()\ntime.sleep(30)\n' % str(marker))
        self.manifest['frozen'][str(self.grader)] = c.fingerprint(self.grader)
        proc = self.start_cli()
        self.cli_complete()
        until = time.monotonic()+2
        while not marker.exists():
            self.assertIsNone(proc.poll())
            self.assertLess(time.monotonic(), until)
            time.sleep(.01)
        (self.output / 'cancel').touch()
        out, err = proc.communicate(timeout=3)
        self.assertEqual(proc.returncode, 1, out + err)
        result = json.loads((self.output / 'report.json').read_text())
        self.assertFalse(result['qualified'])
        self.assertEqual(result['checks']['independent']['result'], 130)
        self.assertTrue(result['cancellation_requested'])
        self.assertIsNone(result['service_stop_confirmed'])

    def test_signal_cancellation_before_native_spawn_is_recorded(self):
        proc = self.start_cli()
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=3)
        self.assertEqual(proc.returncode, 1, out + err)
        result = json.loads((self.output / 'report.json').read_text())
        self.assertFalse(result['qualified'])
        self.assertTrue(result['cancellation_requested'])
        self.assertFalse(result['native_task_terminals_observed'])
        self.assertIsNone(result['service_stop_confirmed'])


if __name__ == '__main__':
    unittest.main()
