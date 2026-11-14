"""The executable example must never print PASS with its checks disabled."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/'examples/evolution-dedupe/run.py'
PROBE = '''import hashlib,json,runpy,subprocess,sys
from pathlib import Path
script,output=sys.argv[1:]
state=Path(output)/'state';state.mkdir(parents=True)
program=state/'fixture.py';program.write_text('fixture')
(state/'enabled.json').write_text(json.dumps(dict(policy=hashlib.sha256(program.read_bytes()).hexdigest(),program=program.name)))
subprocess.check_output=lambda *a,**k:json.dumps(dict(status='enabled'))
subprocess.run=lambda *a,**k:subprocess.CompletedProcess(a,0,stdout=b'[]',stderr=b'')
sys.argv=[script,'--output',output]
runpy.run_path(script,run_name='__main__')
'''


class ExampleRecheck(unittest.TestCase):
    def test_incorrect_later_output_is_rejected_with_and_without_optimization(self):
        with tempfile.TemporaryDirectory(prefix='goal-example-recheck-') as tmp:
            for optimization in ([], ['-O']):
                with self.subTest(optimization=optimization):
                    output = str(Path(tmp)/('optimized' if optimization else 'normal'))
                    result = subprocess.run([sys.executable, '-B', *optimization, '-c', PROBE, str(SCRIPT), output],
                                            capture_output=True, text=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn('failed independent recheck', result.stderr)
                    self.assertNotIn('rechecked: PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
