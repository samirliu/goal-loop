#!/usr/bin/env python3
"""Replay two observable defects against frozen before/after source trees."""
import argparse
import importlib.util
import json
import os
import fcntl
from pathlib import Path
import subprocess
import sys
import tempfile


def observe(root):
    spec=importlib.util.spec_from_file_location('replay_fixture',root/'tests/test_crew.py')
    f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
    case=f.Crew();case.setUp()
    try:
        case.write_graph(deps=True)
        wave=case.fresh('crew','dependency-counterexample')
        wave.event('T1','dispatch');case.work(wave,'T1')
        (case.project/'a.out').write_text('corrupted after acceptance')
        refused=False;error=None
        try:wave.event('T2','dispatch')
        except ValueError as e:refused=True;error=str(e)
        marker=case.project/'client-was-invoked'
        client=case.project/'fake-client'
        client.write_text('#!/bin/sh\ntouch "'+str(marker)+'"\n');client.chmod(0o755)
        run=subprocess.run(['bash',str(root/'scripts/goal_loop.sh'),'--continue','--max-iterations=1',
            '--wallclock=3','--project',str(case.project)],capture_output=True,text=True,
            env=dict(os.environ,CLAUDE_BIN=str(client)),timeout=12)
        return dict(stale_parent_refused=refused,dependency_error=error,
                    installed_entry_invoked_client=marker.exists(),entry_result=run.returncode,
                    entry_stdout=run.stdout,entry_stderr=run.stderr)
    finally:case.doCleanups()


def borrowed_context(root):
    with tempfile.TemporaryDirectory(prefix='replay-context-lock-') as directory:
        project=Path(directory)
        subprocess.run(['bash',str(root/'scripts/goal_ctl.sh'),'init','--project',str(project)],check=True,capture_output=True)
        (project/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | example | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
        shown=subprocess.run([sys.executable,'-I',str(root/'scripts/goal_context.py'),'show',str(project)],check=True,capture_output=True)
        revision=json.loads(shown.stdout)['revision']
        fd=os.open(project/'.goal',os.O_RDONLY|os.O_DIRECTORY)
        try:
            fcntl.flock(fd,fcntl.LOCK_SH)
            env=dict(os.environ,GOAL_ACCESS_FD=str(fd),GOAL_ACCESS_MODE='write',GOAL_ACCESS_OWNER_PID=str(os.getpid()))
            result=subprocess.run([sys.executable,'-I',str(root/'scripts/goal_context.py'),'run',str(project),revision,'stamp'],
                                  env=env,pass_fds=(fd,),capture_output=True,text=True,timeout=12)
        finally:os.close(fd)
        return dict(result=result.returncode,approved='approved: PENDING' not in (project/'.goal/goal.md').read_text(),
                    stdout=result.stdout,stderr=result.stderr)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--current',type=Path,required=True)
    p.add_argument('--context-before',type=Path,help='optional frozen initial context implementation for the borrowed-lock regression')
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result={name:observe(root.resolve()) for name,root in [('before',args.baseline),('after',args.current)]}
    result['verified']=(not result['before']['stale_parent_refused'] and result['before']['installed_entry_invoked_client']
                        and result['after']['stale_parent_refused'] and not result['after']['installed_entry_invoked_client']
                        and result['after']['entry_result']==4)
    if args.context_before:
        result['borrowed_context']={label:borrowed_context(root.resolve())
                                  for label,root in [('before',args.context_before),('after',args.current)]}
        result['verified'] &= (result['borrowed_context']['before']['approved']
                               and not result['borrowed_context']['after']['approved']
                               and result['borrowed_context']['after']['result']==4)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,sort_keys=True))
    raise SystemExit(0 if result['verified'] else 1)
