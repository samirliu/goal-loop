"""Original medium TASK coverage through fresh grader CLI processes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

GRADER = Path(__file__).resolve().parents[1] / 'examples/agent-evals/grade.py'
CODEC = '''import json
def parse_line(line):
    row = json.loads(line)
    if (not isinstance(row, dict) or not isinstance(row.get("key"), str)
            or not row["key"] or type(row.get("amount")) is not int):
        raise ValueError("invalid record")
    return {"key": row["key"], "amount": row["amount"]}
'''
AGGREGATE = '''def summarize(records):
    groups = {}
    for row in records:
        groups.setdefault(row["key"], []).append(row["amount"])
    return [dict(key=key, count=len(values), total=sum(values), min=min(values), max=max(values))
            for key, values in sorted(groups.items())]
'''
MAIN = r'''import argparse,json,os,sys,tempfile
from .codec import parse_line
from .aggregate import summarize
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--skip-bad", action="store_true")
    args = parser.parse_args()
    records = []; skipped = 0
    try:
        with open(args.input, encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    records.append(parse_line(line))
                except ValueError:
                    if not args.skip_bad:
                        print("line {}".format(number), file=sys.stderr)
                        return 2
                    skipped += 1
    except FileNotFoundError:
        return 2
    summary = summarize(records)
    directory = os.path.dirname(os.path.abspath(args.output))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as stream:
            temporary = stream.name
            for row in summary:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(temporary, args.output)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
    if args.skip_bad:
        print(json.dumps({"skipped": skipped}), file=sys.stderr)
    return 0
raise SystemExit(main())
'''


class MediumGrader(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='goal-medium-grader-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def grade(self, name, mutation=None):
        project = self.root / name
        package = project / 'auditlog'
        package.mkdir(parents=True)
        programs = {'__init__.py': '', 'codec.py': CODEC, 'aggregate.py': AGGREGATE, '__main__.py': MAIN}
        if mutation is not None:
            filename, old, new = mutation
            self.assertEqual(programs[filename].count(old), 1)
            programs[filename] = programs[filename].replace(old, new)
        for filename, program in programs.items():
            (package / filename).write_text(program)
        # Every call imports the candidate in a new interpreter, so a prior
        # control/mutant cannot supply a cached auditlog module.
        result = subprocess.run([sys.executable, '-B', str(GRADER), '--project', str(project),
                                 '--family', 'medium', '--seed', '911207'],
                                capture_output=True, text=True, timeout=20)
        self.assertTrue(result.stdout, result.stderr)
        report = json.loads(result.stdout)
        failed = [row['name'] for row in report['checks'] if not row['pass_']]
        print('MEDIUM_GRADER_OBSERVATION ' + json.dumps(dict(
            fixture=name, returncode=result.returncode, ok=report['ok'], checks=len(report['checks']),
            failed=failed, error=report['error'], grader_sha256=hashlib.sha256(GRADER.read_bytes()).hexdigest())), flush=True)
        return result, report, failed

    def test_correct_control_is_accepted(self):
        result, report, failed = self.grade('control')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(report['ok'], report['error'])
        self.assertFalse(failed)

    def test_five_single_defect_mutants_are_rejected(self):
        mutants = {
            'missing-input': ('cli-missing-input', ('__main__.py',
                '    except FileNotFoundError:\n        return 2',
                '    except FileNotFoundError:\n        return 1')),
            'physical-line': ('strict-physical-line-13', ('__main__.py',
                '"line {}".format(number)', '"line {}".format(3)')),
            'integer-amount': ('parser-original-integer', ('codec.py',
                'return {"key": row["key"], "amount": row["amount"]}',
                'return {"key": row["key"], "amount": float(row["amount"])}')),
            'skip-fields': ('skip-bad-complete-groups', ('__main__.py',
                '    summary = summarize(records)',
                '    summary = summarize(records)\n    if args.skip_bad:\n'
                '        summary = [{"count": row["count"]} for row in summary]')),
            'literal-utf8': ('cli-literal-utf8', ('__main__.py',
                'open(args.input, encoding="utf-8")', 'open(args.input, encoding="ascii")')),
        }
        for name, (expected_check, mutation) in mutants.items():
            with self.subTest(mutant=name):
                result, report, failed = self.grade(name, mutation)
                self.assertEqual(result.returncode, 1, 'accepted mutant: ' + name)
                self.assertFalse(report['ok'], 'accepted mutant: ' + name)
                self.assertIn(expected_check, failed)


if __name__ == '__main__':
    unittest.main()
