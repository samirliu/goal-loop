"""Real owner exit events and direct-child cleanup, without touching a project."""
import importlib.util
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HELPER = Path(__file__).resolve().parents[1] / 'scripts/goal_owner_watch.py'
SPEC = importlib.util.spec_from_file_location('goal_owner_watch', HELPER)
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)


@unittest.skipUnless(os.name == 'posix' and hasattr(os, 'fork'), 'POSIX process supervision required')
class OwnerWatch(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='goal-owner-watch-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def process(self, *args, **kwargs):
        result = subprocess.Popen(*args, **kwargs)
        def cleanup():
            if result.poll() is None:
                result.kill()
            result.communicate(timeout=5)
        self.addCleanup(cleanup)
        return result

    def owner(self):
        return self.process([sys.executable, '-I', '-c', 'import time; time.sleep(30)'],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start_supervisor(self, owner, command):
        ready_read, ready_write = os.pipe()
        self.addCleanup(lambda: os.close(ready_read))
        try:
            supervisor = self.process(
                [sys.executable, '-I', str(HELPER), 'supervise', str(owner.pid),
                 '--ready-fd', str(ready_write), '--', *command],
                pass_fds=(ready_write,), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        finally:
            os.close(ready_write)
        until = time.monotonic() + 5
        line = b''
        while b'\n' not in line:
            remaining = until - time.monotonic()
            self.assertGreater(remaining, 0, 'watcher did not become ready')
            readable, _, _ = select.select([ready_read], [], [], remaining)
            self.assertTrue(readable, 'watcher did not report readiness')
            chunk = os.read(ready_read, 256)
            if not chunk:
                _, err = supervisor.communicate(timeout=5)
                self.fail('watcher closed readiness without READY: %r' % err)
            line += chunk
        fields = line.decode('ascii').strip().split()
        self.assertEqual(fields[0], 'READY')
        self.assertIn(fields[1], ('kqueue', 'pidfd'))
        return supervisor, int(fields[2])

    def test_owner_zombie_exit_kills_child_before_owner_is_reaped(self):
        if not hasattr(os, 'waitid') or not hasattr(os, 'WNOWAIT'):
            self.skipTest('waitid WNOWAIT unavailable')
        owner = self.owner()
        marker = self.root / 'command-ready'
        code = ('import os,time; from pathlib import Path; '
                'Path(%r).write_text(str(os.getpid())); time.sleep(30)' % str(marker))
        supervisor, child = self.start_supervisor(owner, [sys.executable, '-I', '-c', code])
        until = time.monotonic() + 5
        while not marker.exists():
            self.assertIsNone(supervisor.poll())
            if time.monotonic() >= until:
                self.fail('supervised command did not start')
            time.sleep(0.01)
        self.assertEqual(int(marker.read_text()), child)
        owner.kill()
        waited = os.waitid(os.P_PID, owner.pid, os.WEXITED | os.WNOWAIT)
        self.assertEqual(waited.si_pid, owner.pid)
        self.assertEqual(waited.si_code, os.CLD_KILLED)
        self.assertEqual(waited.si_status, signal.SIGKILL)
        # The owner remains an unreaped zombie for this entire assertion.
        os.kill(owner.pid, 0)
        stdout, stderr = supervisor.communicate(timeout=3)
        self.assertEqual(supervisor.returncode, 143, stdout + stderr)
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)
        still_zombie = os.waitid(os.P_PID, owner.pid, os.WEXITED | os.WNOWAIT)
        self.assertEqual(still_zombie.si_pid, owner.pid)
        self.assertEqual(owner.wait(timeout=3), -signal.SIGKILL)

    def test_normal_command_status_and_exec_pid_are_preserved(self):
        owner = self.owner()
        code = ('import os,sys; '
                'print(str(os.getpid())+"|"+os.environ["GOAL_ACCESS_EXEC_PID"], flush=True); '
                'sys.exit(7)')
        supervisor, child = self.start_supervisor(owner, [sys.executable, '-I', '-c', code])
        stdout, stderr = supervisor.communicate(timeout=3)
        self.assertEqual(supervisor.returncode, 7, stderr)
        self.assertEqual(stdout.decode().strip(), '%s|%s' % (child, child))
        self.assertIsNone(owner.poll())

    def test_already_exited_unreaped_owner_never_starts_command(self):
        if not hasattr(os, 'waitid') or not hasattr(os, 'WNOWAIT'):
            self.skipTest('waitid WNOWAIT unavailable')
        owner = self.owner()
        owner.kill()
        os.waitid(os.P_PID, owner.pid, os.WEXITED | os.WNOWAIT)
        marker = self.root / 'must-not-exist'
        with mock.patch.object(watch.os, 'fork', wraps=os.fork) as fork:
            result = watch.supervise(owner.pid, [sys.executable, '-I', '-c',
                                                'from pathlib import Path; Path(%r).touch()' % str(marker)])
        self.assertEqual(result, 143)
        self.assertFalse(marker.exists())
        fork.assert_not_called()
        self.assertEqual(owner.wait(timeout=3), -signal.SIGKILL)

    def test_supervisor_termination_cleans_its_child(self):
        owner = self.owner()
        supervisor, child = self.start_supervisor(
            owner, [sys.executable, '-I', '-c', 'import time; time.sleep(30)'])
        supervisor.terminate()
        _, stderr = supervisor.communicate(timeout=3)
        self.assertEqual(supervisor.returncode, 143, stderr)
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)

    def test_unavailable_exit_events_never_start_command(self):
        marker = self.root / 'must-not-exist'
        with mock.patch.object(watch, '_process_events', side_effect=watch.WatchError('unsupported')):
            with self.assertRaises(watch.WatchError):
                watch.supervise(os.getpid() + 1, [sys.executable, '-I', '-c',
                                                'from pathlib import Path; Path(%r).touch()' % str(marker)])
        self.assertFalse(marker.exists())

    def test_failed_child_event_registration_never_releases_command(self):
        marker = self.root / 'must-not-exist'
        owner = self.owner()
        events = watch._process_events(owner.pid)
        with mock.patch.object(events, 'add_child', side_effect=OSError('injected registration error')):
            with mock.patch.object(watch, '_process_events', return_value=events):
                with self.assertRaises(OSError):
                    watch.supervise(owner.pid, [sys.executable, '-I', '-c',
                                               'from pathlib import Path; Path(%r).touch()' % str(marker)])
        self.assertFalse(marker.exists())

    def test_ready_fd_must_be_a_pipe_before_starting_command(self):
        marker = self.root / 'must-not-exist'
        with (self.root / 'not-a-pipe').open('wb') as output:
            with self.assertRaises(watch.WatchError):
                watch.supervise(os.getpid() + 1, [sys.executable, '-I', '-c',
                                                'from pathlib import Path; Path(%r).touch()' % str(marker)],
                                output.fileno())
        self.assertFalse(marker.exists())

    def test_inherited_sigchld_ignore_cannot_auto_reap_supervised_child(self):
        owner = self.owner()
        previous = signal.signal(signal.SIGCHLD, signal.SIG_IGN)
        try:
            result = watch.supervise(owner.pid, [sys.executable, '-I', '-c', 'import sys; sys.exit(7)'])
            self.assertEqual(result, 7)
            self.assertEqual(signal.getsignal(signal.SIGCHLD), signal.SIG_IGN)
        finally:
            signal.signal(signal.SIGCHLD, previous)


if __name__ == '__main__':
    unittest.main()
