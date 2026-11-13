#!/usr/bin/env python3
"""Observed command costs, separate from acceptance evidence and iterations.

One atomic JSON record per supervised command; a running record survives an
interrupted supervisor. Nested spans are linked, never summed as wall time.
This is trusted local telemetry, not an OS boundary or a task-quality grader.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import uuid

KINDS = {'executor', 'measurement', 'verification', 'acceptance', 'pause', 'command'}
IDENTITY = re.compile(r'^[0-9a-f]{32}$')
HASH = re.compile(r'^[0-9a-f]{64}$')


def host_metadata(value):
    """Only identity/measurement metadata, never prompts or model reasoning."""
    fields = {'backend', 'session', 'event', 'call_id', 'agent_id', 'parent_agent_id',
              'task', 'files', 'input_sha256', 'output_sha256', 'before_sha256',
              'after_sha256', 'ready', 'outcome', 'receipt_sha256'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('unknown host observation fields')
    for name in ('backend', 'session', 'event'):
        if not isinstance(value[name], str) or not value[name] or '\0' in value[name]:
            raise ValueError('invalid host observation identity')
    for name in ('call_id', 'agent_id', 'parent_agent_id', 'task'):
        if value[name] is not None and (not isinstance(value[name], str) or not value[name] or '\0' in value[name]):
            raise ValueError('invalid native identity')
    for name in ('input_sha256', 'output_sha256', 'before_sha256', 'after_sha256', 'receipt_sha256'):
        if value[name] is not None and (not isinstance(value[name], str) or not HASH.fullmatch(value[name])):
            raise ValueError('invalid native observation digest')
    files = value['files']
    if files is not None and (not isinstance(files, list)
                             or not all(isinstance(p, str) and p and not p.startswith('/')
                                        and not {'.goal', '.git', '..'}.intersection(p.split('/')) for p in files)
                             or len(files) != len(set(files))):
        raise ValueError('invalid native owned scope')
    if value['outcome'] not in ('running', 'returned', 'failed', 'cancel-requested', 'cancelled'):
        raise ValueError('invalid native outcome')
    ready = value['ready']
    if ready is not None and (not isinstance(ready, dict) or set(ready) != {'epoch', 'monotonic'}
            or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in ready.values())):
        raise ValueError('invalid native readiness observation')
    return value


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    return checksum(path.read_bytes()) if path.is_file() else None


def directory(project, create=False):
    root = Path(project).resolve(strict=True)
    path = root
    for part in ('.goal', 'evidence', 'runtime'):
        path = path / part
        if path.is_symlink():
            raise ValueError('symlink runtime directory refused')
        if create and part != '.goal':
            path.mkdir(exist_ok=True)
        if not path.is_dir():
            raise FileNotFoundError(str(path))
    return root, path


def publish(path, payload):
    data = encoded({'payload': payload, 'sha256': checksum(encoded(payload))})
    fd, temp = tempfile.mkstemp(prefix='.trace-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class Trace:
    def __init__(self, project, kind, label, command, artifact=None, host=None):
        if kind not in KINDS or not isinstance(label, str) or not all(isinstance(s, str) for s in command):
            raise ValueError('invalid command trace')
        root, folder = directory(project, create=True)
        self.identity = uuid.uuid4().hex
        self.path = folder / (self.identity + '.json')
        parent = os.environ.get('GOAL_TRACE_PARENT')
        if parent is not None and not IDENTITY.fullmatch(parent):
            raise ValueError('invalid parent trace identity')
        state = root / '.goal'
        run = None
        if (state / 'runner.json').is_file():
            run = json.loads((state / 'runner.json').read_bytes()).get('run')
        instruments = {name: file_hash(Path(__file__).with_name(name)) for name in
                       ('goal_bounded.py', 'goal_owner_watch.py', 'goal_gate.sh')}
        self.data = dict(version=1, id=self.identity, parent=parent, run=run, kind=kind, label=label,
                         command=command, command_sha256=checksum(encoded(command)),
                         artifact=artifact, contract_sha256=file_hash(state / 'goal.md'),
                         check_freeze_sha256=file_hash(state / 'check_freeze'), instruments=instruments,
                         input_coverage='artifact-and-command; external and transitive inputs unknown',
                         started=time.time(), start_monotonic=time.monotonic(), finished=None,
                         elapsed=None, result=None, state='running', tokens=None, money=None)
        if host is not None:
            self.data.update(version=2, host=host_metadata(host))
        publish(self.path, self.data)

    def finish(self, result):
        self.data.update(finished=time.time(), elapsed=max(0, time.monotonic()-self.data['start_monotonic']),
                         result=result, state='complete')
        publish(self.path, self.data)


def records(project):
    try:
        _, folder = directory(project)
    except FileNotFoundError:
        return []
    found = []
    for path in sorted(folder.iterdir()):
        if path.name.startswith('.trace-'):
            continue  # uncommitted temporary, never a completed observation
        if path.is_symlink() or not IDENTITY.fullmatch(path.stem) or path.suffix != '.json':
            raise ValueError('unknown runtime record')
        value = json.loads(path.read_bytes())
        if (not isinstance(value, dict) or set(value) != {'payload', 'sha256'}
                or value['sha256'] != checksum(encoded(value['payload']))):
            raise ValueError('runtime record checksum mismatch')
        row = value['payload']
        fields = {'version', 'id', 'parent', 'run', 'kind', 'label', 'command', 'command_sha256',
                  'artifact', 'contract_sha256', 'check_freeze_sha256', 'instruments', 'input_coverage',
                  'started', 'start_monotonic', 'finished', 'elapsed', 'result', 'state', 'tokens', 'money'}
        if isinstance(row, dict) and row.get('version') == 2:
            fields.add('host')
            host_metadata(row.get('host'))
        if (not isinstance(row, dict) or set(row) != fields or type(row.get('version')) is not int
                or row['version'] not in (1, 2) or row.get('id') != path.stem
                or row.get('kind') not in KINDS or row.get('state') not in ('running', 'complete')
                or row.get('tokens') is not None or row.get('money') is not None
                or not isinstance(row['command'], list) or not all(isinstance(s, str) for s in row['command'])
                or row['command_sha256'] != checksum(encoded(row['command']))
                or not isinstance(row['label'], str)
                or row['parent'] is not None and (not isinstance(row['parent'], str) or not IDENTITY.fullmatch(row['parent']))
                or any(type(row[k]) not in (int, float) or not math.isfinite(row[k]) or row[k] < 0
                       for k in ('started', 'start_monotonic'))):
            raise ValueError('invalid runtime observation')
        if row['state'] == 'complete' and (type(row.get('elapsed')) not in (int, float)
                or not math.isfinite(row['elapsed']) or row['elapsed'] < 0
                or type(row.get('result')) is not int or not 0 <= row['result'] <= 255):
            raise ValueError('invalid completed runtime observation')
        if row['state'] == 'running' and any(row[k] is not None for k in ('result', 'elapsed', 'finished')):
            raise ValueError('unfinished runtime observation claims a result')
        found.append(row)
    return found


def summary(project):
    observed = records(project)
    if not observed:
        print('CTL: RUNTIME observations=none costs=unknown')
        return
    complete = [r for r in observed if r['state'] == 'complete']
    def total(kind):
        rows = [r for r in complete if r['kind'] == kind]
        return 'unknown' if not rows else '%.6f' % sum(r['elapsed'] for r in rows)
    print('CTL: RUNTIME observed-spans=%s complete=%s unfinished=%s executor-span-seconds=%s measurement-span-seconds=%s '
          'wall=not-summed tokens=unknown money=unknown coverage=observed' %
          (len(observed), len(complete), len(observed)-len(complete), total('executor'), total('measurement')))


if __name__ == '__main__':
    try:
        if len(sys.argv) == 3 and sys.argv[1] == 'summary':
            summary(sys.argv[2])
        else:
            raise ValueError('usage: summary PROJECT')
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print('CTL: RUNTIME unavailable: %s (costs=unknown)' % exc, file=sys.stderr)
        sys.exit(4)
