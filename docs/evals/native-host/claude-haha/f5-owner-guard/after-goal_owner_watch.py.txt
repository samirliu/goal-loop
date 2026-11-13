#!/usr/bin/env python3
"""Supervise a borrowed-lock command until its specific owner exits.

Usage: goal_owner_watch.py supervise OWNER [--ready-fd FD] -- COMMAND [ARG ...]

The command is a direct child retained until waitpid, so signaling it cannot
target a recycled PID. Owner exit is observed with pidfd (Linux) or kqueue
NOTE_EXIT (macOS), including exit before the owner zombie is reaped. No polling
fallback is used. Owner identity is bound when the event subscription is armed;
the caller must supply the intended live owner at that point.

Inherited ledger descriptors stay with this supervisor and its child. Internal
event and startup-pipe descriptors are closed in the child. Before exec the
child sets GOAL_ACCESS_EXEC_PID to its own PID, retaining the original owner
and access mode. This is trusted process supervision, not a permission boundary.
"""
import contextlib
import errno
import math
import os
import select
import signal
import stat
import sys
import time


class WatchError(RuntimeError):
    pass


class OwnerExited(Exception):
    pass


class _Cancelled(BaseException):
    def __init__(self, signum):
        self.signum = signum


class _PidfdEvents:
    name = 'pidfd'

    def __init__(self, owner):
        self.poller = select.poll()
        self.handles = {}
        try:
            self._add(owner, 'owner')
        except BaseException:
            self.close()
            raise

    def _add(self, pid, role):
        try:
            fd = os.pidfd_open(pid, 0)
        except ProcessLookupError as exc:
            if role == 'owner':
                raise OwnerExited() from exc
            raise
        try:
            self.poller.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
        except BaseException:
            os.close(fd)
            raise
        self.handles[fd] = role

    def add_child(self, pid):
        self._add(pid, 'child')

    def events(self, timeout):
        milliseconds = -1 if timeout is None else int(timeout * 1000)
        found = set()
        for fd, flags in self.poller.poll(milliseconds):
            if flags & (select.POLLERR | select.POLLNVAL):
                raise WatchError('process event descriptor failed')
            if flags & (select.POLLIN | select.POLLHUP):
                found.add(self.handles[fd])
        return found

    def close(self):
        for fd in self.handles:
            os.close(fd)
        self.handles.clear()


class _KqueueEvents:
    name = 'kqueue'

    def __init__(self, owner):
        self.queue = select.kqueue()
        self.roles = {}
        try:
            self._add(owner, 'owner')
        except BaseException:
            self.close()
            raise

    def _add(self, pid, role):
        event = select.kevent(pid, filter=select.KQ_FILTER_PROC,
                              flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
                              fflags=select.KQ_NOTE_EXIT)
        try:
            self.queue.control([event], 0, 0)
        except ProcessLookupError as exc:
            if role == 'owner':
                raise OwnerExited() from exc
            raise
        self.roles[pid] = role

    def add_child(self, pid):
        self._add(pid, 'child')

    def events(self, timeout):
        found = set()
        for event in self.queue.control([], 2, timeout):
            if event.flags & select.KQ_EV_ERROR:
                raise WatchError('process event registration failed: %s' % event.data)
            if event.fflags & select.KQ_NOTE_EXIT:
                found.add(self.roles[event.ident])
        return found

    def close(self):
        self.queue.close()


def _process_events(owner):
    if sys.platform.startswith('linux') and hasattr(os, 'pidfd_open') and hasattr(select, 'poll'):
        return _PidfdEvents(owner)
    if sys.platform == 'darwin' and hasattr(select, 'kqueue'):
        return _KqueueEvents(owner)
    raise WatchError('identity-bound process exit events unavailable')


def _wait_child(pid):
    while True:
        try:
            _, status = os.waitpid(pid, 0)
            return os.waitstatus_to_exitcode(status)
        except InterruptedError:
            continue


@contextlib.contextmanager
def _defer_cancel():
    # Keep the child handle valid until the caller clears it after waitpid.
    # Otherwise a signal between reap and handle-clear could signal a reused
    # PID from cleanup. Queued cancellation runs after the handle is cleared.
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def _stop_child(pid, process_group=False):
    # This is our own unreaped child: even if it has exited, its PID cannot
    # have been reassigned. Do not reap it before this final signal attempt.
    try:
        if process_group:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(pid, signal.SIGKILL)
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
        _wait_child(pid)


def _group_guard():
    # Darwin returns EPERM when a group contains only an unreaped zombie.
    # Retain one signalable member until group cleanup, so the parent can kill
    # the group BEFORE reaping/reserving its leader. The guard has no user IO
    # or lock descriptors. Fork completes before the actual command can exit.
    # Snapshot actual handles before fork, so unavailable inventories reject
    # command startup in the leader. RLIMIT_NOFILE may be infinity (Bun/macOS)
    # and cannot be passed as the C-int endpoint of os.closerange.
    for directory in ('/proc/self/fd', '/dev/fd'):
        try:
            descriptors = [int(name) for name in os.listdir(directory) if name.isdigit()]
            break
        except OSError:
            continue
    else:
        raise WatchError('open-descriptor-inventory-unavailable')
    if os.fork() == 0:
        for fd in descriptors:
            try:
                os.close(fd)
            except OSError as exc:
                # listdir's own temporary directory descriptor is already
                # closed when its snapshot is returned.
                if exc.errno != errno.EBADF:
                    raise
        while True:
            signal.pause()


def _command_child(command, release, events, process_group=False, close_fds=()):
    try:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        events.close()
        for fd in close_fds:
            os.close(fd)
        if process_group:
            os.setsid()
        allowed = os.read(release, 1)
        os.close(release)
        if allowed != b'1':
            os._exit(143)
        if process_group:
            _group_guard()
        env = os.environ.copy()
        if close_fds:
            env.pop('GOAL_RUNNER_FD', None)
        if process_group:
            # A bounded user command has dropped ledger descriptors. It must
            # acquire fresh access if it invokes a product entrypoint itself.
            env.pop('GOAL_ACCESS_EXEC_PID', None)
        else:
            env['GOAL_ACCESS_EXEC_PID'] = str(os.getpid())
        os.execvpe(command[0], command, env)
    except BaseException as exc:
        print('OWNER_WATCH: ERROR command-start: %s' % exc, file=sys.stderr, flush=True)
        os._exit(127)


def supervise(owner, command, ready_fd=None, *, timeout=None, process_group=False, close_fds=(),
              cancel_file=None, deadline_epoch=None):
    """Run command; return its status, or 143 if owner exits first.

    No command is released until owner and child exit subscriptions are armed.
    `ready_fd`, when supplied, must be an inherited pipe write end; exactly one
    READY line is written after subscriptions are armed and before release.
    Setup errors raise WatchError/OSError and never run the command.
    """
    if type(owner) is not int or owner <= 1 or owner == os.getpid() or not command:
        raise WatchError('requires a distinct positive owner PID and command')
    if timeout is not None and (not math.isfinite(timeout) or timeout < 0):
        raise WatchError('timeout must be finite and nonnegative')
    if deadline_epoch is not None and (not math.isfinite(deadline_epoch) or deadline_epoch < 0):
        raise WatchError('deadline must be finite and nonnegative')
    if cancel_file is not None:
        cancel_file = os.fspath(cancel_file)
        if not cancel_file or '\0' in cancel_file:
            raise WatchError('invalid cancellation path')
        if os.path.lexists(cancel_file):
            return 130
    if deadline_epoch is not None and time.time() >= deadline_epoch:
        return 124
    until = None if timeout is None else time.monotonic() + timeout
    if os.name != 'posix' or not hasattr(os, 'fork') or not hasattr(signal, 'pthread_sigmask'):
        raise WatchError('POSIX fork supervision unavailable')
    if ready_fd is not None:
        if type(ready_fd) is not int or ready_fd < 3 or not stat.S_ISFIFO(os.fstat(ready_fd).st_mode):
            raise WatchError('ready-fd must be an inherited pipe')
    events = None
    child = None
    release_read = release_write = None
    saved_signals = {}
    previous_child_signal = None
    try:
        try:
            events = _process_events(owner)
        except OwnerExited:
            return 143
        if 'owner' in events.events(0):
            return 143

        # Block the child before exec until both process identities are armed.
        # SIG_IGN/SA_NOCLDWAIT would auto-reap children, losing PID reservation.
        previous_child_signal = signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        release_read, release_write = os.pipe()
        child = os.fork()
        if child == 0:
            os.close(release_write)
            if ready_fd is not None:
                os.close(ready_fd)
            _command_child(command, release_read, events, process_group, close_fds)
            os._exit(127)
        os.close(release_read)
        release_read = None

        def cancel(signum, _frame):
            raise _Cancelled(signum)

        for signum in (signal.SIGTERM, signal.SIGINT):
            saved_signals[signum] = signal.signal(signum, cancel)
        events.add_child(child)
        found = events.events(0)
        if 'owner' in found:
            return 143
        if 'child' in found:
            with _defer_cancel():
                if process_group:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(child, signal.SIGKILL)
                status = _wait_child(child)
                child = None
            return status if status >= 0 else 128 - status
        if until is not None and time.monotonic() >= until:
            return 124
        if cancel_file is not None and os.path.lexists(cancel_file):
            return 130
        if deadline_epoch is not None and time.time() >= deadline_epoch:
            return 124
        if ready_fd is not None:
            os.write(ready_fd, ('READY %s %s\n' % (events.name, child)).encode('ascii'))
            os.close(ready_fd)
            ready_fd = None
        os.write(release_write, b'1')
        os.close(release_write)
        release_write = None
        while True:
            if cancel_file is not None and os.path.lexists(cancel_file):
                return 130
            remaining = None if until is None else max(0, until - time.monotonic())
            if deadline_epoch is not None:
                wall_left = max(0, deadline_epoch - time.time())
                remaining = wall_left if remaining is None else min(remaining, wall_left)
            if remaining == 0:
                return 124
            # kqueue timespec / poll millisecond fields have finite ranges.
            # Keep the absolute deadline; bounding one wait never grants time.
            # Native model cancellation may leave its tool process owner alive.
            # Observe only this attempt's cancellation token; PID lifetime still
            # uses kernel events. Existing callers retain the event-only path.
            interval = .05 if cancel_file is not None or deadline_epoch is not None else 60
            wait_for = None if remaining is None else min(remaining, interval)
            if interval < 60 and wait_for is None:
                wait_for = interval
            found = events.events(wait_for)
            if 'owner' in found:
                return 143
            if 'child' in found:
                with _defer_cancel():
                    if process_group:
                        # Kill descendants before reaping the group leader;
                        # its reserved PID cannot yet name an unrelated group.
                        with contextlib.suppress(ProcessLookupError):
                            os.killpg(child, signal.SIGKILL)
                    status = _wait_child(child)
                    child = None
                return status if status >= 0 else 128 - status
    except _Cancelled as exc:
        return 128 + exc.signum
    finally:
        # Ignore repeat termination signals while collecting our child so a
        # second signal cannot strand it between kill and waitpid.
        for signum in saved_signals:
            signal.signal(signum, signal.SIG_IGN)
        try:
            if child is not None:
                _stop_child(child, process_group)
        finally:
            for signum, previous in saved_signals.items():
                signal.signal(signum, previous)
            if previous_child_signal is not None:
                signal.signal(signal.SIGCHLD, previous_child_signal)
            for fd in (release_read, release_write, ready_fd):
                if fd is not None:
                    with contextlib.suppress(OSError):
                        os.close(fd)
            if events is not None:
                events.close()


def main(args):
    if len(args) < 4 or args[0] != 'supervise':
        raise WatchError('usage: supervise OWNER [--ready-fd FD] -- COMMAND [ARG ...]')
    owner = int(args[1])
    rest = args[2:]
    ready_fd = None
    if len(rest) >= 2 and rest[0] == '--ready-fd':
        ready_fd, rest = int(rest[1]), rest[2:]
    if len(rest) < 2 or rest[0] != '--':
        raise WatchError('expected -- COMMAND')
    return supervise(owner, rest[1:], ready_fd)


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except (WatchError, OSError, ValueError) as exc:
        print('OWNER_WATCH: ERROR %s' % exc, file=sys.stderr)
        sys.exit(4)
