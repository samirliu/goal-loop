#!/usr/bin/env python3
"""Independent factorization jobs and a small, exact certificate checker."""
import json
import math
import os
from pathlib import Path
import random
import signal
import sys
import time


def prime(n):
    return type(n) is int and n >= 2 and all(n % d for d in range(2, math.isqrt(n) + 1))


def make_inputs(seed, jobs=3, items=18):
    pool = []
    for base in range(1_000_000, 1_010_000, 500):
        while not prime(base):
            base += 1
        pool.append(base)
    rng = random.Random(seed)
    for i in range(1, jobs + 1):
        values = [rng.choice(pool) * rng.choice(pool) for _ in range(items)]
        Path('input-T%s.json' % i).write_text(json.dumps(values))


def factor(n):
    result, d = [], 2
    while d*d <= n:
        while n % d == 0:
            result.append(d)
            n //= d
        d = 3 if d == 2 else d + 2
    if n > 1:
        result.append(n)
    return result


def work(task):
    numbers = json.loads(Path('input-' + task + '.json').read_bytes())
    Path('output-' + task + '.json').write_text(json.dumps([dict(n=n, factors=factor(n)) for n in numbers]))


def grade(task):
    numbers = json.loads(Path('input-' + task + '.json').read_bytes())
    rows = json.loads(Path('output-' + task + '.json').read_bytes())
    assert len(rows) == len(numbers)
    for n, row in zip(numbers, rows):
        assert set(row) == {'n', 'factors'} and row['n'] == n
        assert isinstance(row['factors'], list) and row['factors']
        # Verify certificates, not the producer's search algorithm.
        assert all(prime(p) for p in row['factors'])
        assert math.prod(row['factors']) == n


if __name__ == '__main__':
    if sys.argv[1] == 'work':
        time.sleep(float(sys.argv[3]))  # explicitly injected backend startup
        print('READY', flush=True)
        if len(sys.argv) > 4 and sys.argv[4] == 'fail':
            os.kill(os.getpid(), signal.SIGKILL)
        work(sys.argv[2])
    elif sys.argv[1] == 'grade':
        grade(sys.argv[2])
    elif sys.argv[1] == 'grade-all':
        for i in range(1, 4):
            grade('T%s' % i)
    else:
        raise SystemExit(4)
