"""Deterministic resource-pressure counterexample for finite-settlement tests."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ScenarioResources(unittest.TestCase):
    def test_same_gate_and_assertion_under_shared_and_isolated_pressure(self):
        with tempfile.TemporaryDirectory(prefix='goal-scenario-resources-') as directory:
            root = Path(directory)
            (root/'scripts').symlink_to(ROOT/'scripts', target_is_directory=True)
            tests = root/'tests'; tests.mkdir()
            for name in ('run_tests.sh', 'lib.sh', 'view_fixture.py'):
                (tests/name).symlink_to(ROOT/'tests'/name)
            # Resolve the runner from a copied file so its test root is local.
            (tests/'run_tests.sh').unlink()
            (tests/'run_tests.sh').write_bytes((ROOT/'tests/run_tests.sh').read_bytes())
            (tests/'cases.inc.sh').write_text('''# 01 shared resource pressure
touch "$RESOURCE_BUSY"
sleep 7
rm "$RESOURCE_BUSY"
ok "pressure producer joined"

# 02 [timing-isolated] finite settlement with a passing check
mkproj t2
TB=1 contract t2 '- AC-1 | check | check: `if test -f .goal/evidence/armed && test -f "$RESOURCE_BUSY"; then sleep 5; fi; true` | expected: exit=0'
sed_in 's/^deadline=.*/deadline=1/' "$T/t2/.goal/state.rec"
close_iter t2
touch "$T/t2/.goal/evidence/armed"
out=$(bash "$GATE" --check --project "$T/t2" 2>&1); rc=$?
printf '%s\\n' "$out"
assert_rc "same green settlement" 0 "$rc"
''')
            outcomes = []
            for shared in (True, False):
                began = time.monotonic()
                result = subprocess.run(['bash', str(tests/'run_tests.sh'), '--jobs=2',
                                         *(['--shared-timing'] if shared else [])], cwd=root,
                                        env=dict(os.environ, RESOURCE_BUSY=str(root/'busy')),
                                        capture_output=True, text=True, timeout=25)
                outcomes.append(dict(shared=shared, result=result.returncode, elapsed=time.monotonic()-began,
                                     stdout=result.stdout, stderr=result.stderr))
            print('RESOURCE_PRESSURE_OBSERVATION '+repr(outcomes), flush=True)
            self.assertEqual(outcomes[0]['result'], 1, outcomes)
            self.assertIn('BLOCKED reason=time-budget-exhausted', outcomes[0]['stdout'], outcomes)
            self.assertEqual(outcomes[1]['result'], 0, outcomes)
            self.assertIn('GATE: GO ', outcomes[1]['stdout'], outcomes)


if __name__ == '__main__':
    unittest.main()
