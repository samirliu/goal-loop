#!/usr/bin/env python3
"""Learn a bounded routing rule on complete, real repository-test workflows.

No model clients or agents. These are local subprocess test jobs; the baseline
is the original unknown-cost serial planner. It is not a native /goal eval.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASELINE = 'import json\nprint(json.dumps(dict(match=False,choice="baseline",reason="original planner")))\n'
CANDIDATE = '''import json,sys
v=json.load(sys.stdin)
m=(v['context'].get('workload')=='repo-regression' and
   v['context'].get('tests_per_job')==2 and len(v['jobs'])==3 and v['capacity']>=3 and
   v.get('instruments')==EXPECTED_INSTRUMENTS)
print(json.dumps(dict(match=m,choice='crew' if m else 'baseline',reason='qualified independent regression jobs')))
'''


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2)+'\n')


def workflow(case, output=None, policy_state=None):
    """Include preparation, policy consumption, processes, checks, close and GO."""
    costs = module('regression_costs', ROOT/'examples/crew-cost/run.py')
    crew = costs.crew
    started = time.monotonic()
    trace = dict(case=case['id'], input_sha256=case['input_sha256'],
                 output_sha256=hashlib.sha256((output or '').encode()).hexdigest(), policy=None)
    decision = json.loads(output) if output is not None else None
    if decision is not None and (not isinstance(decision, dict) or set(decision) != {'match','choice','reason'}
            or type(decision['match']) is not bool or decision['choice'] not in ('baseline','serial','crew')
            or not isinstance(decision['reason'], str) or not decision['reason']
            or (not decision['match'] and decision['choice'] != 'baseline')):
        return dict(floor=False, horizon=False, score=0)
    destination = Path(case['evidence']); destination.mkdir(parents=True, exist_ok=True)
    identity = case['id']+'-'+uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='goal-regression-workflow-') as tmp:
        project = Path(tmp)
        costs.ctl(project, 'init')
        state = project/'.goal'
        shutil.copy2(HERE/'task.py', project/'task.py')
        for index, tests in enumerate(case['jobs'], 1):
            write(project/('input-T%s.json' % index), dict(tests=tests, tests_root=str(ROOT/'tests')))
        (state/'goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | every requested test executes without failure, error or skip | '
            'check: `python3 -B task.py grade-all all` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
        outputs = ['result-T%s.json' % i for i in range(1,4)]
        (state/'work-plan.md').write_text('- [ ] T1 | execute and verify requested regression jobs | files='+','.join(outputs)+'\n')
        (state/'interfaces.md').write_text('Each Tn owns result-Tn.json; inputs and checker are read-only.\n')
        costs.ctl(project, 'stamp', '--auto', '--time-budget=120')
        proposals = state/'proposals'; proposals.mkdir(exist_ok=True)
        graph = dict(version=1, context=case['context'], capacity=3,
            inputs=['input-T%s.json'%i for i in range(1,4)], instruments=['../../task.py',*case['sources']],
            jobs=[dict(id='T%s'%i, files=[outputs[i-1]], deps=[],
                       check=[sys.executable,'-I','-B','task.py','grade','T%s'%i]) for i in range(1,4)],
            final_check=[sys.executable,'-I','-B','task.py','grade-all','all'])
        path = proposals/'crew.json'; write(path,graph)
        selected = None
        if policy_state is not None:
            selected = proposals/'learned'
            shutil.copytree(policy_state,selected)
        recommendation = crew.plan(project,path,policy_state=selected)
        require(recommendation['choice'] != 'stop','planner stopped before work')
        mode = 'crew' if recommendation['choice']=='crew' else 'inline'
        if decision is not None and decision['choice'] != 'baseline':
            mode = 'crew' if decision['choice']=='crew' else 'inline'
        # The actual learned selection is consumed again by begin/dispatch,
        # including qualification, scope, capacity and budget checks.
        result = costs.trial(project,path,graph,mode,identity,0,
                             fail='T1' if case.get('fault') else None,policy_state=selected)
        trace.update(plan=recommendation, mode=mode, observation=result['observation'], raw=result['raw'])
        if selected is not None:
            trace['policy'] = json.loads((selected/'enabled.json').read_bytes())
        floor = result['observation']['quality'] is True
        if floor:
            checked = subprocess.run([sys.executable,'-I','-B','task.py','grade-all','all'], cwd=project,
                                     capture_output=True, text=True, timeout=10)
            require(checked.returncode==0,'independent second pass failed')
            (state/'work-plan.md').write_text('- [x] T1 | executed and verified all requested tests | files='+','.join(outputs)+'\n')
            closed = costs.ctl(project,'close-iteration','--operation-id','workflow-close','--task','T1',
                '--files',','.join(outputs),'--checks-from-verify','--receipt','--progress','yes',
                '--exit-signal','yes','--adversarial','clear',
                '--adversarial-note','Re-ran grade-all after join: exact requested IDs and counts, zero skips/failures/errors')
            receipts = [json.loads(line) for line in closed.splitlines() if line.startswith('{')]
            require(receipts and receipts[-1].get('completion_verified') is True,'original receipt did not grant completion')
            trace['close'] = closed
        else:
            verification = subprocess.run(['bash',str(ROOT/'scripts/goal_gate.sh'),'--verify','--project',str(project)],
                                          capture_output=True,text=True,timeout=15)
            trace['failed_verification'] = dict(result=verification.returncode,stdout=verification.stdout,stderr=verification.stderr)
        trace['results'] = {name:json.loads((project/name).read_bytes()) for name in outputs}
        trace['elapsed'] = time.monotonic()-started
        with tarfile.open(destination/(identity+'.tar.gz'),'w:gz') as archive:
            archive.add(project,arcname='project',filter=lambda item:None if '__pycache__' in Path(item.name).parts else item)
        trace['archive'] = identity+'.tar.gz'; trace['archive_sha256'] = sha(destination/trace['archive'])
    trace['elapsed_with_archive'] = time.monotonic()-started
    trace['floor'] = floor
    write(destination/(identity+'.json'),trace)
    return dict(floor=floor,horizon=all(log['result']==0 for log in result['raw'].values()),score=int(floor))


def test_names():
    sys.path.insert(0,str(ROOT/'tests'))
    modules = ['test_context_actions','test_context_submit','test_crew','test_host',
               'test_incumbent','test_ledger_access','test_close_commit','test_mutation_commit','test_learning_flow']
    def flatten(suite):
        for item in suite:
            if isinstance(item,unittest.TestSuite):yield from flatten(item)
            else:yield item
    seen, names = set(), []
    for item in flatten(unittest.defaultTestLoader.loadTestsFromNames(modules)):
        code=getattr(type(item),item._testMethodName).__code__
        key=(code.co_filename,code.co_firstlineno)
        if key not in seen:
            seen.add(key);names.append(item.id())
    return sorted(names)


def prepare(output):
    output.mkdir(parents=True,exist_ok=False)
    public=output/'protocol';public.mkdir()
    write(output/'preregistration.json',dict(scope='complete repository-subset workflows; local process workers, no agents/models',
        pairs_per_phase=6,minimum_cost_gain=.15,trial_seconds=90,budget_seconds=900,
        selection='72 distinct comparison implementations plus 12 later; seeded shuffle; no cost-based holdout selection',
        seed=141601,later_cases=2,retries=0,learning_cost_accounting='record all preparation, trials, failures, checks and later consumption'))
    (public/'baseline.py').write_text(BASELINE)
    names=test_names();random.Random(141601).shuffle(names)
    require(len(names)>=84,'insufficient distinct repository methods')
    sources={str(p):sha(p) for directory in (ROOT/'scripts',ROOT/'tests',HERE,ROOT/'examples/crew-cost')
             for p in directory.iterdir() if p.is_file() and p.suffix in ('.py','.sh','.awk')}
    instruments=dict(sources,**{'../../task.py':sha(HERE/'task.py')})
    (public/'candidate.py').write_text('EXPECTED_INSTRUMENTS='+repr(instruments)+'\n'+CANDIDATE)
    grader=("import contextlib,hashlib,importlib.util,io,json,sys\nfrom pathlib import Path\n"
        +"sources="+repr(sources)+"\n"
        +"def verify():\n for p,h in sources.items():\n  if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h: raise RuntimeError('frozen workflow source changed')\n"
        +"verify()\nspec=importlib.util.spec_from_file_location('workflow',"+repr(str(HERE/'run.py'))+")\n"
        +"m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\nv=json.load(sys.stdin)\n"
        +"with contextlib.redirect_stdout(io.StringIO()): result=m.workflow(json.loads(v['expected']),v['output'])\n"
        +"verify()\nprint(json.dumps(result))\n")
    (public/'grader.py').write_text(grader)
    config=dict(version=1,baseline='baseline.py',candidate='candidate.py',grader='grader.py',development=[],holdout=[],
                minimum_pairs=6,minimum_cost_gain=.15,quality_tolerance=0,trial_seconds=90,budget_seconds=900,calibration={'good':[],'bad':[]})
    all_cases=[]
    for index in range(14):
        label=('development' if index<6 else 'holdout' if index<12 else 'later')+'-'+str(index)
        context=dict(workload='repo-regression',tests_per_job=2,instance=label)
        task=dict(context=context,jobs=[dict(id='T%s'%i) for i in range(1,4)],capacity=3,instruments=instruments)
        raw=json.dumps(task,sort_keys=True).encode()
        case=dict(id=label,context=context,jobs=[names[index*6+j*2:index*6+j*2+2] for j in range(3)],
                  evidence=str(output/'raw'),input_sha256=hashlib.sha256(raw).hexdigest(),sources=sources)
        (public/(label+'.input.json')).write_bytes(raw);write(public/(label+'.expected.json'),case)
        all_cases.append(case)
        if index<12:
            config['development' if index<6 else 'holdout'].append(dict(input=label+'.input.json',expected=label+'.expected.json'))
    # Known bad artifact must be rejected after real worker exits, alongside
    # a malformed-decision negative. They are not utility trial positions.
    cal=dict(all_cases[0],id='calibration',context=dict(workload='repo-regression',tests_per_job=1,instance='calibration'),
             jobs=[['test_store_observation.Observations.test_future_head_is_observed_by_same_store_instance']]*3)
    for label, decision, fault in [('good',dict(match=False,choice='baseline',reason='calibration'),False),
                                    ('bad-artifact',dict(match=False,choice='baseline',reason='calibration'),True),
                                    ('bad-shape',dict(match=True,choice='invalid',reason='calibration'),False)]:
        write(public/(label+'.output.json'),decision)
        write(public/(label+'.expected.json'),dict(cal,fault=fault,id='calibration-'+label))
        config['calibration']['good' if label=='good' else 'bad'].append(dict(output=label+'.output.json',expected=label+'.expected.json'))
    write(public/'protocol.json',config);write(output/'later-cases.json',all_cases[12:]);write(output/'sources.json',sources)
    return public/'protocol.json'


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    protocol=prepare(args.output)
    if not args.prepare_only:
        subprocess.run([sys.executable,'-I',str(ROOT/'scripts/goal_evolve.py'),str(protocol),'--state',str(args.output/'state')],check=True)
