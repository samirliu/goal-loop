#!/usr/bin/env python3
"""Run one registered host worker's tool under its existing budget and token.

The host still owns agent creation and interruption. This wrapper owns only
the command group it releases; it never interrupts sibling agents or tools.
"""
import argparse
import contextlib
import importlib.util
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('goal_host', Path(__file__).with_name('goal_host.py'))
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


@contextlib.contextmanager
def read_ticket(project):
    root, path = host.folder(project)
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    end = time.monotonic() + 2
    try:
        while True:
            try:
                host.store.fcntl.flock(fd, host.store.fcntl.LOCK_SH | host.store.fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= end:
                    raise ValueError('host receipt busy; command not released')
                time.sleep(.005)
        yield root, path
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='run the registered frozen job check without inline shell code')
    parser.add_argument('project')
    parser.add_argument('ticket')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    host.require(bool(command) != args.check, 'supply either --check or one owned command')
    with read_ticket(args.project) as (root, path):
        _, row = host.get(path, args.ticket)
        session = host.active(path, root, row['session'], row['backend'])
        host.require(row['phase'] == 'prepared' and row['run'] == session['run'], 'attempt is not active')
        host.require(row['boot'] == host.budget.boot_identity(), 'boot changed during host attempt')
        graph = host.crew.load(host.crew.Wave(root, row['wave']).path)
        host.crew.policy_current(graph.get('policy'))
        if args.check:
            wave = host.crew.Wave(root, row['wave'])
            graph = host.crew.load(wave.path)
            host.crew.Wave(root, row['wave'])._instruments(graph)
            job = next(j for j in graph['graph']['jobs'] if j['id'] == row['task'])
            command = [s.replace('{project}', str(root)) for s in job['check']]
        token = host.safe(Path(row['cancel_file']))
        host.require(token.parent == path and token.name == 'cancel-' + row['id'] + '-' + row['nonce'],
                     'invalid cancel token path')
        with host.crew.read_ledger(root) as (state, _):
            cap, expired = host.budget.gate_limit(state, settlement=False)
            runner = host.budget.runner_data((state / 'runner.json').read_bytes())
        host.require(cap is not None, 'missing host deadline')
        end = min(cap, row['deadline_monotonic'])
        epoch = min(runner['deadline'], row['deadline_epoch'])
        seconds = 0 if expired else max(0, end - time.monotonic())
    # No ledger/host writer lock crosses the exec boundary. Nested commands
    # inherit the same cutoff and remain children of the worker span.
    os.environ.update(GOAL_TRACE_PROJECT=str(root), GOAL_TRACE_PARENT=row['trace'],
                      GOAL_RUNNER_MONOTONIC_END=str(end))
    bounded = str(Path(__file__).with_name('goal_bounded.py'))
    if args.check:
        os.chdir(root)
    os.execv(sys.executable, [sys.executable, '-I', bounded, '--owner', str(os.getppid()),
             '--seconds', str(seconds), '--deadline-epoch', str(epoch),
             '--cancel-file', str(token), '--kind', 'measurement' if args.check else 'command',
             '--label', 'host-worker-check' if args.check else 'host-owned-tool',
             '--', *command])


if __name__ == '__main__':
    try:
        main()
    except host.ERRORS as exc:
        print('HOST-TOOL: ERROR ' + str(exc), file=sys.stderr)
        sys.exit(4)
