"""Audit native fork/model/permission/input identities, without copying thinking."""
import argparse
import hashlib
import json
from pathlib import Path


def require(value,message):
    if not value:raise RuntimeError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def audit(workspace,parent):
    launches={}
    for line in parent.read_text().splitlines():
        event=json.loads(line);p=event.get('payload',{})
        if p.get('type')=='function_call' and p.get('name')=='spawn_agent' and p.get('namespace')=='collaboration':
            args=json.loads(p['arguments'])
            if args['task_name'].startswith('delivery_'):launches[args['task_name']]=dict(timestamp=event['timestamp'],args=args)
    rows=[]
    for cohort in ('native','validation'):
        root=workspace/cohort;protocol=json.loads((root/'protocol.json').read_text())
        for row in protocol['order']:
            folder=root/str(row['position']);report=json.loads((folder/'report.json').read_text())
            name='delivery_'+str(row['position']);launch=launches[name];args=launch['args']
            require(args.get('fork_turns')=='none' and not any(k in args for k in ('model','reasoning_effort')), 'fork/override differs')
            expected_prompt=(folder/'prompt.txt').read_text().strip()
            encrypted=args['message'].startswith('gAAAA')
            if not encrypted:
                require(args['message']==expected_prompt,'launched prompt differs from frozen prompt')
            candidates=list((Path.home()/'.codex/sessions').rglob('*'+report['session']+'.jsonl'))
            require(len(candidates)==1,'native session identity ambiguous')
            meta=settings=tools=None
            for line in candidates[0].read_text().splitlines():
                event=json.loads(line);p=event.get('payload',{})
                if event['type']=='session_meta':meta=p
                if event['type']=='turn_context':settings={k:p.get(k) for k in ('model','effort','approval_policy','sandbox_policy')}
                if event['type']=='response_item' and p.get('type')=='additional_tools':tools=p.get('tools')
            require(meta['source']['subagent']['thread_spawn']['agent_path']=='/root/'+name,'native agent relation differs')
            require(settings['model']==protocol['model'] and settings['effort']==protocol['effort'],'model or effort differs')
            require(settings['approval_policy']=='never' and settings['sandbox_policy']=={'type':'danger-full-access'},'permission state differs')
            require(tools is not None,'tool catalog not observed')
            filtered=[json.loads(x) for x in (folder/'events.jsonl').read_text().splitlines()]
            require(all(e['payload'].get('type')!='reasoning' for e in filtered),'thinking retained')
            calls=[e['payload'].get('input',e['payload'].get('arguments','')) for e in filtered if e['payload'].get('type') in ('custom_tool_call','function_call')]
            require(not any('agent-evals/grade.py' in c or '/frozen/grade.py' in c for c in calls),'worker accessed frozen grader')
            expected={k:v for k,v in report['artifacts'].items() if not k.startswith('.goal/')}
            actual={str(f.relative_to(folder/'work')):dict(sha256=hashlib.sha256(f.read_bytes()).hexdigest(),mode=f.stat().st_mode&0o777)
                    for f in (folder/'work').rglob('*') if f.is_file() and '__pycache__' not in f.parts and '.goal' not in f.relative_to(folder/'work').parts}
            require(actual==expected,'business artifact bytes/modes changed after original collection')
            rows.append(dict(position=row['position'],cohort=cohort,session=report['session'],launch_timestamp=launch['timestamp'],
                frozen_prompt_sha256=hashlib.sha256(expected_prompt.encode()).hexdigest(),fork_turns='none',
                native_prompt_at_rest_encrypted=encrypted,
                transport_plaintext_equality_verified=None if encrypted else True,
                parent_thread_id=meta['source']['subagent']['thread_spawn']['parent_thread_id'],
                settings=settings,tool_catalog_sha256=digest(tools),thinking_saved=False,explicit_grader_access=False,
                business_artifacts_match_original_collection=True))
    require(len(rows)==8,'global position budget differs')
    require(len({row['tool_catalog_sha256'] for row in rows})==1,'tool capability catalog differs')
    require(len({row['parent_thread_id'] for row in rows})==1,'native parent differs')
    return dict(verified=True,positions=rows,scope='host-exposed native identities, artifacts and explicit grader access; encrypted native prompt bodies cannot independently establish plaintext transport equality; no unavailable service-compute claim')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('workspace',type=Path);p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=audit(a.workspace,a.parent);a.output.write_text(json.dumps(result,indent=2)+'\n');print('native launch audit verified')
