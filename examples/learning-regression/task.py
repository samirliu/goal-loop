#!/usr/bin/env python3
"""Run named real repository tests and verify their owned result receipts."""
import json
import os
from pathlib import Path
import sys
import unittest


def require(value, message):
    if not value:
        raise ValueError(message)


def work(task, corrupt=False):
    source = json.loads(Path('input-'+task+'.json').read_bytes())
    # Fixtures own separate goal directories. Do not redirect their traces
    # into this workflow or inherit its session identity. The real outer
    # process supervisor still owns this job, its descendants and deadline.
    for name in list(os.environ):
        if name.startswith('GOAL_'):
            os.environ.pop(name)
    sys.path.insert(0, source['tests_root'])
    names = source['tests']
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    require(suite.countTestCases() == len(names), 'requested tests did not load exactly')
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(suite)
    value = dict(requested=names, ran=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                 skipped=len(result.skipped), successful=result.wasSuccessful())
    if corrupt:
        value['ran'] = 0  # Known-bad artifact, with a normal worker exit.
    Path('result-'+task+'.json').write_text(json.dumps(value))
    return 0 if result.wasSuccessful() else 1


def grade(task):
    expected = json.loads(Path('input-'+task+'.json').read_bytes())['tests']
    value = json.loads(Path('result-'+task+'.json').read_bytes())
    require(set(value) == {'requested','ran','failures','errors','skipped','successful'}, 'unknown result fields')
    require(value['requested'] == expected and type(value['ran']) is int and value['ran'] == len(expected), 'missing or substituted tests')
    require(value['successful'] is True and all(type(value[k]) is int and value[k] == 0
            for k in ('failures','errors','skipped')), 'a failed/skipped test is not a successful delivery')


if __name__ == '__main__':
    action, task, *options = sys.argv[1:]
    if action == 'work':
        require(not options or float(options[0]) == 0, 'this experiment never injects startup delay')
        print('READY', flush=True)
        raise SystemExit(work(task, corrupt=len(options) > 1 and options[1] == 'fail'))
    if action == 'grade':
        grade(task)
    elif action == 'grade-all':
        for path in sorted(Path('.').glob('input-T*.json')):
            grade(path.stem.removeprefix('input-'))
    elif action != 'work':
        raise SystemExit(4)
