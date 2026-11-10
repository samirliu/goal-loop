#!/usr/bin/env python3
"""Compare the optional digest accelerator and shell fallback on one tree.

Diagnostic benchmark only: timings are observational, not a CI performance
threshold or an end-to-end agent efficiency claim.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--files', type=int, default=300)
    parser.add_argument('--repeats', type=int, default=2)
    args = parser.parse_args()
    if args.files < 1 or args.repeats < 1:
        parser.error('files and repeats must be positive')
    with tempfile.TemporaryDirectory(prefix='goal-digest-bench-') as tmp:
        root = Path(tmp)
        project, stub = root / 'tree', root / 'bin'
        project.mkdir(); stub.mkdir()
        for index in range(args.files):
            (project / ('item-%06d.txt' % index)).write_bytes(b'sample ' * 80)
        fake = stub / 'python3'
        fake.write_text('#!/bin/sh\nexit 1\n'); fake.chmod(0o755)
        reports = {}
        for label in ('shell', 'automatic'):
            env = os.environ.copy()
            if label == 'shell':
                env['PATH'] = str(stub) + os.pathsep + env.get('PATH', '')
            times, digests = [], []
            for _ in range(args.repeats):
                start = time.monotonic()
                process = subprocess.run(['bash', str(ROOT / 'scripts/goal_gate.sh'),
                                          '--digest', '--project', str(project)],
                                         env=env, capture_output=True, text=True, timeout=300)
                times.append(round(time.monotonic() - start, 4))
                if process.returncode:
                    raise RuntimeError('digest failed: ' + process.stderr)
                digests.append(process.stdout.strip())
            if len(set(digests)) != 1:
                raise RuntimeError(label + ' digest is not stable')
            reports[label] = {'elapsed_seconds': times, 'digest': digests[0]}
        if reports['shell']['digest'] != reports['automatic']['digest']:
            raise RuntimeError('backends disagree')
        print(json.dumps({'platform': platform.platform(), 'files': args.files,
                          'repeats': args.repeats, 'results': reports,
                          'note': 'automatic may use fallback when Python POSIX acceleration is unavailable'},
                         indent=2))


if __name__ == '__main__':
    main()
