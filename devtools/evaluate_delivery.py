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

sys.dont_write_bytecode = True

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


def copy_source(source, target, exclude_evaluation=False):
    manifest = source/'assets/install-files.json'
    if not manifest.exists():
        def ignored(folder,names):
            result={name for name in names if name in ('__pycache__','.git')}
            if exclude_evaluation and Path(folder).resolve()==(source/'examples').resolve():
                result.add('agent-evals')
            return result
        shutil.copytree(source, target, ignore=ignored)
        return
    names = read(manifest)
    if (not isinstance(names, list) or not names or not all(isinstance(name,str) for name in names)
            or len(names)!=len(set(names))):
        raise ValueError('invalid source runtime inventory')
    for name in names:
        if (not isinstance(name,str) or Path(name).is_absolute() or '..' in Path(name).parts
                or not (source/name).is_file() or not (source/name).resolve().is_relative_to(source.resolve())):
            raise ValueError('invalid/escaping source runtime file')
    if exclude_evaluation:
        names=[name for name in names if not name.startswith('examples/agent-evals/')]
    target.mkdir()
    for name in names:
        path=target/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/name,path)


def freeze(output, current, candidate, config=None):
    if config is not None:
        families, instances = config['families'], config['instances']
        if (not families or len(families)!=len(set(families)) or set(families)-{'small','medium','optimization','recovery'}
                or type(instances) is not int or not 1<=instances<=6 or type(config['seed_base']) is not int
                or not isinstance(config['model'],str) or not config['model'].strip()
                or config['effort'] not in ('low','medium','high','xhigh','max','ultra')
                or type(config['seconds']) is not int or type(config['execution_seconds']) is not int
                or not 0<config['execution_seconds']<config['seconds']<=600):
            raise ValueError('invalid fixed cohort configuration')
    output.mkdir(parents=True, exist_ok=False)
    sources = output/'sources'; sources.mkdir()
    for name, path in [('current', current), ('candidate', candidate)]:
        if path is not None:
            copy_source(path, sources/name,exclude_evaluation=config is not None)
    frozen = output/'frozen'; frozen.mkdir()
    for name in ('tasks.py', 'grade.py'):
        shutil.copy2(ROOT/'examples/agent-evals'/name, frozen/name)
    for name in ('evaluate_delivery.py', 'verify_delivery.py', 'delivery_metrics.py'):
        shutil.copy2(ROOT/'devtools'/name, frozen/name)
    if config is not None:
        harness=frozen/'native-harness'
        for name in ('devtools/native_eval_capture.py','scripts/goal_bounded.py',
                     'scripts/goal_owner_watch.py','scripts/goal_trace.py'):
            target=harness/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/name,target)
    tasks = load(frozen/'tasks.py')
    cases = [dict(id='development-small', family='small', seed=131101, split='development'),
             dict(id='holdout-medium', family='medium', seed=131102, split='holdout')]
    if config is not None:
        cases=[dict(id=family+'-'+str(index+1),family=family,
                    seed=config['seed_base']+family_index*1000+index,split='evaluation')
               for family_index,family in enumerate(config['families']) for index in range(config['instances'])]
    for case in cases:
        tasks.prepare(frozen/case['id'], case['family'], case['seed'])
        case['inputs'] = tree(frozen/case['id'])
    if config is None:
        order = [(cases[0]['id'], v) for v in ('bare', 'current', 'candidate')]
        order += [(cases[1]['id'], v) for v in ('candidate', 'current', 'bare')]
    else:
        variants=['bare','current']+(['candidate'] if candidate is not None else [])
        order=[]
        for index,case in enumerate(cases):
            offset=index%len(variants)
            order += [(case['id'],v) for v in variants[offset:]+variants[:offset]]
    protocol = dict(version=2, backend='codex-native', model='gpt-6.1-sol', effort='max',
        primary='bare host serial versus the exact frozen current source',
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
        frozen=tree(frozen), source={v:tree(sources/v) for v in ('current','candidate') if (sources/v).exists()},
        research_costs='separate; missing time/tokens/money unknown, never zero',
        proposed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), tokens=None, money=None)
    if config is not None:
        protocol.update(version=3,model=config['model'],effort=config['effort'],cases=cases,
            seconds=config['seconds'],execution_seconds=config['execution_seconds'],
            verification_reserve_seconds=config['seconds']-config['execution_seconds'],
            maximum_positions=len(order),scheduled_positions=len(order),
            minimum_pairs=3,minimum_cost_gain=.2,
            evidence_kind='calibration-fixture' if config.get('calibration') else 'live-native',
            secondary='optional candidate versus current on the same cases',
            inferential_scope='fixed model, budget and matched task seeds; descriptive cohort only',
            maximum_scheduled_wall_seconds=len(order)*config['seconds'])
        protocol.update(hypotheses=dict(primary='Goal-loop may change qualified delivery and whole-attempt cost versus bare serial execution.',
                        candidate='An optional candidate must retain every baseline delivery while reducing whole-attempt cost.'),
            meaningful_gain='At least three pairs per declared family, no lost paired deliveries, and >=20% lower all-attempt wall per qualified delivery.',
            learning='No independent learning-effect claim; ablations require a separate frozen protocol.')
        protocol['source_exclusions']=['examples/agent-evals/** (independent evaluation material)']
        spec=importlib.util.spec_from_file_location('cohort_state_policy',ROOT/'scripts/goal_store.py')
        state_policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(state_policy)
        protocol['posthoc_observations']={'.goal/'+name:field.append_pattern
            for name,field in state_policy.STATE_FIELDS.items() if field.append_pattern is not None}
    save(output/'protocol.json', protocol)
    return dict(protocol_sha256=sha(output/'protocol.json'), output=str(output))


def begin(root, position, agent_path=None):
    entry, epoch = time.monotonic(), time.time()
    protocol = read(root/'protocol.json')
    if protocol['version']==3:
        raise ValueError('cohort v3 requires capture before native dispatch; wait for ready.json and prompt.txt')
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
        f'The remaining {protocol["verification_reserve_seconds"]} seconds are reserved for independent acceptance. '
        'Return a concise final with artifacts, checks and remaining limitations. ')
    if row['variant'] == 'bare':
        prompt = common + 'Use the bare host serial workflow; no goal-loop contracts, ledger, audit or Gate are required.'
    else:
        prompt = common + (f'Use the goal-loop skill at {skill/"SKILL.md"}; read and follow it. '
            'The user authorizes automatic stamping and execution. You may also write this project .goal metadata. '
            'Bind goal-loop only to the actual backend/session exposed by the host; do not invent a session from '
            'the trial position or replace the original request. Include protocol lookup, implementation, settlement and a fresh '
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


def finish(root, position, session, accounting=None, human_interventions=None):
    folder=root/str(position); manifest=read(folder/'manifest.json'); protocol=read(root/'protocol.json')
    if protocol['version']==3:
        raise ValueError('cohort v3 uses the independent capture/report.json; do not recollect posthoc')
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
        human_interventions=human_interventions, human_intervention_basis='explicit controller observation; missing is unknown',
        internal_worker_calls=0, internal_worker_seconds=0, tokens=None, money=None, server_compute=None,
        cleanup='native terminal receipt required; local artifact checks do not prove service-side cancellation')
    if accounting is not None:
        metrics=load(Path(__file__).with_name('delivery_metrics.py'))
        metrics.accounting(read(accounting),protocol['model'],session)
        shutil.copy2(accounting,folder/'host-accounting.json')
        report['accounting_sha256']=sha(folder/'host-accounting.json')
    save(folder/'report.json', report)
    return dict(position=position,seconds=report['finished']-manifest['entry'],checks={k:v['result'] for k,v in checks.items()})


def native_capture(root, position, agent_path, parent_thread, sessions_root=None):
    """Serial independent observer; dispatch remains an explicit host action."""
    entry,entry_epoch=time.monotonic(),time.time()
    root=root.resolve();protocol=read(root/'protocol.json')
    if protocol['version']!=3:
        raise ValueError('capture requires a v3 matched cohort')
    if (tree(root/'frozen')!=protocol['frozen'] or
            any(tree(root/'sources'/variant)!=expected for variant,expected in protocol['source'].items())):
        raise ValueError('frozen evaluator/source changed; stop before dispatch')
    row=next((r for r in protocol['order'] if r['position']==position),None)
    if row is None:
        raise ValueError('invalid position')
    infrastructure_failures=0
    for previous in protocol['order']:
        if previous['position']>=position:continue
        folder=root/str(previous['position'])
        if not all((folder/name).is_file() for name in ('manifest.json','capture/report.json','host-terminal.json')):
            raise ValueError('serial cohort: collect previous attempt and native terminal first')
        prior=read(folder/'manifest.json')
        observed=read(folder/'capture/report.json')
        if observed.get('settings_drift'):
            raise ValueError('model/effort drift in previous attempt; stop this cohort')
        terminal=read(folder/'host-terminal.json')
        matches=[r for r in terminal['agents'] if r.get('agent_name')==prior['agent_path']]
        if (len(matches)!=1
                or matches[0].get('agent_status') not in ('completed','error','cancelled','interrupted','shutdown')):
            raise ValueError('serial cohort needs actual previous native terminals')
        infrastructure_failures=infrastructure_failures+1 if not observed.get('session_id') else 0
    if infrastructure_failures>=2:
        raise ValueError('two consecutive infrastructure failures; retain this cohort and stop dispatch')
    case=next(c for c in protocol['cases'] if c['id']==row['case'])
    folder=root/str(position);folder.mkdir(exist_ok=False)
    manifest=dict(**row,family=case['family'],seed=case['seed'],split=case['split'],
                  protocol_sha256=sha(root/'protocol.json'),agent_path=agent_path,
                  entry=entry,entry_epoch=entry_epoch)
    save(folder/'manifest.json',manifest)
    native=load(root/'frozen/native-harness/devtools/native_eval_capture.py')
    work=folder/'work'
    checks=[dict(name='independent',argv=[sys.executable,'-B',str(root/'frozen/grade.py'),
                '--project',str(work),'--family',case['family'],'--seed',str(case['seed'])],cwd=str(work))]
    if row['variant']!='bare':
        checks += [dict(name=name,argv=['bash',str(root/'sources'/row['variant']/'scripts'/script),
                    *args,'--project',str(work)],cwd=str(work)) for name,script,args in
                    [('audit','goal_audit.sh',[]),('gate','goal_gate.sh',['--check'])]]
    tasks=load(root/'frozen/tasks.py')
    mutable=set(tasks.STARTERS[case['family']])|{'BENCHMARK.md','seed-data/output.jsonl','seed-data/state.json'}
    frozen=[root/'protocol.json',root/'frozen',root/'frozen'/case['id'],root/'sources',folder/'manifest.json']
    capture_manifest=dict(version=1,position=position,group=row['variant'],goal_loop=row['variant']!='bare',
        agent_path=agent_path,parent_thread_id=parent_thread,model=protocol['model'],effort=protocol['effort'],
        seconds=protocol['seconds'],execution_seconds=protocol['execution_seconds'],max_internal_workers=0,
        initial_workspace=str(root/'frozen'/case['id']),work=str(work),
        immutable_inputs=sorted(set(case['inputs'])-mutable),
        frozen={str(p):native.fingerprint(p) for p in frozen},artifacts=[str(work)],checks=checks)
    path=folder/'capture-manifest.json';save(path,capture_manifest)

    class TrialCapture(native.Capture):
        def prepare(self):
            super().prepare()
            prompt=(f'Complete TASK.md in {work}. Read TASK.md and public.py. Use serial execution, '
                'no subagents, model clients, network, installs, global/permission changes, or access to '
                'other trials, frozen graders or answers. Edit only the deliverable paths allowed by '
                f'TASK.md and optional local tests. Return a normal nonempty final before Unix time '
                f'{self.execution_deadline_epoch:.6f}. Independent acceptance shares the original '
                f'{protocol["seconds"]}-second outer allowance, including setup and dispatch. ')
            if row['variant']=='bare':
                prompt+='Use the ordinary implement/test/fix workflow.'
            else:
                prompt+=(f'Follow {root/"sources"/row["variant"]/"SKILL.md"}. Automatic contract approval '
                    'is authorized for this trial. You may also write .goal metadata. Use the actual '
                    'host backend/session; never invent identity from the trial number. Include protocol '
                    'reading, implementation, settlement and fresh original audit/Gate within the deadline.')
            (folder/'prompt.txt').write_text(prompt+'\n')
    observer=TrialCapture(path,native.sha(path),folder/'capture',sessions_root)
    # Charge metadata/fingerprint setup as well as workspace copying and
    # dispatch to the one outer deadline. These are actual observed clocks.
    observer.entry,observer.entry_epoch=entry,entry_epoch
    observer.deadline=observer.execution_deadline=entry
    observer.deadline_epoch=observer.execution_deadline_epoch=entry_epoch
    report=observer.run()
    return dict(position=position,qualified=report['qualified'],reasons=report['reasons'],folder=str(folder))


def attach_accounting(root, position, receipt, human_interventions=None):
    folder=root/str(position);protocol=read(root/'protocol.json')
    capture=read(folder/'capture/report.json')
    metrics=load(Path(__file__).with_name('delivery_metrics.py'))
    value=read(receipt)
    metrics.accounting(value,protocol['model'],capture['session_id'])
    if (folder/'accounting.json').exists() or (folder/'host-accounting.json').exists():
        raise ValueError('accounting already attached; retain original receipts')
    if human_interventions is not None:
        metrics.number(human_interventions,'human interventions',integer=True)
    shutil.copy2(receipt,folder/'host-accounting.json')
    save(folder/'accounting.json',dict(human_interventions=human_interventions,
                                     receipt_sha256=sha(folder/'host-accounting.json')))
    return dict(position=position,attached=True)


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='action',required=True)
    f=sub.add_parser('freeze'); f.add_argument('output',type=Path); f.add_argument('--current',type=Path,required=True); f.add_argument('--candidate',type=Path,required=True)
    c=sub.add_parser('cohort');c.add_argument('output',type=Path);c.add_argument('--current',type=Path,required=True);c.add_argument('--candidate',type=Path)
    c.add_argument('--model',required=True);c.add_argument('--effort',required=True)
    c.add_argument('--families',nargs='+',default=['small','medium','optimization','recovery'])
    c.add_argument('--instances',type=int,default=3);c.add_argument('--seed-base',type=int,required=True)
    c.add_argument('--seconds',type=int,default=360);c.add_argument('--execution-seconds',type=int,default=330)
    c.add_argument('--calibration',action='store_true',help='synthetic fixtures; ineligible for model utility conclusions')
    capture=sub.add_parser('capture');capture.add_argument('root',type=Path);capture.add_argument('position',type=int)
    capture.add_argument('--agent-path',required=True);capture.add_argument('--parent-thread',required=True)
    capture.add_argument('--sessions-root',type=Path)
    accounting=sub.add_parser('accounting');accounting.add_argument('root',type=Path);accounting.add_argument('position',type=int)
    accounting.add_argument('receipt',type=Path);accounting.add_argument('--human-interventions',type=int)
    for action in ('begin','finish'):
        s=sub.add_parser(action); s.add_argument('root',type=Path); s.add_argument('position',type=int)
        if action=='begin':s.add_argument('--agent-path')
        if action=='finish':
            s.add_argument('--session',required=True);s.add_argument('--accounting',type=Path)
            s.add_argument('--human-interventions',type=int)
    a=p.parse_args()
    if a.action=='capture':result=native_capture(a.root,a.position,a.agent_path,a.parent_thread,a.sessions_root)
    elif a.action=='accounting':result=attach_accounting(a.root,a.position,a.receipt,a.human_interventions)
    elif a.action=='cohort':
        config={k:getattr(a,k) for k in ('model','effort','families','instances','seed_base','seconds','execution_seconds','calibration')}
        result=freeze(a.output,a.current,a.candidate,config)
    elif a.action=='freeze':result=freeze(a.output,a.current,a.candidate)
    elif a.action=='begin':result=begin(a.root,a.position,a.agent_path)
    else:result=finish(a.root,a.position,a.session,a.accounting,a.human_interventions)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
