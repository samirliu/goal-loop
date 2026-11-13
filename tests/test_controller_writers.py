"""End-to-end concurrent controller regression; never touches a real project."""
import os
import fcntl
from pathlib import Path
import re
import subprocess
import shlex
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
CTL = ROOT / 'scripts/goal_ctl.sh'


class ControllerWriters(unittest.TestCase):
    def test_killed_close_blocks_readers_and_recovers_without_replaying_checks(self):
        with tempfile.TemporaryDirectory(prefix='goal-close-crash-') as tmp:
            project = Path(tmp)
            subprocess.run(['bash', str(CTL), 'init', '--project', str(project)], check=True, capture_output=True)
            state = project / '.goal'
            (state / 'goal.md').write_text(
                '# Goal\n\n## Acceptance criteria\n\n'
                '- AC-1 | pass | check: `true` | expected: exit=0\n\n'
                '## Approval\n\napproved: PENDING\n')
            subprocess.run(['bash', str(CTL), 'stamp', '--project', str(project), '--auto'], check=True, capture_output=True)
            (project / 'a.txt').write_text('artifact\n')
            names = ('state.rec', 'loop-log.md', 'scores.rec')
            before = {name: (state / name).read_bytes() if (state / name).exists() else None for name in names}
            bindir = project / 'bin'
            bindir.mkdir()
            shim = bindir / 'after-log-append.sh'
            shim.write_text('''printf() {
  builtin printf "$@" || return $?
  if [ "${2:-}" = '## iteration 1' ] && [ -n "${GOAL_WRITER_OWNER_PID:-}" ]; then
    : > "$GOAL_TEST_KILLED_AT_APPEND"
    kill -KILL "$GOAL_WRITER_OWNER_PID"
  fi
}
''')
            marker = state/'evidence/killed-at-append'
            env = dict(os.environ, BASH_ENV=str(shim), GOAL_TEST_KILLED_AT_APPEND=str(marker))
            result = subprocess.run(['bash', str(CTL), 'close-iteration', '--project', str(project),
                                     '--task', 'T1', '--files', 'a.txt', '--checks-pass', '1',
                                     '--checks-fail', '0', '--checks-unverifiable', '0', '--no-gate'],
                                    env=env, capture_output=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(marker.exists(), 'fault injection did not reach the actual log append')
            self.assertTrue((state / 'store/pending').is_file())
            self.assertIn('## iteration 1', (state / 'loop-log.md').read_text())
            for cmd in (['bash', str(CTL), 'status'], ['bash', str(ROOT / 'scripts/goal_gate.sh'), '--check']):
                refused = subprocess.run(cmd + ['--project', str(project)], capture_output=True)
                self.assertEqual(refused.returncode, 4, refused)
            journal = state / 'store/pending'
            valid_journal = journal.read_bytes()
            journal.write_bytes(valid_journal[:-5])
            interrupted = {name: (state / name).read_bytes() if (state / name).exists() else None for name in names}
            corrupt = subprocess.run(['bash', str(CTL), 'recover', '--project', str(project)], capture_output=True)
            self.assertEqual(corrupt.returncode, 4, corrupt.stderr)
            self.assertTrue(journal.exists())
            self.assertEqual(interrupted, {name: (state / name).read_bytes() if (state / name).exists() else None for name in names})
            journal.write_bytes(valid_journal)
            for _ in range(2):
                recovered = subprocess.run(['bash', str(CTL), 'recover', '--project', str(project)], capture_output=True)
                self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertFalse((state / 'store/pending').exists())
            self.assertEqual(before, {name: (state / name).read_bytes() if (state / name).exists() else None for name in names})
            # Simulate a failed shell append (for example ENOSPC) after the
            # journal is durable, without exhausting the host filesystem.
            startup = project / 'inject-append-failure.sh'
            startup.write_text('''printf() {
  if [ "${1:-}" = '%s|%s|%s|%s\\n' ]; then return 1; fi
  builtin printf "$@"
}
''')
            failed = subprocess.run(['bash', str(CTL), 'close-iteration', '--project', str(project),
                                     '--task', 'T1', '--files', 'a.txt', '--checks-pass', '1',
                                     '--checks-fail', '0', '--checks-unverifiable', '0', '--no-gate'],
                                    env=dict(os.environ, BASH_ENV=str(startup)), capture_output=True, timeout=20)
            self.assertEqual(failed.returncode, 4, failed.stderr)
            self.assertNotIn(b'CTL: CLOSE ok', failed.stdout)
            self.assertTrue((state / 'store/pending').is_file())
            recovered = subprocess.run(['bash', str(CTL), 'recover', '--project', str(project)], capture_output=True)
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertEqual(before, {name: (state / name).read_bytes() if (state / name).exists() else None for name in names})

    def test_malformed_deadline_refuses_writer_without_changing_ledger(self):
        with tempfile.TemporaryDirectory(prefix='goal-writer-deadline-') as tmp:
            project = Path(tmp)
            subprocess.run(['bash', str(CTL), 'init', '--project', str(project)],
                           check=True, capture_output=True)
            (project / '.goal/goal.md').write_text(
                '# Goal\n\n## Acceptance criteria\n\n'
                '- AC-1 | pass | check: `true` | expected: exit=0\n\n'
                '## Approval\n\napproved: PENDING\n')
            subprocess.run(['bash', str(CTL), 'stamp', '--project', str(project), '--auto'],
                           check=True, capture_output=True)
            (project / 'a.txt').write_text('artifact\n')
            state = project / '.goal'
            (state / 'runner.deadline').write_text('invalid\n')
            before = {p: p.read_bytes() for p in state.rglob('*') if p.is_file()}
            result = subprocess.run(
                ['bash', str(CTL), 'close-iteration', '--project', str(project),
                 '--task', 'T1', '--files', 'a.txt', '--checks-pass', '1',
                 '--checks-fail', '0', '--checks-unverifiable', '0', '--no-gate'],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 4, result.stderr)
            self.assertIn('invalid writer deadline', result.stderr)
            self.assertEqual(before, {p: p.read_bytes() for p in state.rglob('*') if p.is_file()})

    def test_contended_writer_respects_expired_deadline(self):
        with tempfile.TemporaryDirectory(prefix='goal-writer-timeout-') as tmp:
            project = Path(tmp)
            subprocess.run(['bash', str(CTL), 'init', '--project', str(project)],
                           check=True, capture_output=True)
            (project / '.goal/goal.md').write_text(
                '# Goal\n\n## Acceptance criteria\n\n'
                '- AC-1 | pass | check: `true` | expected: exit=0\n\n'
                '## Approval\n\napproved: PENDING\n')
            subprocess.run(['bash', str(CTL), 'stamp', '--project', str(project), '--auto'],
                           check=True, capture_output=True)
            (project / 'a.txt').write_text('artifact\n')
            state = project / '.goal'
            (state / 'runner.deadline').write_text('1\n')
            lock_path = state / 'store/writer.lock'
            lock_path.parent.mkdir(exist_ok=True)
            before = {p: p.read_bytes() for p in state.rglob('*') if p.is_file()}
            with lock_path.open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result = subprocess.run(
                    ['bash', str(CTL), 'close-iteration', '--project', str(project),
                     '--task', 'T1', '--files', 'a.txt', '--checks-pass', '1',
                     '--checks-fail', '0', '--checks-unverifiable', '0', '--no-gate'],
                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 4, result.stderr)
            self.assertIn('writer lock timeout', result.stderr)
            self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_two_writers_never_commit_the_same_iteration(self):
        with tempfile.TemporaryDirectory(prefix='goal-writers-') as tmp:
            root = Path(tmp)
            project = root / 'project'
            project.mkdir()
            subprocess.run(['bash', str(CTL), 'init', '--project', str(project)],
                           check=True, capture_output=True)
            (project / '.goal/goal.md').write_text(
                '# Goal\n\n## Acceptance criteria\n\n'
                '- AC-1 | pass | check: `true` | expected: exit=0\n\n'
                '## Approval\n\napproved: PENDING\n')
            subprocess.run(['bash', str(CTL), 'stamp', '--project', str(project), '--auto'],
                           check=True, capture_output=True)
            (project / 'a.txt').write_text('artifact\n')
            bindir, barrier = root / 'bin', root / 'barrier'
            bindir.mkdir(); barrier.mkdir()
            shim = bindir / 'python3'
            shim.write_text('''#!/usr/bin/env bash
if [ "${3:-}" = access-exec ] && [ "${5:-}" = write ]; then
  mkdir "$GOAL_TEST_BARRIER/$$"
  while [ ! -e "$GOAL_TEST_BARRIER/release" ]; do sleep 0.02; done
fi
exec '''+shlex.quote(sys.executable)+''' "$@"
''')
            shim.chmod(0o755)
            env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ['PATH'],
                       GOAL_TEST_BARRIER=str(barrier))
            cmd = ['bash', str(CTL), 'close-iteration', '--project', str(project),
                   '--task', 'T1', '--files', 'a.txt', '--checks-pass', '1',
                   '--checks-fail', '0', '--checks-unverifiable', '0',
                   '--progress', 'yes', '--no-gate']
            processes = [subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True) for _ in range(2)]
            try:
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    if sum(path.is_dir() for path in barrier.iterdir()) >= 2:
                        break
                    time.sleep(0.02)
                self.assertEqual(sum(path.is_dir() for path in barrier.iterdir()), 2,
                                 'both real writers must reach the pre-lock barrier')
                (barrier / 'release').touch()
                results = [process.communicate(timeout=30) for process in processes]
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill(); process.communicate(timeout=5)
            headers = re.findall(r'^## iteration (\d+)$',
                                 (project / '.goal/loop-log.md').read_text(), re.MULTILINE)
            state = (project / '.goal/state.rec').read_text()
            successful = sum(process.returncode == 0 for process in processes)
            self.assertGreaterEqual(successful, 1, results)
            self.assertEqual(len(headers), successful, results)
            self.assertEqual(headers, [str(i) for i in range(1, successful + 1)], results)
            self.assertIn('iteration=%d\n' % successful, state)


if __name__ == '__main__':
    unittest.main()
