#!/usr/bin/env python3
"""Read retained short-READY/Write-fence canary evidence; execute no task code."""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import shlex
import stat


def require(value, message):
    if not value:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def sealed(path):
    value=load(path)
    require(sha(encoded(value['payload']))==value['sha256'],'receipt checksum: '+str(path))
    return value['payload']


def inventory(base):
    files={}
    for p in sorted(base.rglob('*')):
        require(not p.is_symlink(),'unexpected symlink: '+str(p))
        if p.is_file():
            files[str(p.relative_to(base))]=dict(bytes=p.stat().st_size,mode=stat.S_IMODE(p.stat().st_mode),sha256=sha(p.read_bytes()))
    return files


def inspect(base):
    before=inventory(base)
    manifest,report,briefs,events=(load(base/n) for n in ('manifest.json','report.json','briefs.json','events.json'))
    state=base/'work/.goal';work=state.parent;control=base/'control'
    receipts={str(p.relative_to(state)):sealed(p) for kind in ('host','runtime','crew')
              for p in sorted((state/'evidence'/kind).glob('*.json'))}
    attempts=[v for n,v in receipts.items() if n.startswith('evidence/host/attempt-')]
    spans=[v for n,v in receipts.items() if n.startswith('evidence/runtime/')]
    waves=[v for n,v in receipts.items() if n.startswith('evidence/crew/')]
    require(len(attempts)==2 and len(waves)==1,'two actual tickets and one wave')
    attempts.sort(key=lambda a:a['task']);wave=waves[0]
    require(wave==report['wave'] and report['result']==0 and report['error'] is None,'CLI/wave outcome')
    require(wave['observer_transport']=='python-api' and wave['trial']=='real-cli-launcher-write-fence','canary identity')
    require(wave['baseline']=={'out1.txt':None,'out2.txt':None},'original absent outputs')
    require(manifest['seconds']==180 and all(e['session_id']==manifest['session'] for e in events),'session/budget')
    for name,value in manifest['sources'].items():
        require(sha((base/'sources'/name).read_bytes())==value,'source identity: '+name)
    require(manifest['sources']['scripts/goal_host.py']=='6cd50115f5e0ac78e89b9287a2475026a6aa9a3db7a2245a4efe9e9d8c2eb060','evaluated host version')
    graph=wave['graph']
    for name,value in graph['instrument_hashes'].items():
        require(sha((control/name).read_bytes())==value,'frozen instrument: '+name)
    require(graph['instrument_hashes']=={
        'grade.py':'8d5a5bec8725a8f69156ac2a4b5d09aa7d3b63749ec53df88bf8be282e3426ca',
        'job_check.py':'c71c3e3894a6bb9dde2c8572f7d01282a12a8bba6392d69d6bbba5a2e2eb4766'},'canary grader bytes')
    inits=[e for e in events if e.get('subtype')=='init']
    require(len(inits)==2 and all(e['claude_code_version']=='999.0.0-local' and e['model']=='MiniMax-M3.1-Flash'
            and e['skills'].count('goal-loop-host:goal-loop')==1 and any(p['name']=='goal-loop-host'
            and p['source']=='goal-loop-host@inline' and p['path']=='/Users/m/repo/goal-loop' for p in e['plugins']) for e in inits),
            'actual runtime/model/namespace')
    require(load(base/'sources/.claude-plugin/plugin.json')['skills']=='./','root skill declaration')
    require('SessionStart' not in load(base/'sources/hooks/hooks.json')['hooks'],'unexpected plugin SessionStart ownership')
    driver=(base/'driver.py').read_text();tree=ast.parse(driver)
    require(isinstance(tree.body[2],ast.Assign) and isinstance(tree.body[2].targets[0],ast.Tuple)
            and [t.id for t in tree.body[2].targets[0].elts]==['ENTRY_MONOTONIC','ENTRY_EPOCH'],
            'driver entry capture before preparation')
    require("started, epoch = ENTRY_MONOTONIC, ENTRY_EPOCH" in driver and
            "os.environ['GOAL_RUNNER_MONOTONIC_END']=str(started+180)" in driver and
            "'--seconds',str(max(0,started+180-time.monotonic()))" in driver and
            "'--deadline-epoch',str(epoch+180)" in driver,'outer entry deadline binding')
    begin,runner=load(base/'begin.json'),load(state/'runner.json')
    cap=manifest['started_monotonic']+180
    require(begin['deadline_monotonic']==runner['monotonic']['deadline']==wave['deadline']==cap,'persisted entry monotonic cap')
    require(all(a['deadline_monotonic']==cap and a['run']==begin['run'] and a['session']==manifest['session'] for a in attempts),
            'ticket deadline/run/session identity')
    prompt=next(v for n,v in receipts.items() if n.startswith('evidence/host/prompt-'))
    require(prompt['origin']==runner['origin'] and prompt['origin']['kind']=='prompt'
            and prompt['origin']['monotonic']>manifest['started_monotonic'],'actual prompt origin')
    chain=[];head=load(state/'store/commits/current')['head'];seen=set()
    while head:
        require(head not in seen,'cyclic store history');seen.add(head)
        p=state/'store/commits/generations'/head;require(sha(p.read_bytes())==head,'generation checksum');v=load(p)
        if 'runner.json' in v['files']:
            r=json.loads(base64.b64decode(v['files']['runner.json']))
            require(r['run']==begin['run'] and r['monotonic']['deadline']==cap,'generation deadline/run')
            chain.append(dict(generation=head,deadline_epoch=r['deadline'],deadline_monotonic=r['monotonic']['deadline']))
        head=v['previous']
    require(chain,'persisted deadline history')
    batches={}
    for index,e in enumerate(events):
        if e['type']=='assistant' and e.get('parent_tool_use_id') is None:
            for c in e['content']:
                if c['type']=='tool_use':
                    require(e['message_id'],'missing real parent message_id')
                    bucket=batches.setdefault(e['message_id'],{})
                    if c['id'] in bucket:
                        require(bucket[c['id']][1]==c,'conflicting stream call')
                    bucket[c['id']]=(index,c)
    require(len(batches)==1,'parent calls not same native message')
    batch=next(iter(batches.values()));calls=[v[1] for v in batch.values()]
    require(len(calls)==2 and all(c['name']=='Agent' and c['input']['subagent_type']=='goal-loop-host:goal-worker'
            and 'model' not in c['input'] and 'effort' not in c['input'] and c['input'].get('run_in_background') is not True
            for c in calls),'two synchronous native Agent calls')
    workers=[]
    for number,(brief,a) in enumerate(zip(briefs,attempts),1):
        name='out'+str(number)+'.txt';forbidden='forbidden-T'+str(number)+'.txt'
        require(a['task']=='T'+str(number) and a['phase']=='returned' and a['ready'] and a['files']==[name],
                'actual returned/READY owned worker')
        require(brief['ticket']==a['id']+':'+a['nonce'] and brief['trace']==a['trace'],'nonce/trace binding')
        call=next(c for c in calls if c['id']==a['call_id'])
        require(call['input']['prompt'].startswith(brief['worker_prefix']),'exact worker prefix')
        starts=[e for e in events if e.get('subtype')=='task_started' and e.get('tool_use_id')==a['call_id']]
        require(len(starts)==1 and starts[0]['task_id']==a['agent_id'],'actual native Agent ID')
        wc=[(i,e,c) for i,e in enumerate(events) if e.get('parent_tool_use_id')==a['call_id']
            for c in e.get('content',[]) if c['type']=='tool_use']
        require(wc[0][2]['name']=='Bash' and wc[0][2]['input']['command']==brief['launcher_command'],'first Bash exact short launcher')
        argv=shlex.split(brief['launcher_command'])
        require(argv[0]=='bash' and len(argv)==2,'short Bash launcher shape')
        launcher=work/Path(argv[1]).relative_to(Path(a['project']))
        require(sha(launcher.read_bytes())==a['ready_launcher_sha256'] and
            launcher.read_bytes()==('#!/bin/sh\nexec '+brief['owned_ready_command']+'\n').encode()
            and stat.S_IMODE(launcher.stat().st_mode)==0o600,'launcher path/nonce/body/SHA/mode binding')
        returns={r['tool_use_id']:(i,e,r) for i,e in enumerate(events) for r in e.get('tool_results',[])}
        require(returns[wc[0][2]['id']][2]['is_error'] is False,'short READY actual tool result')
        negatives=[(i,e,c) for i,e,c in wc if c['name']=='Write' and c['input']['file_path'].endswith('/'+forbidden)]
        require(len(negatives)==1,'one requested Write negative probe per worker')
        ni,ne,nc=negatives[0];ri,re,rr=returns[nc['id']]
        require(nc['input']['content']=='PROBE' and rr['is_error'] is True and not (work/forbidden).exists(),'negative actual error/file absence')
        # Exact event bracket and hook_id, not a timing-proximity association.
        bracket=events[ni+1:ri]
        hs=[e for e in bracket if e.get('subtype')=='hook_started' and e.get('hook_name')=='PreToolUse:Write']
        hr=[e for e in bracket if e.get('subtype')=='hook_response' and e.get('hook_name')=='PreToolUse:Write']
        require(len(hs)==len(hr)==1 and hs[0]['hook_id']==hr[0]['hook_id'],'negative unique hook bracket')
        decision=json.loads(hr[0]['stdout'])['hookSpecificOutput']
        require(decision['permissionDecision']=='deny' and decision['permissionDecisionReason']==
                'goal-loop: structured worker write outside owned scope','negative hook reason')
        require(not any(e.get('hook_event')=='PostToolUse' for e in bracket),'denied Write executed PostToolUse')
        positives=[(i,e,c) for i,e,c in wc if c['name']=='Write' and c['input']['file_path'].endswith('/'+name)]
        require(len(positives)==1,'one legal structured Write per worker')
        pi,pe,pc=positives[0];pri,pre,pr=returns[pc['id']]
        require(pc['input']['content']=='READY\n' and pr.get('is_error') is not True and
                (work/name).read_bytes()==b'READY\n','legal Write input/result/exact six bytes')
        require(wc[0][0]<ni<ri<pi<pri,'READY/negative/positive order')
        checks=[(i,e,c) for i,e,c in wc if c['name']=='Bash' and c['input']['command']==brief['check_command']]
        require(len(checks)==1 and checks[0][0]>pri and returns[checks[0][2]['id']][2]['is_error'] is False,
                'named check actual call/result after legal Write')
        named=[s for s in spans if s['label']=='host-worker-check' and s.get('parent')==a['trace']]
        require(named and all(s['state']=='complete' and s['result']==0 for s in named),'named check sealed runtime')
        job=wave['jobs'][a['task']]
        completed=[e for e in events if isinstance(e.get('tool_use_result_metadata'),dict)
            and e['tool_use_result_metadata'].get('status')=='completed'
            and e['tool_use_result_metadata'].get('agentId')==a['agent_id']
            and any(r['tool_use_id']==a['call_id'] for r in e.get('tool_results',[]))]
        terminal=[e for e in events if e.get('subtype')=='task_notification' and e.get('tool_use_id')==a['call_id']]
        require(len(completed)==len(terminal)==1 and terminal[0]['status']=='completed' and terminal[0]['task_id']==a['agent_id'],
                'typed native completion ID/status')
        validation=job['validations'][0];validation_abs=wave['origin']+validation['start']
        require(manifest['started_monotonic']+completed[0]['observed_elapsed']<validation_abs and
            manifest['started_monotonic']+terminal[0]['observed_elapsed']<validation_abs,'typed completion precedes parent validation')
        require(job['returned']<validation['start']<=job['first_valid']==validation['end']<job['adopted']
            <wave['final_validation']['start'] and validation['result']==0,'return/validate/first_valid/adopt/final order')
        actual=[stat.S_IMODE((work/name).stat().st_mode),sha((work/name).read_bytes())]
        require(job['adopted_digest']=={name:actual} and wave['final_validation']['digest'][name]==actual
                and a['after_sha256']==sha(encoded({name:actual})),'adopted/final/ticket bytes/mode binding')
        workers.append(dict(task=a['task'],call_id=a['call_id'],agent_id=a['agent_id'],nonce=a['nonce'],
            launcher_command=brief['launcher_command'],launcher_sha256=a['ready_launcher_sha256'],
            first_bash_call_id=wc[0][2]['id'],first_bash_exact=True,ready_monotonic=a['ready']['monotonic'],
            returned_monotonic=wave['origin']+job['returned'],
            denied_write=dict(call_id=nc['id'],hook_id=hr[0]['hook_id'],call_event=ni+1,hook_event=events.index(hr[0])+1,
                tool_result_event=ri+1,is_error=True,permission_decision=decision,file_absent=True),
            legal_write=dict(call_id=pc['id'],bytes=6,sha256=sha(b'READY\n'),tool_result_event=pri+1),
            named_check_call_id=checks[0][2]['id'],named_check_runtime_count=len(named),
            typed_completion_elapsed=completed[0]['observed_elapsed'],parent_validation_start_monotonic=validation_abs,
            first_valid=job['first_valid'],adopted=job['adopted'],
            extra_worker_calls=[dict(call_id=c['id'],name=c['name'],input=c['input']) for i,e,c in wc
                               if c['id'] not in {wc[0][2]['id'],nc['id'],pc['id'],checks[0][2]['id']}]))
    overlap=max(0,min(w['returned_monotonic'] for w in workers)-max(w['ready_monotonic'] for w in workers))
    require(overlap>0,'no actual READY/return interval overlap')
    post_agent_hooks=[dict(event=i+1,hook_id=e['hook_id'],elapsed=e['observed_elapsed'],exit_code=e['exit_code'])
                      for i,e in enumerate(events) if e.get('subtype')=='hook_response'
                      and e.get('hook_name')=='PostToolUse:Agent']
    require(len(post_agent_hooks)==2 and all(h['exit_code']==0 and manifest['started_monotonic']+h['elapsed']<
            min(w['parent_validation_start_monotonic'] for w in workers) for h in post_agent_hooks),
            'successful PostToolUse Agent hooks before parent validation')
    final=wave['final_validation']
    require(final['result']==0 and final['command_sha256']==sha(encoded(graph['final_check']))
        and wave['quality'] is True and all(j['adopted'] is not None for j in wave['jobs'].values()),'derived accepted final')
    require(wave['origin']+final['end']<cap and wave['finished']<manifest['started_epoch']+180,'full verification inside entry budget')
    known=[s for s in spans if s['label']!='host-lifecycle']
    require(all(s['state']=='complete' and s['result']==0 for s in known),'owned/worker/parent runtime completion')
    lifecycle=[s for s in spans if s['label']=='host-lifecycle']
    require(all(s['state']=='running' and s['result'] is None and s['finished'] is None for s in lifecycle),'unknown lifecycle represented as completed')
    host_events=[v for n,v in receipts.items() if n.startswith('evidence/host/event-')]
    require(any(e['event']=='SessionEnd' and e['session']==manifest['session'] for e in host_events),'SessionEnd host receipt')
    require(inventory(base)==before,'independent evidence changed during read')
    return dict(verified=True,scope='one real two-worker short-READY and structured-Write canary',
        checker_sha256=sha(Path(__file__).read_bytes()),driver_sha256=sha((base/'driver.py').read_bytes()),
        evidence_root=str(base),input_inventory=before,input_file_count=len(before),
        source_goal_host_sha256=manifest['sources']['scripts/goal_host.py'],runtime='999.0.0-local',model='MiniMax-M3.1-Flash',
        parent_message_id=next(iter(batches)),workers=workers,actual_ready_interval_overlap_seconds=overlap,
        post_tool_use_agent_hooks=post_agent_hooks,
        cli_returncode=report['result'],recorded_elapsed_before_parent_validation=report['elapsed'],
        final_finish_since_driver_entry=wave['origin']+wave['elapsed']-manifest['started_monotonic'],
        budget=dict(seconds=180,driver_entry_monotonic=manifest['started_monotonic'],deadline_monotonic=cap,
            stored_deadline_epoch=runner['deadline'],outer_deadline_epoch=manifest['started_epoch']+180,
            origin=runner['origin'],generations=chain,full_verification_before_cap=True,deadline_extended=False),
        final_quality=True,negative_write_probes=2,forbidden_files_absent=True,
        live_edit_tool_exercised=any(c.get('name')=='Edit' for e in events for c in e.get('content',[]) if isinstance(c,dict)),
        owned_and_parent_complete_runtime_span_count=len(known),host_lifecycle_unknown_span_count=len(lifecycle),
        session_end_host_receipt=True,session_end_stream_event_present=any(e.get('hook_event')=='SessionEnd' for e in events),
        session_start_attributed_to_this_plugin=False,
        coordination_join_stage_seconds_recorded=all(wave['stage_seconds'].get(n) is not None for n in ('coordination','join')),
        tokens=None,money=None,
        limitations=['Write exercised live; Edit not invoked in this canary.',
            'T2 repeats the named check with echo EXIT; hook wraps the extra shell and its runtime completes/result0.',
            'Negative hook association uses unique ordered call/hook-ID/result brackets; full raw hook inputs and tool text were not retained.',
            'One canary, different task from auditlog v2: no speed causality, 3+3 completion or general net-benefit claim.',
            'No model, named check, existing verifier, production API or test rerun by this reader.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=Path('/tmp/goal-claude-hooks-launcher-rg1v7ekj-independent-frozen'))
    args=parser.parse_args()
    print(json.dumps(inspect(args.base),indent=2,sort_keys=True))
