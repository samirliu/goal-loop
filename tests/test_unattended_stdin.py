"""The model CLI cannot consume or wait on its caller's interactive stdin."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


class ExecutorInput(unittest.TestCase):
    def test_open_caller_pipe_does_not_block_fixed_prompt_executor(self):
        with tempfile.TemporaryDirectory(prefix='goal-host-stdin-') as tmp:
            project = Path(tmp)
            def ctl(*args):
                result = subprocess.run(['bash', str(SCRIPTS / 'goal_ctl.sh'), *args, '--project', tmp],
                                        capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            ctl('init')
            (project / '.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n'
                '- AC-1 | isolated fixed-prompt input | check: `grep -qx EOF artifact.txt` | expected: exit=0\n\n'
                '## Approval\n\napproved: PENDING\n')
            ctl('stamp', '--auto')
            worker = project / 'model-client'
            worker.write_text('#!' + sys.executable + '\n' +
                'import pathlib,subprocess,sys\n'
                'data=sys.stdin.read()\n'
                'pathlib.Path("artifact.txt").write_text("EOF\\n" if not data else "polluted\\n")\n'
                'sys.exit(subprocess.call(' + repr(['bash', str(SCRIPTS / 'goal_ctl.sh'), 'close-iteration',
                    '--project', tmp, '--task', 'T1', '--files', 'artifact.txt', '--checks-pass', '1',
                    '--checks-fail', '0', '--checks-unverifiable', '0', '--exit-signal', 'yes',
                    '--adversarial', 'clear', '--adversarial-note', 'observed actual stdin EOF', '--no-gate']) + '))\n')
            worker.chmod(0o755)
            command = ['bash', str(SCRIPTS.parent / 'devtools/goal_loop.sh'), '--continue', '--project', tmp,
                       '--max-iterations=1', '--wallclock=5']
            process = subprocess.Popen(command, env=dict(os.environ, CLAUDE_BIN=str(worker)),
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                # wait() intentionally keeps the caller's stdin pipe open.
                # communicate() would close it and conceal this bug.
                process.wait(timeout=12)
                process.stdin.close()
                process.stdin = None
                out, err = process.communicate(timeout=2)
                self.assertEqual(process.returncode, 0, out + err)
                self.assertEqual((project / 'artifact.txt').read_text(), 'EOF\n')
            finally:
                if process.poll() is None:
                    process.terminate()
                process.communicate(timeout=4)


if __name__ == '__main__':
    unittest.main(verbosity=2)
