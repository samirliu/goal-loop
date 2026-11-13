"""Frozen job checks for the real auditlog crew; final checks are separate."""
import argparse
import copy
import importlib
import json
from pathlib import Path
import random
import sys


def check(project, task):
    sys.path.insert(0, str(project))
    if task == 'T1':
        parse = importlib.import_module('auditlog.codec').parse_line
        for value in ('x', '中', ' '):
            for amount in (-10**40, 0, 10**40):
                assert parse(json.dumps(dict(key=value, amount=amount, ignored=True))) == dict(key=value, amount=amount)
        for value in ('[]', '{}', '{"key":"","amount":0}', '{"key":"x","amount":true}',
                      '{"key":"x","amount":1.5}', '{bad', '{"key":1,"amount":2}'):
            try:
                parse(value)
            except ValueError:
                pass
            else:
                raise AssertionError('invalid record accepted')
        # CLI integration is deliberately deferred to the independent final
        # grader, after the other worker has supplied aggregate.py.
        compile((project / 'auditlog/__main__.py').read_bytes(), '__main__.py', 'exec')
    else:
        summarize = importlib.import_module('auditlog.aggregate').summarize
        rng = random.Random(911207)
        rows = [dict(key=rng.choice(['a', '中', ' ', 'z']), amount=rng.randrange(-10**5, 10**5)) for _ in range(137)]
        original = copy.deepcopy(rows)
        expected = []
        for key in sorted({r['key'] for r in rows}):
            amounts = [r['amount'] for r in rows if r['key'] == key]
            expected.append(dict(key=key, count=len(amounts), total=sum(amounts), min=min(amounts), max=max(amounts)))
        assert summarize(iter(rows)) == expected and rows == original
        assert summarize(iter([])) == []


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    parser.add_argument('task', choices=('T1', 'T2'))
    args = parser.parse_args()
    check(args.project, args.task)
    print('JOB PASS')
