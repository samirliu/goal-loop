#!/usr/bin/env python3
"""Read-only reconstruction of the retained, incomplete W5 v1 cohort.

Only stdlib, no production imports, subprocesses, model calls or grader reruns.
Evidence checks use explicit exceptions, including under python -O.
"""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import re
import stat
import tarfile


def require(value, message):
    if not value:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def sealed(path):
    value = load(path)
    require(sha(encode(value['payload'])) == value['sha256'], 'receipt checksum: '+str(path))
    return value['payload']


def scope(root, names):
    return {n: [stat.S_IMODE((root/n).stat().st_mode), sha((root/n).read_bytes())] for n in names}


def main(base, inventory_path, liveness_path):
    inventory = load(inventory_path)
    for name, info in inventory['files'].items():
        path = base/name
        require(path.is_file() and not path.is_symlink(), 'input missing/not regular: '+name)
        require(path.stat().st_size == info['bytes'] and stat.S_IMODE(path.stat().st_mode) == info['mode']
                and sha(path.read_bytes()) == info['sha256'], 'changed frozen input: '+name)
    archive = Path(__file__).parent/'w5-headless-v1/raw-run.tar.xz'
    archive_check = None
    if archive.is_file():
        manifest = load(archive.with_name('manifest.json'))
        require(sha(archive.read_bytes()) == manifest['archive_sha256'], 'raw archive checksum')
        with tarfile.open(archive) as retained:
            members = {m.name:m for m in retained.getmembers() if m.isfile()}
            require(set(members) == set(inventory['files']), 'raw archive file set')
            for name, info in inventory['files'].items():
                require(sha(retained.extractfile(members[name]).read()) == info['sha256']
                        and members[name].mode == info['mode'], 'archive differs from independent snapshot: '+name)
        archive_check = dict(sha256=manifest['archive_sha256'],all_original_files_match=True,file_count=len(members))
    report, entry = load(base/'report.json'), load(base/'entry.json')
    work, control = base/'project/work', base/'project/control'
    state = work/'.goal'
    require(sha((base/'driver.py').read_bytes()) == report['driver_sha256'] ==
            '225cbd4e124295b39c282c130a2b6fafe7325a0abe29dbebd3738507928a7d34', 'executed driver identity')
    for name, expected in report['source_hashes'].items():
        require(sha((base/'sources'/name).read_bytes()) == expected, 'frozen source: '+name)
    require(load(base/'sources/.claude-plugin/plugin.json')['skills'] == './', 'root skill declaration')
    require(entry['seconds'] == report['requested_seconds'] == 900, 'original budget')
    require(entry['epoch'] == report['origin']['epoch'] and entry['monotonic'] == report['origin']['monotonic'],
            'entry origin binding')
    order = ['single-1', 'crew-1', 'crew-2', 'single-2', 'single-3', 'crew-3']
    require([s['case'] for s in report['samples']] == report['order'] == order, 'all six fixed slots retained')
    require([s['mode'] for s in report['samples']] == ['fused','crew','crew','fused','fused','crew'], 'ABBAAB')
    require([s['status'] for s in report['samples']] ==
            ['sealed','stopped-unknown-native-terminal']+['not-dispatched']*4, 'retained outcomes')
    require(all(not (base/n).exists() for n in order[2:]), 'undispatched slot has files')
    # Inspect every sealed host/runtime/wave receipt; do not trust report.status.
    receipts = {str(p.relative_to(state)): sealed(p) for kind in ('host','runtime','crew')
                for p in sorted((state/'evidence'/kind).glob('*.json'))}
    spans = [v for n,v in receipts.items() if n.startswith('evidence/runtime/')]
    waves = [v for n,v in receipts.items() if n.startswith('evidence/crew/')]
    require(len(waves) == 2, 'unexpected/replacement/seventh wave')
    # Content-addressed runner generations independently establish one shrinking deadline.
    chain, head = [], load(state/'store/commits/current')['head']
    seen = set()
    while head:
        require(head not in seen, 'cyclic store generation chain'); seen.add(head)
        path = state/'store/commits/generations'/head
        require(sha(path.read_bytes()) == head, 'store generation hash')
        value = load(path)
        if 'runner.json' in value['files']:
            runner = json.loads(base64.b64decode(value['files']['runner.json']))
            chain.append(dict(generation=head, run=runner['run'], origin=runner['origin'],
                              deadline_epoch=runner['deadline'], deadline_monotonic=runner['monotonic']['deadline']))
        head = value['previous']
    chain.reverse()
    require(chain and len({r['run'] for r in chain}) == 1, 'same persisted run')
    require(all(r['origin'] == report['origin'] for r in chain), 'runner origin reset')
    require(all(b['deadline_epoch'] <= a['deadline_epoch'] and b['deadline_monotonic'] <= a['deadline_monotonic']
                for a,b in zip(chain, chain[1:])), 'deadline extension')
    require(chain[0]['deadline_epoch'] <= entry['epoch']+900
            and chain[0]['deadline_monotonic'] <= entry['monotonic']+900, 'late budget start')
    require(load(state/'runner.json')['deadline'] == report['deadline_epoch'] == chain[-1]['deadline_epoch'],
            'final persisted deadline')
    require(report['suite_elapsed'] < 900 and report['finished_epoch'] < report['deadline_epoch'], 'controller finished after cap')
    definitions = {}
    tree = ast.parse((base/'sources/examples/agent-evals/tasks.py').read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('STARTERS','TASKS','PUBLIC'):
                    definitions[target.id] = ast.literal_eval(node.value)
    starters = definitions['STARTERS']['medium']
    actual_inputs = scope(work, ['TASK.md','public.py'])
    require((work/'TASK.md').read_text() == definitions['TASKS']['medium']
            and (work/'public.py').read_text() == definitions['PUBLIC']['medium'], 'fixture input bytes')
    approval = re.findall(r'^approved: ([0-9a-f]{6,})(?:\s|$)', (state/'goal.md').read_text(), re.M)
    require(len(approval) == 1, 'approval identity')
    def key(graph, wave):
        value = dict(graph=graph, baseline=wave['baseline'], inputs=wave['inputs'], approval=approval[0],
                     contract=sha((state/'goal.md').read_bytes()),
                     observer=report['source_hashes']['scripts/goal_crew.py'], observer_transport='python-api',
                     check_freeze=sha((state/'check_freeze').read_bytes()))
        return sha(encode(value))
    observations = []
    for sample in report['samples'][:2]:
        name = sample['case']; folder = base/name
        manifest, briefs, attempts = (load(folder/n) for n in ('manifest.json','briefs.json','native-attempts.json'))
        events = [json.loads(line) for line in (folder/'events.jsonl').read_text().splitlines()]
        wave = receipts['evidence/crew/'+manifest['wave']+'.json']
        require(wave == (load(folder/'result.json') if name == 'single-1' else sealed(folder/'unsealed-wave.json')),
                'archived/live wave binding')
        require(wave['trial'] == name and wave['observer_transport'] == 'python-api', 'wave identity')
        require(wave['inputs'] == actual_inputs, 'frozen inputs mismatch')
        require(set(wave['baseline']) == set(starters) and all(v == [420,sha(starters[n].encode())]
                for n,v in wave['baseline'].items()), 'initial bytes/modes/reset mismatch')
        graph = wave['graph']
        require(graph['context']['controller'] == report['cohort'] and graph['capacity'] == 2, 'graph context')
        fingerprint = sha((json.dumps(dict(production=report['source_hashes'], client=report['client_source_hashes'],
                      env_sha256=report['user_env_sha256']), indent=2,sort_keys=True)+'\n').encode())
        require(graph['context']['source_fingerprint'] == fingerprint, 'source/client/environment fingerprint')
        for instrument, expected in graph['instrument_hashes'].items():
            require(sha((control/instrument).read_bytes()) == expected, 'instrument changed')
        definition = {k:v for k,v in graph.items() if k != 'instrument_paths'}
        require(key(definition, wave) == wave['condition'], 'condition hash')
        require(key({k:graph[k] for k in ('version','context','final_check','instrument_hashes')}, wave)
                == wave['batch_condition'], 'batch hash')
        require(all(e.get('session_id') == sample['session'] for e in events), 'stream session binding')
        inits = [e for e in events if e.get('subtype') == 'init']
        require(len(inits) == 2, 'two phase init receipts')
        for e in inits:
            require(e['model'] == 'MiniMax-M3.1-Flash' and e['claude_code_version'] == '999.0.0-local', 'actual runtime/model')
            require(e['skills'].count('goal-loop-host:goal-loop') == e['slash_commands'].count('goal-loop-host:goal-loop') == 1,
                    'actual namespaced skill registry')
            require(any(p['name'] == 'goal-loop-host' and p['path'] == '/Users/m/repo/goal-loop'
                        and p['source'] == 'goal-loop-host@inline' for p in e['plugins']), 'inline plugin loaded')
        results = [e for e in events if e['type'] == 'result']
        require(results[0]['result_sha256'] == sha(b'READY') and results[0]['is_error'] is False, 'bootstrap READY receipt')
        prompt = load(folder/'prompt-receipt.json')['origin']
        require(prompt['session'] == sample['session'] and prompt['kind'] == 'prompt'
                and manifest['host_origin']['monotonic'] <= prompt['monotonic'], 'actual prompt receipt')
        batches, event_batches = {}, []
        for e in events:
            if e['type'] != 'assistant' or e.get('parent_tool_use_id') is not None:
                continue
            calls = [c for c in e['content'] if c['type'] == 'tool_use']
            if calls:
                require(e['message_id'], 'missing real parent message_id')
                event_batches.append(calls)
                bucket = batches.setdefault(e['message_id'], {})
                for c in calls:
                    if c['id'] in bucket:
                        require(bucket[c['id']] == c, 'conflicting repeated call_id')
                    bucket[c['id']] = c
        calls = [c for bucket in batches.values() for c in bucket.values()]
        parent_ok = (len(calls) == len(briefs) and all(c['name'] in ('Agent','Task')
                     and c['input'].get('subagent_type') == 'goal-loop-host:goal-worker'
                     and c['input'].get('run_in_background') is not True and 'model' not in c['input']
                     and 'effort' not in c['input'] for c in calls)
                     and all(sum(c['input']['prompt'].startswith(b['header']+'\n') for c in calls) == 1 for b in briefs)
                     and (sample['mode'] != 'crew' or any(len(b) == 2 for b in batches.values())))
        require(parent_ok, 'actual parent dispatch protocol')
        workers = []
        for brief, attempt in zip(briefs, attempts):
            require(attempt == sealed(folder/'host-attempts-before-validation'/('attempt-'+attempt['id']+'.json')),
                    'pre-validation attempt binding')
            require(attempt['run'] == chain[0]['run'] and attempt['session'] == sample['session']
                    and attempt['id']+':'+attempt['nonce'] == brief['ticket'], 'ticket/session/nonce binding')
            call = next(c for c in calls if c['id'] == attempt['call_id'])
            require(call['input']['prompt'].startswith(brief['worker_prefix']), 'worker header/prefix changed')
            starts = [e for e in events if e.get('subtype') == 'task_started' and e.get('tool_use_id') == attempt['call_id']]
            require(len(starts) == 1 and starts[0]['task_id'] == attempt['agent_id'], 'actual Agent ID')
            activity = [e for e in events if e.get('parent_tool_use_id') == attempt['call_id']]
            worker_calls = [dict(c, observed_monotonic=e['observed_monotonic']) for e in activity
                            for c in e.get('content',[]) if c['type'] == 'tool_use']
            terminal = [e for e in events if e.get('subtype') == 'task_notification'
                        and e.get('tool_use_id') == attempt['call_id']]
            if attempt['phase'] == 'returned':
                require(len(terminal) == 1 and terminal[0]['status'] == 'completed'
                        and terminal[0]['task_id'] == attempt['agent_id'], 'actual native completion')
                require(any(e.get('tool_use_result_metadata',{}).get('status') == 'completed'
                            and e['tool_use_result_metadata']['agentId'] == attempt['agent_id']
                            and attempt['call_id'] in e['tool_use_ids'] for e in events
                            if isinstance(e.get('tool_use_result_metadata'), dict)), 'structured completion')
            else:
                require(not terminal and wave['jobs'][attempt['task']]['returned'] is None, 'invented terminal')
            tool_results = {r['tool_use_id']:r for e in activity for r in e.get('tool_results',[])}
            allowed = {str(Path(attempt['project'])/n) for n in attempt['files']+['TASK.md','public.py']}
            direct_scope = [dict(call_id=c['id'], tool=c['name'], path=c['input'].get('file_path') or c['input'].get('path'),
                                 result=tool_results.get(c['id'])) for c in worker_calls
                            if c['name'] in ('Read','Write','Edit','Grep')
                            and (c['input'].get('file_path') or c['input'].get('path')) not in allowed
                            and not (sample['mode'] == 'fused' and c['name']=='Grep'
                                     and c['input'].get('path') == str(Path(attempt['project'])/'auditlog'))]
            command_calls = [c for c in worker_calls if c['name']=='Bash']
            unprefixed = [dict(call_id=c['id'], command=c['input']['command'], result=tool_results.get(c['id']))
                         for c in command_calls if not c['input']['command'].startswith(brief['tool_prefix'])
                         and c['input']['command'] != brief['check_command']]
            notable_shell = [dict(call_id=c['id'], command=c['input']['command'], result=tool_results.get(c['id']))
                             for c in command_calls if any(t in c['input']['command']
                             for t in ('/.goal','auditlog_scratch',' -B -c '))]
            other_owned = set(starters)-set(attempt['files'])
            shell_cross_reads = [dict(call_id=c['id'],command=c['input']['command'],result=tool_results.get(c['id']))
                                 for c in command_calls if 'cat ' in c['input']['command']
                                 and any(str(Path(attempt['project'])/n) in c['input']['command'] for n in other_owned)]
            job = wave['jobs'][attempt['task']]
            workers.append(dict(task=attempt['task'], call_id=attempt['call_id'], wire_name=call['name'],
                agent_id=attempt['agent_id'], nonce=attempt['nonce'], phase=attempt['phase'],
                ready_monotonic=attempt['ready']['monotonic'], ready_to_host_return_seconds=(
                    wave['origin']+job['returned']-attempt['ready']['monotonic'] if job['returned'] is not None else None),
                terminal_monotonic=wave['origin']+job['returned'] if job['returned'] is not None else None,
                last_worker_activity_monotonic=max(e['observed_monotonic'] for e in activity),
                first_tool_call_id=worker_calls[0]['id'], first_tool_exact_ready=(worker_calls[0]['name']=='Bash'
                    and worker_calls[0]['input']['command'] == brief['owned_ready_command']),
                first_tool_command=worker_calls[0]['input'].get('command'), first_tool_result=tool_results.get(worker_calls[0]['id']),
                direct_scope_deviations=direct_scope, shell_without_exact_owned_prefix=unprefixed,
                notable_shell_deviations=notable_shell, shell_reads_other_job_files=shell_cross_reads,
                worker_subagent_calls=[c['id'] for c in worker_calls if c['name'] in ('Agent','Task')]))
        host_events = [sealed(p) for p in (folder/'host-events').glob('*.json')]
        require(any(e['event']=='SessionEnd' and e['session']==sample['session'] for e in host_events), 'SessionEnd receipt')
        overlap = None
        if len(workers) == 2:
            overlap = max(0, min(w['terminal_monotonic'] if w['terminal_monotonic'] is not None
                                else w['last_worker_activity_monotonic'] for w in workers)
                          - max(w['ready_monotonic'] for w in workers))
        observations.append(dict(case=name, status=sample['status'], wave=wave['id'], condition=wave['condition'],
            batch_condition=wave['batch_condition'], original_report_protocol_ok=sample.get('protocol_ok'),
            original_report_has_protocol_ok='protocol_ok' in sample,
            original_event_batch_crew_requirement=(sample['mode']!='crew' or any(len(b)==2 for b in event_batches)),
            reconstructed_parent_batch_protocol_ok=parent_ok,
            parent_batches=[dict(message_id=m, wire_names=[c['name'] for c in cs.values()], call_ids=list(cs)) for m,cs in batches.items()],
            workers=workers, ready_overlap_lower_bound_seconds=overlap, full_ready_overlap_unknown=any(w['phase']!='returned' for w in workers),
            cli_returncode=sample['cli_returncode'], final_cli_result={k:results[-1].get(k) for k in
                ('subtype','is_error','errors','total_cost_usd','num_turns')}, quality=wave['quality'],
            elapsed=wave['elapsed'], worker_seconds=wave.get('worker_seconds'),
            namespace_registered=True, explicit_bootstrap_in_frozen_driver=True, skill_command_field_retained=False))
    single = next(w for w in waves if w['trial']=='single-1')
    crew = next(w for w in waves if w['trial']=='crew-1')
    job, final = single['jobs']['T1'], single['final_validation']
    require(job['returned'] < job['validations'][0]['start'] <= job['first_valid'] < job['adopted'] < final['start'],
            'terminal/independent validate/first_valid/adopt/final order')
    require(job['validations'][0]['result'] == final['result'] == 0 and job['first_valid'] == job['validations'][0]['end'],
            'recorded independent validation')
    require(final['command_sha256'] == sha(encode(single['graph']['final_check'])), 'frozen final command')
    require(job['adopted_digest'] == final['digest'] == scope(base/'single-1/artifact', starters), 'adopted artifact bytes/modes')
    graded = json.loads(final['stdout'])
    require(graded['ok'] is True and graded['error'] is None and len(graded['checks']) == 21
            and all(c['pass_'] is True for c in graded['checks']), 'retained final grader checks')
    require(crew['finished'] is None and crew['final_validation'] is None and crew['quality'] is None
            and all(j['adopted'] is None and not j['validations'] for j in crew['jobs'].values()), 'unknown wave falsely accepted')
    require(scope(base/'crew-1/partial-artifact', starters) == scope(work, starters), 'partial artifact not preserved')
    require(single['batch_condition'] == crew['batch_condition'] and single['condition'] != crew['condition'], 'comparison identity')
    require(report['planner'] == dict(executed=False,reason='incomplete/unknown/stale cohort; no qualified baseline reset')
            and report['baseline_restored'] is False, 'planner/reset used incomplete cohort')
    lifecycle = [s for s in spans if s['label']=='host-lifecycle']
    require(all(s['state']=='running' and s['result'] is None and s['finished'] is None for s in lifecycle),
            'lifecycle unknown represented as completed')
    liveness = load(liveness_path)
    require(liveness['recorded_supervisor_pids'] == [11581,13022]
            and not liveness['recorded_pids_still_present'] and not liveness['matching_session_processes'],
            'later exact local process observation')
    return dict(evidence_consistent=True, complete_comparison=False, net_benefit_established=False,
        evidence_root=str(base), input_inventory_sha256=sha(inventory_path.read_bytes()),
        checker_sha256=sha(Path(__file__).read_bytes()), raw_report_sha256=sha((base/'report.json').read_bytes()),
        retained_raw_archive=archive_check,
        all_six_slots=[{k:s.get(k) for k in ('case','mode','status','quality','reason')} for s in report['samples']],
        dispatched=observations, budget=dict(requested_seconds=900, suite_elapsed=report['suite_elapsed'],
            generations=chain, deadline_extended=False, ended_before_mechanical_deadline=True,
            stop_trigger='CLI-reported local USD estimate cap, not mechanical timeout or supplier billing'),
        condition_coverage=dict(fused=1,crew=1,planned_each=3,completed_fused=1,completed_crew=0),
        single_final_recorded_checks=graded['checks'], grader_rerun=False,
        parent_batch_correction_changes_neither_worker_deviations_nor_unknown_terminal=True,
        planner=report['planner'], baseline_restored=False, tokens=None, money=None,
        host_lifecycle_unknown_span_count=len(lifecycle),
        runtime_failures=[dict(id=s['id'],label=s['label'],result=s['result']) for s in spans if s['result'] not in (None,0)],
        later_separate_liveness=dict(source=str(liveness_path),sha256=sha(liveness_path.read_bytes()),observation=liveness,
            native_completion_proven=False,remote_inference_absence_proven=False),
        limits=['No new models, production imports, tests, grader rerun or raw mutation.',
                'Namespaced init registry and frozen bootstrap literal retained; processed skill_command field/body not retained.',
                'T1 crew native terminal unknown; overlap is an observed activity-window lower bound, not a completed duration.',
                'CLI cumulative USD estimate and worker metadata are not supplier bills or complete token accounting.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=Path('/tmp/goal-w5-claude-auditlog-new-independent-frozen'))
    parser.add_argument('--inventory', type=Path, default=Path(__file__).with_name('w5-headless-independent-inputs.json'))
    parser.add_argument('--liveness', type=Path, default=Path('/tmp/goal-w5-claude-auditlog-new-owned-liveness.json'))
    args = parser.parse_args()
    print(json.dumps(main(args.base,args.inventory,args.liveness), indent=2,sort_keys=True))
