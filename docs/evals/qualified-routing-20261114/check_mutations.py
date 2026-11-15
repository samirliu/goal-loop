#!/usr/bin/env python3
"""Exercise independent reconstruction against damaged copies of the evidence.

Copies use hard links; every changed file is replaced, never modified in place.
No experiment, worker test, model or policy is executed.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location('qualified_replay',HERE/'verify.py')
replay=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(replay)


def replace(path,value):
    temporary=path.with_name(path.name+'.mutation')
    temporary.write_bytes(value if isinstance(value,bytes) else (json.dumps(value,indent=2)+'\n').encode())
    temporary.replace(path)


def change(path,mutate):
    value=replay.load(path);mutate(value);replace(path,value)


def report(root,section,mutate):
    state=root/section/'state';selected=replay.load(state/'enabled.json')
    path=state/selected['run']/'report.json'
    change(path,mutate)
    selected['qualification']=replay.sha(path);replace(state/'enabled.json',selected)


def first_run(root,section='routing'):
    state=root/section/'state'
    return state/replay.load(state/'enabled.json')['run']


def invalid_calibration(root):
    run=first_run(root);path=run/'calibration-bad-0.out'
    replace(path,dict(floor=True,horizon=True,score=1))
    def reseal(value):
        row=value['calibration']['cases'][1]
        row['output_sha256']=replay.sha(path)
        row['observed']=dict(floor=True,horizon=True,score=1,ok=True,regression=False,reason=None)
    report(root,'routing',reseal)


def missing_trial(root):
    path=first_run(root)/'trials.jsonl'
    replace(path,('\n'.join(path.read_text().splitlines()[1:])+'\n').encode())


def false_bad_acceptance(root):
    path=next(p for p in (root/'routing/raw').glob('*.json')
              if replay.load(p)['case']=='calibration-bad-artifact')
    change(path,lambda value:value.update(floor=True))


def false_mode(root):
    path=next(p for p in (root/'routing/raw').glob('*.json')
              if replay.load(p)['policy'] is not None)
    change(path,lambda value:value.update(mode='inline'))


def main():
    archive=replay.load(HERE/'archive.json')
    replay.require(replay.sha(HERE/archive['file'])==archive['sha256'],'original archive changed')
    cases=[
        ('incomplete-phase-resealed','routing',lambda root:report(root,'routing',lambda value:value['phases']['holdout']['pairs'].pop())),
        ('false-benefit-resealed','routing',lambda root:report(root,'routing',lambda value:value['phases']['holdout']['decision'].update(cost_gain=.99))),
        ('false-calibration-resealed','routing',invalid_calibration),
        ('omitted-raw-trial','routing',missing_trial),
        ('changed-runtime','routing',lambda root:replace(first_run(root)/'goal_bounded.py',b'changed runtime\n')),
        ('changed-workflow-source','routing',lambda root:replace(root/'source/scripts/goal_crew.py',b'changed workflow\n')),
        ('known-bad-marked-accepted','routing',false_bad_acceptance),
        ('false-learned-execution-mode','routing',false_mode),
        ('omitted-consumption-cost','routing',lambda root:change(root/'routing/later-summary.json',lambda value:value['records'][0]['learned'].update(elapsed=.001))),
        ('reset-statistical-history','upgrade',lambda root:change(root/'upgrade/state/statistical-budget.json',lambda value:value.update(evaluations=1))),
        ('omitted-prior-exposure','upgrade',lambda root:change(root/'upgrade/prior-exposure.json',lambda value:value.pop())),
    ]
    records=[]
    with tempfile.TemporaryDirectory(prefix='goal-evidence-mutations-') as tmp:
        base=Path(tmp)/'base';base.mkdir()
        with tarfile.open(HERE/archive['file']) as bundle:bundle.extractall(base,filter='data')
        for label,section,mutate in cases:
            altered=Path(tmp)/label;shutil.copytree(base,altered,copy_function=os.link)
            mutate(altered)
            try:
                (replay.verify_routing if section=='routing' else replay.verify_upgrade)(altered)
            except replay.stats.VerificationError as exc:
                records.append(dict(case=label,rejected=True,reason=str(exc)))
            else:
                raise RuntimeError('independent replay accepted '+label)
            shutil.rmtree(altered)
    benchmark=copy.deepcopy(replay.load(HERE/'benchmark.json'))
    benchmark['cases']['large-context']['cost_gain']=.99
    try:
        replay.verify_benchmark(benchmark)
    except replay.stats.VerificationError as exc:
        records.append(dict(case='false-hot-path-aggregation',rejected=True,reason=str(exc)))
    else:
        raise RuntimeError('independent replay accepted false hot-path aggregation')
    print(json.dumps(dict(verified=True,cases=records),indent=2))


if __name__=='__main__':
    main()
