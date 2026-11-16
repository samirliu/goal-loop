"""User controls compose real host fences, archives, recovery and acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT/'scripts/goal_commands.py'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


commands = module('test_controls', CLI)
host = commands.host
fixtures = module('controls_fixture', ROOT/'tests/test_context_actions.py')


class CommandPrompts(unittest.TestCase):
    def test_controls_and_aliases_never_initialize_or_capture_a_goal(self):
        with tempfile.TemporaryDirectory(prefix='goal-control-prompts-') as directory:
            root = Path(directory)
            for prefix in ('/goal-loop', '/goal-loop-host:goal-loop'):
                for word in ('', *commands.COMMANDS, *commands.ALIASES):
                    with self.subTest(prefix=prefix, word=word):
                        output = host.hook(dict(hook_event_name='UserPromptSubmit', session_id='actual-session',
                            cwd=directory, prompt=prefix+(' '+word if word else '')), 'claude')
                        text = output['hookSpecificOutput']['additionalContext']
                        action = commands.ALIASES.get(word, word) if word else 'status'
                        self.assertIn(commands.command(action, root.resolve(), 'claude', 'actual-session'), text)
                        self.assertFalse((root/'.goal').exists())

    def test_unexpected_management_arguments_only_show_help(self):
        with tempfile.TemporaryDirectory(prefix='goal-control-args-') as directory:
            output = host.hook(dict(hook_event_name='UserPromptSubmit', session_id='actual-session',
                cwd=directory, prompt='/goal-loop clear extra'), 'codex')
            self.assertIn(commands.command('help', Path(directory).resolve(), 'codex', 'actual-session'),
                          output['hookSpecificOutput']['additionalContext'])
            self.assertFalse((Path(directory)/'.goal').exists())

    def test_help_doctor_and_empty_status_are_read_only(self):
        with tempfile.TemporaryDirectory(prefix='goal-empty-controls-') as directory:
            for action in ('help', 'doctor', 'status', 'pause', 'clear'):
                result = subprocess.run([sys.executable, '-I', str(CLI), action, '--project', directory],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertFalse((Path(directory)/'.goal').exists())
            self.assertEqual(commands.doctor()['version'], (ROOT/'VERSION').read_text().strip())


class GoalCommands(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ContextActions()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.project.resolve()
        self.state = self.root/'.goal'
        self.backend, self.session = 'claude', 'actual-controls-fixture'
        host.begin(self.root, self.backend, self.session, 120, request='Deliver the exact answer bytes.')
        contract = self.f.view()['author_contract']['template'].replace('<outcome>', 'Deliver the exact answer bytes.').replace(
            '<yes/no statement>', 'answer matches the independent expectation').replace('<command>', 'python3 check.py')
        (self.state/'goal.md').write_text(contract)
        (self.root/'check.py').write_text('from pathlib import Path\nraise SystemExit(0 if Path("answer").read_bytes()==b"correct" else 1)\n')
        (self.root/'answer').write_bytes(b'correct')
        (self.state/'work-plan.md').write_text('- [ ] T1 answer | files=answer\n')
        self.f.execute(self.f.view(), 'verify')
        self.f.execute(self.f.view(), 'stamp')

    def cli(self, action, expected=0, *, env=None, session=None):
        argv = [sys.executable, '-I', str(CLI), action, '--project', str(self.root)]
        if action == 'resume':
            argv += ['--backend', self.backend, '--session', session or self.session]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30, env=env)
        self.assertEqual(result.returncode, expected, result.stdout+result.stderr)
        return result

    def budget_bytes(self):
        return {name:(self.state/name).read_bytes() for name in ('runner.json', 'runner.clock', 'runner.deadline')}

    def worker(self):
        graph = self.root/'graph.json'
        graph.write_text(json.dumps(dict(version=1, context={}, capacity=1, inputs=[], instruments=[],
            jobs=[dict(id='T1', files=['answer'], deps=[], check=['true'])], final_check=['true'])))
        wave = host.crew.begin(self.root, graph, 'crew', 'controls-worker')
        item = host.prepare(self.root, wave, 'T1')
        host.attach(self.root, item['ticket'], {'agentId':'controlled-worker'})
        return item

    def hook(self, command, agent=None):
        payload = dict(hook_event_name='PreToolUse', session_id=self.session, cwd=str(self.root),
                       tool_name='Bash', tool_input={'command':command})
        if agent:
            payload['agent_id'] = agent
        return host.hook(payload, self.backend)

    def test_status_reads_effective_host_budget_without_modifying_any_files(self):
        before = {str(p):p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        value = json.loads(self.cli('status').stdout)
        self.assertEqual(value['state'], 'active')
        self.assertGreater(value['remaining_seconds'], 0)
        self.assertLess(value['remaining_seconds'], 120)
        self.assertFalse(value['completion_verified'])
        old = subprocess.run(['bash', str(ROOT/'scripts/goal_ctl.sh'), 'status', '--project', str(self.root)],
                             capture_output=True, text=True, timeout=15)
        self.assertEqual(old.returncode, 0, old.stdout+old.stderr)
        self.assertNotIn('time_left=off', old.stdout)
        self.assertEqual(before, {str(p):p.read_bytes() for p in self.state.rglob('*') if p.is_file()})

    def test_pause_resume_same_session_preserves_budget_request_and_invalidates_old_map(self):
        original, old = self.budget_bytes(), self.f.view()
        self.cli('pause')
        self.assertEqual(commands.status(self.root)['state'], 'paused')
        view = self.f.view()
        self.assertTrue(view['paused'])
        self.assertNotIn('verify', view['actions'])
        with self.assertRaisesRegex(ValueError, 'paused'):
            host.begin(self.root, self.backend, self.session, 10000)
        resumed = json.loads(self.cli('resume').stdout)
        self.assertTrue(resumed['resumed'])
        self.assertEqual(resumed['host']['request'], 'Deliver the exact answer bytes.')
        self.assertEqual(self.budget_bytes(), original)
        self.assertIn('verify', resumed['context']['actions'])
        self.f.execute(old, 'verify', expected=4)

    def test_resume_in_new_real_session_keeps_original_request_and_enter_selects_current(self):
        original = self.budget_bytes()
        self.cli('pause')
        result = json.loads(self.cli('resume', session='new-actual-session').stdout)
        self.assertEqual(result['host']['session'], 'new-actual-session')
        self.assertEqual(result['host']['request'], 'Deliver the exact answer bytes.')
        self.assertEqual(self.budget_bytes(), original)
        view, _ = self.f.request()
        self.f.execute(view, 'close')
        value = host.enter(self.root, 9999)
        self.assertEqual(value['session'], 'new-actual-session')
        self.assertEqual(value['run'], result['host']['run'])
        self.assertEqual(json.loads((self.state/'runner.json').read_bytes())['deadline'],
                         json.loads(original['runner.json'])['deadline'])
        host.hook(dict(hook_event_name='UserPromptSubmit', session_id='unbound-actual-session',
                       cwd=str(self.root), prompt='/goal-loop another real prompt'), self.backend)
        with self.assertRaisesRegex(ValueError, 'ambiguous recorded host identity'):
            host.enter(self.root, 60)

    def test_expired_resume_never_reopens_or_renews_the_run(self):
        self.cli('pause')
        host.budget.adopt_host(self.state, host.capture(self.backend, self.session, 'tool'), .1)
        time.sleep(.12)
        original = self.budget_bytes()
        result = json.loads(self.cli('resume', expected=3).stdout)
        self.assertFalse(result['resumed'])
        self.assertEqual(result['state'], 'expired')
        self.assertEqual(self.budget_bytes(), original)
        self.assertEqual(commands.status(self.root)['state'], 'paused')

    def test_pause_cancels_real_owned_process_but_waits_for_native_terminal_before_resume(self):
        item = self.worker()
        marker = self.root/'answer'
        code = ('import time; from pathlib import Path\np=Path(%r)\n'
                'while True:\n with p.open("ab") as f: f.write(b"x"); f.flush()\n time.sleep(.02)\n') % str(marker)
        process = subprocess.Popen([sys.executable, '-I', str(ROOT/'scripts/goal_host_command.py'),
            str(self.root), item['ticket'], '--', sys.executable, '-I', '-c', code],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        until = time.monotonic()+5
        while marker.stat().st_size <= len(b'correct'):
            self.assertIsNone(process.poll())
            self.assertLess(time.monotonic(), until)
            time.sleep(.02)
        paused = json.loads(self.cli('pause').stdout)
        self.assertEqual(paused['cancellation_pending'][0]['agent_id'], 'controlled-worker')
        out, err = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 130, out+err)
        stopped = marker.read_bytes()
        time.sleep(.08)
        self.assertEqual(marker.read_bytes(), stopped)
        self.assertEqual(self.hook(item['owned_ready_command'], 'controlled-worker')['hookSpecificOutput']['permissionDecision'], 'deny')
        self.cli('resume', expected=3)
        row = host.get(host.folder(self.root)[1], item['ticket'])[1]
        self.assertEqual(row['phase'], 'prepared', 'a cancellation request was falsely treated as terminal')
        host.reconcile(self.root, {'agentId':'controlled-worker', 'status':'interrupted'}, self.session, self.backend)
        self.assertTrue(json.loads(self.cli('resume').stdout)['resumed'])

    def test_clear_waits_for_actual_terminal_and_keeps_worker_evidence(self):
        item = self.worker()
        first = json.loads(self.cli('clear', expected=3).stdout)
        self.assertFalse(first['cleared'])
        self.assertTrue((self.state/'runner.json').exists())
        self.assertEqual(host.get(host.folder(self.root)[1], item['ticket'])[1]['phase'], 'prepared')
        host.reconcile(self.root, {'agentId':'controlled-worker', 'status':'interrupted'}, self.session, self.backend)
        archive = Path(json.loads(self.cli('clear').stdout)['archive'])
        row = host.load(archive/'evidence/host'/('attempt-'+item['ticket'].split(':')[0]+'.json'))
        self.assertEqual(row['phase'], 'cancelled')

    def test_clear_archives_same_inode_and_new_goal_gets_new_run_with_old_budget_preserved(self):
        original = self.budget_bytes()
        inode = self.state.stat().st_ino
        digest = subprocess.check_output(['bash', str(ROOT/'scripts/goal_gate.sh'), '--digest', '--project', str(self.root)])
        archive = Path(json.loads(self.cli('clear').stdout)['archive'])
        self.assertEqual(self.state.stat().st_ino, inode)
        self.assertEqual(host.load(archive/'.archive.json')['head'],
                         json.loads((archive/'store/commits/current').read_bytes())['head'])
        self.assertEqual((archive/'runner.json').read_bytes(), original['runner.json'])
        self.assertEqual((self.root/'answer').read_bytes(), b'correct')
        self.assertEqual(commands.status(self.root)['state'], 'none')
        self.assertEqual(digest, subprocess.check_output(['bash', str(ROOT/'scripts/goal_gate.sh'), '--digest', '--project', str(self.root)]))
        self.assertEqual(self.f.view()['next'], 'initialize-ledger')
        # The actual next prompt initializes in the retained directory.
        host.hook(dict(hook_event_name='UserPromptSubmit', session_id=self.session,
                       cwd=str(self.root), prompt='/goal-loop-host:goal-loop Deliver the next artifact'), self.backend)
        fresh = host.enter(self.root, 120)
        self.assertNotEqual(fresh['run'], json.loads(original['runner.json'])['run'])
        self.assertEqual((archive/'runner.json').read_bytes(), original['runner.json'])
        self.assertEqual(self.state.stat().st_ino, inode)

    def test_clear_refuses_live_runner_and_policy_directory_locks(self):
        policy = self.state/'proposals/policy'; policy.mkdir(parents=True)
        lock = self.state/'store/runner.lock'; lock.touch()
        for path in (lock, policy):
            with self.subTest(path=path):
                fd = os.open(path, os.O_RDONLY)
                try:
                    host.store.fcntl.flock(fd, host.store.fcntl.LOCK_SH)
                    result = self.cli('clear', expected=4)
                    self.assertIn('still owns', result.stderr)
                    self.assertTrue((self.state/'runner.json').exists())
                    self.assertFalse((self.state/'clear-pending.json').exists())
                finally:
                    os.close(fd)

    def test_interrupted_clear_recovers_same_archive_without_replaying_checks(self):
        original = self.budget_bytes()
        env = dict(os.environ, GOAL_COMMAND_FAULT='moved-evidence')
        self.cli('clear', expected=91, env=env)
        pending = host.load(self.state/'clear-pending.json')
        self.assertEqual(self.f.view()['next'], 'recover-clear')
        denied = subprocess.run(['bash', str(ROOT/'scripts/goal_ctl.sh'), 'init', '--project', str(self.root)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(denied.returncode, 4)
        self.assertIn('clear-recovery-required', denied.stderr)
        recovered = json.loads(self.cli('recover').stdout)
        self.assertEqual(Path(recovered['archive']), self.state/pending['archive'])
        self.assertEqual((Path(recovered['archive'])/'runner.json').read_bytes(), original['runner.json'])
        self.assertFalse((self.state/'clear-pending.json').exists())

    def test_clear_after_archive_publication_recovers_via_original_controller_recover(self):
        self.cli('clear', expected=91, env=dict(os.environ, GOAL_COMMAND_FAULT='archive-published'))
        result = subprocess.run(['bash', str(ROOT/'scripts/goal_ctl.sh'), 'recover', '--project', str(self.root)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue(json.loads(result.stdout)['history_retained'])
        self.assertFalse((self.state/'clear-pending.json').exists())

    def test_clear_journal_before_any_move_is_recoverable(self):
        original = self.budget_bytes()
        self.cli('clear', expected=91, env=dict(os.environ, GOAL_COMMAND_FAULT='clear-prepared'))
        self.assertTrue((self.state/'runner.json').exists())
        recovered = json.loads(self.cli('recover').stdout)
        self.assertEqual((Path(recovered['archive'])/'runner.json').read_bytes(), original['runner.json'])
        self.assertFalse(json.loads(self.cli('recover').stdout)['recovered'])

    def test_clear_after_moving_the_store_still_fences_new_goal_entry_and_recovers(self):
        self.cli('clear', expected=91, env=dict(os.environ, GOAL_COMMAND_FAULT='moved-store'))
        self.assertFalse((self.state/'store').exists())
        with self.assertRaisesRegex(ValueError, 'clear-recovery-required'):
            host.begin(self.root, self.backend, 'new-entry', 9999)
        self.assertEqual(json.loads(self.cli('status').stdout)['state'], 'recovery-required')
        self.assertTrue(json.loads(self.cli('recover').stdout)['history_retained'])

    def test_clear_recovery_rejects_a_resealed_path_escape_without_touching_external_files(self):
        self.cli('clear', expected=91, env=dict(os.environ, GOAL_COMMAND_FAULT='clear-prepared'))
        pending = self.state/'clear-pending.json'
        record = host.load(pending)
        record['entries'][0]['name'] = '../answer'
        host.save(pending, record)
        result = self.cli('recover', expected=4)
        self.assertIn('invalid clear entry', result.stderr)
        self.assertEqual((self.root/'answer').read_bytes(), b'correct')
        self.assertTrue((self.state/'runner.json').exists())

    def test_resume_finishes_a_pause_interrupted_before_session_or_cancellation_updates(self):
        item = self.worker()
        # Kill the actual durable first step, before host cancellation/flags.
        self.cli('pause', expected=91, env=dict(os.environ, GOAL_COMMAND_FAULT='control-installed'))
        result = json.loads(self.cli('resume', expected=3).stdout)
        self.assertFalse(result['resumed'])
        self.assertEqual(result['cancellation_pending'][0]['agent_id'], 'controlled-worker')
        self.assertTrue(Path(item['cancel_file']).exists())

    def control_fault(self, stage, paused):
        original = self.budget_bytes()
        self.cli('pause', expected=91, env=dict(os.environ, GOAL_COMMAND_FAULT='control-'+stage))
        if paused:
            self.cli('status', expected=4)
            with self.assertRaisesRegex(host.store.StoreError, 'ledger-view-mismatch'):
                host.begin(self.root, self.backend, 'must-not-dispatch', 9999)
        self.cli('recover')
        self.assertEqual(commands.status(self.root)['state'], 'paused' if paused else 'active')
        self.assertEqual(self.budget_bytes(), original)
        if paused:
            self.assertTrue(json.loads(self.cli('resume').stdout)['resumed'])

    def test_control_crash_before_commit_keeps_previous_fence(self):
        self.control_fault('generation-published', False)

    def test_control_crash_after_commit_requires_recovery_and_retains_pause(self):
        self.control_fault('pointer-published', True)

    def test_pause_cannot_advance_head_while_a_close_transaction_is_pending(self):
        self.f.request(claim='no')
        env = fixtures.faults.CloseCommit.fault_env(self.f, 'generation-published')
        self.f.execute(self.f.view(), 'close', expected=None, env=env)
        self.assertTrue((self.state/'store/pending').exists())
        before = {str(p):p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        self.assertIn('recovery-required', self.cli('pause', expected=4).stderr)
        self.assertEqual(before, {str(p):p.read_bytes() for p in self.state.rglob('*') if p.is_file()})
        self.cli('recover')
        self.assertFalse((self.state/'store/pending').exists())

    def test_check_adopts_existing_legacy_control_without_changing_its_mode_or_budget(self):
        commits = host.store.Store(self.state/'store/commits')
        head, snapshot = commits.read()
        meta = json.loads(snapshot[host.store._VIEW_META])
        meta['views'].pop('control.json')
        snapshot[host.store._VIEW_META] = host.store._encode(meta)
        commits.commit('legacy-control-fixture', b'legacy sidecar', snapshot, expected_head=head)
        run = json.loads((self.state/'runner.json').read_bytes())['run']
        control = dict(version=1, project=str(self.root), run=run, mode='paused', updated=time.time())
        host.save(self.state/'control.json', control)
        original = self.budget_bytes()
        self.cli('check', expected=2)
        _, adopted = commits.read()
        self.assertIn('control.json', json.loads(adopted[host.store._VIEW_META])['views'])
        self.assertEqual(host.load(self.state/'control.json'), control)
        self.assertEqual(self.budget_bytes(), original)
        self.assertEqual(commands.status(self.root)['state'], 'paused')

    def test_clear_recovery_preserves_conflicting_new_files(self):
        self.cli('clear', expected=91, env=dict(os.environ, GOAL_COMMAND_FAULT='moved-evidence'))
        path = self.state/'evidence'; path.mkdir(); valuable = path/'user-file'; valuable.write_text('preserve')
        result = self.cli('recover', expected=4)
        self.assertIn('clear conflict', result.stderr)
        self.assertEqual(valuable.read_text(), 'preserve')
        self.assertTrue((self.state/'clear-pending.json').exists())

    def test_management_commands_remain_available_after_deadline_and_reject_shell_suffixes(self):
        host.budget.adopt_host(self.state, host.capture(self.backend, self.session, 'tool'), .1)
        time.sleep(.12)
        for action in commands.COMMANDS:
            with self.subTest(action=action):
                cmd = commands.command(action, self.root, self.backend, self.session)
                self.assertEqual(self.hook(cmd), {})
                for invalid in (cmd+'; touch forbidden', cmd+' > redirected', 'env '+cmd):
                    self.assertEqual(self.hook(invalid)['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_check_uses_fresh_original_audit_and_gate(self):
        view, _ = self.f.request()
        self.f.execute(view, 'close')
        receipt = json.loads(self.cli('check').stdout)
        self.assertTrue(receipt['completion_verified'])
        (self.root/'answer').write_bytes(b'changed')
        receipt = json.loads(self.cli('check', expected=2).stdout)
        self.assertFalse(receipt['completion_verified'])

    def test_check_rejects_corrupt_ledger_as_state_error_without_repairing_it(self):
        path = self.state/'state.rec'
        changed = path.read_bytes()+b'unsigned=changed\n'
        path.write_bytes(changed)
        result = self.cli('check', expected=4)
        self.assertIn('ledger-view-mismatch', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(path.read_bytes(), changed)

    def test_rejected_claim_can_be_repaired_and_submitted_again_without_replaying_old_judgment(self):
        (self.root/'answer').write_bytes(b'wrong')
        (self.state/'work-plan.md').write_text('- [x] T1 answer | files=answer\n')
        request = dict(progress='yes', exit_signal='yes', adversarial='finding',
                       adversarial_note='Controlled rejected claim: wrong bytes must fail.')
        rejected = self.f.view()
        result = subprocess.run(shlex.split(rejected['submissions']['close']['command']), input=json.dumps(request),
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
        old = self.f.view()
        self.assertIn('verify', old['actions'])
        self.assertIn('close', old['submissions'])
        self.assertIsNone(old['actions']['close']['command'])
        self.f.execute(old, 'retry-close', expected=2)
        (self.root/'answer').write_bytes(b'correct')
        fixed = self.f.view()
        self.f.execute(fixed, 'verify')
        request.update(adversarial='clear', adversarial_note='Actual check.py independently verifies the repaired exact bytes.')
        result = subprocess.run(shlex.split(fixed['submissions']['close']['command']), input=json.dumps(request),
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('"completion_verified": true', result.stdout)
        self.assertIn('iteration=2\n', (self.state/'state.rec').read_text())
        self.assertIn('false_completes=1\n', (self.state/'state.rec').read_text())


class ControlIntegrity(unittest.TestCase):
    def case(self, checker):
        temporary = tempfile.TemporaryDirectory(prefix='goal-control-integrity-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        host.begin(root, 'claude', 'integrity-fixture', 180, request='Deliver answer.')
        state = root/'.goal'
        (root/'answer').write_text('correct')
        (root/'check.py').write_text('from pathlib import Path\nassert Path("answer").read_text()=="correct"\n'+checker)
        (state/'goal.md').write_text('# Goal\n\n## Objective\n\nDeliver answer.\n\n## Acceptance criteria\n\n'
            '- AC-1 | exact answer | check: `python3 check.py` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
        (state/'work-plan.md').write_text('- [ ] T1 answer | files=answer\n')
        return root, state

    def submit(self, root, action, request):
        view = commands.context_result('show', root, True)
        return subprocess.run(shlex.split(view['submissions'][action]['command']), input=json.dumps(request),
                              capture_output=True, text=True, timeout=25)

    def test_smoke_cannot_stamp_a_check_that_mutates_management_state(self):
        for name in ('control.json', 'clear-pending.json', 'cleared.json'):
            with self.subTest(name=name):
                root, state = self.case('Path(%r).write_text("changed by check")\n' % ('.goal/'+name))
                result = self.submit(root, 'stamp', {})
                self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
                self.assertIn('check-mutated-ledger', result.stdout+result.stderr)
                self.assertIn('approved: PENDING', (state/'goal.md').read_text())

    def test_check_cannot_unpause_and_original_recover_restores_the_committed_fence(self):
        root, state = self.case('import hashlib,json\np=Path(".goal/control.json")\nif p.exists():\n'
            ' r=json.loads(p.read_text());r["payload"]["mode"]="active"\n'
            ' r["sha256"]=hashlib.sha256(json.dumps(r["payload"],sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")).hexdigest()\n'
            ' p.write_text(json.dumps(r))\n')
        stamped = self.submit(root, 'stamp', {})
        self.assertEqual(stamped.returncode, 0, stamped.stdout+stamped.stderr)
        (state/'work-plan.md').write_text('- [x] T1 answer | files=answer\n')
        closed = self.submit(root, 'close', dict(progress='yes',exit_signal='yes',adversarial='clear',
            adversarial_note='Controlled integrity fixture: the exact answer check passes before pause.'))
        self.assertEqual(closed.returncode, 0, closed.stdout+closed.stderr)
        commands.pause(root)
        fence = (state/'control.json').read_bytes()
        budget_before = (state/'runner.json').read_bytes()
        checked = subprocess.run([sys.executable,'-I',str(CLI),'check','--project',str(root)],
                                 capture_output=True,text=True,timeout=25)
        self.assertEqual(checked.returncode, 4, checked.stdout+checked.stderr)
        self.assertNotIn('"completion_verified": true', checked.stdout)
        with self.assertRaisesRegex(host.store.StoreError, 'ledger-view-mismatch'):
            host.begin(root, 'claude', 'unauthorized-entry', 9999)
        commands.recover(root)
        self.assertEqual((state/'control.json').read_bytes(), fence)
        self.assertEqual((state/'runner.json').read_bytes(), budget_before)
        self.assertEqual(commands.status(root)['state'], 'paused')
        with self.assertRaisesRegex(ValueError, 'paused'):
            host.begin(root, 'claude', 'still-must-not-enter', 9999)


if __name__ == '__main__':
    unittest.main()
