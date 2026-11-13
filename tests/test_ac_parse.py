"""Frozen original-parser outputs, including CRLF/duplicates/backtick decoys."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARSER = ROOT/'scripts/goal_parse.sh'


class ACParsing(unittest.TestCase):
    def test_matches_six_hundred_frozen_original_outputs(self):
        golden = json.loads((ROOT/'tests/fixtures/ac-parser-golden.json').read_bytes())
        script = '. "$1"; shift; project="$1"; shift; for fn in "$@"; do value=$("$fn" "$project" AC-1); printf "%s\\0" "$value"; done'
        with tempfile.TemporaryDirectory(prefix='goal-ac-parser-') as directory:
            project = Path(directory); (project/'.goal').mkdir()
            for index, case in enumerate(golden['cases']):
                with self.subTest(case=index):
                    (project/'.goal/goal.md').write_bytes(case['text'].encode())
                    fields = list(case['expected'])
                    result = subprocess.run(['bash', '-c', script, 'parser', str(PARSER), str(project), *fields],
                                            capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    values = [v.decode() for v in result.stdout.split(b'\0')[:-1]]
                    self.assertEqual(dict(zip(fields, values)), case['expected'])

    def test_field_reads_current_bytes_after_change(self):
        with tempfile.TemporaryDirectory(prefix='goal-ac-fresh-') as directory:
            project = Path(directory); (project/'.goal').mkdir()
            goal = project/'.goal/goal.md'
            goal.write_text('- AC-1 | check: `old` | expected: exit=0\n')
            script = '. "$1"; gp_ac_check_cmd "$2" AC-1; '
            script += 'printf \'%s\\n\' \'- AC-1 | check: `new` | expected: exit=1\' > "$2/.goal/goal.md"; gp_ac_check_cmd "$2" AC-1'
            result = subprocess.run(['bash', '-c', script, 'parser', str(PARSER), str(project)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, b'old\nnew\n')


if __name__ == '__main__':
    unittest.main()
