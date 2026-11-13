#!/usr/bin/env python3
"""Linux-only local supervision diagnostic; never runs a model or full suite."""
import argparse
import contextlib
import ctypes
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
import traceback

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', default='/src', type=Path)
p.add_argument('--output', default='/results/owner-watch-diagnostic.json', type=Path)
p.add_argument('--observe', default=2.2, type=float)
a = p.parse_args()
if not sys.platform.startswith('linux') or not 0 <= a.observe <= 10:
    raise SystemExit('requires Linux and --observe between 0 and 10 seconds')
observation_spec = importlib.util.spec_from_file_location('observed_ledger_test', a.output.parent/'test_ledger_access-after.py')
observation = importlib.util.module_from_spec(observation_spec)
observation_spec.loader.exec_module(observation)

def read(path):
    try:
        return Path(path).read_text(errors='replace')
    except OSError as e:
        return {'error': repr(e)}

def process(pid, full=True):
    raw = read('/proc/%s/stat' % pid)
    if not isinstance(raw, str):
        return {'pid': pid, 'stat_error': raw}
    end = raw.rfind(')'); fields = raw[end+2:].split()
    row = dict(pid=pid, comm=raw[raw.find('(')+1:end], state=fields[0],
               ppid=int(fields[1]), pgrp=int(fields[2]), session=int(fields[3]),
               starttime=int(fields[19]), stat=raw)
    if full:
        row.update(status=read('/proc/%s/status' % pid),
                   cmdline=read('/proc/%s/cmdline' % pid),
                   children=read('/proc/%s/task/%s/children' % (pid, pid)))
        try:
            row['fds'] = {f.name: os.readlink(f) for f in Path('/proc/%s/fd' % pid).iterdir()}
        except OSError as e:
            row['fds_error'] = repr(e)
    return row

def ancestors(pid):
    rows, seen = [], set()
    while pid > 0 and pid not in seen and len(rows) < 10:
        seen.add(pid); row = process(pid); rows.append(row)
        pid = row.get('ppid', 0)
    return rows

def group(pgid):
    rows = []
    for path in Path('/proc').iterdir():
        if path.name.isdecimal():
            row = process(int(path.name), False)
            if row.get('pgrp') == pgid:
                rows.append(process(row['pid']))
    return rows

root = Path(tempfile.mkdtemp(prefix='goal-owner-diagnostic-'))
state = root/'ledger'; state.mkdir()
writer = state/'writer.lock'; writer.touch()
marker = root/'childpid'
late_write = root/'late-write'
def lock_probe(path):
    fd = os.open(path, os.O_RDONLY | (os.O_DIRECTORY if path.is_dir() else 0))
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return 'available'
        except BlockingIOError:
            return 'blocked'
    finally:
        os.close(fd)

targets = {name: '%x:%x:%d' % (os.major(path.stat().st_dev), os.minor(path.stat().st_dev), path.stat().st_ino)
           for name, path in (('ledger_directory', state), ('writer_lock', writer))}
def locks():
    raw = read('/proc/locks')
    return {'target_inodes': targets,
            'matching': [line for line in raw.splitlines() if any(':'+t.rsplit(':', 1)[1]+' ' in line for t in targets.values())]
                        if isinstance(raw, str) else raw,
            'probes': {'ledger_directory': lock_probe(state), 'writer_lock': lock_probe(writer)}}

fd_dir = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
fd_writer = os.open(writer, os.O_RDONLY)
for fd in (fd_dir, fd_writer):
    fcntl.flock(fd, fcntl.LOCK_EX)
    os.set_inheritable(fd, True)
result = {'source': str(a.source), 'uid': os.geteuid(), 'pid': os.getpid(),
          'owner_watch_sha256': hashlib.sha256((a.source/'scripts/goal_owner_watch.py').read_bytes()).hexdigest(),
          'temporary_fixture': str(root), 'parent_chain': ancestors(os.getpid()),
          'pid1': process(1), 'locks_held_by_this_supervisor': locks(),
          'cpu_stat_before': read('/sys/fs/cgroup/cpu.stat'), 'load_before': read('/proc/loadavg')}
flag = ctypes.c_int()
libc = ctypes.CDLL(None, use_errno=True)
result['get_child_subreaper'] = {'returncode': libc.prctl(37, ctypes.byref(flag), 0, 0, 0), 'value': flag.value}
spec = importlib.util.spec_from_file_location('diagnosed_watch', a.source/'scripts/goal_owner_watch.py')
watch = importlib.util.module_from_spec(spec); spec.loader.exec_module(watch)
owner = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(15)'],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
result['live_control_running'] = observation.LedgerAccess.child_running(owner.pid)
if not result['live_control_running']:
    raise RuntimeError('Live control was incorrectly treated as stopped')
result['observation_test_sha256'] = hashlib.sha256((a.output.parent/'test_ledger_access-after.py').read_bytes()).hexdigest()
ready_read, ready_write = os.pipe()
try:
    started = time.monotonic()
    command = ('import os,sys,time; from pathlib import Path; child=os.fork()\n'
               'if child == 0:\n'
               ' time.sleep(1.5); Path(sys.argv[2]).write_text("escaped\\n"); os._exit(0)\n'
               'Path(sys.argv[1]).write_text(str(child))\n')
    result['supervise_result'] = watch.supervise(owner.pid,
        [sys.executable, '-I', '-c', command, str(marker), str(late_write)],
        ready_fd=ready_write, timeout=3, process_group=True, close_fds=(fd_dir, fd_writer))
    ready_write = None  # supervise owns and closes it.
    result['supervise_elapsed'] = time.monotonic()-started
    ready = os.read(ready_read, 256).decode(); result['ready'] = ready
    pgid = int(ready.split()[2]); child = int(marker.read_text())
    result['background_pid'] = child
    result['locks_before_retained_fds_close'] = locks()
    os.close(fd_dir); fd_dir = None
    os.close(fd_writer); fd_writer = None
    result['locks_after_retained_fds_close'] = locks()
    begin = time.monotonic(); result['observations'] = []
    for offset in (0, .1, .5, 1, a.observe):
        time.sleep(max(0, begin+offset-time.monotonic()))
        row = process(child)
        running = observation.LedgerAccess.child_running(child)
        if row.get('state') == 'Z' and running:
            raise RuntimeError('Zombie was incorrectly treated as running')
        try:
            os.kill(child, 0); signal0 = 'success'
        except OSError as e:
            signal0 = repr(e)
        result['observations'].append({'after_return': time.monotonic()-begin, 'signal0': signal0, 'test_observer_running': running,
            'background': row, 'parent_chain': ancestors(child), 'group': group(pgid), 'locks': locks()})
    result['cleanup'] = []
    for row in group(pgid):
        item = {'pid': row['pid'], 'state': row['state']}
        if row['state'] == 'Z':
            try:
                item['waitpid'] = os.waitpid(row['pid'], os.WNOHANG)
            except ChildProcessError as e:
                item['waitpid'] = repr(e)  # Adopted by its recorded parent, not ours to reap.
        elif hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'):
            fd = os.pidfd_open(row['pid'])
            try:
                if process(row['pid'], False).get('starttime') == row['starttime']:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                    item['action'] = 'SIGKILL through identity-bound pidfd'
            finally:
                os.close(fd)
        else:
            item['action'] = 'not signaled: no identity-bound pidfd capability'
        result['cleanup'].append(item)
except BaseException as e:
    result['diagnostic_error'] = repr(e)
    result['traceback'] = traceback.format_exc()
finally:
    if owner.poll() is None:
        owner.terminate()
    result['owner_wait'] = owner.wait(timeout=3)
    result['reaped_control_running'] = observation.LedgerAccess.child_running(owner.pid)
    if result['reaped_control_running']:
        raise RuntimeError('Reaped control was incorrectly treated as running')
    for fd in (fd_dir, fd_writer, ready_read, ready_write):
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)
result['cpu_stat_after'] = read('/sys/fs/cgroup/cpu.stat')
result['load_after'] = read('/proc/loadavg')
result['late_write_exists'] = late_write.exists()
a.output.write_text(json.dumps(result, indent=2)+'\n')
last = result.get('observations', [{}])[-1]
print(json.dumps({'output': str(a.output), 'uid': result['uid'], 'supervise_result': result.get('supervise_result'),
                  'background_pid': result.get('background_pid'), 'final_signal0': last.get('signal0'),
                  'final_state': last.get('background', {}).get('state'),
                  'final_ppid': last.get('background', {}).get('ppid'),
                  'locks': last.get('locks', {}).get('probes'), 'cleanup': result.get('cleanup'),
                  'late_write_exists': result['late_write_exists'],
                  'diagnostic_error': result.get('diagnostic_error')}, indent=2))
