"""Immutable, single-pointer ledger storage for POSIX hosts (Python 3 stdlib).

Used by actual close commits, retry receipts, journal recovery and entrypoint
locking. Other writer snapshots and full reader version validation remain
unintegrated; no external action is replayed by recovery.
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


def _atomic(path, data):
    fd, name = tempfile.mkstemp(prefix=_TMP_PREFIX, dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, str(path))
        _fsync_dir(path.parent)
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
            if obj['head'] is not None:
                self._generation(obj['head'])
            return obj['head']
        except StoreError:
            raise
        except (ValueError, TypeError) as e:
            raise StoreError('corrupt pointer') from e

    def _history(self, head):
        seen, operations = set(), {}
        while head is not None:
            if head in seen:
                raise StoreError('cyclic generation history')
            seen.add(head)
            obj, _ = self._generation(head)
            if obj['op'] in operations:
                raise StoreError('duplicate committed operation')
            operations[obj['op']] = (obj['request'], head)
            head = obj['previous']
        return operations

    def read(self):
        """Return (generation id, mapping); validates entire committed chain."""
        head = self._head()
        if head is None:
            return None, {}
        self._history(head)
        return head, self._generation(head)[1]

    def lookup(self, operation_id):
        """Read a committed operation without creating files or moving HEAD."""
        head = self._head()
        operations = self._history(head)
        if operation_id not in operations:
            return None
        operation_head = operations[operation_id][1]
        return operation_head, self._generation(operation_head)[1]

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
            self._history(head)
            keep = set()
            while head is not None:
                keep.add(head)
                head = self._generation(head)[0]['previous']
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
    os.execvpe('bash', ['bash', controller] + argv[2:], env)


def _access_exec(argv):
    """Lock the ledger directory itself: read access never creates files.

    The descriptor survives exec and is shared by cooperating child readers.
    Nested writers are refused, including writers launched by a check.
    """
    if len(argv) < 3 or argv[1] not in ('read', 'write', 'gate'):
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
            if mode == 'write' and (os.environ.get('GOAL_ACCESS_MODE') != 'write' or owner != os.getpid()):
                raise StoreError('nested-writer')
            os.close(fd)
            fd = existing
        else:
            try:
                fcntl.flock(fd, (fcntl.LOCK_EX if mode == 'write' else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            except OSError as exc:
                raise StoreError('ledger-busy; retry after current operation') from exc
        actual_mode = os.environ.get('GOAL_ACCESS_MODE', 'write' if mode == 'write' else 'read')
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
        env = os.environ.copy()
        env['GOAL_ACCESS_FD'] = str(fd)
        env['GOAL_ACCESS_EXEC_PID'] = str(os.getpid())
        env.setdefault('GOAL_ACCESS_OWNER_PID', str(os.getpid()))
        env['GOAL_ACCESS_MODE'] = actual_mode
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
_MUTATION_FILES = {
    'init': ('state.rec', 'loop-log.md', 'verdicts.rec', 'work-plan.md'),
    'stamp': ('state.rec', 'goal.md', 'check_freeze', 'pre-reg.md'),
    'bind': ('verdicts.rec',),
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
        if (not isinstance(meta, dict) or set(meta) != {'version', 'operation', 'intent', 'result', 'iteration', 'missing'}
                or type(meta['version']) is not int or meta['version'] != 1
                or meta['operation'] != operation or not isinstance(meta['intent'], str)
                or not _SHA256.fullmatch(meta['intent']) or type(meta['result']) is not int
                or meta['result'] not in (0, 2, 3, 4) or type(meta['iteration']) is not int
                or not isinstance(meta['missing'], list) or any(not isinstance(n, str) for n in meta['missing'])
                or len(set(meta['missing'])) != len(meta['missing'])):
            raise StoreError('invalid close commit metadata')
        files = {name: data for name, data in snapshot.items() if name != _CLOSE_META}
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
            or payload['version'] not in (1, 2, 3)
            or set(payload) != ({'version', 'files'} if payload['version'] == 1 else
                                {'version', 'files', 'operation', 'intent'} if payload['version'] == 2 else
                                {'version', 'files', 'operation', 'intent', 'base_head'})
            or obj.get('sha256') != _hash(_encode(payload))):
        raise StoreError('corrupt close journal')
    if payload['version'] >= 2 and (not isinstance(payload['operation'], str)
            or not _OPERATION.fullmatch(payload['operation']) or not isinstance(payload['intent'], str)
            or not _SHA256.fullmatch(payload['intent'])):
        raise StoreError('invalid journal operation identity')
    if payload['version'] == 3 and payload['base_head'] is not None and (
            not isinstance(payload['base_head'], str) or not _SHA256.fullmatch(payload['base_head'])):
        raise StoreError('invalid journal base version')
    files = payload.get('files')
    _close_file_set(files)
    for value in files.values():
        if value is not None:
            if not isinstance(value, str):
                raise StoreError('invalid journal file contents')
            base64.b64decode(value, validate=True)
    return payload


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
            or set(record['files']) != set(_MUTATION_FILES[record['kind']])):
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
    files = {name: data for name, data in snapshot.items() if name != _MUTATION_META}
    if set(files).intersection(meta['missing']):
        raise StoreError('conflicting mutation snapshot paths')
    files.update(dict.fromkeys(meta['missing']))
    if set(files) != set(_MUTATION_FILES[kind]):
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
        _sync_views(state, record['files'])
        files = _capture_files(state, record['files'])
        snapshot = {name: data for name, data in files.items() if data is not None}
        snapshot[_MUTATION_META] = _encode({'version': 1, 'kind': kind, 'operation': record['operation'],
                                          'intent': record['intent'],
                                          'missing': sorted(name for name, data in files.items() if data is None)})
        commits.commit(record['operation'], record['intent'].encode('ascii'), snapshot,
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
    mutation_journal(state, 'finish')
    print('CTL: BIND ok appended=%s skipped=0 operation=%s' % (len(lines), identity))


def close_journal(state, action, result=0):
    """Rollback journal for the existing close writer; never replay checks."""
    state = Path(state)
    pending = state / 'store/pending'
    if action == 'recover' and pending.exists():
        envelope = json.loads(pending.read_bytes())
        if (isinstance(envelope, dict) and isinstance(envelope.get('payload'), dict)
                and envelope['payload'].get('version') == 4):
            return mutation_journal(state, 'recover')
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
            snapshot[_CLOSE_META] = _encode({'version': 1, 'operation': record['operation'],
                                            'intent': record['intent'], 'result': result,
                                            'iteration': iteration, 'missing': sorted(missing)})
            commits = Store(state / 'store/commits')
            head, _ = commits.read()
            if record['version'] == 3 and head != record['base_head']:
                raise Conflict('close baseline committed version changed')
            # The atomic current pointer publication is the close commit point.
            # Its snapshot is also the source of recovery after this point.
            commits.commit(record['operation'], record['intent'].encode('ascii'), snapshot,
                           expected_head=head, lock_timeout=0)
        pending.unlink()
        _fsync_dir(pending.parent)
    elif action == 'recover':
        with Store(state / 'store')._lock(0):
            if not pending.exists():
                return
            record = _close_record(pending)
            files = record['files']
            committed = (_close_committed(state, record['operation'], record['intent'], require_current=True)
                         if record['version'] >= 2 else None)
            if committed is None:
                head, _ = Store(state / 'store/commits').read()
                if record['version'] == 3:
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
        elif len(sys.argv) >= 2 and sys.argv[1] == 'writer-exec':
            _writer_exec(sys.argv[2:])
        elif len(sys.argv) >= 2 and sys.argv[1] == 'access-exec':
            _access_exec(sys.argv[2:])
        else:
            raise StoreError('unknown command')
    except (StoreError, OSError, ValueError, KeyError, TypeError) as exc:
        print('CTL: ERROR writer-lock: %s' % exc, file=sys.stderr)
        sys.exit(4)
