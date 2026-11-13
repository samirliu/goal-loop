#!/usr/bin/env python3
"""Explicit, bounded developer comparison. Never called by the installed skill.

Legacy comparison B: both before and after load goal-loop. Neither is bare host.
Four predeclared calls, no retries, no installation or permission changes.
Uses a user-supplied existing CLI. Filtered logs omit model thinking and secrets.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]


def save(path,value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(path):
    spec=importlib.util.spec_from_file_location('entry_tasks',path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def filtered(value):
    kind=value.get('type')
    if kind=='assistant':
        message=value.get('message',{});blocks=[]
        for b in message.get('content',[]):
            if b.get('type')=='tool_use': blocks.append({k:b[k] for k in ('type','id','name','input') if k in b})
            elif b.get('type')=='text': blocks.append(dict(type='text',sha256=hashlib.sha256(b.get('text','').encode()).hexdigest()))
        return dict(type=kind,session_id=value.get('session_id'),message_id=message.get('id'),
                    model=message.get('model'),usage=message.get('usage'),content=blocks)
    if kind=='user':
        raw=value.get('tool_use_result')
        metadata={k:raw[k] for k in ('exitCode','exit_code','status','interrupted','durationMs','agentId') if k in raw} if isinstance(raw,dict) else None
        results=[]
        for b in value.get('message',{}).get('content',[]):
            if b.get('type')=='tool_result':
                body=json.dumps(b.get('content'),sort_keys=True)
                results.append(dict(tool_use_id=b.get('tool_use_id'),is_error=b.get('is_error'),
                                    content_sha256=hashlib.sha256(body.encode()).hexdigest()))
        return dict(type=kind,results=results,metadata=metadata)
    if kind=='result':
        result={k:value[k] for k in ('type','subtype','session_id','is_error','num_turns','usage','modelUsage',
                                   'duration_ms','duration_api_ms','errors') if k in value}
        if isinstance(value.get('result'),str): result['result_sha256']=hashlib.sha256(value['result'].encode()).hexdigest()
        result['result_nonempty']=isinstance(value.get('result'),str) and bool(value['result'].strip())
        return result
    if kind=='system':
        return {k:value[k] for k in ('type','subtype','session_id','model','plugins','skills','hook_event',
                                    'hook_id','outcome','exit_code','stdout','stderr') if k in value}
    return None


def trial(folder,plugin,cli,specimen,seed,grader,permission_mode=None):
    entry,epoch=time.monotonic(),time.time();end=entry+360
    folder.mkdir();work=folder/'work';control=folder/'control';control.mkdir()
    shutil.copytree(specimen,work)
    shutil.copy2(grader,control/'grade.py');(control/'mcp.json').write_text('{"mcpServers":{}}\n')
    inputs={n:sha(work/n) for n in ('TASK.md','public.py')}
    session=str(uuid.uuid4())
    prompt=('/goal-loop-host:goal-loop --auto --time-budget=360 Complete TASK.md in the current project '+str(work)+
        '. The user authorizes automatic contract stamping and execution; do not request approval again. '
        'TASK.md and public.py are frozen inputs. Modify only solution.py, optional tests, and this project .goal metadata. '
        'Do not modify the skill or any other repository, and do not use web, MCP, dependencies or model overrides. '
        'Use the skill normal completion conditions and report the resulting evidence.')
    command=[str(cli),'--print','--no-session-persistence','--session-id',session,
        '--plugin-dir',str(plugin),'--output-format','stream-json','--verbose','--include-hook-events','--max-turns','80',
        '--tools','Agent,Read,Grep,Glob,Write,Edit,Bash','--strict-mcp-config','--mcp-config',str(control/'mcp.json'),'--',prompt]
    if permission_mode is not None:
        command[1:1]=['--permission-mode',permission_mode]
    # Same 15-second independent verification reserve in every position.
    cli_end=end-15
    bounded=[sys.executable,'-I',str(plugin/'scripts/goal_bounded.py'),'--owner',str(os.getpid()),
             '--seconds',str(max(0,cli_end-time.monotonic())),'--deadline-epoch',str(epoch+345),'--',*command]
    save(folder/'manifest.json',dict(entry=entry,epoch=epoch,seconds=360,cli_seconds=345,seed=seed,
        session=session,command=command,inputs=inputs,grader_sha256=sha(control/'grade.py'),plugin=str(plugin)))
    env=dict(os.environ,GOAL_RUNNER_MONOTONIC_END=str(cli_end))
    error=(folder/'stderr.txt').open('wb');events=(folder/'events.jsonl').open('w')
    process=subprocess.Popen(bounded,cwd=work,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=error)
    selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
    os.set_blocking(process.stdout.fileno(),False);buffer=b'';event_rows=[];parse_errors=[]
    def observe(line):
        if not line.strip():return
        try:value=filtered(json.loads(line))
        except (ValueError,TypeError) as e:
            parse_errors.append(dict(error=type(e).__name__,line_sha256=hashlib.sha256(line).hexdigest()));return
        if value is not None:
            value['observed']=time.monotonic();event_rows.append(value)
            events.write(json.dumps(value,sort_keys=True)+'\n');events.flush()
    failure=None
    try:
        while process.poll() is None and time.monotonic()<cli_end+2:
            for key,_ in selector.select(.2):
                chunk=os.read(key.fd,65536)
                if not chunk:selector.unregister(key.fileobj);continue
                buffer+=chunk
                while b'\n' in buffer:
                    line,buffer=buffer.split(b'\n',1);observe(line)
        if process.poll() is None:process.terminate()
        process.wait(timeout=3)
        while True:
            try:chunk=os.read(process.stdout.fileno(),65536)
            except BlockingIOError:break
            if not chunk:break
            buffer+=chunk
        for line in buffer.splitlines():observe(line)
    except BaseException as e:
        failure=repr(e)
        if process.poll() is None:process.terminate()
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:failure+='; teardown unknown'
    finally:selector.close();events.close();error.close()
    cli_elapsed=time.monotonic()-entry
    checks={}
    verification_env=dict(os.environ,GOAL_RUNNER_MONOTONIC_END=str(end))
    if process.poll() is not None:
        for name,args in [('independent',[sys.executable,'-B',str(control/'grade.py'),'--project',str(work),
                            '--family','small','--seed',str(seed)]),
                          ('audit',['bash',str(plugin/'scripts/goal_audit.sh'),'--project',str(work)]),
                          ('gate',['bash',str(plugin/'scripts/goal_gate.sh'),'--check','--project',str(work)])]:
            started=time.monotonic()
            if started>=end:checks[name]=dict(result=None,reason='original deadline expired');continue
            try:
                checked=subprocess.run(args,cwd=work,env=verification_env,capture_output=True,text=True,timeout=max(.01,end-started))
                checks[name]=dict(command=args,result=checked.returncode,stdout=checked.stdout,stderr=checked.stderr,
                                  started=started,finished=time.monotonic(),within_budget=time.monotonic()<=end)
            except subprocess.TimeoutExpired:checks[name]=dict(result=None,reason='verification timed out')
    calls={b['id']:b for e in event_rows for b in e.get('content',[]) if b.get('type')=='tool_use' and b.get('id')}
    errors=[r for e in event_rows for r in e.get('results',[]) if r.get('is_error')]
    terminals=[e for e in event_rows if e.get('type')=='result']
    accepted=(len(checks)==3 and all(c.get('result')==0 and c.get('within_budget') for c in checks.values()))
    report=dict(cli_result=process.poll(),cli_elapsed=cli_elapsed,finished_elapsed=time.monotonic()-entry,
        checks=checks,accepted=accepted,normal_final_delivery=process.poll()==0 and bool(terminals) and
        terminals[-1].get('subtype')=='success' and not terminals[-1].get('is_error') and terminals[-1].get('result_nonempty'),
        tool_calls=len(calls),tool_errors=len(errors),parse_errors=parse_errors,error=failure,
        protocol_lookups=sum(b.get('name') in ('Read','Grep','Glob') and str(plugin) in json.dumps(b.get('input',{})) for b in calls.values()),
        inputs_changed=[n for n,h in inputs.items() if not (work/n).is_file() or sha(work/n)!=h],
        human_interventions=0,human_intervention_basis='one scheduled prompt; stdin closed; no subsequent user input',
        reported_terminal=terminals[-1] if terminals else None,tokens=None,money=None)
    save(folder/'report.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True)
    p.add_argument('--cli',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--permission-mode',help='forward only an explicitly authorized mode; omitted preserves the host default')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    tasks=module(ROOT/'examples/agent-evals/tasks.py')
    order=[('before',911221),('after',911221),('after',911222),('before',911222)]
    frozen=args.output/'frozen';frozen.mkdir()
    for name in ('grade.py','tasks.py'):
        shutil.copy2(ROOT/'examples/agent-evals'/name,frozen/name)
    inputs={}
    for seed in (911221,911222):
        specimen=frozen/str(seed);tasks.prepare(specimen,'small',seed)
        inputs[str(seed)]={str(f.relative_to(specimen)):sha(f) for f in specimen.rglob('*') if f.is_file()}
    save(args.output/'pre-registration.json',dict(order=order,maximum_calls=4,trial_seconds=360,cli_seconds=345,
        maximum_turns=80,permission_mode=args.permission_mode or 'host-default',model_override=None,
        scope='same small-family task with two held-out grading seeds; descriptive entry comparison only',
        frozen_inputs=inputs,grader_sha256=sha(frozen/'grade.py'),task_generator_sha256=sha(frozen/'tasks.py'),
        cli_sha256=sha(args.cli),tokens=None,money=None))
    shutil.copy2(Path(__file__),args.output/'driver.py')
    source={}
    for name,path in [('before',args.before.resolve()),('after',args.after.resolve())]:
        source[name]={str(f.relative_to(path)):sha(f) for f in path.rglob('*') if f.is_file() and '__pycache__' not in f.parts}
    save(args.output/'source-hashes.json',source)
    records=[]
    for n,(name,seed) in enumerate(order,1):
        plugin=(args.before if name=='before' else args.after).resolve()
        report=trial(args.output/('%s-%s'%(n,name)),plugin,args.cli.resolve(),frozen/str(seed),seed,frozen/'grade.py',args.permission_mode)
        records.append(dict(position=n,variant=name,seed=seed,**report))
        save(args.output/'report.json',dict(scope='descriptive pilot, no general superiority claim',records=records,tokens=None,money=None))
        print(json.dumps(dict(position=n,variant=name,accepted=report['accepted'],cli=report['cli_result'],tools=report['tool_calls'],seconds=report['finished_elapsed'])),flush=True)
    changed={}
    for name,path in [('before',args.before.resolve()),('after',args.after.resolve())]:
        now={str(f.relative_to(path)):sha(f) for f in path.rglob('*') if f.is_file() and '__pycache__' not in f.parts}
        changed[name]=[n for n in sorted(set(now)|set(source[name])) if now.get(n)!=source[name].get(n)]
    save(args.output/'source-check.json',changed)
    return 0 if not any(changed.values()) else 1


if __name__=='__main__':
    raise SystemExit(main())
