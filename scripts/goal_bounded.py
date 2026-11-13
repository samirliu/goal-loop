#!/usr/bin/env python3
"""Bound an owned command group using the shared kernel exit supervisor.

No GNU timeout dependency. A runner lock, when supplied by the runner, remains
with this supervisor until the command group is dead, and never reaches user
commands. Stdout remains the command's measurement channel.
"""
import argparse
import importlib.util
import math
import os
from pathlib import Path
import shutil
import sys
import time

sys.dont_write_bytecode = True
# -I deliberately excludes ambient Python modules, including the script dir.
spec = importlib.util.spec_from_file_location('goal_owner_watch', Path(__file__).with_name('goal_owner_watch.py'))
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)
trace_spec = importlib.util.spec_from_file_location('goal_trace', Path(__file__).with_name('goal_trace.py'))
tracing = importlib.util.module_from_spec(trace_spec)
trace_spec.loader.exec_module(tracing)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--owner', type=int, required=True)
    parser.add_argument('--seconds', type=float)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--settlement', action='store_true')
    parser.add_argument('--reserve', action='store_true')
    parser.add_argument('--kind', choices=sorted(tracing.KINDS), default='command')
    parser.add_argument('--label', default='command')
    parser.add_argument('--artifact')
    parser.add_argument('--cancel-file', type=Path)
    parser.add_argument('--deadline-epoch', type=float)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command or shutil.which(command[0]) is None:
        raise FileNotFoundError('command unavailable: ' + (command[0] if command else '(empty)'))
    seconds = args.seconds
    if seconds is not None and (not math.isfinite(seconds) or seconds < 0):
        raise ValueError('invalid command budget')
    if not args.settlement and os.environ.get('GOAL_RUNNER_MONOTONIC_END'):
        remaining = max(0, float(os.environ['GOAL_RUNNER_MONOTONIC_END']) - time.monotonic())
        seconds = remaining if seconds is None else min(seconds, remaining)
    if args.reserve:
        if seconds is None:
            raise ValueError('executor reservation needs a budget')
        seconds = max(0, seconds - min(3, seconds * 0.1))
    if args.settlement:
        if seconds is None:
            raise ValueError('settlement needs a budget')
        # Nested checks share the same finite settlement, rather than the
        # expired search budget or a new three seconds per AC.
        os.environ['GOAL_RUNNER_MONOTONIC_END'] = str(time.monotonic() + seconds)
    end = None if seconds is None else time.monotonic() + seconds
    # Nested command supervisors must survive their owner's group being
    # cancelled. Otherwise outer killpg kills the supervisor itself while its
    # separately sessioned check group continues running without supervision.
    if os.getsid(0) != os.getpid():
        os.setsid()
    retained = ()
    if os.environ.get('GOAL_RUNNER_FD'):
        fd = int(os.environ['GOAL_RUNNER_FD'])
        os.fstat(fd)  # Fail closed if the advertised ownership is not held.
        retained = (fd,)
    trace = None
    if os.environ.get('GOAL_TRACE_PROJECT'):
        try:
            trace = tracing.Trace(os.environ['GOAL_TRACE_PROJECT'], args.kind, args.label, command, args.artifact)
            os.environ['GOAL_TRACE_PARENT'] = trace.identity
        except (OSError, ValueError, TypeError) as exc:
            print('BOUNDED: NOTE trace-unavailable: %s; cost unknown' % exc, file=sys.stderr)
    # Metadata preparation/fsync spends the same allowance as the command.
    left = None if end is None else max(0, end - time.monotonic())
    result = None
    try:
        result = watch.supervise(args.owner, command, timeout=left,
                                 process_group=True, close_fds=retained,
                                 cancel_file=args.cancel_file, deadline_epoch=args.deadline_epoch)
    except (watch.WatchError, OSError, ValueError):
        result = 4  # Same handled state error returned by the public entry.
        raise
    finally:
        if trace is not None and result is not None:
            try:
                trace.finish(result)
            except (OSError, ValueError) as exc:
                print('BOUNDED: NOTE trace-incomplete: %s; cost unknown' % exc, file=sys.stderr)
    if args.receipt:
        args.receipt.write_text(str(result), encoding='ascii')
        return 0
    return result


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (watch.WatchError, OSError, ValueError) as exc:
        print('BOUNDED: ERROR %s' % exc, file=sys.stderr)
        sys.exit(4)
