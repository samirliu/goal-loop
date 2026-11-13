"""Real subprocess checks for lock ownership across controller/read entrypoints."""
import fcntl
import os
from pathlib import Path
import subprocess
import signal
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
CTL = ROOT / 'scripts/goal_ctl.sh'
GATE = ROOT / 'scripts/goal_gate.sh'
AUDIT = ROOT / 'scripts/goal_audit.sh'


class LedgerAccess(unittest.TestCase):
    @staticmethod
    def child_running(pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        if sys.platform.startswith('linux'):
            # A non-reaping container PID1 can retain killed grandchildren.
            # Zombies execute no code and hold no locks; signal 0 still works.
            try:
                state = (Path('/proc')/str(pid)/'stat').read_text().rpartition(')')[2].split()[0]
            except FileNotFoundError:
                return False
            return state not in ('Z', 'X')
        return True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='goal-access-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.state = self.project / '.goal'
        self.run_script(CTL, 'init', expected=0)

    def run_script(self, script, *args, expected=None, **kw):
        result = subprocess.run(['bash', str(script), *args, '--project', str(self.project)],
                                capture_output=True, text=True, timeout=15, **kw)
        if expected is not None:
            self.assertEqual(result.returncode, expected, result.stderr + result.stdout)
        return result

    def snapshot(self):
        return {str(p.relative_to(self.state)): p.read_bytes() for p in self.state.rglob('*') if p.is_file()}

    def test_exclusive_owner_excludes_every_controller_and_reader(self):
        before = self.snapshot()
        fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            for command in ('init', 'stamp', 'bind', 'close-iteration', 'recover', 'status'):
                denied = self.run_script(CTL, command, expected=4, input='')
                self.assertIn('ledger-busy', denied.stderr)
            for script, flags in ((GATE, ('--check',)), (GATE, ('--verify',)), (AUDIT, ())):
                denied = self.run_script(script, *flags, expected=4)
                self.assertIn('ledger-busy', denied.stderr)
        finally:
            os.close(fd)
        self.assertEqual(before, self.snapshot())

    def test_shared_reader_excludes_writer_without_creating_files(self):
        before = self.snapshot()
        fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH)
            self.run_script(CTL, 'status', expected=0)
            denied = self.run_script(CTL, 'bind', expected=4, input='AC-1|PASS|x|x|x|x\n')
            self.assertIn('ledger-busy', denied.stderr)
        finally:
            os.close(fd)
        self.assertEqual(before, self.snapshot())

    def test_init_and_stamp_preflight_preserve_ledger_and_decimal_budgets(self):
        before = self.snapshot()
        self.run_script(CTL, 'init', '--max-iterations=garbage', expected=4)
        self.assertEqual(before, self.snapshot())
        (self.state / 'goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | pass | check: `true` | expected: exit=0\n\n'
            '## Budgets\n\nmax_iterations=08 wallclock=08\n\n'
            '## Approval\n\napproved: PENDING\n')
        before = self.snapshot()
        self.run_script(CTL, 'stamp', '--auto', '--time-budget=bad', expected=4)
        self.assertEqual(before, self.snapshot())
        start = int(time.time())
        self.run_script(CTL, 'stamp', '--auto', '--time-budget=08', expected=0)
        values = dict(line.split('=', 1) for line in (self.state / 'state.rec').read_text().splitlines())
        self.assertEqual(values['max_iterations'], '8')
        self.assertEqual(values['time_budget'], '8')
        self.assertGreaterEqual(int(values['deadline']), start + 8)
        self.assertLessEqual(int(values['deadline']), int(time.time()) + 8)

    def test_check_cannot_reenter_controller_writer(self):
        (self.state / 'goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | nested | check: `bash ' + str(CTL) + ' bind --project . </dev/null; '
            'test $? -eq 4` | expected: exit=0\n\n'
            '## Approval\n\napproved: PENDING\n')
        self.run_script(CTL, 'stamp', '--auto', expected=0)
        before = (self.state / 'verdicts.rec').read_bytes()
        self.run_script(GATE, '--verify', expected=0)
        self.assertEqual((self.state / 'verdicts.rec').read_bytes(), before)

    def test_live_verification_holds_shared_lock_for_entire_check(self):
        (self.state / 'goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | wait | check: `touch .goal/evidence/entered-$$; '
            'while [ ! -f .goal/evidence/release ]; do sleep 0.02; done` | expected: exit=0\n\n'
            '## Approval\n\napproved: PENDING\n')
        self.run_script(CTL, 'stamp', '--auto', expected=0)
        readers = [subprocess.Popen(['bash', str(GATE), '--verify', '--project', str(self.project)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        try:
            until = time.monotonic() + 10
            while len(list((self.state / 'evidence').glob('entered-*'))) < 2:
                self.assertTrue(all(p.poll() is None for p in readers))
                if time.monotonic() >= until:
                    self.fail('both real verification readers did not enter checks')
                time.sleep(0.02)
            denied = self.run_script(CTL, 'bind', expected=4, input='AC-1|PASS|x|x|x|x\n')
            self.assertIn('ledger-busy', denied.stderr)
            (self.state / 'evidence/release').touch()
            for reader in readers:
                out, err = reader.communicate(timeout=15)
                self.assertEqual(reader.returncode, 0, out + err)
        finally:
            (self.state / 'evidence/release').touch()
            for reader in readers:
                if reader.poll() is None:
                    reader.kill()
                    reader.communicate(timeout=5)
        self.run_script(CTL, 'bind', expected=0, input='AC-1|PASS|x|x|x|x\n')

    def test_stale_inherited_descriptor_is_refused(self):
        for descriptor in ('3', '999999'):
            result = self.run_script(CTL, 'status', expected=4,
                                     env=dict(os.environ, GOAL_ACCESS_FD=descriptor,
                                              GOAL_ACCESS_OWNER_PID=str(os.getpid()), GOAL_ACCESS_MODE='read'))
            self.assertIn('invalid inherited ledger lock', result.stderr)

    def test_background_check_is_cancelled_and_cannot_keep_access_or_store_lock(self):
        (self.state / 'goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | spawn | check: `sleep 30 </dev/null >/dev/null 2>&1 & '
            'echo $! > .goal/evidence/childpid` | expected: exit=0\n\n'
            '## Approval\n\napproved: PENDING\n')
        self.run_script(CTL, 'stamp', '--auto', expected=0)
        (self.project / 'artifact.txt').write_text('artifact\n')
        children = []
        try:
            for command in ('verify', 'close'):
                if command == 'verify':
                    self.run_script(GATE, '--verify', expected=0)
                else:
                    self.run_script(CTL, 'close-iteration', '--task', 'T1', '--files', 'artifact.txt',
                                    '--checks-pass', '1', '--checks-fail', '0',
                                    '--checks-unverifiable', '0', '--no-gate', expected=0)
                child = int((self.state / 'evidence/childpid').read_text())
                children.append(child)
                until = time.monotonic() + 2
                while self.child_running(child):
                    self.assertLess(time.monotonic(), until, 'background check escaped cancellation')
                    time.sleep(0.01)
                self.run_script(CTL, 'bind', expected=0, input='AC-1|PASS|x|x|x|x\n')
                if command == 'close':
                    with (self.state / 'store/writer.lock').open('rb') as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            for child in children:
                try:
                    os.kill(child, signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def test_external_cache_gate_serializes_readers(self):
        (self.state / 'goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | cache | check: `true` | '
            'external: `touch .goal/evidence/external-entered; '
            'while [ ! -f .goal/evidence/release ]; do sleep 0.02; done` | window: 1 | expected: exit=0\n\n'
            '## Approval\n\napproved: PENDING\n')
        self.run_script(CTL, 'stamp', '--auto', expected=0)
        reader = subprocess.Popen(['bash', str(GATE), '--verify', '--project', str(self.project)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            until = time.monotonic() + 10
            while not (self.state / 'evidence/external-entered').exists():
                self.assertIsNone(reader.poll())
                if time.monotonic() >= until:
                    self.fail('external verification did not start')
                time.sleep(0.02)
            denied = self.run_script(GATE, '--verify', expected=4)
            self.assertIn('ledger-busy', denied.stderr)
            (self.state / 'evidence/release').touch()
            out, err = reader.communicate(timeout=15)
            self.assertEqual(reader.returncode, 0, out + err)
        finally:
            (self.state / 'evidence/release').touch()
            if reader.poll() is None:
                reader.kill(); reader.communicate(timeout=5)

    def test_killed_gate_does_not_leave_foreground_shell_holding_lock(self):
        (self.state / 'goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | wait | check: `touch .goal/evidence/foreground; sleep 30` | expected: exit=0\n\n'
            '## Approval\n\napproved: PENDING\n')
        self.run_script(CTL, 'stamp', '--auto', expected=0)
        reader = subprocess.Popen(['bash', str(GATE), '--verify', '--project', str(self.project)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            until = time.monotonic() + 10
            while not (self.state / 'evidence/foreground').exists():
                self.assertIsNone(reader.poll())
                if time.monotonic() >= until:
                    self.fail('foreground check did not enter')
                time.sleep(0.02)
            reader.kill()
            reader.wait(timeout=5)
            # Descendant command is still alive; only the actual owner should
            # have held the directory lock, so a new writer can enter now.
            self.run_script(CTL, 'bind', expected=0, input='AC-1|PASS|x|x|x|x\n')
        finally:
            try:
                os.killpg(reader.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            reader.communicate(timeout=5)

    def test_killed_controller_releases_borrowed_raw_gate_locks(self):
        (self.state / 'goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | wait | check: `touch .goal/evidence/foreground; sleep 30` | expected: exit=0\n\n'
            '## Approval\n\napproved: PENDING\n')
        (self.project / 'artifact.txt').write_text('artifact\n')
        self.run_script(CTL, 'stamp', '--auto', expected=0)
        controller = subprocess.Popen(
            ['bash', str(CTL), 'close-iteration', '--project', str(self.project),
             '--task', 'T1', '--files', 'artifact.txt', '--checks-pass', '1',
             '--checks-fail', '0', '--checks-unverifiable', '0', '--no-gate'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            until = time.monotonic() + 10
            while not (self.state / 'evidence/foreground').exists():
                self.assertIsNone(controller.poll())
                if time.monotonic() >= until:
                    self.fail('controller did not enter raw verification')
                time.sleep(0.02)
            controller.kill()
            observed = os.waitid(os.P_PID, controller.pid, os.WEXITED | os.WNOWAIT)
            self.assertEqual(observed.si_code, os.CLD_KILLED)
            fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY)
            try:
                until = time.monotonic() + 3
                while True:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= until:
                            self.fail('borrowed gate retained dead controller lock')
                        time.sleep(0.02)
                with (self.state / 'store/writer.lock').open('rb') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)
            self.run_script(CTL, 'recover', expected=0)
            self.assertIn('iteration=0\n', (self.state / 'state.rec').read_text())
            # Still unreaped: exit events, rather than kill(pid, 0), released
            # the locks and allowed recovery despite the zombie PID existing.
            os.kill(controller.pid, 0)
            self.assertEqual(controller.wait(timeout=5), -signal.SIGKILL)
        finally:
            try:
                os.killpg(controller.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            controller.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
