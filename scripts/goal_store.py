"""Immutable, single-pointer ledger storage for POSIX hosts (Python 3 stdlib).

Used by controller commits, retry receipts, journal recovery, runner budget
publication and entrypoint locking. No external action is replayed by recovery.
"""
import base64
import contextlib
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
import uuid

try:
    import fcntl
except ImportError:  # Windows cannot silently run without a lock.
    fcntl = None


class StoreError(RuntimeError):
    pass


class Conflict(StoreError):
    pass


_TMP_PREFIX = '.goal-store-v1-'
_TMP_NAME = re.compile(r'^\.goal-store-v1-[a-z0-9_]{8}$')
_GEN_NAME = re.compile(r'^[0-9a-f]{64}$')


def _encode(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _valid_name(name):
    return (isinstance(name, str) and bool(name) and '\\' not in name and
            '\x00' not in name and all(part not in ('', '.', '..') for part in name.split('/')))


def _fsync_dir(path):
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic(path, data, *, mode=None, staging=None):
    fd, name = tempfile.mkstemp(prefix=_TMP_PREFIX, dir=str(staging or path.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            if mode is not None:
                os.fchmod(f.fileno(), mode)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, str(path))
        _fsync_dir(path.parent)
        if staging is not None and staging != path.parent:
            _fsync_dir(staging)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Store:
    """Store(root).commit(id, intent, files), .read(), .recover().

    `files` maps safe relative ledger paths to bytes. `intent` identifies
    the caller's requested operation; the same id with a changed intent or
    payload is a conflict. A retry returns the original committed generation,
    which may not be the current head; callers must reread before later writes
    and must never publish the returned historical head as the current head.
    All snapshots are whole immutable generations.
    Methods raise StoreError for corrupt/unsupported state. Hash chaining alone
    cannot detect an attacker restoring the pointer to an older valid head.
    The lock file is opened without following symlinks; parent directories and
    snapshot files are not a security sandbox against an adversarial local user.
    """
    def __init__(self, root):
        self.root = Path(root)
        if fcntl is None:
            raise StoreError('POSIX fcntl locking unavailable')
        self.generations = self.root / 'generations'
        self.pointer = self.root / 'current'
        self.lock = self.root / 'writer.lock'

    def _lock(self, timeout=None):
        if timeout is not None:
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 <= timeout < float('inf'):
                raise StoreError('invalid lock timeout')
            deadline = time.monotonic() + timeout
        if not getattr(os, 'O_NOFOLLOW', 0):
            raise StoreError('O_NOFOLLOW unavailable; refusing writer lock')
        self.root.mkdir(parents=True, exist_ok=True)
        self.generations.mkdir(exist_ok=True)
        try:
            fd = os.open(str(self.lock), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        except OSError as e:
            raise StoreError('cannot safely open writer lock') from e
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise StoreError('writer lock is not a regular file')
            lock = os.fdopen(fd, 'r+b')
        except Exception:
            os.close(fd)
            raise
        try:
            if timeout is None:
                fcntl.flock(lock, fcntl.LOCK_EX)
            else:
                first = True
                while True:
                    if not first and time.monotonic() >= deadline:
                        raise StoreError('writer lock timeout')
                    first = False
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        if timeout > 0 and time.monotonic() > deadline:
                            raise StoreError('writer lock timeout')
                        break
                    except OSError as e:
                        if e.errno not in (errno.EACCES, errno.EAGAIN):
                            raise
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise StoreError('writer lock timeout')
                        time.sleep(min(remaining, 0.05))
        except Exception:
            lock.close()
            raise
        return lock

    def _generation(self, name):
        if not isinstance(name, str) or len(name) != 64 or any(c not in '0123456789abcdef' for c in name):
            raise StoreError('invalid generation identity')
        try:
            data = (self.generations / name).read_bytes()
            if _hash(data) != name:
                raise StoreError('generation checksum mismatch')
            obj = json.loads(data)
            if (not isinstance(obj, dict) or set(obj) != {'version', 'previous', 'op', 'request', 'files'}
                    or type(obj['version']) is not int or obj['version'] != 1):
                raise StoreError('unknown generation schema')
            if not isinstance(obj['op'], str) or not obj['op'] or not isinstance(obj['request'], str) or len(obj['request']) != 64 or any(c not in '0123456789abcdef' for c in obj['request']):
                raise StoreError('invalid operation')
            if obj['previous'] is not None and (not isinstance(obj['previous'], str) or len(obj['previous']) != 64 or any(c not in '0123456789abcdef' for c in obj['previous'])):
                raise StoreError('invalid predecessor')
            if not isinstance(obj['files'], dict):
                raise StoreError('invalid files')
            decoded = {}
            for key, value in obj['files'].items():
                if not _valid_name(key) or not isinstance(value, str):
                    raise StoreError('invalid ledger filename')
                decoded[key] = base64.b64decode(value, validate=True)
            return obj, decoded
        except StoreError:
            raise
        except (OSError, ValueError, TypeError) as e:
            raise StoreError('unreadable or corrupt generation') from e

    def _head(self):
        try:
            raw = self.pointer.read_bytes()
        except FileNotFoundError:
            # Distinguish a fresh store from deleted/corrupted pointer.
            if self.generations.exists() and any(self.generations.iterdir()):
                raise StoreError('missing pointer; recovery required')
            return None
        except OSError as e:
            raise StoreError('unreadable pointer') from e
        try:
            obj = json.loads(raw)
            if (not isinstance(obj, dict) or set(obj) != {'version', 'head'}
                    or type(obj['version']) is not int or obj['version'] != 1):
                raise StoreError('unknown pointer schema')
            if obj['head'] is not None and (not isinstance(obj['head'], str) or not _GEN_NAME.fullmatch(obj['head'])):
                raise StoreError('invalid generation identity')
            return obj['head']
        except StoreError:
            raise
        except (ValueError, TypeError) as e:
            raise StoreError('corrupt pointer') from e

    def _walk(self, head):
        """Validate every generation once per observation; never cache across reads."""
        seen, operations = set(), set()
        while head is not None:
            if head in seen:
                raise StoreError('cyclic generation history')
            seen.add(head)
            obj, files = self._generation(head)
            if obj['op'] in operations:
                raise StoreError('duplicate committed operation')
            operations.add(obj['op'])
            yield head, obj, files
            head = obj['previous']

    def _history(self, head):
        return {obj['op']: (obj['request'], name) for name, obj, _ in self._walk(head)}

    def read(self):
        """Return (generation id, mapping); validates entire committed chain."""
        head = self._head()
        snapshot = {}
        for name, _, files in self._walk(head):
            if name == head:
                snapshot = files
        return head, snapshot

    def lookup(self, operation_id):
        """Read a committed operation without creating files or moving HEAD."""
        head = self._head()
        selected = None
        for name, obj, files in self._walk(head):
            if obj['op'] == operation_id:
                selected = name, files
        return selected

    def commit(self, operation_id, intent, files, expected_head=None, fault=None, lock_timeout=None):
        if not isinstance(operation_id, str) or not operation_id or not isinstance(intent, bytes) or not isinstance(files, dict):
            raise StoreError('bad operation')
        encoded = {}
        for key, value in files.items():
            if not _valid_name(key) or not isinstance(value, bytes):
                raise StoreError('invalid file')
            encoded[key] = base64.b64encode(value).decode('ascii')
        request = _hash(_encode({'intent': base64.b64encode(intent).decode('ascii'), 'files': encoded}))
        with self._lock(lock_timeout):
            head = self._head()
            history = self._history(head)
            if operation_id in history:
                old, old_head = history[operation_id]
                if old != request:
                    raise Conflict('operation id reused with different payload')
                return old_head
            if head != expected_head:
                raise Conflict('stale expected head')
            # Publish an explicit empty head first, so a first-write crash can
            # be distinguished from accidental deletion of a real pointer.
            if head is None and not self.pointer.exists():
                _atomic(self.pointer, _encode({'version': 1, 'head': None}))
            obj = {'version': 1, 'previous': head, 'op': operation_id, 'request': request, 'files': encoded}
            data = _encode(obj)
            name = _hash(data)
            target = self.generations / name
            if target.exists():
                if target.read_bytes() != data:
                    raise StoreError('generation collision')
            else:
                _atomic(target, data)
            if fault:
                fault('generation-published')
            _atomic(self.pointer, _encode({'version': 1, 'head': name}))
            if fault:
                fault('pointer-published')
            return name

    def recover(self, lock_timeout=None):
        """Under writer lock remove incomplete temps and unreferenced generations.

        A missing or corrupt pointer fails closed. No external tools are run.
        """
        with self._lock(lock_timeout):
            head = self._head()
            keep = {name for name, _, _ in self._walk(head)}
            remove = []
            # Validate the complete cleanup set before deleting anything.
            for path in self.generations.iterdir():
                if path.name in keep:
                    continue
                if not path.is_file() or path.is_symlink():
                    raise StoreError('unexpected generation entry')
                if _TMP_NAME.fullmatch(path.name):
                    remove.append(path)
                elif _GEN_NAME.fullmatch(path.name):
                    self._generation(path.name)  # valid format and content hash
                    remove.append(path)
                else:
                    raise StoreError('unknown generation entry')
            for path in self.root.glob(_TMP_PREFIX + '*'):
                if not _TMP_NAME.fullmatch(path.name) or not path.is_file() or path.is_symlink():
                    raise StoreError('unexpected temporary entry')
                remove.append(path)
            for path in remove:
                path.unlink()
            _fsync_dir(self.generations)
            _fsync_dir(self.root)


def _writer_exec(argv):
    """Hold the writer lock across exec; this does not make writes atomic."""
    if len(argv) < 2:
        raise StoreError('writer-exec requires state directory and controller')
    state, controller = Path(argv[0]), argv[1]
    deadlines = []
    for path, is_state in ((state / 'state.rec', True), (state / 'runner.deadline', False)):
        try:
            content = path.read_text(encoding='ascii')
        except FileNotFoundError:
            continue
        values = [line[9:] for line in content.splitlines() if line.startswith('deadline=')] if is_state else [content.strip()]
        if len(values) > 1 or any(not value.isascii() or not value.isdigit() for value in values):
            raise StoreError('invalid writer deadline')
        deadlines.extend(int(value) for value in values if int(value) > 0)
    timeout = max(0, min(deadlines) - time.time()) if deadlines else None
    lock = Store(state / 'store')._lock(timeout)
    if (state / 'store/pending').exists():
        raise StoreError('recovery required; run goal_ctl.sh recover')
    os.set_inheritable(lock.fileno(), True)
    env = os.environ.copy()
    env['GOAL_WRITER_OWNER_PID'] = str(os.getpid())
    env['GOAL_CLOSE_EXEC_PID'] = str(os.getpid())
    env['GOAL_CLOSE_LOCK_FD'] = str(lock.fileno())
    operation, intent = _close_request(argv[2:])
    env['GOAL_CLOSE_OPERATION'] = operation or uuid.uuid4().hex
    env['GOAL_CLOSE_INTENT'] = intent
    arguments = argv[2:] if operation is not None else [*argv[2:], '--operation-id', env['GOAL_CLOSE_OPERATION']]
    env['GOAL_CLOSE_ARGUMENTS'] = json.dumps(arguments)
    os.execvpe('bash', ['bash', controller] + argv[2:], env)


def _access_exec(argv):
    """Lock the ledger directory itself: read access never creates files.

    The descriptor survives exec and is shared by cooperating child readers.
    Nested writers are refused, including writers launched by a check.
    """
    entered = time.monotonic()
    write_modes = ('write', 'recover', 'migrate', 'init')
    if len(argv) < 3 or argv[1] not in ('read', 'gate') + write_modes:
        raise StoreError('access-exec requires state, read|write|gate, script')
    state, mode, script = Path(argv[0]), argv[1], argv[2]
    if fcntl is None or not getattr(os, 'O_DIRECTORY', 0) or not getattr(os, 'O_NOFOLLOW', 0):
        raise StoreError('POSIX directory locking unavailable')
    inherited = os.environ.get('GOAL_ACCESS_FD')
    if inherited is not None:
        # Validate before opening anything: a closed inherited descriptor may
        # otherwise be recycled by open(state), falsely validating itself.
        try:
            existing = int(inherited)
            same = os.fstat(existing)
            owner = int(os.environ.get('GOAL_ACCESS_OWNER_PID', '0'))
            if owner <= 0:
                raise StoreError('invalid inherited owner')
            os.kill(owner, 0)
        except (OSError, ValueError) as exc:
            raise StoreError('invalid inherited ledger lock') from exc
    fd = os.open(str(state), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if inherited is not None:
            current = os.fstat(fd)
            if (same.st_dev, same.st_ino) != (current.st_dev, current.st_ino):
                raise StoreError('inherited lock belongs to another ledger')
            if mode in write_modes and (os.environ.get('GOAL_ACCESS_MODE') != 'write' or owner != os.getpid()):
                raise StoreError('nested-writer')
            os.close(fd)
            fd = existing
        else:
            try:
                fcntl.flock(fd, (fcntl.LOCK_EX if mode in write_modes else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            except OSError as exc:
                raise StoreError('ledger-busy; retry after current operation') from exc
        actual_mode = os.environ.get('GOAL_ACCESS_MODE') if inherited is not None else ('write' if mode in write_modes else 'read')
        if actual_mode not in ('read', 'write', 'exclusive-read'):
            raise StoreError('invalid inherited access mode')
        # External receipts are a cache used by later decisions. Conservatively
        # serialize gates mentioning them, including a harmless text decoy.
        # Inspect only after acquiring SH, then upgrade before reading any views.
        if mode == 'gate' and actual_mode == 'read':
            try:
                has_external = b'external:' in (state / 'goal.md').read_bytes()
            except FileNotFoundError:
                has_external = False
            if has_external:
                if inherited is not None:
                    raise StoreError('ledger-read-needs-exclusive-gate')
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise StoreError('ledger-busy; retry external-cache gate') from exc
                actual_mode = 'exclusive-read'
        pending = (state / 'store/pending').exists()
        if actual_mode != 'write':
            if pending:
                raise StoreError('recovery-required')
            verify_views(state)
        elif not pending and mode not in ('recover', 'migrate'):
            if mode != 'init' or Store(state / 'store/commits').read()[0] is not None or (state / 'state.rec').exists():
                verify_views(state)
        env = os.environ.copy()
        env['GOAL_ACCESS_FD'] = str(fd)
        env['GOAL_ACCESS_EXEC_PID'] = str(os.getpid())
        env['GOAL_ACCESS_OWNER_PID'] = str(owner if inherited is not None else os.getpid())
        env['GOAL_ACCESS_MODE'] = actual_mode
        if inherited is None:
            for key in ('GOAL_GATE_SUPERVISED', 'GOAL_GATE_MONOTONIC_START', 'GOAL_WRITER_OWNER_PID', 'GOAL_CLOSE_EXEC_PID', 'GOAL_CLOSE_LOCK_FD',
                        'GOAL_CLOSE_OPERATION', 'GOAL_CLOSE_INTENT', 'GOAL_CLOSE_ARGUMENTS'):
                env.pop(key, None)
        if mode == 'gate' and 'GOAL_GATE_MONOTONIC_START' not in env:
            # Fresh access owns this origin; caller environment cannot grant
            # time. Borrowed readers retain it, including time spent here
            # acquiring/validating the ledger before gate-limit can run.
            env['GOAL_GATE_MONOTONIC_START'] = repr(entered)
        # Kept for the controller's internal check until its pending marker
        # check is replaced by the common lock-aware access guard.
        if env['GOAL_ACCESS_MODE'] == 'write':
            env['GOAL_WRITER_OWNER_PID'] = env['GOAL_ACCESS_OWNER_PID']
        os.set_inheritable(fd, True)
        if inherited is not None and owner != os.getpid():
            # Kernel exit events observe death before zombie reaping. The
            # supervisor owns its child until waitpid, so cleanup cannot signal
            # a recycled borrower PID. It retains these borrowed descriptors.
            watcher = str(Path(__file__).with_name('goal_owner_watch.py'))
            os.execve(sys.executable, [sys.executable, '-I', watcher, 'supervise', str(owner), '--',
                                      'bash', script] + argv[3:], env)
        os.execvpe('bash', ['bash', script] + argv[3:], env)
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)


_CLOSE_FILES = ('state.rec', 'loop-log.md', 'scores.rec',
                'evidence/adversarial.rec', 'evidence/faults.rec')
_OPERATION = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
_SHA256 = re.compile(r'^[0-9a-f]{64}$')
_CLOSE_META = '.close-commit.json'
_MUTATION_META = '.mutation-commit.json'
_VIEW_META = '.ledger-views.json'
_VIEW_FILES = {'state.rec', 'loop-log.md', 'scores.rec', 'verdicts.rec', 'check_freeze',
               'evidence/adversarial.rec', 'evidence/faults.rec'}
_RUNNER_FILES = {'runner.clock', 'runner.deadline', 'runner.json'}
_MUTATION_FILES = {
    'init': ('state.rec', 'loop-log.md', 'verdicts.rec', 'work-plan.md'),
    'stamp': ('state.rec', 'goal.md', 'check_freeze', 'pre-reg.md'),
    'bind': ('verdicts.rec', 'state.rec'),
    'forge': ('state.rec', 'check_freeze', 'evidence/raw/0.txt'),
}


def _close_request(args):
    """Exact argument intent, excluding project location and commit identity."""
    value_flags = {'--project', '--operation-id', '--task', '--files', '--checks-pass',
                   '--checks-fail', '--checks-unverifiable', '--progress', '--exit-signal',
                   '--error-signature', '--false-complete', '--dry', '--score', '--judge-score',
                   '--strategy-delta', '--strategy', '--adversarial', '--adversarial-note',
                   '--fault', '--fault-outcome', '--fault-note'}
    operation, request, i = None, [], 0
    while i < len(args):
        flag = args[i]
        if flag in value_flags:
            if i + 1 >= len(args):
                raise StoreError('missing argument for ' + flag)
            value = args[i + 1]
            if flag == '--operation-id':
                operation = value
            elif flag != '--project':
                request.extend((flag, value))
            i += 2
        else:
            request.append(flag)
            i += 1
    if operation is not None and not _OPERATION.fullmatch(operation):
        raise StoreError('invalid operation-id')
    return operation, _hash(_encode(request))


def _close_file_set(files):
    if not isinstance(files, dict) or not set(_CLOSE_FILES).issubset(files) or len(files) != len(_CLOSE_FILES) + 1:
        raise StoreError('invalid close journal file set')
    extra = set(files) - set(_CLOSE_FILES)
    raw = next(iter(extra))
    if not re.fullmatch(r'evidence/raw/[1-9][0-9]*\.txt', raw):
        raise StoreError('invalid raw journal path')
    return int(Path(raw).stem)


def _close_committed(state, operation, intent, require_current=False):
    commits = Store(Path(state) / 'store/commits')
    found = commits.lookup(operation)
    if found is None:
        return None
    operation_head, snapshot = found
    if _MUTATION_META in snapshot:
        raise Conflict('operation-id belongs to another command')
    if require_current and commits.read()[0] != operation_head:
        raise StoreError('pending operation is not the current committed version')
    try:
        meta = json.loads(snapshot[_CLOSE_META])
        if (not isinstance(meta, dict) or set(meta) != {'version', 'operation', 'intent', 'result', 'iteration', 'missing'} | (
                    {'arguments'} if meta.get('version') == 2 else set())
                or type(meta['version']) is not int or meta['version'] not in (1, 2)
                or meta['operation'] != operation or not isinstance(meta['intent'], str)
                or not _SHA256.fullmatch(meta['intent']) or type(meta['result']) is not int
                or meta['result'] not in (0, 2, 3, 4) or type(meta['iteration']) is not int
                or not isinstance(meta['missing'], list) or any(not isinstance(n, str) for n in meta['missing'])
                or len(set(meta['missing'])) != len(meta['missing'])):
            raise StoreError('invalid close commit metadata')
        if meta['version'] == 2:
            _validate_close_arguments(meta)
        scope = set(_CLOSE_FILES) | {'evidence/raw/%s.txt' % meta['iteration']}
        files = {name: data for name, data in snapshot.items() if name in scope}
        if not set(meta['missing']).issubset(scope):
            raise StoreError('invalid close missing-file scope')
        if set(files).intersection(meta['missing']):
            raise StoreError('conflicting close snapshot paths')
        files.update(dict.fromkeys(meta['missing']))
        if _close_file_set(files) != meta['iteration']:
            raise StoreError('invalid committed iteration')
        if any(files.get(name) is None for name in ('state.rec', 'loop-log.md', 'scores.rec',
                                                   'evidence/raw/%s.txt' % meta['iteration'])):
            raise StoreError('missing committed close view')
        if meta['intent'] != intent:
            raise Conflict('operation-id reused with different arguments')
        return meta, files
    except (KeyError, TypeError, ValueError) as exc:
        raise StoreError('corrupt close commit metadata') from exc


def close_retry(state, args):
    operation, intent = _close_request(args)
    if operation is None:
        return 100
    receipt = _close_committed(state, operation, intent)
    if receipt is None:
        return 100
    meta, _ = receipt
    print('CTL: REPLAY operation=%s iter=%s historical-result=%s (no checks rerun; not a fresh GO)' %
          (operation, meta['iteration'], meta['result']))
    return meta['result']


def _close_record(pending):
    obj = json.loads(pending.read_bytes())
    if not isinstance(obj, dict) or set(obj) != {'payload', 'sha256'}:
        raise StoreError('invalid close journal envelope')
    payload = obj['payload']
    if (not isinstance(payload, dict) or type(payload.get('version')) is not int
            or payload['version'] not in (1, 2, 3, 6)
            or set(payload) != ({'version', 'files'} if payload['version'] == 1 else
                                {'version', 'files', 'operation', 'intent'} if payload['version'] == 2 else
                                {'version', 'files', 'operation', 'intent', 'base_head'} | (
                                    {'arguments'} if payload['version'] == 6 else set()))
            or obj.get('sha256') != _hash(_encode(payload))):
        raise StoreError('corrupt close journal')
    if payload['version'] >= 2 and (not isinstance(payload['operation'], str)
            or not _OPERATION.fullmatch(payload['operation']) or not isinstance(payload['intent'], str)
            or not _SHA256.fullmatch(payload['intent'])):
        raise StoreError('invalid journal operation identity')
    if payload['version'] in (3, 6) and payload['base_head'] is not None and (
            not isinstance(payload['base_head'], str) or not _SHA256.fullmatch(payload['base_head'])):
        raise StoreError('invalid journal base version')
    if payload['version'] == 6:
        _validate_close_arguments(payload)
    files = payload.get('files')
    _close_file_set(files)
    for value in files.values():
        if value is not None:
            if not isinstance(value, str):
                raise StoreError('invalid journal file contents')
            base64.b64decode(value, validate=True)
    return payload


def _validate_close_arguments(record):
    args = record['arguments']
    if (not isinstance(args, list) or not args or any(not isinstance(s, str) or '\0' in s for s in args)
            or _close_request(args) != (record['operation'], record['intent'])):
        raise StoreError('close arguments do not match operation intent')


def _close_payload(pending):
    return _close_record(pending)['files']


def _validate_close_append(record, snapshot, iteration):
    """The newly appended score and log must describe the allocated iteration."""
    old = record['files']
    suffixes = {}
    for name in ('loop-log.md', 'scores.rec'):
        before = base64.b64decode(old[name], validate=True) if old[name] is not None else b''
        if not snapshot[name].startswith(before):
            raise StoreError('close rewrote previous history')
        suffixes[name] = snapshot[name][len(before):].decode('utf-8')
    lines = suffixes['loop-log.md'].splitlines()
    if not lines or lines[0] != '## iteration %s' % iteration:
        raise StoreError('close log iteration mismatch')
    block = {}
    for line in lines[1:]:
        if '=' not in line:
            raise StoreError('invalid close log row')
        key, value = line.split('=', 1)
        if key in block:
            raise StoreError('duplicate close log field')
        block[key] = value
    required = {'task', 'files_modified', 'checks_pass', 'checks_fail', 'checks_unverifiable',
                'error_signature', 'progress', 'exit_signal', 'false_complete', 'digest',
                'score', 'strategy_delta', 'strategy'}
    if set(block) != required:
        raise StoreError('incomplete close log block')
    score_lines = suffixes['scores.rec'].splitlines()
    if len(score_lines) != 1:
        raise StoreError('close score row count mismatch')
    columns = score_lines[0].split('|')
    if (len(columns) != 4 or columns[0] != str(iteration)
            or columns[1] != block['score'] or columns[3] != block['strategy']):
        raise StoreError('close score/log mismatch')


def _close_path(state, name):
    path = state / name
    parents = [path.parent]
    while parents[-1] != state:
        parents.append(parents[-1].parent)
    if path.is_symlink() or any(parent.is_symlink() for parent in parents):
        raise StoreError('symlink journal path refused')
    return path


def _capture_files(state, names):
    files = {}
    for name in names:
        path = _close_path(state, name)
        files[name] = path.read_bytes() if path.exists() else None
    return files


def _is_view(name):
    return name in _VIEW_FILES | _RUNNER_FILES or re.fullmatch(r'evidence/raw/(0|[1-9][0-9]*)\.txt', name) is not None


def _view_names(state, include_runner=True):
    names = set(_VIEW_FILES)
    if include_runner:
        names.update(name for name in _RUNNER_FILES if (state / name).exists() or (state / name).is_symlink())
    raw = state / 'evidence/raw'
    if raw.exists():
        for path in raw.iterdir():
            name = 'evidence/raw/' + path.name
            if _is_view(name):
                names.add(name)
    return names


def attach_views(state, snapshot):
    """Every controller commit carries complete recoverable managed views."""
    state = Path(state)
    commits = Store(state / 'store/commits')
    _, previous = commits.read()
    previous_meta = json.loads(previous[_VIEW_META]) if _VIEW_META in previous else None
    approved = previous_meta.get('approved') if previous_meta and previous_meta.get('version') == 2 else None
    if 'goal.md' in snapshot:
        current = _approval_from_text(snapshot['goal.md'].decode('utf-8'))
        if approved is not None and current != approved:
            raise StoreError('contract-approval-mismatch: an approved contract cannot be restamped')
        approved = current
    files = _capture_files(state, _view_names(state))
    views = {name: _hash(data) if data is not None else None for name, data in files.items()}
    snapshot.update({name: data for name, data in files.items() if data is not None})
    for name, data in files.items():
        if data is None:
            snapshot.pop(name, None)
    snapshot[_VIEW_META] = _encode({'version': 2, 'views': views, 'approved': approved})
    return snapshot


def _approval_from_text(text):
    rows = re.findall(r'^approved: (.*)$', text, re.M)
    if len(rows) > 1:
        raise StoreError('ambiguous contract approval marker')
    if not rows:
        return None
    match = re.match(r'([0-9a-f]{6,})(?:\s|$)', rows[0])
    return match.group(1) if match else None


def current_approval(state):
    goal = state / 'goal.md'
    return _approval_from_text(goal.read_text()) if goal.exists() else None


def _assert_approval(state, snapshot):
    meta = json.loads(snapshot[_VIEW_META])
    if meta['version'] != 2:
        raise StoreError('ledger-migration-required: run goal_ctl.sh migrate')
    if current_approval(state) != meta['approved']:
        raise StoreError('contract-approval-mismatch: restore the reviewed contract; migration cannot reapprove edits')


def _historical_approval(commits, head):
    observed = set()
    while head is not None:
        entry, files = commits._generation(head)
        if _MUTATION_META in files:
            meta = json.loads(files[_MUTATION_META])
            if meta.get('kind') == 'stamp' and 'goal.md' in files:
                approved = _approval_from_text(files['goal.md'].decode('utf-8'))
                if approved is not None:
                    observed.add(approved)
        head = entry['previous']
    if len(observed) > 1:
        raise StoreError('contradictory historical contract approvals; migration refused')
    return next(iter(observed)) if observed else None


def _committed_views(snapshot):
    try:
        meta = json.loads(snapshot[_VIEW_META])
    except KeyError as exc:
        raise StoreError('ledger-migration-required: run goal_ctl.sh migrate') from exc
    if (not isinstance(meta, dict) or type(meta.get('version')) is not int or meta['version'] not in (1, 2)
            or set(meta) != ({'version', 'views'} if meta['version'] == 1 else {'version', 'views', 'approved'})
            or not isinstance(meta['views'], dict) or not _VIEW_FILES.issubset(meta['views'])):
        raise StoreError('unknown ledger view manifest')
    if meta['version'] == 2 and meta['approved'] is not None and (
            not isinstance(meta['approved'], str) or not re.fullmatch(r'[0-9a-f]{6,}', meta['approved'])):
        raise StoreError('invalid committed contract approval')
    files = {}
    for name, checksum in meta['views'].items():
        if not isinstance(name, str) or not _is_view(name):
            raise StoreError('invalid ledger view path')
        if checksum is None:
            if name in snapshot:
                raise StoreError('conflicting missing ledger view')
            files[name] = None
        elif (not isinstance(checksum, str) or not _SHA256.fullmatch(checksum)
              or name not in snapshot or _hash(snapshot[name]) != checksum):
            raise StoreError('ledger snapshot view checksum mismatch')
        else:
            files[name] = snapshot[name]
    return files


def verify_views(state):
    state = Path(state)
    head, snapshot = Store(state / 'store/commits').read()
    if head is None:
        raise StoreError('ledger-migration-required: run goal_ctl.sh migrate')
    expected = _committed_views(snapshot)
    # Legacy sidecars predate transactional runner state. Until first import,
    # leave them untouched; runner begin validates their minimum/highwater.
    actual = _capture_files(state, set(expected).union(_view_names(state, bool(_RUNNER_FILES.intersection(expected)))))
    if actual != expected:
        changed = sorted(name for name in set(actual).union(expected) if actual.get(name) != expected.get(name))
        raise StoreError('ledger-view-mismatch: ' + ','.join(changed) + '; run goal_ctl.sh recover')
    _assert_approval(state, snapshot)
    return head


def guard_digest(state):
    state = Path(state)
    names = _view_names(state) | {'goal.md', 'work-plan.md', 'baseline.md', 'interfaces.md',
                                 'forge-plan.json', 'store/commits/current', 'store/pending'}
    output_iteration = os.environ.get('GOAL_RAW_OUTPUT_ITERATION')
    if (os.environ.get('GOAL_ACCESS_MODE') == 'write' and os.environ.get('GOAL_CLOSE_OPERATION')
            and output_iteration is not None and re.fullmatch(r'[1-9][0-9]*', output_iteration)):
        names.discard('evidence/raw/' + output_iteration + '.txt')
    files = _capture_files(state, names)
    return _hash(_encode({name: _hash(data) if data is not None else None for name, data in files.items()}))


def restore_committed_views(state, allow_legacy=False):
    state = Path(state)
    head, snapshot = Store(state / 'store/commits').read()
    if head is None:
        raise StoreError('ledger-migration-required: run goal_ctl.sh migrate')
    files = _committed_views(snapshot)
    if not allow_legacy or json.loads(snapshot[_VIEW_META])['version'] == 2:
        _assert_approval(state, snapshot)
    # Canonical raw files added without a commit are not part of this version.
    files.update({name: None for name in _view_names(state, bool(_RUNNER_FILES.intersection(files))) - set(files)})
    _restore_views(state, files)


def _restore_if_versioned(state, required=False):
    head, snapshot = Store(state / 'store/commits').read()
    if head is not None and _VIEW_META in snapshot:
        restore_committed_views(state, allow_legacy=True)
    elif head is not None and required:
        raise StoreError('ledger-migration-required: run goal_ctl.sh migrate')


def migrate_views(state):
    state = Path(state)
    commits = Store(state / 'store/commits')
    head, snapshot = commits.read()
    if _VIEW_META in snapshot:
        known = _committed_views(snapshot)
        if json.loads(snapshot[_VIEW_META])['version'] == 2:
            verify_views(state)
            return
        if _capture_files(state, set(known).union(_view_names(state))) != known:
            raise StoreError('legacy views disagree with committed history; migration refused')
    if head is not None:
        known = {}
        cursor = head
        while cursor is not None:
            entry, files = commits._generation(cursor)
            for meta_name in (_CLOSE_META, _MUTATION_META):
                if meta_name in files:
                    meta = json.loads(files[meta_name])
                    if (not isinstance(meta, dict) or type(meta.get('version')) is not int
                            or meta['version'] not in ((1, 2) if meta_name == _CLOSE_META else (1,))
                            or not isinstance(meta.get('missing'), list)):
                        raise StoreError('invalid legacy commit metadata')
                    common = {'version', 'operation', 'intent', 'missing'}
                    expected = common | ({'kind'} if meta_name == _MUTATION_META else {'result', 'iteration'})
                    if meta_name == _CLOSE_META and meta['version'] == 2:
                        expected.add('arguments')
                        _validate_close_arguments(meta)
                    if (set(meta) != expected or not isinstance(meta.get('operation'), str)
                            or not _OPERATION.fullmatch(meta['operation']) or not isinstance(meta.get('intent'), str)
                            or not _SHA256.fullmatch(meta['intent'])):
                        raise StoreError('unknown legacy commit metadata')
                    if meta_name == _MUTATION_META:
                        if meta['kind'] not in _MUTATION_FILES:
                            raise StoreError('unknown legacy mutation kind')
                    elif (type(meta['iteration']) is not int or meta['iteration'] <= 0
                          or type(meta['result']) is not int or meta['result'] not in (0, 2, 3, 4)):
                        raise StoreError('invalid legacy close metadata')
                    for name in meta['missing']:
                        if not isinstance(name, str):
                            raise StoreError('invalid legacy missing-file path')
                        if _is_view(name):
                            known.setdefault(name, None)
            for name, data in files.items():
                if _is_view(name):
                    known.setdefault(name, data)
            cursor = entry['previous']
        if _capture_files(state, known) != known:
            raise StoreError('legacy views disagree with committed history; migration refused')
    state_file = state / 'state.rec'
    if not state_file.is_file() or not (state / 'loop-log.md').is_file() or not (state / 'verdicts.rec').is_file():
        raise StoreError('incomplete legacy ledger')
    values = [line[10:] for line in state_file.read_text().splitlines() if line.startswith('iteration=')]
    if len(values) != 1 or not values[0].isascii() or not values[0].isdigit():
        raise StoreError('invalid legacy iteration')
    blocks = re.findall(r'^## iteration ([0-9]+)$', (state / 'loop-log.md').read_text(), re.M)
    if [int(value) for value in blocks] != list(range(1, int(values[0]) + 1)):
        raise StoreError('legacy state/log iteration mismatch')
    scores = state / 'scores.rec'
    if scores.is_file():
        rows = [line.split('|') for line in scores.read_text().splitlines() if line]
        if (any(len(row) not in (3, 4) or not row[0].isascii() or not row[0].isdigit() for row in rows)
                or [int(row[0]) for row in rows] != list(range(1, int(values[0]) + 1))):
            raise StoreError('legacy state/score iteration mismatch')
    approved = _historical_approval(commits, head)
    if approved is not None and current_approval(state) != approved:
        raise StoreError('legacy contract approval disagrees with committed history; migration refused')
    seed = {'goal.md': (state / 'goal.md').read_bytes()} if (state / 'goal.md').exists() else {}
    commits.commit('migration-' + uuid.uuid4().hex, b'ledger view migration v1',
                   attach_views(state, seed), expected_head=head, lock_timeout=0)


def _encoded_files(files):
    return {name: base64.b64encode(data).decode('ascii') if data is not None else None
            for name, data in files.items()}


def _sync_views(state, names):
    directories = {state, state / 'store'}
    for name in names:
        path = _close_path(state, name)
        if path.exists():
            fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise StoreError('journal view is not a regular file')
                os.fsync(fd)
            finally:
                os.close(fd)
            parent = path.parent
            while parent != state:
                directories.add(parent)
                parent = parent.parent
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        _fsync_dir(directory)


def _restore_views(state, files):
    # Validate all paths before the first write, including missing targets.
    for name in files:
        _close_path(state, name)
    for name, data in files.items():
        path = state / name
        if data is None:
            if path.exists():
                path.unlink()
                _fsync_dir(path.parent)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic(path, data)
    _sync_views(state, files)


def _mutation_record(pending):
    obj = json.loads(pending.read_bytes())
    if not isinstance(obj, dict) or set(obj) != {'payload', 'sha256'}:
        raise StoreError('invalid mutation journal envelope')
    record = obj['payload']
    if (not isinstance(record, dict) or set(record) != {'version', 'kind', 'operation', 'intent', 'base_head', 'files'}
            or type(record['version']) is not int or record['version'] != 4
            or obj['sha256'] != _hash(_encode(record))):
        raise StoreError('corrupt mutation journal')
    if (not isinstance(record['kind'], str) or record['kind'] not in _MUTATION_FILES
            or not isinstance(record['operation'], str) or not _OPERATION.fullmatch(record['operation'])
            or not isinstance(record['intent'], str) or not _SHA256.fullmatch(record['intent'])
            or (record['base_head'] is not None and (not isinstance(record['base_head'], str)
                or not _SHA256.fullmatch(record['base_head'])))
            or not isinstance(record['files'], dict)
            or (set(record['files']) != set(_MUTATION_FILES[record['kind']])
                and not (record['kind'] == 'bind' and set(record['files']) == {'verdicts.rec'}))):
        raise StoreError('invalid mutation journal fields')
    for data in record['files'].values():
        if data is not None:
            if not isinstance(data, str):
                raise StoreError('invalid mutation journal contents')
            base64.b64decode(data, validate=True)
    return record


def _mutation_committed(state, kind, operation, intent, require_current=False):
    commits = Store(state / 'store/commits')
    found = commits.lookup(operation)
    if found is None:
        return None
    head, snapshot = found
    if require_current and commits.read()[0] != head:
        raise StoreError('pending operation is not the current committed version')
    if _MUTATION_META not in snapshot:
        raise Conflict('operation-id belongs to another command')
    meta = json.loads(snapshot[_MUTATION_META])
    if (not isinstance(meta, dict) or set(meta) != {'version', 'kind', 'operation', 'intent', 'missing'}
            or type(meta['version']) is not int or meta['version'] != 1
            or meta['operation'] != operation or meta['kind'] != kind or not isinstance(meta['intent'], str)
            or not _SHA256.fullmatch(meta['intent']) or not isinstance(meta['missing'], list)
            or any(not isinstance(n, str) for n in meta['missing'])
            or len(set(meta['missing'])) != len(meta['missing'])):
        raise StoreError('invalid mutation commit metadata')
    scope = set(_MUTATION_FILES[kind])
    # Earlier bind commits owned verdicts only. Preserve that historical
    # scope when replaying/recovering; there was no qualified-state mutation.
    if kind == 'bind' and 'state.rec' not in snapshot and 'state.rec' not in meta['missing']:
        scope = {'verdicts.rec'}
    files = {name: data for name, data in snapshot.items() if name in scope}
    if not set(meta['missing']).issubset(scope):
        raise StoreError('invalid mutation missing-file scope')
    if set(files).intersection(meta['missing']):
        raise StoreError('conflicting mutation snapshot paths')
    files.update(dict.fromkeys(meta['missing']))
    if set(files) != scope:
        raise StoreError('invalid mutation snapshot file set')
    if meta['intent'] != intent:
        raise Conflict('operation-id reused with different arguments or input')
    return files


def mutation_retry(state, kind, args, stdin=None):
    operation, intent = _close_request(args)
    if stdin is not None:
        intent = _hash(_encode({'arguments': intent, 'stdin': base64.b64encode(stdin).decode('ascii')}))
    if operation is not None and _mutation_committed(Path(state), kind, operation, intent) is not None:
        print('CTL: REPLAY operation=%s command=%s historical-result=0 (not a fresh GO)' % (operation, kind))
        return True, operation, intent
    return False, operation, intent


def mutation_journal(state, action, kind=None, args=(), intent=None, operation=None):
    """Small controller mutations share the close commit history and pointer."""
    state = Path(state)
    pending = state / 'store/pending'
    commits = Store(state / 'store/commits')
    if action == 'begin':
        if kind not in _MUTATION_FILES or pending.exists():
            raise StoreError('invalid mutation kind or recovery required')
        if intent is None:
            operation, intent = _close_request(args)
        operation = operation or kind + '-' + uuid.uuid4().hex
        head, _ = commits.read()
        record = {'version': 4, 'kind': kind, 'operation': operation, 'intent': intent,
                  'base_head': head, 'files': _encoded_files(_capture_files(state, _MUTATION_FILES[kind]))}
        pending.parent.mkdir(parents=True, exist_ok=True)
        _atomic(pending, _encode({'payload': record, 'sha256': _hash(_encode(record))}))
        _fsync_dir(state)
        return operation
    record = _mutation_record(pending)
    kind = record['kind']
    if action == 'finish':
        if kind == 'bind':
            _, previous = commits.read()
            if _VIEW_META in previous:
                expected = _committed_views(previous)
                names = (set(expected) | _view_names(state, bool(_RUNNER_FILES.intersection(expected)))) - set(record['files'])
                if _capture_files(state, names) != {name: expected.get(name) for name in names}:
                    raise StoreError('bind modified managed evidence outside its write scope')
        _sync_views(state, record['files'])
        files = _capture_files(state, record['files'])
        snapshot = {name: data for name, data in files.items() if data is not None}
        snapshot[_MUTATION_META] = _encode({'version': 1, 'kind': kind, 'operation': record['operation'],
                                          'intent': record['intent'],
                                          'missing': sorted(name for name, data in files.items() if data is None)})
        commits.commit(record['operation'], record['intent'].encode('ascii'), attach_views(state, snapshot),
                       expected_head=record['base_head'], lock_timeout=0)
    elif action == 'recover':
        with Store(state / 'store')._lock(0):
            files = _mutation_committed(state, kind, record['operation'], record['intent'], require_current=True)
            if files is None:
                if commits.read()[0] != record['base_head']:
                    raise StoreError('pending baseline is not the current committed version')
                files = {name: base64.b64decode(data, validate=True) if data is not None else None
                         for name, data in record['files'].items()}
            _restore_views(state, files)
            _restore_if_versioned(state)
    else:
        raise StoreError('unknown mutation journal action')
    pending.unlink()
    _fsync_dir(pending.parent)


def bind_mutation(state, args, stdin):
    replay, operation, intent = mutation_retry(state, 'bind', args, stdin)
    if replay:
        return
    lines = [line for line in stdin.decode('utf-8').replace('\r', '').split('\n') if line]
    for line in lines:
        columns = line.split('|')
        if '\x00' in line or len(columns) != 6 or columns[1] not in ('PASS', 'FAIL', 'UNVERIFIABLE'):
            raise StoreError('malformed bind row; no rows appended')
    state = Path(state)
    target = _close_path(state, 'verdicts.rec')
    if not target.is_file():
        raise StoreError('no-verdicts-rec')
    if not lines and operation is None:
        print('CTL: BIND ok appended=0 skipped=0')
        return
    identity = mutation_journal(state, 'begin', 'bind', intent=intent, operation=operation)
    with target.open('ab') as output:
        output.write(('\n'.join(lines) + '\n').encode('utf-8'))
    qualify_objective(state)
    mutation_journal(state, 'finish')
    print('CTL: BIND ok appended=%s skipped=0 operation=%s' % (len(lines), identity))


def _incumbent_scope(project, names):
    import unicodedata

    if not names:
        raise StoreError('explicit owned files required')
    paths = {}
    aliases = set()
    for name in names:
        if not _valid_name(name) or {'.goal', '.git'}.intersection(part.casefold() for part in name.split('/')):
            raise StoreError('invalid owned file path')
        alias = unicodedata.normalize('NFC', name).casefold()
        if alias in aliases or any(a.startswith(alias + '/') or alias.startswith(a + '/') for a in aliases):
            raise StoreError('overlapping owned files')
        aliases.add(alias)
        path = _close_path(project, name)
        if not path.parent.is_dir():
            raise StoreError('owned file parent must already exist')
        paths[name] = path
    return paths


def _incumbent_file(path):
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) > 0o777):
            raise StoreError('expected an owned regular file without aliases or special permissions')
        data = stream.read()
        after = os.fstat(stream.fileno())
        live = path.lstat()
        def identity(s):
            return s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns
        if identity(info) != identity(after) or identity(after) != identity(live):
            raise StoreError('owned file changed during capture')
    return {'mode': stat.S_IMODE(info.st_mode), 'bytes': base64.b64encode(data).decode('ascii')}


def _incumbent_context(state):
    freeze = state / 'check_freeze'
    return {'contract': _hash((state / 'goal.md').read_bytes()),
            'check_freeze': _hash(freeze.read_bytes()) if freeze.exists() else None}


def watermark_basis(state):
    import subprocess
    state = Path(state)
    body = subprocess.check_output(['bash', '-c', '. "$1"; gp_ac_body "$2"', 'watermark',
                                    str(Path(__file__).with_name('goal_parse.sh')), str(state.parent)])
    freeze = state / 'check_freeze'
    return 'quality-v1:' + _hash(_encode(dict(contract=_hash(body),
        check_freeze=_hash(freeze.read_bytes()) if freeze.exists() else None)))


def qualify_objective(state):
    """Advance best only from current floors+horizon, inside the caller's commit."""
    from decimal import Decimal, InvalidOperation
    import subprocess

    state = Path(state)
    if not (state / 'goal.md').is_file():
        return
    objectives = re.findall(r'^objective: *(maximize|minimize) +(AC-[0-9]+).*$',
                            (state / 'goal.md').read_text().replace('\r', ''), re.M)
    if not objectives:
        return
    if os.environ.get('GOAL_ACCESS_MODE') != 'write' or not (state / 'store/pending').is_file():
        raise StoreError('objective qualification requires an active controller transaction')
    path = state / 'state.rec'
    lines = path.read_text().splitlines()
    values = dict(line.split('=', 1) for line in lines if '=' in line)
    basis = watermark_basis(state)
    qualified = values.get('best_score_basis') == basis
    previous = values.get('best_score', 'none') if qualified else 'none'
    quality_score = values.get('last_quality_score', 'none') if qualified else 'none'
    quality_judge = values.get('last_quality_judge', 'none') if qualified else 'none'
    if previous == 'none' and values.get('best_score', 'none') != 'none':
        print('CTL: NOTE legacy-watermark-unqualified:value=' + values['best_score'])
    descriptors = tuple({int(os.environ[key]) for key in ('GOAL_ACCESS_FD', 'GOAL_CLOSE_LOCK_FD', 'GOAL_RUNNER_FD')
                         if os.environ.get(key)})
    check = subprocess.run(['bash', str(Path(__file__).with_name('goal_gate.sh')), '--quality',
                            '--project', str(state.parent)], pass_fds=descriptors, capture_output=True)
    text = check.stdout.decode('utf-8', 'replace')
    diagnostics = text + check.stderr.decode('utf-8', 'replace')
    if check.returncode == 4 or re.search(r'reason=check-mutated-(tree|ledger)', diagnostics):
        raise StoreError('objective qualification corrupted its input; recover before retry: ' + diagnostics.strip())
    observed = re.findall(r'^GATE: QUALITY-OK .* score=(-?[0-9]+(?:\.[0-9]+)?)$', text, re.M)
    best = previous
    if check.returncode == 0 and len(observed) == 1:
        try:
            candidate = Decimal(observed[0])
            current = None if previous == 'none' else Decimal(previous)
            if not candidate.is_finite() or current is not None and not current.is_finite():
                raise InvalidOperation()
            if current is None or (candidate > current if objectives[-1][0] == 'maximize' else candidate < current):
                best = observed[0]
            rows = [line.split('|') for line in (state / 'scores.rec').read_text().splitlines()]
            current_rows = [row for row in rows if len(row) >= 3 and row[0] == values.get('iteration')]
            quality_score = observed[0]
            quality_judge = current_rows[-1][2] if current_rows else 'none'
        except InvalidOperation as exc:
            raise StoreError('invalid qualified objective score') from exc
        print(text.strip())
    else:
        reason = check.stderr.decode('utf-8', 'replace').strip().splitlines()
        print('CTL: QUALITY not-qualified result=%s reason=%s' % (check.returncode, reason[-1] if reason else 'no receipt'))
        return  # A failed/tampered contract cannot erase a prior qualification.
    updated = [line for line in lines if not line.startswith(('best_score=', 'best_score_basis=', 'best_score_judge=',
                                                             'last_quality_score=', 'last_quality_judge='))]
    updated.extend(['best_score=' + best, 'best_score_basis=' + basis,
                    'last_quality_score=' + quality_score, 'last_quality_judge=' + quality_judge])
    _atomic(path, ('\n'.join(updated) + '\n').encode())


def _incumbent_archive(state, identity):
    if not isinstance(identity, str) or not _SHA256.fullmatch(identity):
        raise StoreError('invalid checkpoint identity')
    path = _close_path(state, 'store/incumbents/' + identity + '.json')
    data = path.read_bytes()
    if _hash(data) != identity:
        raise StoreError('checkpoint checksum mismatch')
    record = json.loads(data)
    if (not isinstance(record, dict)
            or set(record) != {'version', 'kind', 'base', 'context', 'head', 'artifact', 'proof', 'files'}
            or type(record['version']) is not int or record['version'] != 1
            or record['kind'] not in ('incumbent', 'candidate') or not isinstance(record['files'], dict)):
        raise StoreError('invalid checkpoint schema')
    _incumbent_scope(state.parent, record['files'])
    for value in record['files'].values():
        if value is not None:
            if (not isinstance(value, dict) or set(value) != {'mode', 'bytes'}
                    or type(value['mode']) is not int or not 0 <= value['mode'] <= 0o777
                    or not isinstance(value['bytes'], str)):
                raise StoreError('invalid checkpoint file')
            base64.b64decode(value['bytes'], validate=True)
    return record


def _incumbent_pair(state, baseline, candidate):
    best = _incumbent_archive(state, baseline)
    trial = _incumbent_archive(state, candidate)
    if (best['kind'] != 'incumbent' or trial['kind'] != 'candidate' or trial['base'] != baseline
            or set(best['files']) != set(trial['files']) or best['context'] != trial['context']
            or best['context'] != _incumbent_context(state)):
        raise StoreError('checkpoint scope, lineage or frozen contract changed')
    return best, trial


def _recover_incumbent(state, envelope):
    if set(envelope) != {'payload', 'sha256'}:
        raise StoreError('invalid incumbent recovery envelope')
    record = envelope['payload']
    if (set(record) != {'version', 'base', 'candidate', 'head'} or type(record['version']) is not int
            or record['version'] != 5 or _hash(_encode(record)) != envelope['sha256']
            or verify_views(state) != record['head']):
        raise StoreError('invalid or stale incumbent recovery journal')
    best, trial = _incumbent_pair(state, record['base'], record['candidate'])
    paths = _incumbent_scope(state.parent, best['files'])
    staging = state / 'store/incumbents'
    device = staging.stat().st_dev
    for name, path in paths.items():
        if path.parent.stat().st_dev != device:
            raise StoreError('owned files must share a filesystem with the archive')
        if _incumbent_file(path) not in (best['files'][name], trial['files'][name]):
            raise StoreError('restore conflict: ' + name)
    for name in paths:
        path = _close_path(state.parent, name)
        target = best['files'][name]
        current = _incumbent_file(path)
        if current == target:
            continue
        if current != trial['files'][name]:
            raise StoreError('restore conflict: ' + name)
        if target is None:
            path.unlink()
            _fsync_dir(path.parent)
        else:
            _atomic(path, base64.b64decode(target['bytes']), mode=target['mode'], staging=staging)
        if os.environ.get('GOAL_INCUMBENT_FAULT') == 'first-file':
            os._exit(91)
    if {name: _incumbent_file(path) for name, path in paths.items()} != best['files']:
        raise StoreError('restore verification failed')
    pending = state / 'store/pending'
    pending.unlink()
    _fsync_dir(pending.parent)


def incumbent_cli(argv):
    import argparse
    import subprocess

    parser = argparse.ArgumentParser(description='Archive and restore an explicit owned file scope')
    parser.add_argument('action', choices=('save', 'candidate', 'restore'))
    parser.add_argument('--project', default='.')
    parser.add_argument('--file', action='append', default=[])
    parser.add_argument('--base')
    parser.add_argument('--candidate')
    parser.add_argument('--intermediate', action='store_true', help='save after checkpoint qualification, before GO')
    args = parser.parse_args(argv)
    if args.action == 'save':
        valid = args.file and args.base is None and args.candidate is None
    else:
        valid = (not args.file and not args.intermediate and args.base
                 and (args.candidate if args.action == 'restore' else args.candidate is None))
    if not valid:
        raise StoreError('save requires --file, candidate requires --base, restore requires both checkpoint IDs')
    project = Path(args.project).resolve(strict=True)
    state = project / '.goal'
    fd = os.open(str(state), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pending = state / 'store/pending'
        if pending.exists():
            raise StoreError('recovery-required')
        head = verify_views(state)
        context = _incumbent_context(state)
        if args.action == 'restore':
            best, trial = _incumbent_pair(state, args.base, args.candidate)
            paths = _incumbent_scope(project, best['files'])
            actual = {name: _incumbent_file(path) for name, path in paths.items()}
            if actual != best['files']:
                if actual != trial['files']:
                    raise StoreError('restore conflict: owned files changed after candidate capture')
                device = (state / 'store/incumbents').stat().st_dev
                if any(path.parent.stat().st_dev != device for path in paths.values()):
                    raise StoreError('owned files must share a filesystem with the archive')
                record = dict(version=5, base=args.base, candidate=args.candidate, head=head)
                envelope = {'payload': record, 'sha256': _hash(_encode(record))}
                _atomic(pending, _encode(envelope))
                _recover_incumbent(state, envelope)
            print('INCUMBENT: restored %s (fresh gate required)' % args.base)
            return

        script = str(Path(__file__).with_name('goal_gate.sh'))
        command = ['bash', script, '--project', str(project)]
        baseline = None if args.action == 'save' else _incumbent_archive(state, args.base)
        if baseline and (baseline['kind'] != 'incumbent' or baseline['context'] != context):
            raise StoreError('candidate requires a checkpoint of the same frozen contract')
        paths = _incumbent_scope(project, args.file if baseline is None else baseline['files'])
        files = {name: _incumbent_file(path) for name, path in paths.items()}
        proof = None
        if baseline is None:
            env = {k: v for k, v in os.environ.items() if not k.startswith(('GOAL_ACCESS_', 'GOAL_CLOSE_', 'GOAL_WRITER_', 'GOAL_GATE_'))}
            env.update(GOAL_ACCESS_FD=str(fd), GOAL_ACCESS_OWNER_PID=str(os.getpid()),
                       GOAL_ACCESS_MODE='exclusive-read')
            mode = '--checkpoint' if args.intermediate else '--check'
            check = subprocess.run(command + [mode], env=env, pass_fds=(fd,), capture_output=True)
            if check.returncode != 0:
                print((check.stdout + check.stderr).decode('utf-8', 'replace'), file=sys.stderr, end='')
                raise StoreError('incumbent must pass a fresh gate')
            outcome = b'CHECKPOINT-OK' if args.intermediate else b'GO'
            receipts = re.findall(rb'^GATE: ' + outcome + rb' digest=(v2-[0-9a-f]{64}) ', check.stdout, re.M)
            if len(receipts) != 1:
                raise StoreError('missing artifact identity in gate receipt')
            artifact = receipts[0].decode('ascii')
            proof = base64.b64encode(check.stdout + check.stderr).decode('ascii')
        else:
            artifact = subprocess.check_output(command + ['--digest']).decode('ascii').strip()
        if (verify_views(state) != head or _incumbent_context(state) != context
                or {name: _incumbent_file(path) for name, path in paths.items()} != files
                or subprocess.check_output(command + ['--digest']).decode('ascii').strip() != artifact):
            raise StoreError('project changed during checkpoint capture')
        data = _encode(dict(version=1, kind='incumbent' if baseline is None else 'candidate',
                            base=args.base, context=context, head=head, artifact=artifact, proof=proof, files=files))
        identity = _hash(data)
        path = _close_path(state, 'store/incumbents/' + identity + '.json')
        path.parent.mkdir(exist_ok=True)
        _fsync_dir(path.parent.parent)
        if path.exists():
            if path.read_bytes() != data:
                raise StoreError('checkpoint checksum mismatch')
        else:
            _atomic(path, data)
        print(identity)
    except subprocess.CalledProcessError as exc:
        raise StoreError('unable to bind artifact digest') from exc
    finally:
        os.close(fd)


def close_journal(state, action, result=0):
    """Rollback journal for the existing close writer; never replay checks."""
    state = Path(state)
    pending = state / 'store/pending'
    if action == 'recover' and pending.exists():
        envelope = json.loads(pending.read_bytes())
        if (isinstance(envelope, dict) and isinstance(envelope.get('payload'), dict)
                and envelope['payload'].get('version') == 4):
            return mutation_journal(state, 'recover')
        if (isinstance(envelope, dict) and isinstance(envelope.get('payload'), dict)
                and envelope['payload'].get('version') == 5):
            return _recover_incumbent(state, envelope)
    if action == 'begin':
        if pending.exists():
            raise StoreError('recovery required')
        # Bind the newly allocated raw evidence path as well as the ledgers.
        values = [line[10:] for line in (state / 'state.rec').read_text().splitlines()
                  if line.startswith('iteration=')]
        if len(values) != 1 or not values[0].isascii() or not values[0].isdigit():
            raise StoreError('invalid iteration for journal')
        names = list(_CLOSE_FILES) + ['evidence/raw/%d.txt' % (int(values[0]) + 1)]
        files = {}
        for name in names:
            path = _close_path(state, name)
            files[name] = base64.b64encode(path.read_bytes()).decode('ascii') if path.exists() else None
        payload = {'version': 1, 'files': files}
        operation, intent = os.environ.get('GOAL_CLOSE_OPERATION'), os.environ.get('GOAL_CLOSE_INTENT')
        if operation is not None or intent is not None:
            if (not isinstance(operation, str) or not _OPERATION.fullmatch(operation)
                    or not isinstance(intent, str) or not _SHA256.fullmatch(intent)):
                raise StoreError('invalid close operation identity')
            base_head, _ = Store(state / 'store/commits').read()
            payload.update(version=3, operation=operation, intent=intent, base_head=base_head)
            arguments = os.environ.get('GOAL_CLOSE_ARGUMENTS')
            if arguments is not None:
                payload.update(version=6, arguments=json.loads(arguments))
                _validate_close_arguments(payload)
        _atomic(pending, _encode({'payload': payload, 'sha256': _hash(_encode(payload))}))
        _fsync_dir(state)
    elif action == 'finish':
        record = _close_record(pending)
        files = record['files']
        if type(result) is not int or result not in (0, 2, 3, 4):
            raise StoreError('invalid close result')
        # The rollback marker may only disappear after every written view and
        # its directory entries are durable. An fsync error leaves it intact.
        _sync_views(state, files)
        if record['version'] >= 2:
            snapshot, missing = {}, []
            iteration = _close_file_set(files)
            for name in files:
                path = _close_path(state, name)
                if path.exists():
                    snapshot[name] = path.read_bytes()
                else:
                    missing.append(name)
            raw = 'evidence/raw/%d.txt' % iteration
            if not all(name in snapshot for name in ('state.rec', 'loop-log.md', 'scores.rec', raw)):
                raise StoreError('incomplete close views')
            iterations = [line[10:] for line in snapshot['state.rec'].decode('utf-8').splitlines()
                          if line.startswith('iteration=')]
            if iterations != [str(iteration)] or not snapshot[raw]:
                raise StoreError('inconsistent close iteration or evidence')
            _validate_close_append(record, snapshot, iteration)
            meta = {'version': 1, 'operation': record['operation'], 'intent': record['intent'],
                    'result': result, 'iteration': iteration, 'missing': sorted(missing)}
            if record['version'] == 6:
                meta.update(version=2, arguments=record['arguments'])
            snapshot[_CLOSE_META] = _encode(meta)
            commits = Store(state / 'store/commits')
            head, previous = commits.read()
            if record['version'] in (3, 6) and head != record['base_head']:
                raise Conflict('close baseline committed version changed')
            if _VIEW_META in previous:
                expected = _committed_views(previous)
                names = (set(expected) | _view_names(state, bool(_RUNNER_FILES.intersection(expected)))) - set(files)
                if _capture_files(state, names) != {name: expected.get(name) for name in names}:
                    raise StoreError('close modified managed evidence outside its write scope')
            # The atomic current pointer publication is the close commit point.
            # Its snapshot is also the source of recovery after this point.
            commits.commit(record['operation'], record['intent'].encode('ascii'), attach_views(state, snapshot),
                           expected_head=head, lock_timeout=0)
        pending.unlink()
        _fsync_dir(pending.parent)
    elif action == 'recover':
        with Store(state / 'store')._lock(0):
            if not pending.exists():
                _restore_if_versioned(state, required=True)
                return
            record = _close_record(pending)
            files = record['files']
            committed = (_close_committed(state, record['operation'], record['intent'], require_current=True)
                         if record['version'] >= 2 else None)
            if committed is None:
                head, _ = Store(state / 'store/commits').read()
                if record['version'] in (3, 6):
                    if head != record['base_head']:
                        raise StoreError('pending baseline is not the current committed version')
                elif head is not None:
                    raise StoreError('legacy pending journal conflicts with committed history')
            # Validate the entire restore before mutating any path.
            decoded = {}
            for name, value in files.items():
                _close_path(state, name)
                decoded[name] = base64.b64decode(value, validate=True) if value is not None else None
            if committed is not None:
                _, final_files = committed
                if set(final_files) != set(files):
                    raise StoreError('committed close file set mismatch')
                decoded = final_files
            _restore_views(state, decoded)
            _restore_if_versioned(state)
            pending.unlink()
            _fsync_dir(pending.parent)
    else:
        raise StoreError('unknown journal action')


if __name__ == '__main__':
    try:
        if len(sys.argv) in (4, 5) and sys.argv[1] == 'close-journal':
            close_journal(sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) == 5 else 0)
        elif len(sys.argv) >= 3 and sys.argv[1] == 'close-retry':
            sys.exit(close_retry(sys.argv[2], sys.argv[3:]))
        elif len(sys.argv) >= 5 and sys.argv[1] == 'mutation-retry':
            sys.exit(0 if mutation_retry(sys.argv[2], sys.argv[3], sys.argv[4:])[0] else 100)
        elif len(sys.argv) >= 4 and sys.argv[1] == 'mutation-journal':
            identity = mutation_journal(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None,
                                        sys.argv[5:])
            if identity is not None:
                print(identity)
        elif len(sys.argv) >= 3 and sys.argv[1] == 'bind-mutation':
            bind_mutation(sys.argv[2], sys.argv[3:], sys.stdin.buffer.read())
        elif len(sys.argv) == 3 and sys.argv[1] == 'qualify-objective':
            qualify_objective(sys.argv[2])
        elif len(sys.argv) == 3 and sys.argv[1] == 'watermark-basis':
            print(watermark_basis(sys.argv[2]))
        elif len(sys.argv) == 3 and sys.argv[1] == 'check-views':
            print(verify_views(sys.argv[2]))
        elif len(sys.argv) == 3 and sys.argv[1] == 'guard-digest':
            print(guard_digest(sys.argv[2]))
        elif len(sys.argv) == 3 and sys.argv[1] == 'migrate-views':
            migrate_views(sys.argv[2])
            print('CTL: MIGRATE ok')
        elif len(sys.argv) >= 2 and sys.argv[1] == 'writer-exec':
            _writer_exec(sys.argv[2:])
        elif len(sys.argv) >= 2 and sys.argv[1] == 'access-exec':
            _access_exec(sys.argv[2:])
        elif len(sys.argv) >= 2 and sys.argv[1] == 'incumbent':
            incumbent_cli(sys.argv[2:])
        else:
            raise StoreError('unknown command')
    except (StoreError, OSError, ValueError, KeyError, TypeError) as exc:
        print('CTL: ERROR writer-lock: %s' % exc, file=sys.stderr)
        sys.exit(4)
