#!/usr/bin/env python3
"""Reconstruct generic native delivery trials from frozen inputs and receipts.

Posthoc rechecks never rescue a missing in-budget final, check, or terminal.
Bare host has business acceptance only; goal-loop additionally owes audit/Gate.
"""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

spec=importlib.util.spec_from_file_location('delivery_records',Path(__file__).with_name('evaluate_delivery.py'))
records=importlib.util.module_from_spec(spec);spec.loader.exec_module(records)
read,sha,tree=records.read,records.sha,records.tree


def require(value, message):
    if not value:raise RuntimeError(message)


def text(message):
    return '\n'.join(v.get('text','') for v in message.get('content',[]) if v.get('type') in ('text','output_text'))


def timestamp(value):
    return datetime.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()


def protocol_lookup(call):
    value=call.get('input','')+call.get('arguments','')
    return ('SKILL.md' in value or 'references/' in value or
            ('scripts/goal_' in value and any(k in value for k in
                ('cat ', 'sed ', 'rg ', 'head ', 'read_text', '--help', '"Read"'))))


def classify(protocol, manifest, report, events, status):
    """Only original receipts affect original qualification, including final time."""
    bare=manifest['variant']=='bare'
    required={'independent'} if bare else {'independent','audit','gate'}
    settings=[v['payload'] for v in events if v['type']=='turn_context']
    require(settings and all(v.get('model')==protocol['model'] and v.get('effort')==protocol['effort'] for v in settings),
            'model/effort differs or unknown')
    identities=[v['payload'].get('id') for v in events if v['type']=='session_meta']
    require(identities==[report['session']], 'native session identity differs')
    finals=[v for v in events if v['type']=='response_item' and v['payload'].get('type')=='message'
            and v['payload'].get('role')=='assistant' and v['payload'].get('phase')=='final_answer' and text(v['payload']).strip()]
    normal=bool(finals) and timestamp(finals[-1]['timestamp'])<=manifest['execution_deadline_epoch'] and status=='completed'
    checks=report['checks']
    passed=set(checks)==required and all(v.get('result')==0 and
        manifest['entry']<=v.get('started',-1)<=v.get('finished',float('inf'))<=manifest['deadline'] for v in checks.values())
    if passed and not bare:
        require('GATE: GO ' in checks['gate']['stdout'], 'missing original GO receipt')
    calls=[v['payload'] for v in events if v['type']=='response_item' and v['payload'].get('type') in ('function_call','custom_tool_call')]
    require(not any('spawn_agent' in v.get('name','') or 'spawn_agent' in v.get('input','') or
                    'create_thread' in v.get('input','') for v in calls), 'unbudgeted internal worker')
    return dict(qualified=normal and passed and report['finished']<=manifest['deadline'], normal_final=normal,
                checks_passed=passed, tool_calls=len(calls),
                protocol_lookup_calls=sum(protocol_lookup(v) for v in calls),
                failures=int(not(normal and passed)), seconds=report['finished']-manifest['entry'])


def verify(root, replay=True):
    protocol=read(root/'protocol.json')
    require(protocol['version']==2 and 0<len(protocol['order'])<=protocol['maximum_positions']<=8, 'invalid bounded protocol')
    require(len(protocol['order'])==protocol['scheduled_positions'], 'scheduled positions changed')
    require(0<protocol['execution_seconds']<protocol['seconds']<=360, 'invalid budget')
    require(tree(root/'frozen')==protocol['frozen'], 'frozen evaluator/task bytes changed')
    for variant, expected in protocol['source'].items():
        require(tree(root/'sources'/variant)==expected, 'source changed: '+variant)
    rows=[]
    for planned in protocol['order']:
        folder=root/str(planned['position'])
        require((folder/'report.json').exists(), 'missing scheduled position; do not drop failures')
        manifest=read(folder/'manifest.json'); report=read(folder/'report.json')
        require(all(manifest[k]==v for k,v in planned.items()), 'position identity differs')
        require(manifest['protocol_sha256']==sha(root/'protocol.json'), 'protocol changed after begin')
        require(manifest['deadline']==manifest['entry']+protocol['seconds'] and
                manifest['execution_deadline']==manifest['entry']+protocol['execution_seconds'], 'position budget changed')
        require(sha(folder/'events.jsonl')==report['events_sha256'], 'filtered native events changed')
        case=next(v for v in protocol['cases'] if v['id']==planned['case'])
        for name in ('TASK.md','public.py'):
            require(sha(folder/'work'/name)==case['inputs'][name]['sha256'], 'business acceptance input changed')
        # Host tool receipt is independently captured by the controller, never
        # inferred from the worker's final prose or a work-plan tick.
        terminal=read(folder/'host-terminal.json')
        agents=terminal['agents']
        matching=[v for v in agents if v['agent_name']=='/root/delivery_'+str(planned['position'])]
        require(len(matching)==1, 'missing/ambiguous native terminal')
        status=matching[0]['agent_status']
        if isinstance(status,dict):status=next(iter(status))
        require(status in ('completed','error','cancelled','interrupted','shutdown'), 'worker still active or terminal unknown')
        events=[json.loads(v) for v in (folder/'events.jsonl').read_text().splitlines()]
        result=classify(protocol,manifest,report,events,status)
        rechecks={}
        if replay:
            commands=[('independent',[sys.executable,'-B',str(root/'frozen/grade.py'),'--project',str(folder/'work'),
                       '--family',manifest['family'],'--seed',str(manifest['seed'])])]
            if planned['variant']!='bare':
                commands += [(name,['bash',str(root/'sources'/planned['variant']/'scripts'/script),*args,
                                    '--project',str(folder/'work')]) for name,script,args in
                             [('audit','goal_audit.sh',[]),('gate','goal_gate.sh',['--check'])]]
            for name,command in commands:
                done=subprocess.run(command,cwd=folder/'work',capture_output=True,text=True,timeout=15)
                rechecks[name]=dict(result=done.returncode,stdout=done.stdout,stderr=done.stderr)
            if result['qualified']:
                require(all(v['result']==0 for v in rechecks.values()), 'recorded delivery fails independent replay')
        rows.append(dict(**planned,**result,status=status,posthoc=rechecks,human_interventions=report['human_interventions'],
                         tokens=None,money=None,server_compute=None))
    totals={}
    for variant in sorted({v['variant'] for v in rows}):
        subset=[v for v in rows if v['variant']==variant]; count=sum(v['qualified'] for v in subset); cost=sum(v['seconds'] for v in subset)
        totals[variant]=dict(attempts=len(subset),qualified=count,normal_finals=sum(v['normal_final'] for v in subset),
            failed=sum(not v['qualified'] for v in subset),all_attempt_wall_seconds=cost,
            wall_seconds_per_qualified=cost/count if count else None,
            protocol_lookup_calls=sum(v['protocol_lookup_calls'] for v in subset),
            tool_calls=sum(v['tool_calls'] for v in subset),human_interventions=sum(v['human_interventions'] for v in subset),
            tokens=None,money=None,server_compute=None)
    return dict(verified=True,scope=protocol['inferential_scope'],rows=rows,totals=totals)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args();result=verify(a.root)
    if a.output:records.save(a.output,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
