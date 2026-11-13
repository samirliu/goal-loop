#!/usr/bin/env python3
"""Read only the two retained claude-haha integration recordings.

No production imports, policy execution, model calls, or report-status oracle.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path


GRADER_SHA256 = 'ad524844a1830c428fbd35fd83f9ce46b8340d3f35412dd0c760b9b251ca0b8d'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('ascii')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def sealed(path):
    value = load(path)
    require(value['sha256'] == digest(encoded(value['payload'])), 'receipt checksum: '+str(path))
    return value['payload']


def one(values, label):
    require(len(values) == 1, 'expected one '+label)
    return values[0]


def inventory(root):
    values = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            values[str(path.relative_to(root))] = dict(symlink=os.readlink(path))
        elif path.is_file():
            values[str(path.relative_to(root))] = digest(path.read_bytes())
    return dict(files=len(values), sha256=digest(encoded(values)))


def inspect(root, repo, clean):
    root = root.resolve()
    before = inventory(root)
    work, control = root/'work', root/'control'
    manifest, events = load(root/'manifest.json'), load(root/'events.json')
    report, begin, brief = (load(root/name) for name in ('report.json', 'begin.json', 'brief.json'))
    state = work/'.goal'
    host = [sealed(path) for path in (state/'evidence/host').glob('*.json')]
    spans = [sealed(path) for path in (state/'evidence/runtime').glob('*.json')]
    attempt = one([value for value in host if 'nonce' in value], 'host attempt')
    wave = sealed(one(list((state/'evidence/crew').glob('*.json')), 'crew wave'))
    runner = load(state/'runner.json')
    session, origin = manifest['session'], manifest['started_monotonic']
    require(all(e.get('session_id') == session for e in events), 'stream session mismatch')
    require(begin['session'] == attempt['session'] == session and begin['run'] == attempt['run'] == runner['run'],
            'run/session binding mismatch')
    require(Path(attempt['project']).resolve() == work and attempt['backend'] == 'claude', 'project/backend binding')
    inits = [event for event in events if event.get('subtype') == 'init']
    require(inits and all(event['claude_code_version'] == '999.0.0-local' for event in inits), 'runtime identity')
    require(all(event['model'] == 'MiniMax-M3.1-Flash' for event in inits), 'model identity')
    for event in inits:
        plugin = one([p for p in event['plugins'] if p['name'] == 'goal-loop-host'], 'loaded plugin')
        require(Path(plugin['path']).resolve() == repo and plugin['source'] == 'goal-loop-host@inline', 'plugin source')
        require('goal-loop-host:goal-worker' in event['agents'] and 'goal-loop' in event['skills'], 'roles/skill registration')
    require(Path(manifest['command'][0]) == Path(manifest['cli_entrypoint']), 'CLI command identity')
    require(digest(Path(manifest['cli_entrypoint']).read_bytes()) == manifest['cli_entrypoint_sha256'], 'CLI entrypoint hash')
    require(manifest['command'][manifest['command'].index('--plugin-dir')+1] == str(repo), 'plugin argument')
    skill = work/'.claude/skills/goal-loop/SKILL.md'
    require(skill.is_symlink() and skill.resolve() == repo/'SKILL.md', 'project SKILL link')
    responses = [e for e in events if e.get('subtype') == 'hook_response']
    require(all(e['exit_code'] == 0 and e['outcome'] == 'success' for e in responses), 'hook process failure')
    prompt = one([v for v in host if 'origin' in v], 'cached prompt')['origin']
    require(prompt == runner['origin'] and prompt['kind'] == 'prompt', 'cached origin not adopted')
    require(begin['scope'] == runner['scope'] == 'host-prompt-entry', 'origin scope')
    submits = [e for e in events if e.get('hook_event') == 'UserPromptSubmit']
    require(len(submits) == 4, 'expected two prompt hooks')
    require(origin+submits[0]['observed_elapsed'] <= prompt['monotonic'] <= origin+submits[1]['observed_elapsed'],
            'cached origin is not from first prompt')
    require(prompt['monotonic'] < origin+submits[2]['observed_elapsed'], 'second prompt reset origin')
    require(begin['deadline_monotonic'] == runner['monotonic']['deadline'], 'begin/runner deadline')
    require(brief['deadline_monotonic'] <= begin['deadline_monotonic']+1e-5 and wave['deadline'] <= brief['deadline_monotonic']+1e-5,
            'worker deadline extended')
    if clean:
        require(begin['deadline_monotonic'] <= origin+manifest['seconds']+1e-5, 'global cap was extended')
    tools = [(event, block) for event in events if event.get('type') == 'assistant'
             for block in event.get('content', []) if block.get('type') == 'tool_use']
    dispatch, task = one([(event, block) for event, block in tools if block['name'] in ('Task', 'Agent')], 'native dispatch')
    ticket = attempt['id']+':'+attempt['nonce']
    require(brief['ticket'] == ticket and brief['header'] == 'GOAL_HOST_TICKET '+ticket, 'nonce/header binding')
    require(task['input']['prompt'].startswith(brief['worker_prefix']) and task['input']['prompt'].splitlines()[0] == brief['header'],
            'worker prompt does not start with registered header')
    require(task['id'] == attempt['call_id'], 'native call binding')
    started = one([e for e in events if e.get('subtype') == 'task_started'], 'native started event')
    require(started['tool_use_id'] == task['id'] and started['task_id'] == attempt['agent_id']
            and started['prompt'] == task['input']['prompt'], 'native agent/call/prompt binding')
    lifecycle = [span for span in spans if span['label'] == 'host-lifecycle']
    start_receipt = one([span for span in lifecycle if span['host']['event'] == 'SubagentStart'], 'SubagentStart receipt')
    require(start_receipt['host']['agent_id'] == attempt['agent_id'], 'SubagentStart agent identity')
    ready = attempt['ready']['monotonic']
    bash = [(event, block) for event, block in tools if block['name'] == 'Bash']
    require(bash and bash[0][1]['input']['command'] == brief['owned_ready_command'], 'first command is not owned READY')
    require(origin+started['observed_elapsed'] <= ready and start_receipt['start_monotonic'] <= ready,
            'READY preceded native startup')
    require(all(event.get('parent_tool_use_id') == task['id'] for event, _ in bash), 'worker parent call mismatch')
    require(any(block['input']['command'] == brief['check_command'] for _, block in bash), 'named frozen check absent')
    completed = one([e for e in events if e.get('subtype') == 'task_notification'], 'native completion notification')
    require(completed['task_id'] == attempt['agent_id'] and completed['tool_use_id'] == task['id']
            and completed['status'] == 'completed', 'structured native completion binding')
    post = one([e for e in responses if e.get('hook_name') in ('PostToolUse:Agent', 'PostToolUse:Task')], 'dispatch post-hook')
    require(attempt['phase'] == attempt['outcome'] == 'returned' and len(attempt['receipts']) == 2, 'hook completion receipt')
    require(report['attempt_before_parent_validation'] == attempt, 'pre-validation completion snapshot differs')
    job = wave['jobs']['T1']
    validation = one(job['validations'], 'parent validation')
    require(wave['origin']+job['returned'] <= origin+post['observed_elapsed']+.1, 'return receipt follows post-hook')
    require(max(origin+post['observed_elapsed'], origin+completed['observed_elapsed']) < wave['origin']+validation['start'],
            'parent validation preceded native completion')
    require(validation['result'] == 0 and validation['end'] == job['first_valid'] <= job['adopted']
            <= wave['final_validation']['start'] <= wave['final_validation']['end'], 'validation/adoption order')
    require(wave['final_validation']['result'] == job['result'] == 0, 'independent validation failed')
    graph = load(control/'graph.json')
    require(digest((control/'grade.py').read_bytes()) == GRADER_SHA256 == wave['graph']['instrument_hashes']['grade.py'],
            'frozen grader bytes changed')
    require(all(wave['graph'][key] == graph[key] for key in graph), 'frozen graph differs from original control')
    command_hash = digest(encoded(graph['jobs'][0]['check']))
    require(validation['command_sha256'] == wave['final_validation']['command_sha256'] == command_hash, 'validation instrument changed')
    output = work/'out.txt'
    require(output.read_bytes() == b'READY\n', 'artifact is not exactly READY newline')
    scope = {'out.txt': [output.stat().st_mode & 0o7777, digest(output.read_bytes())]}
    require(scope == validation['digest'] == job['adopted_digest'] == wave['final_validation']['digest'], 'adopted artifact differs')
    require(attempt['after_sha256'] == digest(encoded(scope)) and attempt['before_sha256'] == digest(encoded(wave['baseline'])),
            'host artifact bindings differ')
    freeze_path, freeze_hash = (state/'check_freeze').read_text().strip().removesuffix(';').rsplit('=', 1)
    require(Path(freeze_path).resolve() == control/'grade.py' and
            freeze_hash == hashlib.sha1((control/'grade.py').read_bytes()).hexdigest()[:8], 'original check freeze changed')
    executions = [span for span in spans if span['label'] in ('host-owned-tool', 'host-worker-check')]
    for span in spans:
        require(span['contract_sha256'] == digest((state/'goal.md').read_bytes())
                and span['check_freeze_sha256'] == digest((state/'check_freeze').read_bytes()), 'runtime frozen contract changed')
        require(all(value == manifest['sources']['scripts/'+name] for name, value in span['instruments'].items()),
                'runtime instrument hashes differ from run manifest')
        require(span['command_sha256'] == digest(encoded(span['command'])), 'runtime command hash')
    complete = [span for span in executions if span['state'] == 'complete' and span['result'] == 0]
    if clean:
        require(len(executions) == len(complete) == 4, 'owned executions did not all finish successfully')
        require(all(span['parent'] == attempt['trace'] for span in executions), 'owned runtime parent')
        require(one([s for s in executions if s['label'] == 'host-worker-check'], 'named check')['command'] == graph['jobs'][0]['check'],
                'named check ran a different instrument')
        require(all(block['input']['command'].startswith(brief['tool_prefix']) or block['input']['command'] == brief['check_command']
                    for _, block in bash), 'unwrapped Bash in repaired run')
    else:
        require(len(complete) < len(executions) and any(e.get('hook_event') == 'PostToolUseFailure' for e in events),
                'old owned-command failure evidence missing')
    require(len(lifecycle) == 4 and all(span['state'] == 'running' and span['result'] is None
            and span['finished'] is None and span['elapsed'] is None for span in lifecycle), 'unknown lifecycle promoted to completion')
    require(any(v.get('event') == 'SessionEnd' for v in host), 'SessionEnd not persisted')
    require(not any(e.get('hook_event') == 'SessionEnd' for e in events), 'unexpected SessionEnd stream observation')
    require('SessionStart' not in load(repo/'hooks/hooks.json')['hooks'], 'SessionStart plugin attribution changed')
    errors = [error for event in events for error in event.get('tool_errors', [])]
    require(inventory(root) == before, 'recording changed during read-only check')
    return dict(recording=str(root), raw_inventory=before, session=session, native_call_id=task['id'], native_agent_id=attempt['agent_id'],
                runtime='999.0.0-local', model='MiniMax-M3.1-Flash', plugin='goal-loop-host@inline', cli_sha256=manifest['cli_entrypoint_sha256'],
                project_skill_link=os.readlink(skill), current_skill_sha256=digest((repo/'SKILL.md').read_bytes()),
                skill_text_selection='current root body not proven selected; local loader puts distinct user skill before project skill',
                recorded_namespaced_root_skill=any('goal-loop-host:goal-loop' in event['skills'] for event in inits),
                artifact_sha256=scope['out.txt'][1], grader_sha256=GRADER_SHA256,
                owned_executions=len(executions), successful_owned_executions=len(complete),
                unfinished_or_failed_owned=[dict(id=s['id'], label=s['label'], state=s['state'], result=s['result'])
                                           for s in executions if s not in complete],
                unknown_lifecycle_events=[s['host']['event'] for s in lifecycle],
                session_end='persisted host event; not emitted in captured stream',
                session_start='observed stream hook; not registered or credited to this plugin',
                retained_tool_errors=errors, captured_cli_elapsed=report['elapsed'],
                timeline_seconds_from_cli_start=dict(cached_prompt=prompt['monotonic']-origin, dispatch=dispatch['observed_elapsed'],
                    native_start=started['observed_elapsed'], ready=ready-origin, post_tool=post['observed_elapsed'],
                    native_completion=completed['observed_elapsed'], parent_validation=wave['origin']+validation['start']-origin,
                    first_valid=wave['origin']+job['first_valid']-origin, adopted=wave['origin']+job['adopted']-origin,
                    final_validated=wave['origin']+wave['final_validation']['end']-origin),
                structured_hook_body='not retained in full; stream call/agent/completion, post-hook, sealed host receipts cross-checked',
                clean_owned_execution=clean)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('--repo', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(dict(verified=True, checker_sha256=digest(Path(__file__).read_bytes()),
                         scope='two retained real integration recordings, not a performance cohort',
                         before=inspect(args.before, args.repo.resolve(), False), after=inspect(args.after, args.repo.resolve(), True)),
                     indent=2, ensure_ascii=True))
