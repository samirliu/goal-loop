#!/usr/bin/env python3
"""Collect ONE frozen native Codex evaluation, without a model client.

Start ``run MANIFEST --manifest-sha256 SHA --output NEW_DIR`` before spawning
the worker. Wait for NEW_DIR/ready.json and use its deadlines in the prompt.
The manifest has version=1, position, group, goal_loop, agent_path,
parent_thread_id, model, effort, seconds, execution_seconds,
max_internal_workers, initial_workspace, immutable_inputs=[relative_path],
work (must not exist), frozen={absolute_path: fingerprint(path)},
artifacts=[absolute_path], and checks=[{name, argv, cwd}]. ``independent`` is
required; goal_loop also requires the frozen original ``audit`` and ``gate``.
``fingerprint PATH ...`` prints fingerprints for preparing that manifest.

Only a matching host task_complete, a normal final, and terminal descendants
permit checks. Checks share the ORIGINAL outer deadline. No replay can rescue
a failure. SIGINT/SIGTERM or NEW_DIR/cancel cancels local collection/checks;
NEW_DIR/needs-interrupt.json asks the parent to interrupt native workers.
This process cannot cancel a service-side model or prove service compute ended.

Native logs are trusted host evidence, not signed evidence or a security
boundary. Unflushed/unavailable sessions, opaque tool bodies and unsupported
schemas remain unknown. Frozen bytes are checked at startup, before/between
checks and at completion; transient changes between snapshots are unobservable.
Synthetic tests exercise this mechanism only, never model effectiveness.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = [Path(__file__), *(ROOT / 'scripts' / n for n in
           ('goal_bounded.py', 'goal_owner_watch.py', 'goal_trace.py'))]
UNKNOWN = '[UNKNOWN: encrypted or opaque at rest]'
SECRET = re.compile(r'(?i)(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|'
                    r'password|passwd|client[_-]?secret|credential|cookie|private[_-]?key)')
TOOLS = {'function_call', 'custom_tool_call', 'function_call_output', 'custom_tool_call_output'}
LIFECYCLE = {'task_started', 'task_complete', 'turn_aborted'}
MAX_LINE = 16 * 1024 * 1024
MAX_SESSION = 128 * 1024 * 1024


class CaptureError(RuntimeError):
    pass


def require(value, reason):
    if not value:
        raise CaptureError(reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(path):
    """Hash bytes and modes, including directory membership; never follow links."""
    path = Path(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {'kind': 'missing'}
    result = {'mode': stat.S_IMODE(info.st_mode)}
    if stat.S_ISLNK(info.st_mode):
        return dict(result, kind='symlink', target=os.readlink(path))
    if stat.S_ISREG(info.st_mode):
        return dict(result, kind='file', sha256=sha(path))
    require(stat.S_ISDIR(info.st_mode), 'unsupported filesystem entry: ' + str(path))
    return dict(result, kind='directory', entries={p.name: fingerprint(p) for p in sorted(path.iterdir())})


def sanitize(value):
    """Allow readable receipts; discard reasoning, secrets and opaque ciphertext."""
    if isinstance(value, dict):
        if any('encrypt' in str(k).lower() or 'ciphertext' in str(k).lower() for k in value):
            return UNKNOWN
        if value.get('type') in ('reasoning', 'encrypted', 'encrypted_text'):
            return UNKNOWN
        return {k: ('[REDACTED]' if SECRET.search(str(k)) else sanitize(v))
                for k, v in value.items() if 'reasoning' not in str(k).lower()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if not isinstance(value, str):
        return value
    if re.search(r'(?i)(?:\[|<)\s*(?:content )?encrypted|ciphertext|encrypted[_-]content', value):
        return UNKNOWN
    value = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----',
                   '[REDACTED]', value, flags=re.S)
    value = re.sub(r'(?i)\b(?:bearer|basic)\s+[A-Za-z0-9_./+=-]+', '[REDACTED]', value)
    value = re.sub(r'\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|'
                   r'github_pat_[A-Za-z0-9_]{12,}|AKIA[A-Z0-9]{16})\b', '[REDACTED]', value)
    value = re.sub(r'(?i)((?:[A-Za-z0-9_]*(?:token|password|passwd|secret|api_key|apikey|'
                   r'credential|cookie)[A-Za-z0-9_]*|authorization)[\s\"\x27]*[:=]\s*)'
                   r'(?:\"[^\"]*\"|\x27[^\x27]*\x27|[^\s,;}]+)', r'\1[REDACTED]', value)
    value = re.sub(r'https?://[^\s/:]+:[^\s/@]+@', 'https://[REDACTED]@', value)
    return re.sub(r'(?<![A-Za-z0-9_/])[A-Za-z0-9_+/=-]{100,}(?![A-Za-z0-9_/])', UNKNOWN, value)


def save(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(sanitize(value), stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def epoch(value):
    result = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.tzinfo is not None, 'native timestamp has no timezone')
    return result.timestamp()


def metadata(payload):
    result = {k: payload[k] for k in ('id', 'session_id', 'timestamp', 'cwd', 'agent_path',
              'parent_thread_id', 'model_provider', 'cli_version') if k in payload}
    spawn = payload.get('source', {})
    if isinstance(spawn, dict):
        spawn = spawn.get('subagent', {}).get('thread_spawn', {})
        result['spawn'] = {k: spawn[k] for k in ('parent_thread_id', 'agent_path', 'depth') if k in spawn}
    return result


class NativeSession:
    def __init__(self, path, meta, capture):
        self.path, self.meta, self.capture = path, meta, capture
        info = path.stat()
        self.identity = (info.st_dev, info.st_ino)
        self.source_mode = stat.S_IMODE(info.st_mode)
        self.offset = self.lines = self.metas = self.tools = self.opaque_tools = 0
        self.source_hash = hashlib.sha256()
        self.tasks, self.settings, self.finals = {}, [], []
        self.current, self.pending = None, False

    @property
    def terminal(self):
        return bool(self.tasks) and self.current is None and not self.pending

    @property
    def status(self):
        return list(self.tasks.values())[-1]['status'] if self.tasks else 'unknown'

    def read(self):
        info = self.path.stat()
        require((info.st_dev, info.st_ino) == self.identity and info.st_size >= self.offset,
                'native session replaced or truncated')
        require(info.st_size <= MAX_SESSION, 'native session exceeds bounded reader limit')
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            while True:
                raw = stream.readline(MAX_LINE + 1)
                self.pending = bool(raw) and not raw.endswith(b'\n')
                require(len(raw) <= MAX_LINE, 'native row exceeds bounded reader limit')
                if not raw or self.pending:
                    break
                self.offset += len(raw)
                self.source_hash.update(raw)
                self.lines += 1
                self.accept(json.loads(raw))

    def accept(self, row):
        kind, payload = row.get('type'), row.get('payload', {})
        require(isinstance(payload, dict), 'unsupported native payload')
        subtype = payload.get('type')
        kept = None
        if kind == 'session_meta':
            self.metas += 1
            require(self.metas == 1 and metadata(payload) == self.meta, 'native metadata changed')
            kept = self.meta
        elif kind == 'turn_context':
            require(self.current == payload.get('turn_id') and self.current is not None,
                    'native settings have no matching active turn')
            require(payload.get('model') == self.capture.manifest['model'] and
                    payload.get('effort') == self.capture.manifest['effort'], 'model/effort differs or unknown')
            kept = {k: payload[k] for k in ('turn_id', 'root_turn_id', 'model', 'effort',
                    'approval_policy', 'sandbox_policy', 'permission_profile') if k in payload}
            self.settings.append(kept)
        elif kind == 'event_msg' and subtype in LIFECYCLE:
            at, turn = epoch(row['timestamp']), payload.get('turn_id')
            require(isinstance(turn, str) and bool(turn), 'native lifecycle has no turn id')
            if subtype == 'task_started':
                require(self.current is None and turn not in self.tasks, 'overlapping/repeated native turn')
                require(at >= epoch(self.meta['timestamp']), 'native turn predates native session')
                if self.meta['id'] == self.capture.session_id:
                    require(not self.tasks, 'multiple evaluation turns')
                self.current = turn
                self.tasks[turn] = dict(started_epoch=at, finished_epoch=None, status='running',
                                        root_turn_id=payload.get('root_turn_id'))
            else:
                require(self.current == turn, 'terminal has no matching active native turn')
                task = self.tasks[turn]
                require(at >= task['started_epoch'] and payload.get('root_turn_id') == task['root_turn_id'],
                        'native terminal time/root turn differs')
                require(all(epoch(f['timestamp']) <= at for f in self.finals if f['turn_id'] == turn),
                        'native terminal predates final')
                require(any(s['turn_id'] == turn for s in self.settings), 'native model/effort unobserved')
                task.update(finished_epoch=at, status='completed' if subtype == 'task_complete' else 'aborted')
                self.current = None
            kept = {k: payload[k] for k in ('type', 'turn_id', 'root_turn_id', 'started_at',
                    'completed_at', 'duration_ms', 'reason', 'time_to_first_token_ms') if k in payload}
        elif kind == 'response_item' and subtype in TOOLS:
            kept = {k: payload[k] for k in ('type', 'name', 'namespace', 'call_id', 'status',
                    'input', 'arguments', 'output') if k in payload}
            self.tools += subtype in ('function_call', 'custom_tool_call')
            cleaned = sanitize(kept)
            self.opaque_tools += UNKNOWN in json.dumps(cleaned)
            kept = cleaned
        elif kind == 'response_item' and subtype == 'message' and payload.get('role') == 'assistant' and payload.get('phase') == 'final_answer':
            require(self.current is not None, 'final has no matching active native turn')
            require(epoch(row['timestamp']) >= self.tasks[self.current]['started_epoch'] and
                    payload.get('status', 'completed') == 'completed', 'native final time/status differs')
            content = [dict(type=v['type'], text=v.get('text', '')) for v in payload.get('content', [])
                       if v.get('type') in ('text', 'output_text')]
            final = '\n'.join(v['text'] for v in content)
            self.finals.append(dict(turn_id=self.current, timestamp=row['timestamp'],
                                    text=sanitize(final)))
            kept = dict(type=subtype, role='assistant', phase='final_answer', content=content)
        if kept is not None:
            at = epoch(row['timestamp'])
            require(self.capture.ready_epoch <= at <= self.capture.clock.time() + .1,
                    'native event precedes ready or has a future timestamp')
            receipt = dict(session_id=self.meta['id'], native_line=self.lines, timestamp=row['timestamp'],
                           observed_epoch=self.capture.clock.time(), observed_monotonic=self.capture.clock.monotonic(),
                           type=kind, payload=sanitize(kept))
            with (self.capture.output / 'events.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + '\n')


class Capture:
    def __init__(self, manifest, expected_sha, output, sessions_root=None, *, clock=time):
        self.clock = clock
        self.entry, self.entry_epoch = clock.monotonic(), clock.time()
        self.manifest_path, self.expected_sha, self.output = Path(manifest).absolute(), expected_sha, Path(output).absolute()
        self.sessions_root = Path(sessions_root or Path.home() / '.codex/sessions').absolute()
        self.manifest, self.headers, self.sessions, self.checks, self.reasons = {}, {}, {}, {}, []
        self.original_inputs, self.original_artifacts, self.runtime, self.immutable = {}, {}, {}, {}
        self.artifact_paths = []
        self.preparation = {}
        self.session_id, self.ready_epoch, self.cancelled = None, None, False
        self.deadline = self.execution_deadline = self.entry
        self.deadline_epoch = self.execution_deadline_epoch = self.entry_epoch
        self.peak = 0

    def prepare(self):
        require(sha(self.manifest_path) == self.expected_sha, 'frozen manifest hash differs')
        m = json.loads(self.manifest_path.read_bytes())
        require(isinstance(m, dict), 'manifest must be an object')
        self.manifest = m
        require(m.get('version') == 1 and type(m.get('position')) is int and 0 < m['position'] < 1000,
                'unsupported manifest/position')
        require(m.get('agent_path') == '/root/efficiency_%03d' % m['position'] and
                all(isinstance(m.get(k), str) and m[k] for k in ('parent_thread_id', 'model', 'effort', 'group')),
                'missing frozen native identity/settings')
        for key in ('seconds', 'execution_seconds'):
            require(type(m.get(key)) in (int, float) and math.isfinite(m[key]), 'invalid budget')
        require(0 < m['execution_seconds'] <= 780 and m['execution_seconds'] < m['seconds'] <= 900,
                'invalid outer/execution budget')
        require(type(m.get('max_internal_workers')) is int and 0 <= m['max_internal_workers'] <= 2,
                'invalid native worker bound')
        self.deadline, self.execution_deadline = self.entry + m['seconds'], self.entry + m['execution_seconds']
        self.deadline_epoch = self.entry_epoch + m['seconds']
        self.execution_deadline_epoch = self.entry_epoch + m['execution_seconds']
        require(type(m.get('goal_loop')) is bool and isinstance(m.get('frozen'), dict) and m['frozen'],
                'missing frozen inputs/source/grader')
        require(isinstance(m.get('artifacts'), list) and m['artifacts'] and
                all(isinstance(p, str) and Path(p).is_absolute() for p in m['artifacts']), 'missing/invalid artifact paths')
        self.artifact_paths = m['artifacts'][:]
        paths = [m.get('work'), m.get('initial_workspace'), *m['frozen'], *self.artifact_paths]
        require(all(isinstance(p, str) and Path(p).is_absolute() for p in paths), 'paths must be absolute')
        require(all(not self.output.resolve().is_relative_to(Path(p).resolve()) for p in paths),
                'collector output must be outside frozen/work/artifact paths')
        require(isinstance(m.get('checks'), list) and m['checks'], 'missing frozen acceptance commands')
        for check in m['checks']:
            require(re.fullmatch(r'[a-z][a-z0-9_-]*', check.get('name', '')) and
                    check['name'] not in self.checks, 'invalid/duplicate check name')
            require(isinstance(check.get('argv'), list) and check['argv'] and
                    all(isinstance(v, str) and '\0' not in v for v in check['argv']) and
                    isinstance(check.get('cwd'), str) and Path(check['cwd']).is_absolute(), 'invalid frozen command')
            self.checks[check['name']] = dict(result=None, reason='not run')
        required = {'independent', 'audit', 'gate'} if m['goal_loop'] else {'independent'}
        require(required <= set(self.checks), 'missing independent/original audit/Gate command')
        self.original_inputs = {p: fingerprint(p) for p in m['frozen']}
        require(self.original_inputs == m['frozen'], 'frozen input/source/grader differs at entry')
        initial, work = Path(m['initial_workspace']), Path(m['work'])
        require(m['initial_workspace'] in m['frozen'] and initial.is_dir() and
                m['frozen'][m['initial_workspace']]['kind'] == 'directory', 'initial workspace must be a frozen tree')
        require(not os.path.lexists(work) and not work.resolve().is_relative_to(initial.resolve()),
                'work must be a fresh path outside initial workspace')
        require(isinstance(m.get('immutable_inputs'), list) and m['immutable_inputs'], 'missing immutable workspace inputs')
        for name in m['immutable_inputs']:
            require(isinstance(name, str) and name and not Path(name).is_absolute() and
                    '..' not in Path(name).parts and name != '.', 'invalid immutable relative input')
            expected = fingerprint(initial / name)
            require(expected['kind'] != 'missing', 'immutable original input missing')
            self.immutable[str(work / name)] = expected
        self.runtime = {str(p): fingerprint(p) for p in RUNTIME}
        copy = dict(name='preparation', cwd=str(initial), argv=[sys.executable, '-I', '-B', '-c',
                    'import shutil,sys; shutil.copytree(sys.argv[1],sys.argv[2],symlinks=True)', str(initial), str(work)])
        self.preparation = self.bounded_command(copy, self.execution_deadline, self.execution_deadline_epoch)
        require(self.preparation.get('result') == 0 and self.preparation.get('supervisor_returncode') == 0 and
                self.preparation['finished'] <= self.execution_deadline and
                self.preparation['finished_epoch'] <= self.execution_deadline_epoch,
                'workspace preparation failed/exceeded original execution allowance')
        self.original_artifacts = {p: fingerprint(p) for p in m['artifacts']}
        self.discover()
        require(not self.candidates(), 'matching native session already existed before ready')
        require(self.clock.monotonic() < self.execution_deadline, 'setup exhausted execution deadline')
        self.ready_epoch = self.clock.time()
        save(self.output / 'manifest.sanitized.json', m)
        ready = dict(position=m['position'], agent_path=m['agent_path'], parent_thread_id=m['parent_thread_id'],
                     entry=self.entry, entry_epoch=self.entry_epoch, ready_epoch=self.ready_epoch,
                     deadline=self.deadline, deadline_epoch=self.deadline_epoch,
                     execution_deadline=self.execution_deadline, execution_deadline_epoch=self.execution_deadline_epoch,
                     manifest_sha256=self.expected_sha, pid=os.getpid())
        save(self.output / 'ready.json', ready)
        print('READY ' + json.dumps(ready, sort_keys=True), flush=True)

    def discover(self):
        require(self.sessions_root.is_dir(), 'native session directory unavailable')
        for path in sorted(self.sessions_root.rglob('*.jsonl')):
            info = path.stat()
            identity = (info.st_dev, info.st_ino)
            if path in self.headers and self.headers[path][0] == identity:
                continue
            with path.open('rb') as stream:
                line = stream.readline(MAX_LINE + 1)
            if not line.endswith(b'\n'):
                continue
            require(len(line) <= MAX_LINE, 'native metadata exceeds reader limit')
            row = json.loads(line)
            if row.get('type') == 'session_meta':
                self.headers[path] = (identity, metadata(row['payload']))

    def candidates(self):
        return [(p, meta) for p, (_, meta) in self.headers.items()
                if meta.get('agent_path') == self.manifest['agent_path'] and
                meta.get('parent_thread_id') == self.manifest['parent_thread_id']]

    def poll(self):
        self.discover()
        matches = self.candidates()
        require(len(matches) <= 1, 'ambiguous native evaluation identity')
        if matches and self.session_id is None:
            self.session_id = matches[0][1]['id']
        if self.session_id is None:
            return
        wanted = {self.session_id}
        while True:
            addition = {meta['id'] for _, meta in self.headers.values()
                        if meta.get('parent_thread_id') in wanted}
            if addition <= wanted:
                break
            wanted |= addition
        for sid in sorted(wanted):
            matching = [(p, meta) for p, (_, meta) in self.headers.items() if meta.get('id') == sid]
            require(len(matching) == 1, 'ambiguous descendant native session id')
            path, meta = matching[0]
            spawn = meta.get('spawn', {})
            require(spawn.get('agent_path') == meta.get('agent_path') and
                    spawn.get('parent_thread_id') == meta.get('parent_thread_id'), 'native source identity differs')
            require(meta['agent_path'] == self.manifest['agent_path'] or
                    meta['agent_path'].startswith(self.manifest['agent_path'] + '/'), 'descendant agent path differs')
            require(epoch(meta['timestamp']) >= self.ready_epoch, 'native session predates collector ready')
            if sid not in self.sessions:
                self.sessions[sid] = NativeSession(path, meta, self)
                if sid == self.session_id:
                    save(self.output / 'identity.json', dict(session_id=sid, agent_path=meta['agent_path'],
                         parent_thread_id=meta['parent_thread_id'], runtime_session_id=meta.get('session_id'),
                         observed_epoch=self.clock.time(), observed_monotonic=self.clock.monotonic(),
                         execution_deadline=self.execution_deadline, execution_deadline_epoch=self.execution_deadline_epoch,
                         deadline=self.deadline, deadline_epoch=self.deadline_epoch, manifest_sha256=self.expected_sha))
            self.sessions[sid].read()
        transitions = []
        for sid, session in self.sessions.items():
            if sid == self.session_id:
                continue
            tasks = list(session.tasks.values())
            if not tasks:
                transitions.append((epoch(session.meta['timestamp']), 1))
            for i, task in enumerate(tasks):
                transitions.append((epoch(session.meta['timestamp']) if i == 0 else task['started_epoch'], 1))
                if task['finished_epoch'] is not None:
                    transitions.append((task['finished_epoch'], -1))
        current = 0
        for _, delta in sorted(transitions):
            current += delta
            self.peak = max(self.peak, current)
        require(self.peak <= self.manifest['max_internal_workers'], 'native internal concurrency bound exceeded')

    def integrity(self):
        require(sha(self.manifest_path) == self.expected_sha, 'frozen manifest changed')
        require({p: fingerprint(p) for p in self.manifest['frozen']} == self.manifest['frozen'],
                'frozen input/source/grader changed')
        require({p: fingerprint(p) for p in self.runtime} == self.runtime, 'collector/supervisor source changed')
        require({p: fingerprint(p) for p in self.immutable} == self.immutable, 'immutable workspace input changed')

    def interrupt_needed(self, reason):
        path = self.output / 'needs-interrupt.json'
        if not path.exists():
            save(path, dict(reason=reason, epoch=self.clock.time(), agent_path=self.manifest.get('agent_path'),
                            session_id=self.session_id,
                            observed_active=[sid for sid, s in self.sessions.items() if not s.terminal],
                            native_interrupt_sent=False, service_stop_confirmed=None))

    def run_check(self, check):
        return self.bounded_command(check, self.deadline, self.deadline_epoch)

    def bounded_command(self, check, deadline, deadline_epoch):
        start, wall = self.clock.monotonic(), self.clock.time()
        require(start < deadline and wall < deadline_epoch, 'original deadline expired before command')
        status = self.output / (check['name'] + '.status')
        argv = [sys.executable, '-I', '-B', str(ROOT / 'scripts/goal_bounded.py'), '--owner', str(os.getpid()),
                '--seconds', str(deadline - start), '--deadline-epoch', str(deadline_epoch),
                '--cancel-file', str(self.output / 'cancel'), '--receipt', str(status), '--', *check['argv']]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', GOAL_RUNNER_MONOTONIC_END=str(deadline))
        for key in ('GOAL_RUNNER_FD', 'GOAL_TRACE_PROJECT', 'GOAL_TRACE_PARENT', 'GOAL_ACCESS_EXEC_PID'):
            env.pop(key, None)
        proc = subprocess.Popen(argv, cwd=check['cwd'], env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        cleanup = 'shared kernel supervisor returned after owned command-group cleanup'
        try:
            stdout, stderr = proc.communicate(timeout=max(0, deadline - self.clock.monotonic()) + .5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=2)
                cleanup = 'supervisor unresponsive; local descendant cleanup unknown'
        end = self.clock.monotonic()
        result = int(status.read_text()) if status.is_file() else None
        stdout, stderr = (sanitize(v.decode('utf-8', errors='replace')) for v in (stdout, stderr))
        for channel, value in (('stdout', stdout), ('stderr', stderr)):
            (self.output / (check['name'] + '.' + channel + '.txt')).write_text(value, encoding='utf-8')
        return dict(command=check['argv'], cwd=check['cwd'], supervisor_command=argv,
                    supervisor_returncode=proc.returncode, result=result, stdout=stdout, stderr=stderr,
                    started=start, started_epoch=wall, finished=end, finished_epoch=self.clock.time(),
                    local_cleanup=cleanup)

    def collect(self):
        while self.clock.monotonic() < self.deadline and self.clock.time() < self.deadline_epoch:
            if self.cancelled or (self.output / 'cancel').exists():
                raise CaptureError('collection cancelled; native service stop unknown')
            self.poll()
            root = self.sessions.get(self.session_id)
            if root and root.terminal:
                require(root.status == 'completed', 'native evaluation aborted')
                require(len(root.finals) == 1 and root.finals[0]['text'].strip() and UNKNOWN not in root.finals[0]['text'],
                        'normal nonempty native final missing/unknown')
                require(epoch(root.finals[0]['timestamp']) <= self.execution_deadline_epoch and
                        all(t['finished_epoch'] <= self.execution_deadline_epoch for t in root.tasks.values()),
                        'native final/terminal after execution deadline')
                if all(s.terminal for s in self.sessions.values()):
                    require(all(t['finished_epoch'] <= self.execution_deadline_epoch for s in self.sessions.values()
                                for t in s.tasks.values()), 'descendant terminal after execution deadline')
                    self.integrity()
                    for check in self.manifest['checks']:
                        require(not self.cancelled and not (self.output / 'cancel').exists(), 'collection cancelled')
                        self.checks[check['name']] = self.run_check(check)
                        receipt = self.checks[check['name']]
                        require(receipt.get('result') == 0 and receipt.get('supervisor_returncode') == 0,
                                'acceptance check failed or result unknown: ' + check['name'])
                        require(receipt['finished'] <= self.deadline and receipt['finished_epoch'] <= self.deadline_epoch,
                                'acceptance check after original outer deadline')
                        if self.manifest['goal_loop'] and check['name'] == 'gate':
                            require('GATE: GO ' in receipt['stdout'], 'original Gate GO receipt missing')
                        self.integrity()
                    self.poll()
                    require(all(s.terminal for s in self.sessions.values()), 'active descendant after checks')
                    require(all(t['finished_epoch'] <= self.execution_deadline_epoch for s in self.sessions.values()
                                for t in s.tasks.values()), 'late descendant terminal after checks')
                    self.integrity()
                    require(not self.cancelled and not (self.output / 'cancel').exists(), 'collection cancelled')
                    return
            if self.clock.monotonic() >= self.execution_deadline or self.clock.time() >= self.execution_deadline_epoch:
                self.interrupt_needed('execution deadline reached; native terminal not yet fully observed')
            self.clock.sleep(min(.1, max(0, self.deadline - self.clock.monotonic())))
        raise CaptureError('original outer deadline expired; no posthoc acceptance')

    def run(self):
        self.output.mkdir(parents=True, exist_ok=False)
        (self.output / 'events.jsonl').touch()
        previous = {}
        def cancel(signum, _frame):
            self.cancelled = True
            (self.output / 'cancel').touch()
        try:
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous[signum] = signal.signal(signum, cancel)
            try:
                self.prepare()
                self.collect()
            except (CaptureError, OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
                self.reasons.append(str(exc))
                self.interrupt_needed(str(exc))
            return self.finish()
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)

    def finish(self):
        artifacts = {}
        for p in self.artifact_paths:
            try:
                artifacts[p] = fingerprint(p)
            except (OSError, CaptureError) as exc:
                artifacts[p] = dict(kind='unknown', reason=str(exc))
                self.reasons.append('artifact snapshot unavailable: ' + p)
        if self.ready_epoch is not None:
            try:
                self.integrity()
            except (CaptureError, OSError) as exc:
                self.reasons.append(str(exc))
        now, wall = self.clock.monotonic(), self.clock.time()
        if now > self.deadline or wall > self.deadline_epoch:
            self.reasons.append('collection finished after original outer deadline')
        root = self.sessions.get(self.session_id)
        normal = bool(root and root.terminal and root.status == 'completed' and len(root.finals) == 1 and
                      root.finals[0]['text'].strip() and UNKNOWN not in root.finals[0]['text'] and
                      epoch(root.finals[0]['timestamp']) <= self.execution_deadline_epoch)
        sessions = {sid: dict(metadata=s.meta, status=s.status, terminal=s.terminal, tasks=s.tasks,
                              settings=s.settings, finals=s.finals, tool_calls=s.tools,
                              opaque_tool_receipts=s.opaque_tools, native_bytes_observed=s.offset,
                              native_source=str(s.path), native_prefix_sha256=s.source_hash.hexdigest(),
                              native_source_mode=s.source_mode)
                    for sid, s in self.sessions.items()}
        worker_tasks = [t for sid, s in self.sessions.items() if sid != self.session_id for t in s.tasks.values()]
        report = dict(version=1, position=self.manifest.get('position'), group=self.manifest.get('group'),
                      qualified=not self.reasons, reasons=self.reasons, normal_final=normal,
                      manifest_sha256=self.expected_sha, entry=self.entry, entry_epoch=self.entry_epoch,
                      ready_epoch=self.ready_epoch, finished=now, finished_epoch=wall,
                      elapsed_seconds=now-self.entry, deadline=self.deadline, deadline_epoch=self.deadline_epoch,
                      execution_deadline=self.execution_deadline, execution_deadline_epoch=self.execution_deadline_epoch,
                      session_id=self.session_id, sessions=sessions, checks=self.checks,
                      original_inputs=self.original_inputs, immutable_inputs=self.immutable,
                      original_artifacts=self.original_artifacts, preparation=self.preparation,
                      artifacts=artifacts, collector_runtime=self.runtime, events_sha256=sha(self.output / 'events.jsonl'),
                      peak_internal_workers_observed=self.peak,
                      internal_worker_seconds_terminal_observed=sum(t['finished_epoch'] - t['started_epoch']
                          for t in worker_tasks if t['finished_epoch'] is not None),
                      internal_worker_seconds_active_lower_bound=sum(max(0, wall - t['started_epoch'])
                          for t in worker_tasks if t['finished_epoch'] is None),
                      tokens=None, fees=None, money=None, service_compute_seconds=None,
                      cancellation_requested=self.cancelled or (self.output / 'cancel').exists(),
                      native_task_terminals_observed=bool(root and all(s.terminal for s in self.sessions.values())),
                      service_stop_confirmed=None,
                      limits='Trusted local rollout evidence only; unflushed sessions/tool ciphertext and service compute unknown; '
                             'hash snapshots cannot detect transient restored changes; parent owns native interrupt/terminal checks.')
        save(self.output / 'report.json', report)
        if self.clock.monotonic() > self.deadline or self.clock.time() > self.deadline_epoch:
            report['qualified'] = False
            report['reasons'].append('report persistence exceeded original outer deadline')
            report['finished'], report['finished_epoch'] = self.clock.monotonic(), self.clock.time()
            report['elapsed_seconds'] = report['finished'] - self.entry
            save(self.output / 'report.json', report)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='action', required=True)
    freeze = sub.add_parser('fingerprint')
    freeze.add_argument('paths', type=Path, nargs='+')
    run = sub.add_parser('run')
    run.add_argument('manifest', type=Path)
    run.add_argument('--manifest-sha256', required=True)
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--sessions-root', type=Path)
    args = parser.parse_args()
    if args.action == 'fingerprint':
        print(json.dumps({str(p.absolute()): fingerprint(p) for p in args.paths}, sort_keys=True))
        return 0
    report = Capture(args.manifest, args.manifest_sha256, args.output, args.sessions_root).run()
    print(json.dumps(dict(qualified=report['qualified'], reasons=report['reasons'], output=str(args.output))))
    return 0 if report['qualified'] else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (CaptureError, OSError, ValueError) as exc:
        print('CAPTURE: ERROR ' + str(sanitize(str(exc))), file=sys.stderr)
        sys.exit(4)
