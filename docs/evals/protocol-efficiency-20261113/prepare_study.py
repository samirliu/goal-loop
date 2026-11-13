#!/usr/bin/env python3
"""Freeze this one native study. Never launches workers, clients or queues."""
import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import sys

REPO = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('capture', REPO/'devtools/native_eval_capture.py')
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n')


def prepare(base, output):
    private = base/'holdout-private'
    corpus = json.loads((private/'corpus.json').read_text())
    readiness = json.loads((base/'holdout-readiness.json').read_text())
    assert readiness['ready'] and len(corpus['cases']) == 6
    assert hashlib.sha256((private/'corpus.json').read_bytes()).hexdigest() == readiness['corpus_sha256']
    assert not (output/'freeze.json').exists(), 'Never replace a frozen study'
    cases = sorted(corpus['cases'], key=lambda x: x['id'])
    public_python = base/'runtime-public/bin/python'
    permutations = ['ABC', 'BCA', 'CAB', 'CBA', 'BAC', 'ACB']
    order = [dict(position=i*3+j+1, case=c['id'], family=c['family'], group=g)
             for i, (c, groups) in enumerate(zip(cases, permutations)) for j, g in enumerate(groups)]
    protocol = dict(version=1, frozen_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        baseline_commit='cc26e0b4d8e847d7bc64fd4ce3f09159ab5724cb',
        candidate_commit='76140262bab69f6e31c032cb1c2dd760a1bd3a3a',
        source_freeze='candidate-production-manifest.json',
        corpus_sha256=readiness['corpus_sha256'], groups={
            'A':'bare native host; normal tools and at most two native workers; no goal-loop duties',
            'B':'frozen baseline goal-loop; standard SKILL and manual close template',
            'C':'frozen candidate goal-loop plus explicit opt-in measured close and receipt'},
        causal_scope='A/C compares product workflows; B/C compares candidate+explicit opt-in, not code bytes alone.',
        actual_model='gpt-6.1-sol', effort='max', fork_turns='none',
        permissions=dict(approval_policy='never', sandbox_policy='danger-full-access'),
        tool_capability='Same native host and tool catalog; no secondary host/client/service/queue.',
        max_positions=18, default_serial=True, seconds=900, execution_seconds=780,
        verification_reserve_seconds=120, max_internal_workers=2, order=order,
        qualification=['same frozen independent behavior/upstream tests pass',
            'one normal nonempty native final and actual completed host task/descendants by execution deadline',
            'all preparation, tool/worker work and independent checks/report within original outer deadline',
            'unchanged frozen source/grader/immutable inputs; same actual model/effort/permissions',
            'goal-loop groups additionally pass original audit and emit original Gate GO'],
        main_cost='sum(actual elapsed seconds of ALL positions, including failures)/qualified deliveries; zero qualified => undefined',
        adoption=dict(any_of=[
            'C qualified >= A qualified+2 AND C qualified >= B qualified+2, no quality regression',
            'C qualified >= max(A,B) AND C cost/qualified <= 0.8*min(A cost/qualified,B cost/qualified)'],
            family_guard='benefit in >=2 families; every other family C cost/qualified <=1.10*better reference and no lower qualification',
            family_benefit='C family qualified >=both and either exceeds both or has lower cost/qualified than better reference',
            quality='same frozen grader, including genuine regressions, negative behaviors and compatibility requirements',
            default='Baseline remains default throughout; candidate is opt-in. No promotion or general stability claim without all gates.'),
        stopping=['no reruns, replacement cases/seeds, deadline extensions or posthoc eligibility rescue',
                  'interrupt still-active native work at execution deadline and collect actual terminal; late remains failed',
                  'stop real calls after position18; retain all startup/tool/timeout/cancel/no-final/late failures'],
        costs=['position elapsed','root evaluation worker span','internal worker-seconds',
               'research/tooling/development/holdout/follow-up costs separately',
               'tokens/fees/service compute unknown where unexposed; never zero'],
        limitations=['one pair per task/group; six public historical tasks, no general statistical stability',
            'pretraining familiarity cannot be excluded',
            'local native logs trusted but unsigned; opaque tool bodies remain unknown',
            'snapshot hashes cannot detect transient restored edits',
            'parent interruption/service stop latency remains separately observed/unknown'])
    write(output/'protocol.json', protocol)
    common_paths = [base/'sources/B', base/'sources/C', private/'grade.py', private/'corpus.json',
        private/'requirements.lock', private/'runtime', base/'runtime-public',
        base/'runtime-public-identity.json', Path(public_python.resolve()),
        output/'protocol.json', Path(__file__).resolve()]
    common_frozen = {str(p): capture.fingerprint(p) for p in common_paths}
    manifests = {}
    for row in order:
        n, group = row['position'], row['group']
        c = next(c for c in cases if c['id'] == row['case'])
        position = base/'positions'/f'{n:03d}'
        position.mkdir(parents=True, exist_ok=False)
        work, collected = position/'work', position/'capture'
        source = base/'sources'/group
        common = f'''Deliver the business request in {work}/TASK.md in this fresh workspace.
Your business project is {work}. Set every shell/tool cwd explicitly to it.
Read TASK.md and the real source, implement the complete requirements, add focused tests when useful, run meaningful existing checks, review, and give a concise normal final report with actual test results and remaining limitations.
Use prepared TASK_PYTHON={public_python}; dependencies are already installed. For business Python use -B (or PYTHONDONTWRITEBYTECODE=1), and disable pytest cache when useful. Do not install packages or alter the environment.
Actual original deadlines are in {collected}/ready.json: execution_deadline_epoch (finish work AND final before it), deadline_epoch (outer independent acceptance). Preparation/spawn/tool/worker overhead already counts. Never restart these clocks. Leave time for your review, any required settlement, and final. Do not wait for the independent collector after your final.
You may use at most two simultaneously active native internal workers if they help. Fresh native contexts and local tools only; no second host/model client/service/queue. Stop workers and observe actual terminal before your final. Do not fetch upstream solutions, contact external services, push/commit, or request confirmation.
Keep business edits within the package/tests scopes in TASK.md. Preserve TASK.md, verify_public.py, dependency/config/documentation inputs. Put any temporary business test helpers under allowed test scopes or your own /tmp scratch, not as unrelated project-root files.
Do not inspect other attempts, initial-source stores, private graders, corpus/proof records, historical solutions, parent goal state, or study results. You may read this prompt, your capture ready/identity, your project, prepared public runtime, native host metadata, and your group protocol source if applicable. No benchmark score, hidden answer or acceptance selector is provided. Work from the request and observed source.
'''
        if group == 'A':
            workflow = 'Workflow: normal bare native host execution. No goal-loop protocol or .goal bookkeeping is required. Use the same native worker capability only when justified by the remaining budget.\n'
        else:
            workflow = f'''Workflow: follow goal-loop at {source}/SKILL.md and its host/crew references as needed. Apply the original five invariants, actual review, booking, audit and Gate. Automatic execution and stamp --auto are already authorized.
Before business execution bind the actual native Codex identity from {collected}/identity.json (session_id is the unique actual thread ID; do not guess it or use runtime_session_id). Begin using goal_host.py with remaining ORIGINAL outer seconds from ready.json, then use the normal version-bound context map. All protocol preparation/reading counts inside the same clock. Use the public business check (TASK_PYTHON environment with prepared interpreter, verify_public.py) as a deterministic exit=N contract check, retaining the full business requirement and meaningful review/regression work. Do not mark work complete based on ticks or worker prose.
'''
            if group == 'C':
                workflow += 'This invocation explicitly opts into the candidate mechanical close: choose close_input.measured_template in the normal context map, author actual progress/exit/review fields in the same request path, regenerate context and run its close action. The original verifier derives counts and the same call runs the original fresh audit/Gate receipt. Do not manually transcribe counts or separately call receipt after a verified combined receipt. Recovery and exact-intent retry remain unchanged.\n'
        prompt = position/'prompt.md'
        prompt.write_text(common+'\n'+workflow)
        business_check = dict(name='independent', cwd=str(work), argv=[str(public_python), '-B',
            str(private/'grade.py'), '--case', c['id'], '--project', str(work),
            '--log-dir', str(position/'independent-acceptance')])
        checks = [business_check]
        if group != 'A':
            checks += [dict(name='audit', cwd=str(work), argv=['bash',str(source/'scripts/goal_audit.sh'),'--project',str(work)]),
                       dict(name='gate', cwd=str(work), argv=['bash',str(source/'scripts/goal_gate.sh'),'--check','--project',str(work)])]
        assets = [base/'initial'/c['id'], private/'cases'/c['id']/'validator',
            private/'cases'/c['id']/'validation.json', private/'cases'/c['id']/'input-manifest.json', prompt]
        frozen = dict(common_frozen)
        frozen.update({str(p):capture.fingerprint(p) for p in assets})
        manifest = dict(version=1, position=n, group=group, goal_loop=group!='A',
            agent_path=f'/root/efficiency_{n:03d}', parent_thread_id='01a1d348-5480-7601-ace5-8b01be0530a0',
            model='gpt-6.1-sol', effort='max', seconds=900, execution_seconds=780, max_internal_workers=2,
            initial_workspace=str(base/'initial'/c['id']), work=str(work),
            immutable_inputs=[v['relative_path'] for v in c['immutable_inputs']],
            frozen=frozen, artifacts=[str(work)], checks=checks)
        path=position/'manifest.json'; write(path,manifest)
        manifests[str(path)]=capture.sha(path)
    write(output/'freeze.json',dict(version=1,frozen_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        protocol_sha256=capture.sha(output/'protocol.json'), manifests=manifests,
        source_files={str(p):capture.sha(p) for p in (REPO/'devtools/native_eval_capture.py',Path(__file__).resolve())},
        evaluation_positions_started=0, real_model_calls_for_calibration=0))
    print(json.dumps(dict(frozen=True,positions=len(order),protocol=str(output/'protocol.json'),
                         protocol_sha256=capture.sha(output/'protocol.json')),sort_keys=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.base.absolute(),a.output.absolute())
