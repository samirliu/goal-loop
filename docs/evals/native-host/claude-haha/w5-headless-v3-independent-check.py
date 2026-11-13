#!/usr/bin/env python3
"""Independently read the six retained W5 v3 positions after controller exit.

No models, subprocesses, production imports or grader execution. This checks
recorded evidence and visible assignment deviations, not arbitrary shell code.
"""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import posixpath
import re
import shlex
import stat
import tarfile


def require(value, message):
    if not value:
        raise ValueError(message)


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def sealed(path):
    obj=load(path)
    require(sha(encode(obj['payload']))==obj['sha256'],'receipt checksum: '+str(path))
    return obj['payload']


def scope(root,names):
    return {n:[stat.S_IMODE((root/n).stat().st_mode),sha((root/n).read_bytes())] for n in names}


def require_close(a,b,message):
    require(abs(a-b)<0.00001,message)


def inspect(base,inventory_path,closed_manifest_path):
    inventory=load(inventory_path)
    for name,info in inventory['files'].items():
        p=base/name
        require(p.is_file() and not p.is_symlink() and sha(p.read_bytes())==info['sha256']
                and stat.S_IMODE(p.stat().st_mode)==info['mode'],'changed frozen input: '+name)
    archive=Path(__file__).parent/'w5-headless-v3/raw-run.tar.xz';archive_check=None
    if archive.is_file():
        manifest=load(archive.with_name('manifest.json'))
        require(sha(archive.read_bytes())==manifest['archive_sha256'],'retained raw archive checksum')
        with tarfile.open(archive) as saved:
            members={m.name:m for m in saved.getmembers() if m.isfile()}
            require(set(members)==set(inventory['files']),'archive/frozen file set')
            for name,info in inventory['files'].items():
                require(sha(saved.extractfile(members[name]).read())==info['sha256']
                        and members[name].mode==info['mode'],'archive/frozen bytes/modes: '+name)
        archive_check=dict(sha256=manifest['archive_sha256'],file_count=len(members),all_original_files_match=True)
    report,entry=load(base/'report.json'),load(base/'entry.json')
    require(report['status'] in ('finished','driver-failed-retained'),'controller not terminal; no final review')
    require(report['driver_sha256']==sha((base/'driver.py').read_bytes())==
            'aa6db26266ab956a5613a4e31c831b660e990df949e517f93d81ff7c41057a98','v3 driver identity')
    require(sha((base/'prereg.md').read_bytes())=='b8e6f43057d7494069992a78f9d7bd9079aab4103d19afe1c48b95c0dbd7e407',
            'executed preregistration identity')
    require(report['cohort'] not in ('74641771-6b4b-4b80-a845-3259fd1ad0ce','38883892-c997-49f1-b3ee-59c85b79698c'),'old cohort pooled into v3')
    require(entry['seconds']==report['requested_seconds']==1800,'fixed 1800-second budget')
    require(report.get('tokens') is None and report.get('money') is None,'unknown full token/billing totals changed')
    require(entry['epoch']==report['origin']['epoch'] and entry['monotonic']==report['origin']['monotonic'],'entry origin')
    require(load(base/'sources/.claude-plugin/plugin.json')['skills']=='./','namespaced root skill declaration')
    for name,value in report['source_hashes'].items():
        require(sha((base/'sources'/name).read_bytes())==value,'source identity: '+name)
    ready=report['f5_ready'];closed=load(closed_manifest_path)
    require(ready['status']=='ready' and ready['full_suites_terminal'] is True and ready['full_suites_all_green'] is True,
            'declared regression admission')
    require(sha(closed_manifest_path.read_bytes())==ready['source_manifest_sha256'],'closed regression source manifest')
    require(ready['matched_source_files']==len(closed)==139,'closed source file count')
    require(all(closed.get(n)==h for n,h in report['source_hashes'].items()),'cohort source differs from closed regression source')
    require(ready['host_sha256']==report['source_hashes']['scripts/goal_host.py'] and
            ready['owner_watch_sha256']==report['source_hashes']['scripts/goal_owner_watch.py'],'admission host/owner source')
    admission=dict(closed_source_manifest_sha256=ready['source_manifest_sha256'],closed_source_file_count=len(closed),
                   cohort_bound_source_count=len(report['source_hashes']),all_cohort_sources_match=True,
                   full_suites_terminal_declared=True,full_suites_all_green_declared=True)
    fingerprint=sha((json.dumps(dict(production=report['source_hashes'],client=report['client_source_hashes'],
                    env_sha256=report['user_env_sha256']),indent=2,sort_keys=True)+'\n').encode())
    state=base/'project/work/.goal';work=state.parent;control=base/'project/control'
    order=['single-1','crew-1','crew-2','single-2','single-3','crew-3']
    require(report['order']==[s['case'] for s in report['samples']]==order,'six fixed slots')
    require([s['mode'] for s in report['samples']]==['fused','crew','crew','fused','fused','crew'],'ABBAAB order')
    original_origin=report['origin'];chain=[];head=load(state/'store/commits/current')['head'];seen=set()
    while head:
        require(head not in seen,'cyclic generation history');seen.add(head)
        p=state/'store/commits/generations'/head
        require(sha(p.read_bytes())==head,'generation identity')
        v=load(p)
        if 'runner.json' in v['files']:
            r=json.loads(base64.b64decode(v['files']['runner.json']))
            chain.append(dict(generation=head,run=r['run'],origin=r['origin'],deadline_epoch=r['deadline'],
                              deadline_monotonic=r['monotonic']['deadline']))
        head=v['previous']
    chain.reverse()
    require(chain and len({r['run'] for r in chain})==1 and all(r['origin']==original_origin for r in chain),'run/origin reset')
    require(chain[0]['deadline_epoch']<=entry['epoch']+1800 and chain[0]['deadline_monotonic']<=entry['monotonic']+1800,'late start')
    require(all(b['deadline_epoch']<=a['deadline_epoch'] and b['deadline_monotonic']<=a['deadline_monotonic']
                for a,b in zip(chain,chain[1:])),'deadline extension')
    require(report['deadline_epoch']==chain[-1]['deadline_epoch'] and
            report['deadline_monotonic']==chain[-1]['deadline_monotonic'],'final controller deadline')
    receipts={str(p.relative_to(state)):sealed(p) for kind in ('host','runtime','crew')
              for p in sorted((state/'evidence'/kind).glob('*.json'))}
    waves=[v for p,v in receipts.items() if p.startswith('evidence/crew/')]
    spans=[v for p,v in receipts.items() if p.startswith('evidence/runtime/')]
    definitions={}
    for node in ast.parse((base/'sources/examples/agent-evals/tasks.py').read_text()).body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in ('STARTERS','TASKS','PUBLIC'):
                    definitions[target.id]=ast.literal_eval(node.value)
    starters=definitions['STARTERS']['medium'];inputs=scope(work,['TASK.md','public.py'])
    require((work/'TASK.md').read_text()==definitions['TASKS']['medium'] and
            (work/'public.py').read_text()==definitions['PUBLIC']['medium'],'fixture inputs changed')
    approval=re.findall(r'^approved: ([0-9a-f]{6,})(?:\s|$)',(state/'goal.md').read_text(),re.M)
    require(len(approval)==1,'approval identity')
    def condition(graph,wave):
        return sha(encode(dict(graph=graph,baseline=wave['baseline'],inputs=wave['inputs'],approval=approval[0],
            contract=sha((state/'goal.md').read_bytes()),observer=report['source_hashes']['scripts/goal_crew.py'],
            observer_transport='python-api',check_freeze=sha((state/'check_freeze').read_bytes()))))
    observations=[];seen_sessions=set();all_deviations=[];prior_wave=None
    for sample in report['samples']:
        name=sample['case'];folder=base/name
        if sample['status']=='not-dispatched':
            require(not folder.exists(),'not-dispatched slot has execution directory')
            observations.append(dict(case=name,mode=sample['mode'],status='not-dispatched',quality=None))
            continue
        manifest,briefs,attempts=(load(folder/n) for n in ('manifest.json','briefs.json','native-attempts.json'))
        events=[json.loads(l) for l in (folder/'events.jsonl').read_text().splitlines()]
        session=sample['session']
        require(session not in seen_sessions,'resumed/reused CLI session');seen_sessions.add(session)
        require(all(e.get('session_id')==session for e in events),'event session identity')
        wave=receipts['evidence/crew/'+sample['wave']+'.json']
        require(wave['trial']==name and wave['observer_transport']=='python-api','wave/trial/producer')
        require(wave['inputs']==inputs and set(wave['baseline'])==set(starters)
                and all(v==[420,sha(starters[n].encode())] for n,v in wave['baseline'].items()),'reset bytes/modes/inputs')
        require(sample['round_started']['monotonic']<=manifest['host_origin']['monotonic']<=wave['origin'],
                'round/reset/begin/Wave timing order')
        if prior_wave:
            require(prior_wave['finished'] is not None and prior_wave['origin']+prior_wave['elapsed']<=wave['origin'],
                    'new Wave before prior Wave finished')
        require(manifest['session']['run']==chain[0]['run'] and manifest['session']['deadline_monotonic']<=entry['monotonic']+1800,
                'round begins a new deadline/run')
        prior_wave=wave
        graph=wave['graph'];context=graph['context']
        require(len(briefs)==len(attempts)==len(graph['jobs']) and
                {a['task'] for a in attempts}=={j['id'] for j in graph['jobs']},'complete native ticket/job set')
        require(context['controller']==report['cohort'] and context['source_fingerprint']==fingerprint
                and context['cli_budget_usd'] is None and context['controller_version']==3,'v3 comparison context')
        for n,h in graph['instrument_hashes'].items():
            require(sha((control/n).read_bytes())==h,'changed grader/instrument: '+n)
        require(condition({k:v for k,v in graph.items() if k!='instrument_paths'},wave)==wave['condition'],'condition key')
        require(condition({k:graph[k] for k in ('version','context','final_check','instrument_hashes')},wave)
                ==wave['batch_condition'],'batch key')
        command=load(folder/'command.json')['command']
        require('--max-budget-usd' not in command and command[command.index('--max-turns')+1]=='8'
                and command[command.index('--session-id')+1]==session and
                '--resume' not in command and '--continue' not in command,'CLI cap/session settings')
        inits=[e for e in events if e.get('subtype')=='init']
        require(inits and all(e['model']=='MiniMax-M3.1-Flash' and e['claude_code_version']=='999.0.0-local'
            and e['skills'].count('goal-loop-host:goal-loop')==1 and e['slash_commands'].count('goal-loop-host:goal-loop')==1
            and any(p['name']=='goal-loop-host' and p['source']=='goal-loop-host@inline'
                    and p['path']=='/Users/m/repo/goal-loop' for p in e['plugins']) for e in inits),'native runtime/namespace')
        prompt=load(folder/'prompt-receipt.json')['origin']
        require(prompt['kind']=='prompt' and prompt['session']==session and
                manifest['host_origin']['monotonic']<=prompt['monotonic'],'actual prompt origin')
        results=[e for e in events if e['type']=='result']
        require(results and results[0]['is_error'] is False,'bootstrap result')
        bootstrap_exact_ready=results[0].get('result_sha256')==sha(b'READY')
        hook_interpreters=[];pretool_decisions=[]
        for line,e in enumerate(events,1):
            if e.get('subtype')!='hook_response':
                continue
            for field in ('stdout','output'):
                try:
                    output=json.loads(e.get(field) or '{}')
                except json.JSONDecodeError:
                    continue
                decision=output.get('hookSpecificOutput',{})
                if decision.get('permissionDecision'):
                    pretool_decisions.append(dict(event_line=line,hook_id=e.get('hook_id'),hook_name=e.get('hook_name'),
                        observed_monotonic=e['observed_monotonic'],decision=decision))
                cmd=output.get('hookSpecificOutput',{}).get('updatedInput',{}).get('command')
                if isinstance(cmd,str):
                    argv=shlex.split(cmd)
                    if len(argv)>5 and argv[2]=='/Users/m/repo/goal-loop/scripts/goal_host_command.py':
                        hook_interpreters.append(dict(event_line=line,hook_id=e.get('hook_id'),argv_prefix=argv[:6]))
                        break
                if decision.get('permissionDecision'):
                    break
        batches={}
        for e in events:
            if e['type']=='assistant' and e.get('parent_tool_use_id') is None:
                for c in e['content']:
                    if c['type']=='tool_use':
                        require(e['message_id'],'missing actual parent message ID')
                        bucket=batches.setdefault(e['message_id'],{})
                        if c['id'] in bucket:
                            require(bucket[c['id']]==c,'conflicting parent stream call')
                        bucket[c['id']]=c
        calls=[c for bucket in batches.values() for c in bucket.values()]
        dispatch_ok=(len(calls)==len(briefs) and all(c['name'] in ('Agent','Task')
            and c['input'].get('subagent_type')=='goal-loop-host:goal-worker' and 'model' not in c['input']
            and 'effort' not in c['input'] and c['input'].get('run_in_background') is not True for c in calls)
            and all(sum(c['input'].get('prompt','').startswith(b['header']+'\n') for c in calls)==1 for b in briefs)
            and (sample['mode']!='crew' or any(len(bucket)==2 for bucket in batches.values())))
        require(load(folder/'parent-message-batch-indices.json')=={m:i for i,m in enumerate(batches)},'native message batch index')
        workers=[];round_deviations=[]
        if not bootstrap_exact_ready:
            round_deviations.append(dict(task=None,reason='bootstrap result text hash differs from exact READY'))
        for brief,a in zip(briefs,attempts):
            require(a==sealed(folder/'host-attempts-before-validation'/('attempt-'+a['id']+'.json')),'before validation binding')
            require(a['id']+':'+a['nonce']==brief['ticket'] and a['run']==chain[0]['run'] and a['session']==session,'ticket/run/nonce')
            require(a['wave']==wave['id'] and a['files']==next(j['files'] for j in graph['jobs'] if j['id']==a['task']),
                    'native ticket Wave/owned scope identity')
            launcher_command=brief.get('launcher_command')
            launcher_info=None
            if launcher_command:
                argv=shlex.split(launcher_command)
                require(len(argv)==2 and argv[0]=='bash','short launcher command shape')
                path=work/Path(argv[1]).relative_to(Path(a['project']))
                body=('#!/bin/sh\nexec '+brief['owned_ready_command']+'\n').encode()
                require(path.is_file() and not path.is_symlink() and path.read_bytes()==body
                        and sha(body)==a['ready_launcher_sha256'] and stat.S_IMODE(path.stat().st_mode)==0o600,
                        'pinned launcher body/nonce/SHA/mode')
                require(shlex.split(brief['owned_ready_command'])[0]==a['command_python'],'pinned ticket interpreter')
                launcher_info=dict(command=launcher_command,sha256=a['ready_launcher_sha256'],mode=0o600)
            matching=[c for c in calls if c['id']==a['call_id']]
            if not matching:
                require(a['phase'] not in ('returned','failed','cancelled'),'terminal ticket without native call binding')
                workers.append(dict(task=a['task'],call_id=a['call_id'],wire_name=None,agent_id=a['agent_id'],
                    native_agent_id=None,
                    ticket=brief['ticket'],phase=a['phase'],ready=a.get('ready'),terminal_monotonic=None,
                    wave_ready_monotonic=None,last_activity_monotonic=manifest['host_origin']['monotonic'],
                    visible_deviations=[],first_tool_exact_ready=None,native_binding_observed=False))
                continue
            require(len(matching)==1,'duplicate actual parent call ID');call=matching[0]
            prefix_exact=call['input'].get('prompt','').startswith(brief['worker_prefix'])
            native_start=[e for e in events if e.get('subtype')=='task_started' and e.get('tool_use_id')==a['call_id']]
            if a['agent_id'] is not None:
                require(len(native_start)==1 and native_start[0]['task_id']==a['agent_id'],'actual native Agent ID')
            activity=[e for e in events if e.get('parent_tool_use_id')==a['call_id']]
            worker_calls={}
            for e in activity:
                for c in e.get('content',[]):
                    if c['type']=='tool_use':
                        if c['id'] in worker_calls:
                            require({k:v for k,v in worker_calls[c['id']].items() if k!='observed_monotonic'}==c,'conflicting worker call')
                        worker_calls[c['id']]=dict(c,observed_monotonic=e['observed_monotonic'])
            cs=list(worker_calls.values())
            if not cs:
                require(a['phase'] not in ('returned','failed','cancelled'),'terminal worker has no visible tools')
                workers.append(dict(task=a['task'],call_id=a['call_id'],wire_name=call['name'],agent_id=a['agent_id'],
                    native_agent_id=native_start[0]['task_id'] if native_start else None,
                    ticket=brief['ticket'],phase=a['phase'],ready=a.get('ready'),terminal_monotonic=None,
                    wave_ready_monotonic=None,last_activity_monotonic=manifest['host_origin']['monotonic'],
                    visible_deviations=[],first_tool_exact_ready=None,native_binding_observed=bool(native_start)))
                continue
            tool_results={r['tool_use_id']:r for e in activity for r in e.get('tool_results',[])}
            terminal=[e for e in events if e.get('subtype')=='task_notification' and e.get('tool_use_id')==a['call_id']]
            if a['phase']=='returned':
                require(len(terminal)==1 and terminal[0]['task_id']==a['agent_id'] and terminal[0]['status']=='completed','native completed receipt')
                completions=[e for e in events if isinstance(e.get('tool_use_result_metadata'),dict) and
                    e['tool_use_result_metadata'].get('status')=='completed' and
                    e['tool_use_result_metadata'].get('agentId')==a['agent_id'] and a['call_id'] in e['tool_use_ids']
                    ]
                require(completions,'structured completed metadata')
                if wave['jobs'][a['task']]['validations']:
                    require(max(e['observed_monotonic'] for e in completions)<wave['origin']+
                        wave['jobs'][a['task']]['validations'][0]['start'],'structured completion precedes parent validate')
            allowed={str(Path(a['project'])/n) for n in a['files']+['TASK.md','public.py']}
            violations=[]
            def deviation(c,reason):
                violations.append(dict(call_id=c['id'],tool=c['name'],reason=reason,
                    path=c['input'].get('file_path') or c['input'].get('path'),
                    command=c['input'].get('command'),tool_result=tool_results.get(c['id'])))
            if not prefix_exact:
                violations.append(dict(reason='native worker prompt does not preserve whole brief prefix',call_id=a['call_id']))
            first=cs[0]
            expected_first=launcher_command or brief['owned_ready_command']
            if first['name']!='Bash' or first['input'].get('command')!=expected_first:
                deviation(first,'first tool is not the exact supplied First tool command')
            for c in cs:
                x=c['input'];p=x.get('file_path') or x.get('path');cmd=x.get('command','')
                normalized=posixpath.normpath(p if p.startswith('/') else a['project']+'/'+p) if p else None
                if normalized and normalized.startswith('/tmp/'):
                    normalized='/private'+normalized
                if c['name'] in ('Read','Write','Edit','Grep') and normalized and normalized not in allowed:
                    if not (sample['mode']=='fused' and c['name']=='Grep' and normalized==str(Path(a['project'])/'auditlog')):
                        deviation(c,'explicit path outside this worker assignment')
                if c['name'] in ('Agent','Task'):
                    deviation(c,'worker dispatched another native agent')
                if c['name']=='Bash':
                    if not cmd.startswith(brief['tool_prefix']) and cmd!=brief['check_command'] and cmd!=expected_first:
                        deviation(c,'shell text does not use supplied exact owned prefix')
                    if '/.goal' in cmd and cmd.strip()!=launcher_command:
                        deviation(c,'shell explicitly references excluded .goal state (inspect command for listing/content distinction)')
                    if 'cat ' in cmd and any(str(Path(a['project'])/n) in cmd for n in set(starters)-set(a['files'])):
                        deviation(c,'explicit cat reads the other worker file')
                    inline_script=bool(re.search(r'\bpython[0-9.]*(?:\s+-[A-Za-z0-9]+)*\s+(?:-c\b|-\s*<<)',cmd))
                    inline_test=inline_script and bool(re.search(r'\bassert\s|AssertionError|def\s+(?:test_|check\b|expect\b)',cmd))
                    experiment_write='/tmp/exp' in cmd and any(t in cmd for t in ('mkdir','makedirs','write_text','shutil.copy'))
                    shell_cli_test='mktemp' in cmd and bool(re.search(r'\b-m\s+auditlog\b',cmd))
                    if any(t in cmd for t in ('scratch','extra_tests')) or inline_test or experiment_write or shell_cli_test:
                        deviation(c,'extra test/scratch command beyond named check; inspect retained command')
                    if inline_script and 'inspect.getsource' in cmd:
                        deviation(c,'explicit standard-library source inspection outside assigned read files')
            j=wave['jobs'][a['task']];ready=a.get('ready')
            named_checks=sorted([s for s in spans if s['label']=='host-worker-check' and s.get('parent')==a['trace']],
                                key=lambda s:s['start_monotonic'])
            if a['phase']=='returned':
                expected_check=next(g['check'] for g in graph['jobs'] if g['id']==a['task'])
                expected_check=[v.replace('{project}',a['project']) for v in expected_check]
                require(named_checks and all(s['command']==expected_check for s in named_checks)
                        and named_checks[-1]['state']=='complete' and named_checks[-1]['result']==0,
                        'actual named check identity and final worker check passed')
            returned=wave['origin']+j['returned'] if j['returned'] is not None else None
            if ready:
                require(wave['origin']+j['started']>=ready['monotonic'],'READY wave/attempt event ordering')
            workers.append(dict(task=a['task'],call_id=a['call_id'],wire_name=call['name'],agent_id=a['agent_id'],
                native_agent_id=native_start[0]['task_id'] if native_start else None,
                ticket=brief['ticket'],phase=a['phase'],ready=ready,terminal_monotonic=returned,
                wave_ready_monotonic=wave['origin']+j['started'] if j['started'] is not None else None,
                last_activity_monotonic=max(e['observed_monotonic'] for e in activity),
                raw_worker_tool_use_count=len(cs),raw_worker_error_result_count=sum(r.get('is_error') is True for r in tool_results.values()),
                short_ready_launcher=launcher_info,
                exact_original_ready_attempt_call_ids=[c['id'] for c in cs if c['name']=='Bash' and
                    c['input'].get('command','').strip() in (brief['owned_ready_command'],brief['ready_command'],launcher_command)],
                tool_inputs=[dict(call_id=c['id'],tool=c['name'],observed_monotonic=c['observed_monotonic'],
                    input_sha256=sha(encode(c['input'])),
                    input_summary={k:(dict(sha256=sha(v.encode()),bytes=len(v.encode()))
                        if k in ('content','old_string','new_string') and isinstance(v,str) else v) for k,v in c['input'].items()},
                    tool_result=tool_results.get(c['id'])) for c in cs],
                direct_child_runtime_spans=[dict(id=s['id'],label=s['label'],state=s['state'],result=s['result'])
                                            for s in spans if s.get('parent')==a['trace']],
                named_check_measurements=[dict(id=s['id'],result=s['result'],start_monotonic=s['start_monotonic']) for s in named_checks],
                visible_deviations=violations,first_tool_exact_ready=not any(v.get('call_id')==first['id'] and
                    v['reason'].startswith('first tool') for v in violations)))
            round_deviations.extend(dict(task=a['task'],**v) for v in violations)
        overlap=None;full_intervals=all(w['terminal_monotonic'] is not None and w['ready'] for w in workers)
        if len(workers)==2 and all(w['ready'] for w in workers):
            overlap=max(0,min(w['terminal_monotonic'] if w['terminal_monotonic'] is not None else w['last_activity_monotonic']
                              for w in workers)-max(w['ready']['monotonic'] for w in workers))
        actual_parallel=sample['mode']!='crew' or full_intervals and overlap is not None and overlap>0
        validation=None;quality=None;wave_overlap=None
        if sample['status']=='sealed':
            require(wave==load(folder/'result.json'),'sealed archive/live wave binding')
            require(wave['finished'] is not None and all(a['phase'] in ('returned','failed','cancelled') for a in attempts),'sealed unknown native')
            final=wave['final_validation']
            require(final['command_sha256']==sha(encode(graph['final_check'])),'frozen final command')
            require(scope(folder/'artifact',starters)==final['digest'],'archived final bytes/modes')
            adopted={}
            for j in wave['jobs'].values():
                if j['adopted'] is not None:
                    valid=[v for v in j['validations'] if v['result']==0]
                    require(valid and j['first_valid']==valid[0]['end'] and
                        j['returned']<valid[0]['start']<=j['first_valid']<j['adopted']<final['start'],'return/validate/adopt/final ordering')
                    adopted.update(j['adopted_digest'])
            quality=final['result']==0 and all(j['adopted'] is not None for j in wave['jobs'].values()) and adopted==final['digest']
            require(quality==wave['quality']==sample['quality'],'derived quality mismatch')
            require_close(sum(j['returned']-j['dispatch'] for j in wave['jobs'].values()),wave['worker_seconds'],'worker occupancy sum')
            require_close(sample['worker_seconds'],wave['worker_seconds'],'reported worker occupancy')
            require_close(sample['elapsed'],wave['elapsed'],'reported Wave elapsed')
            for stage in ('coordination','join','conflict','recovery','revalidation'):
                entries=[s for s in wave['stages'] if s['name']==stage]
                expected=sum(s['end']-s['start'] for s in entries) if entries else None
                if expected is None:
                    require(wave['stage_seconds'][stage] is None,'unobserved stage filled with duration')
                else:
                    require(all(s['end'] is not None and 0<=s['start']<=s['end']<=wave['elapsed'] for s in entries),
                            'stage interval outside completed Wave')
                    require_close(wave['stage_seconds'][stage],expected,'independent stage sum: '+stage)
            if quality:
                graded=json.loads(final['stdout'])
                require(graded['ok'] and len(graded['checks'])==21 and all(c['pass_'] for c in graded['checks']),'recorded independent final grader')
            validation=dict(result=final['result'],recorded_stdout=final['stdout'],digest=final['digest'],grader_rerun=False)
            before_deadline=(wave['origin']+final['end']<=wave['deadline'] and wave['finished']<=manifest['session']['deadline_epoch'])
            require(not sample['timely'] or before_deadline,'reported timely final exceeded original deadline')
            if sample['mode']=='crew':
                if all(w['terminal_monotonic'] is not None and w['wave_ready_monotonic'] is not None for w in workers):
                    wave_overlap=max(0,min(w['terminal_monotonic'] for w in workers)-max(w['wave_ready_monotonic'] for w in workers))
                    require_close(sample['ready_interval_overlap_seconds'],wave_overlap,'reported wave READY overlap')
                else:
                    require(sample['ready_interval_overlap_seconds'] is None,'reported absent READY interval')
            controller_parallel=sample['mode']!='crew' or wave_overlap is not None and wave_overlap>0
            require(sample['dispatch_protocol_ok']==dispatch_ok and sample['protocol_ok']==bool(dispatch_ok and controller_parallel),
                    'controller parent/wave-concurrency flags')
        else:
            require(wave['finished'] is None and wave['final_validation'] is None,'unsealed wave has fabricated final')
            require(not any(j['adopted'] is not None for j in wave['jobs'].values()),'partial wave adopted')
            before_deadline=None
        host_events=[sealed(p) for p in (folder/'host-events').glob('*.json')]
        post_hooks=[dict(event_line=i+1,hook_id=e['hook_id'],observed_monotonic=e['observed_monotonic'],exit_code=e['exit_code'])
                    for i,e in enumerate(events) if e.get('subtype')=='hook_response'
                    and e.get('hook_name') in ('PostToolUse:Agent','PostToolUse:Task')]
        if sample['status']=='sealed' and all(a['phase']=='returned' for a in attempts):
            first_parent_validate=min(wave['origin']+j['validations'][0]['start'] for j in wave['jobs'].values())
            require(len(post_hooks)==len(attempts) and all(h['exit_code']==0 and h['observed_monotonic']<first_parent_validate
                        for h in post_hooks),'successful native PostToolUse hooks precede parent validation')
        observations.append(dict(case=name,mode=sample['mode'],status=sample['status'],wave=wave['id'],condition=wave['condition'],
            batch_condition=wave['batch_condition'],quality=quality,elapsed=wave['elapsed'],worker_seconds=wave.get('worker_seconds'),
            stage_seconds=wave.get('stage_seconds'),round_wall=sample.get('round_wall'),timely=sample.get('timely'),
            final_completed_before_original_deadline=before_deadline,
            reconstructed_dispatch_protocol_ok=dispatch_ok,completed_ready_overlap_seconds=overlap if full_intervals else None,
            production_wave_ready_overlap_seconds=wave_overlap,
            censored_ready_activity_overlap_lower_bound_seconds=overlap if not full_intervals else None,
            actual_completed_parallelism=bool(actual_parallel) if sample['mode']=='crew' else None,
            concurrency_requirement_satisfied=bool(actual_parallel),original_controller_protocol_ok=sample.get('protocol_ok'),
            full_assignment_adherence_proven=False,visible_assignment_deviation_count=len(round_deviations),
            bootstrap_text_exact_READY=bootstrap_exact_ready,
            parent_batches=[dict(message_id=m,call_ids=list(cs),wire_names=[c['name'] for c in cs.values()]) for m,cs in batches.items()],
            workers=workers,independent_validation=validation,cli_returncode=sample.get('cli_returncode'),
            final_cli_result={k:results[-1].get(k) for k in ('subtype','is_error','errors','total_cost_usd','num_turns')},
            session_end_host_receipt=any(e['event']=='SessionEnd' for e in host_events),namespace_registry_present=True,
            observed_hook_generated_wrapper_interpreters=hook_interpreters,
            observed_pretool_decisions=pretool_decisions,
            native_posttool_hooks=post_hooks,
            observed_hook_wrapper_interpreters_match_prepare=all(h['argv_prefix'][0]==graph['final_check'][0] for h in hook_interpreters)
                if hook_interpreters else None,
            processed_skill_command_body_retained=False))
        observations[-1]['observed_assistant_models']=sorted({e['model'] for e in events if e.get('type')=='assistant' and e.get('model')})
        all_deviations.extend(dict(case=name,**v) for v in round_deviations)
    dispatched=[o for o in observations if o['status']!='not-dispatched']
    require(len(waves)==len(dispatched)<=6,'replacement/seventh wave')
    conditions={m:sorted({o['condition'] for o in dispatched if o['mode']==m}) for m in ('fused','crew')}
    batchkeys=sorted({o['batch_condition'] for o in dispatched})
    complete=len(dispatched)==6 and all(o['status']=='sealed' for o in dispatched)
    planner=report['planner'];derived_plan=None;cost_bounds=None;possible_decisions=None;remaining_interval=None
    if complete:
        require(report['baseline_restored'] and scope(work,starters)==waves[0]['baseline'],'qualified final reset')
        require(all(len(v)==1 for v in conditions.values()) and len(batchkeys)==1,'three-plus-three comparison keys')
        require(planner.get('executed') is not False,'missing original planner')
        require(planner['condition']==conditions['crew'][0] and planner['effective_dependencies']=={'T1':[],'T2':[]},
                'original planner condition/dependency identity')
        require(planner.get('tokens') is None and planner.get('money') is None,'unknown planner billing/token totals')
        singles=[w for w in waves if w['mode']=='inline'];crews=[w for w in waves if w['mode']=='crew']
        require(len(singles)==len(crews)==3,'3+3 mode coverage')
        remaining_lo=report['deadline_monotonic']-(entry['monotonic']+report['suite_elapsed'])
        remaining_hi=report['deadline_monotonic']-max(w['origin']+w['elapsed'] for w in waves)
        require(remaining_hi>=remaining_lo,'planner time observation bracket')
        remaining_interval=[remaining_lo,remaining_hi]
        if planner['reason']!='time-budget-exhausted':
            require(planner['observations']==6 and planner['single_observations']==3 and planner['pending']==0
                and planner['failures']==sum(w['quality'] is False for w in waves)
                and planner['observer_transport']=='python-api','original planner complete retained window')
        if all(w['quality'] and all(not j['fault'] and j['started'] is not None for j in w['jobs'].values()) for w in waves):
            def overhead(w):
                intervals=sorted((j['dispatch'],j['returned']) for j in w['jobs'].values());end=None;union=0
                for a,b in intervals:
                    union+=b-a if end is None or a>end else max(0,b-end);end=max(end or b,b)
                return max(0,w['elapsed']-union)
            serial=min(w['elapsed'] for w in singles);serial_worker=min(w['worker_seconds'] for w in singles)
            durations={t:max(w['jobs'][t]['returned']-w['jobs'][t]['dispatch'] for w in crews) for t in ('T1','T2')}
            parallel=max(max(durations.values())+max(overhead(w) for w in crews),max(w['elapsed'] for w in crews))
            cost_bounds=dict(serial_lower=serial,crew_upper=parallel,serial_worker_seconds_lower=serial_worker,
                             crew_worker_seconds_upper=sum(durations.values()),uncertainty='observed range only')
            def decide(remaining):
                if remaining<=0:
                    return ('stop','time-budget-exhausted')
                choice,reason='serial','startup-coordination-or-dependency-cost'
                if serial-parallel>max(.05,.1*serial) and parallel<remaining:
                    if sum(durations.values())>serial_worker and serial<remaining:
                        reason='latency-gain-with-worker-cost-tradeoff'
                    else:
                        choice='crew'
                        reason='only-observed-deadline-fit' if serial>=remaining else 'observed-latency-benefit'
                if choice=='serial' and serial>=remaining:
                    choice,reason='stop','insufficient-measured-budget'
                return choice,reason
            points=[remaining_lo,remaining_hi]
            for boundary in (0,serial,parallel):
                for point in (boundary-0.000001,boundary,boundary+0.000001):
                    if remaining_lo<=point<=remaining_hi:
                        points.append(point)
            possible_decisions=sorted({decide(r) for r in points})
            require((planner['choice'],planner['reason']) in possible_decisions,'independent original planner decision')
            if planner.get('serial_lower') is not None:
                require(planner['serial_basis']=='single-worker','original planner baseline basis')
                for k in ('serial_lower','crew_upper','serial_worker_seconds_lower','crew_worker_seconds_upper'):
                    require_close(planner[k],cost_bounds[k],'independent planner bound: '+k)
                if serial-parallel>max(.05,.1*serial) and sum(durations.values())>serial_worker:
                    derived_plan='retain serial when both fit: latency-gain-with-worker-cost-tradeoff'
                else:
                    derived_plan='no robust >10% observed crew latency advantage' if serial-parallel<=max(.05,.1*serial) else 'crew may fit; evaluate original remaining time'
        else:
            derived_plan='failure-or-unknown-startup-in-latest-window'
            require(planner['reason']==derived_plan or planner['reason']=='time-budget-exhausted','planner quality guard')
    else:
        require(planner.get('executed') is False and report['baseline_restored'] is False,'incomplete cohort reset/planner')
    pairs=[]
    for i in range(1,4):
        a=next(o for o in observations if o['case']=='single-'+str(i));b=next(o for o in observations if o['case']=='crew-'+str(i))
        pairs.append(dict(pair=i,single_status=a['status'],crew_status=b['status'],
            elapsed_crew_minus_single=b.get('elapsed')-a.get('elapsed') if a.get('elapsed') is not None and b.get('elapsed') is not None else None,
            worker_seconds_crew_minus_single=b.get('worker_seconds')-a.get('worker_seconds') if a.get('worker_seconds') is not None and b.get('worker_seconds') is not None else None))
    known_spans=[s for s in spans if s['label']!='host-lifecycle']
    require(all(s['state']=='complete' and isinstance(s['result'],int) and s['finished'] is not None for s in known_spans),
            'unsettled non-lifecycle runtime measurement')
    lifecycle=[s for s in spans if s['label']=='host-lifecycle']
    require(all(s['state']=='running' and s['result'] is None and s['finished'] is None for s in lifecycle),
            'unknown lifecycle converted into completion')
    require(report['goal_gate_go_claimed'] is False,'unearned Gate GO claim')
    structured={tool:dict(attempts=0,error_results=0,successful_result_records=0) for tool in ('Write','Edit')}
    for o in observations:
        for w in o.get('workers',[]):
            for c in w.get('tool_inputs',[]):
                if c['tool'] in structured:
                    stats=structured[c['tool']];stats['attempts']+=1
                    if c['tool_result'] is not None:
                        if c['tool_result'].get('is_error') is True:
                            stats['error_results']+=1
                        else:
                            stats['successful_result_records']+=1
    write_denials=[dict(case=o['case'],**d) for o in observations for d in o.get('observed_pretool_decisions',[])
        if d['decision'].get('permissionDecision')=='deny' and
        d['decision'].get('permissionDecisionReason','').startswith('goal-loop: structured worker write')]
    mode_totals={}
    if complete:
        for mode in ('fused','crew'):
            rows=[o for o in observations if o['mode']==mode]
            mode_totals[mode]=dict(count=len(rows),elapsed=sum(o['elapsed'] for o in rows),
                worker_seconds=sum(o['worker_seconds'] for o in rows),quality_passes=sum(o['quality'] is True for o in rows))
    return dict(evidence_consistent=True,complete_six_position_comparison=complete,
        net_benefit_established=False,full_assignment_adherence=False if all_deviations else None,
        original_controller_planner_applicable=report.get('planner_applicable'),
        no_visible_assignment_deviations=not all_deviations,
        evidence_root=str(base),cohort=report['cohort'],checker_sha256=sha(Path(__file__).read_bytes()),
        raw_report_sha256=sha((base/'report.json').read_bytes()),input_inventory_sha256=sha(inventory_path.read_bytes()),
        retained_raw_archive=archive_check,
        admission=admission,source_bindings=report['source_hashes'],
        runtime='999.0.0-local',model='MiniMax-M3.1-Flash',dispatched=len(dispatched),observations=observations,
        visible_assignment_deviations=all_deviations,conditions=conditions,batch_keys=batchkeys,pairs=pairs,
        all_retained_mode_totals=mode_totals,structured_tool_summary=structured,structured_write_fence_denials=write_denials,
        budget=dict(requested_seconds=1800,suite_elapsed=report['suite_elapsed'],runner_history=chain,
                    deadline_extended=False,finished_epoch=report['finished_epoch'],mechanical_deadline_epoch=report['deadline_epoch']),
        planner=planner,independent_planner_bounds=cost_bounds,independent_planner_interpretation=derived_plan,
        independent_planner_possible_decisions=possible_decisions,planner_remaining_seconds_bracket=remaining_interval,
        baseline_restored=report['baseline_restored'],tokens=None,money=None,
        runtime_failures=[dict(id=s['id'],label=s['label'],result=s['result']) for s in spans if s['result'] not in (None,0)],
        settled_non_lifecycle_runtime_spans=len(known_spans),gate_go_claimed=False,
        host_lifecycle_unknown_count=sum(s['label']=='host-lifecycle' and s['state']=='running' for s in spans),
        limits=['No new models, tests, production imports, grader reruns or raw changes.',
                'Parent dispatch/concurrency and full worker assignment adherence are separate.',
                'Visible tool input/result evidence is not a general shell interpreter or proof of every transitive read.',
                'Namespaced registry and frozen literal bootstrap retained; processed SKILL body receipt absent.',
                'No complete supplier token/billing accounting; CLI estimates are not pooled or treated as bills.',
                'Observed ranges in one auditlog cohort do not establish general agent-session benefit.'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True)
    p.add_argument('--inventory',type=Path,required=True)
    p.add_argument('--closed-manifest',type=Path,
                   default=Path(__file__).with_name('w5-headless-v3-independent-closed-source-manifest.json'))
    a=p.parse_args()
    print(json.dumps(inspect(a.base,a.inventory,a.closed_manifest),indent=2,sort_keys=True))
