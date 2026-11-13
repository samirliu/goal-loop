#!/usr/bin/env python3
"""Screen one existing scoped routing hypothesis; do not activate a policy."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('candidate_audit_crew', ROOT/'scripts/goal_crew.py')
crew = importlib.util.module_from_spec(spec); spec.loader.exec_module(crew)
IDENTITY = '2fece5c96df63e69a1ad247f4e5965608bc816422520794351676f86ee23444f'


def audit():
    began = time.monotonic()
    archive = ROOT/'docs/evals/learning-edge-20261113/mechanism-run.tar.xz'
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    prefix = 'mechanism/project/.goal/proposals/routing/'
    with tarfile.open(archive) as source:
        candidate = source.extractfile(prefix+'policies/'+IDENTITY+'.py').read()
        selection = source.extractfile(prefix+'enabled.json').read()
        statistics = source.extractfile(prefix+'statistical-budget.json').read()
    if hashlib.sha256(candidate).hexdigest() != IDENTITY:
        raise RuntimeError('archived candidate identity changed')
    proposal_seconds = time.monotonic()-began
    trigger = ROOT/'docs/evals/native-host/claude-haha/w5-headless-v3/report.json'
    with tempfile.TemporaryDirectory(prefix='goal-routing-screen-') as temporary:
        root = Path(temporary); state = root/'.goal'
        def ctl(*args):
            result = subprocess.run(['bash', str(ROOT/'scripts/goal_ctl.sh'), *args, '--project', str(root)],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError(result.stdout+result.stderr)
        ctl('init')
        (root/'verify.py').write_text('from pathlib import Path\n'
            'raise SystemExit(0 if all(Path(n+".out").read_bytes()==Path(n+".in").read_bytes() for n in ("a","b")) else 1)\n')
        for n in ('a', 'b'):
            (root/(n+'.in')).write_text(n.upper())
        (state/'goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | exact copies | check: `python3 verify.py` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
        ctl('stamp', '--auto', '--time-budget=60')
        graph = dict(version=2, context={'workload':'two-copies'}, capacity=2,
            inputs=['a.in','b.in'], instruments=[str(root/'verify.py')],
            jobs=[dict(id='T'+str(i), files=[n+'.out'], inputs=[n+'.in'], deps=[],
                       check=[sys.executable, 'verify.py']) for i,n in enumerate(('a','b'), 1)],
            final_check=[sys.executable, 'verify.py'])
        path = state/'proposals/crew.json'; path.parent.mkdir(); path.write_text(json.dumps(graph))
        baseline_began = time.monotonic()
        baseline = crew.plan(root, path)
        baseline_seconds = time.monotonic()-baseline_began
        frozen, _, _ = crew.load_graph(path)
        payload = dict(version=1, context=frozen['context'], jobs=frozen['jobs'], capacity=frozen['capacity'],
                       inputs=crew.scope_digest(root, frozen['inputs']), instruments=frozen['instrument_hashes'],
                       contract=crew.store._hash((state/'goal.md').read_bytes()))
        candidate_began = time.monotonic()
        output, rc, reason, error = crew.evolution().run_program(candidate, crew.store._encode(payload), time.monotonic()+2)
        candidate_seconds = time.monotonic()-candidate_began
        if rc or reason:
            raise RuntimeError(dict(result=rc, reason=reason, error=error))
        decision = json.loads(output)
        if baseline['choice'] != 'serial' or decision['choice'] != 'serial' or not decision['match']:
            raise RuntimeError('screen no longer establishes duplicate behavior; inspect new evidence')
        # Actual product execution stays on the unmodified baseline. All output
        # bytes are checked by a separate frozen script and the original Gate.
        execute_began = time.monotonic()
        for n in ('a', 'b'):
            subprocess.run([sys.executable, '-I', '-c',
                'from pathlib import Path; import sys; n=sys.argv[1]; Path(n+".out").write_bytes(Path(n+".in").read_bytes())', n],
                cwd=root, check=True, timeout=5)
        checked = subprocess.run([sys.executable, '-I', str(root/'verify.py')], cwd=root, capture_output=True, timeout=5)
        if checked.returncode:
            raise RuntimeError('independent baseline check failed')
        ctl('close-iteration', '--operation-id', 'screen-baseline-only', '--task', 'T1', '--files', 'a.out b.out',
            '--checks-pass', '1', '--checks-fail', '0', '--checks-unverifiable', '0', '--progress', 'yes',
            '--exit-signal', 'yes', '--adversarial', 'clear', '--adversarial-note',
            'Separate frozen verifier checked both copies byte-for-byte against their declared immutable inputs.')
        baseline_execution_seconds = time.monotonic()-execute_began
        activated = list((state/'proposals').glob('*/enabled.json'))
        if activated:
            raise RuntimeError('an ineligible candidate was activated')
    if hashlib.sha256(archive.read_bytes()).hexdigest() != archive_hash:
        raise RuntimeError('historical policy archive changed')
    return dict(kind='one-candidate eligibility screen, not a paired utility trial', candidate=IDENTITY,
        trigger=dict(path=str(trigger.relative_to(ROOT)), sha256=hashlib.sha256(trigger.read_bytes()).hexdigest()),
        frozen_archive=dict(path=str(archive.relative_to(ROOT)), sha256=archive_hash,
            final_selection=json.loads(selection), statistical_budget=json.loads(statistics), history_changed=False),
        hypothesis='Avoid startup/coordination for two small independent copy jobs',
        baseline=baseline, candidate_decision=decision, behavior_difference=False,
        eligibility='rejected-duplicate-baseline', disposition='retain-baseline',
        scope='two-copies with two jobs and no comparable observed costs',
        falsifier='A matched independent task has a different baseline action and lower accepted-delivery cost under this candidate.',
        withdrawal='Any verified floor/horizon regression or held-out cost regression; use the existing state and testing budget.',
        costs=dict(proposal_artifact_read_seconds=proposal_seconds, proposal_model_seconds=None,
            baseline_plan_seconds=baseline_seconds, candidate_screen_seconds=candidate_seconds,
            baseline_execution_and_gate_seconds=baseline_execution_seconds, development_trials=0, holdout_trials=0,
            enabled_followup_trials=0, measured_screen_total_seconds=time.monotonic()-began,
            failures=0, timeouts=0, tokens=None, money=None),
        utility=dict(qualified_candidate=False, paired_real_deliveries=0, incremental_gain=None,
                     estimated_break_even_tasks=None, reason='No incremental action or proven positive saving; no finite payback established.'),
        controlled_mechanisms='Separate unittest fixtures cover plan/begin/prepare/terminal validation/adoption, mismatch, holdout regression, switch recovery and stale withdrawal.',
        real_utility_rows=[], new_model_calls=0)


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2, sort_keys=True))
