#!/usr/bin/env python3
"""Prepare/collect native-host trials. This devtool never creates a model client.

The controller uses the host's spawn/list/interrupt tools between begin and
finish. Raw host receipts and a filtered native transcript remain auditable.
Legacy evaluate_entry.py remains a distinct, fixed comparison B.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+'\n')


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(path):
    return {str(p.relative_to(path)): dict(sha256=sha(p), mode=p.stat().st_mode & 0o777)
            for p in sorted(path.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts}


def load(path):
    spec = importlib.util.spec_from_file_location('delivery_tasks', path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def freeze(output, current, candidate):
    output.mkdir(parents=True, exist_ok=False)
    sources = output/'sources'; sources.mkdir()
    for name, path in [('current', current), ('candidate', candidate)]:
        shutil.copytree(path, sources/name, ignore=shutil.ignore_patterns('__pycache__', '.git'))
    frozen = output/'frozen'; frozen.mkdir()
    for name in ('tasks.py', 'grade.py'):
        shutil.copy2(ROOT/'examples/agent-evals'/name, frozen/name)
    for name in ('evaluate_delivery.py', 'verify_delivery.py'):
        shutil.copy2(ROOT/'devtools'/name, frozen/name)
    tasks = load(frozen/'tasks.py')
    cases = [dict(id='development-small', family='small', seed=131101, split='development'),
             dict(id='holdout-medium', family='medium', seed=131102, split='holdout')]
    for case in cases:
        tasks.prepare(frozen/case['id'], case['family'], case['seed'])
        case['inputs'] = tree(frozen/case['id'])
    order = [(cases[0]['id'], v) for v in ('bare', 'current', 'candidate')]
    order += [(cases[1]['id'], v) for v in ('candidate', 'current', 'bare')]
    protocol = dict(version=2, backend='codex-native', model='gpt-6.1-sol', effort='max',
        primary='A: bare host serial versus frozen accbe9a goal-loop',
        secondary='B: same current observations versus brief presentation; shared controls, not independent samples',
        hypotheses=dict(A='The extra contract/settlement cost may buy complete delivery on the multi-file case, but may cost more on the small case.',
                        B='Hiding redundant presentation reduces all-attempt qualified-delivery wall cost by at least 20% without losing either delivery.'),
        learning='C not scheduled: screen incremental action before spending utility slots',
        cases=cases, order=[dict(position=i, case=c, variant=v) for i, (c,v) in enumerate(order,1)],
        maximum_positions=8, scheduled_positions=6, seconds=360, execution_seconds=330,
        verification_reserve_seconds=30, worker_concurrency=1, internal_workers=0,
        permission='inherited host; no overrides', context='fork_turns=none; no tuning conversation',
        success='independent business check + normal nonempty final within budget; goal-loop also original audit/Gate',
        meaningful_gain='no lost qualified deliveries and >=20% lower all-attempt wall per qualified delivery on both cases',
        stop='source/model/effort drift or two consecutive infrastructure failures; retain all attempts; no retries or replacement seeds',
        inferential_scope='two task instances; descriptive only, no statistical or transfer claim',
        frozen=tree(frozen), source={v:tree(sources/v) for v in ('current','candidate')},
        research_costs='separate; missing time/tokens/money unknown, never zero',
        proposed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), tokens=None, money=None)
    save(output/'protocol.json', protocol)
    return dict(protocol_sha256=sha(output/'protocol.json'), output=str(output))


def begin(root, position):
    entry, epoch = time.monotonic(), time.time()
    protocol = read(root/'protocol.json')
    row = next((r for r in protocol['order'] if r['position'] == position), None)
    if row is None:
        raise ValueError('invalid position')
    folder = root/str(position); folder.mkdir(exist_ok=False)
    case = next(c for c in protocol['cases'] if c['id'] == row['case'])
    shutil.copytree(root/'frozen'/case['id'], folder/'work')
    manifest = dict(**row, family=case['family'], seed=case['seed'], split=case['split'], entry=entry, epoch=epoch,
        deadline=entry+protocol['seconds'], execution_deadline=entry+protocol['execution_seconds'],
        execution_deadline_epoch=epoch+protocol['execution_seconds'],
        started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), protocol_sha256=sha(root/'protocol.json'))
    save(folder/'manifest.json', manifest)
    skill = root/'sources'/row['variant']
    common = (f'Complete TASK.md in {folder/"work"}. Read TASK.md and public.py there. '
        'Use serial execution, no subagents or other model clients. Use only local host tools; '
        'no network, installs, global changes, permission changes, or access to other trials, frozen graders, or answers. '
        'Only edit the deliverable paths allowed by TASK.md and optional tests in that project. '
        f'All work and a normal final report must end before Unix time {manifest["execution_deadline_epoch"]:.6f}; '
        'the remaining 30 seconds are reserved for independent acceptance. '
        'Return a concise final with artifacts, checks and remaining limitations. ')
    if row['variant'] == 'bare':
        prompt = common + 'Use the bare host serial workflow; no goal-loop contracts, ledger, audit or Gate are required.'
    else:
        prompt = common + (f'Use the goal-loop skill at {skill/"SKILL.md"}; read and follow it. '
            'The user authorizes automatic stamping and execution. You may also write this project .goal metadata. '
            f'This native Codex worker identity is /root/delivery_{position}; use that actual identity for explicit '
            'host begin if no prompt receipt exists. Include protocol lookup, implementation, settlement and a fresh '
            'original audit/Gate in the same deadline. No other repository may be modified.')
    (folder/'prompt.txt').write_text(prompt+'\n')
    return dict(position=position, prompt=prompt, execution_deadline=manifest['execution_deadline'], folder=str(folder))


def redact(text):
    text = re.sub(r'(?i)(authorization["\s:=]+bearer\s+)\S+', r'\1[REDACTED]', text)
    return re.sub(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,})\b', '[REDACTED]', text)


def transcript(source, target):
    """Allowlist tool calls/results, final text and settings. Never save reasoning."""
    rows=[]
    for line in source.read_text().splitlines():
        value=json.loads(line); kind=value.get('type'); payload=value.get('payload', {})
        keep=False
        if kind=='session_meta':
            payload={k:payload[k] for k in ('id','timestamp','cwd','source') if k in payload}; keep=True
        elif kind=='turn_context':
            payload={k:payload[k] for k in ('model','effort','approval_policy','sandbox_policy') if k in payload}; keep=True
        elif kind=='response_item':
            keep=payload.get('type') in ('function_call','function_call_output','custom_tool_call','custom_tool_call_output')
            if payload.get('type')=='message' and payload.get('role')=='assistant':
                keep=payload.get('phase')=='final_answer'
        elif kind=='event_msg' and payload.get('type') in ('task_started','task_complete','turn_aborted'):
            keep=True
        if keep:
            rows.append(dict(timestamp=value.get('timestamp'), type=kind, payload=payload))
    target.write_text(''.join(redact(json.dumps(row,ensure_ascii=False))+'\n' for row in rows))
    return rows


def finish(root, position, session):
    folder=root/str(position); manifest=read(folder/'manifest.json'); protocol=read(root/'protocol.json')
    if (folder/'report.json').exists():
        raise ValueError('position already collected; no replacement attempts')
    source=list((Path.home()/'.codex/sessions').rglob('*'+session+'.jsonl'))
    if len(source)!=1:
        raise ValueError('native transcript identity missing or ambiguous')
    transcript(source[0],folder/'events.jsonl')
    checks={}; variant=manifest['variant']; work=folder/'work'
    commands=[('independent',[sys.executable,'-B',str(root/'frozen/grade.py'),'--project',str(work),
                             '--family',manifest['family'],'--seed',str(manifest['seed'])])]
    if variant!='bare':
        commands += [(n,['bash',str(root/'sources'/variant/'scripts'/s),*a,'--project',str(work)])
                     for n,s,a in [('audit','goal_audit.sh',[]),('gate','goal_gate.sh',['--check'])]]
    for name,cmd in commands:
        start=time.monotonic()
        if start>=manifest['deadline']:
            checks[name]=dict(result=None,reason='original deadline expired');continue
        try:
            env=dict(os.environ,GOAL_RUNNER_MONOTONIC_END=str(manifest['deadline']))
            done=subprocess.run(cmd,cwd=work,env=env,capture_output=True,text=True,timeout=manifest['deadline']-start)
            checks[name]=dict(command=cmd,result=done.returncode,stdout=redact(done.stdout),stderr=redact(done.stderr),
                              started=start,finished=time.monotonic())
        except subprocess.TimeoutExpired:
            checks[name]=dict(result=None,reason='verification timeout',started=start,finished=time.monotonic())
    report=dict(session=session, checks=checks, finished=time.monotonic(),
        events_sha256=sha(folder/'events.jsonl'), artifacts=tree(work),
        human_interventions=0, human_intervention_basis='one frozen prompt; no followup to evaluation worker',
        internal_worker_calls=0, internal_worker_seconds=0, tokens=None, money=None, server_compute=None,
        cleanup='native terminal receipt required; local artifact checks do not prove service-side cancellation')
    save(folder/'report.json', report)
    return dict(position=position,seconds=report['finished']-manifest['entry'],checks={k:v['result'] for k,v in checks.items()})


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='action',required=True)
    f=sub.add_parser('freeze'); f.add_argument('output',type=Path); f.add_argument('--current',type=Path,required=True); f.add_argument('--candidate',type=Path,required=True)
    for action in ('begin','finish'):
        s=sub.add_parser(action); s.add_argument('root',type=Path); s.add_argument('position',type=int)
        if action=='finish':s.add_argument('--session',required=True)
    a=p.parse_args()
    result=freeze(a.output,a.current,a.candidate) if a.action=='freeze' else begin(a.root,a.position) if a.action=='begin' else finish(a.root,a.position,a.session)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
