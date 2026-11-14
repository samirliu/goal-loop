#!/usr/bin/env python3
"""Reconstruct policy qualification and complete deliveries, without the runner.

Default replay is data-only. --recheck-gates also runs the original acceptance
on extracted project copies; it never reruns tests, policies, models or trials.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SPEC = importlib.util.spec_from_file_location('paired_evidence', ROOT/'examples/evolution-dedupe/verify_agent.py')
stats = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stats)
require, sha = stats.require, stats.sha


def load(path):
    return json.loads(path.read_bytes())


def payload(path):
    envelope = load(path)
    require(set(envelope) == {'payload','sha256'}, 'invalid observation envelope')
    encoded = json.dumps(envelope['payload'], sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True).encode('ascii')
    require(hashlib.sha256(encoded).hexdigest() == envelope['sha256'], 'observation checksum changed')
    return envelope['payload']


def instruments(run, report):
    require(sha(run/'protocol.json')==report['frozen_manifest_sha256'], 'frozen manifest changed')
    require(sha(run/'runner.py')==report['runner_sha256'], 'runner changed')
    for name,digest in report['runtime_sources'].items():
        require(sha(run/name)==digest, 'runtime source changed: '+name)


def method(root, name):
    module, owner, label = name.split('.')
    path=root/'source/tests'/(module+'.py')
    classes={node.name:node for node in ast.parse(path.read_bytes()).body if isinstance(node,ast.ClassDef)}
    def find(owner):
        node=classes[owner]
        matches=[n for n in node.body if isinstance(n,ast.FunctionDef) and n.name==label]
        if matches:
            require(len(matches)==1, 'ambiguous test method')
            return (path.name,matches[0].lineno)
        parents=[base.id for base in node.bases if isinstance(base,ast.Name) and base.id in classes]
        require(len(parents)==1, 'unknown test inheritance')
        return find(parents[0])
    return find(owner)


def calibration(run, protocol, report, grader):
    value=report['calibration']
    expected=[(kind,index) for kind in ('good','bad') for index in range(len(protocol['calibration'][kind]))]
    require(value['status']=='passed' and all(protocol['calibration'].values())
            and [(row['kind'],row['index']) for row in value['cases']]==expected, 'incomplete calibration')
    for row in value['cases']:
        fixture=protocol['calibration'][row['kind']][row['index']]
        grade=grader(fixture)
        recorded=load(run/row['output'])
        require(recorded==grade and sha(run/row['output'])==row['output_sha256'], 'calibration output changed')
        eligible=grade['floor'] and grade['horizon']
        observed=dict(grade,ok=eligible,regression=not eligible,reason=None if eligible else 'floor-or-horizon')
        require(row['observed']==observed and row['grader_exit']==0 and row['matched'] is True
                and eligible==(row['kind']=='good'), 'false calibration pass')
    return value['elapsed']


def selection(state, report):
    selected = load(state/'enabled.json')
    require(selected == dict(version=report['version'],policy=report['enabled'],
        program='policies/'+report['enabled']+'.py',run=report['run'],protocol=report['protocol'],
        qualification=sha(state/report['run']/'report.json')), 'selection/qualification mismatch')
    require(sha(state/selected['program']) == selected['policy'], 'selected archive changed')
    return selected


def maximum_overlap(intervals):
    events = [(start,1) for start,end in intervals]+[(end,-1) for start,end in intervals]
    active, maximum = 0, 0
    for _,delta in sorted(events):
        active += delta;maximum = max(maximum,active)
    return maximum


def project_trace(raw, path, expected, gate_replay=False):
    value = load(path)
    require(value['case'] == expected['id'] and value['input_sha256'] == expected['input_sha256'], 'workflow input substituted')
    require(sha(raw/value['archive']) == value['archive_sha256'], 'project archive changed')
    with tempfile.TemporaryDirectory(prefix='goal-qualified-project-') as tmp:
        with tarfile.open(raw/value['archive']) as archive:
            archive.extractall(tmp,filter='data')
        project = Path(tmp)/'project'
        observation = value['observation']
        waves = list((project/'.goal/evidence/crew').glob('*.json'))
        require(len(waves)==1 and payload(waves[0])==observation, 'wave trace/ledger mismatch')
        require(observation['mode']==value['mode'], 'actual execution mode mismatch')
        require(set(observation['jobs'])=={'T1','T2','T3'} and observation['graph']['capacity']==3, 'worker scope changed')
        valid = True
        for index,names in enumerate(expected['jobs'],1):
            task='T'+str(index)
            source=load(project/('input-'+task+'.json'))
            result=load(project/('result-'+task+'.json'))
            require(source['tests']==names and result==value['results']['result-'+task+'.json'], 'requested/result tests changed')
            require(result['requested']==names and value['raw'][task]['result']==0, 'worker did not execute requested tests')
            actual = re.findall(r'^Ran ([0-9]+) tests? in ',value['raw'][task]['stderr'],re.M)
            require(actual and int(actual[-1])==len(names) and re.search(r'\nOK\s*$',value['raw'][task]['stderr']), 'missing real unittest completion')
            good = (type(result['ran']) is int and result['ran']==len(names) and result['successful'] is True
                    and all(type(result[k]) is int and result[k]==0 for k in ('failures','errors','skipped')))
            valid &= good
            row=observation['jobs'][task]
            require(row['dispatch'] is not None and row['started'] is not None and row['returned'] is not None
                    and row['result']==0 and row['validations'], 'incomplete worker lifecycle')
            require((row['adopted'] is not None)==good, 'unverified artifact adopted')
        require(valid is value['floor'] and valid is observation['quality'], 'workflow false completion')
        intervals=[]
        for item in (project/'.goal/evidence/runtime').glob('*.json'):
            span=payload(item)
            if span['kind']=='executor' and span['label'] in ('T1','T2','T3'):
                require(span['state']=='complete' and span['result']==0 and span['elapsed']>0, 'incomplete process span')
                intervals.append((span['start_monotonic'],span['start_monotonic']+span['elapsed']))
        require(len(intervals)==3, 'missing owned process measurements')
        width=maximum_overlap(intervals)
        require(width==1 if value['mode']=='inline' else 2<=width<=3, 'declared concurrency did not happen')
        if valid:
            receipts=[json.loads(line) for line in value['close'].splitlines() if line.startswith('{')]
            require(receipts and receipts[-1]['completion_verified'] is True, 'no original final receipt')
            require(set(receipts[-1]['checks'])=={'audit','gate'} and
                    all(row['result']==0 for row in receipts[-1]['checks'].values()), 'original acceptance failed')
            require(observation['final_validation']['result']==0,'final integrated check failed')
        else:
            require(expected.get('fault') is True and value['failed_verification']['result']==2, 'missing known-bad artifact refusal')
        if value['policy'] is not None:
            require(valid and value['mode']=='crew' and value['plan']['choice']=='crew', 'learned rule did not change execution')
            require(value['plan']['policy']['selection']==value['policy']==observation['policy']['selection'], 'consumed policy identity changed')
            require(sha(project/'.goal/proposals/learned'/value['policy']['program'])==value['policy']['policy'], 'different program consumed')
            require(sha(project/'.goal/proposals/learned'/value['policy']['run']/'report.json')==value['policy']['qualification'], 'different qualification consumed')
        if gate_replay:
            env={k:v for k,v in os.environ.items() if not k.startswith('GOAL_')}
            commands=[('audit',['bash',str(ROOT/'scripts/goal_audit.sh'),'--project',str(project)])] if valid else []
            commands.append(('gate',['bash',str(ROOT/'scripts/goal_gate.sh'),'--check' if valid else '--verify','--project',str(project)]))
            for label,command in commands:
                result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=20)
                require(result.returncode==0 if valid else result.returncode!=0,
                        'current original '+label+' disagrees with frozen artifact: '+result.stdout+result.stderr)
    return value


def verify_routing(root, recheck=False):
    study=root/'routing';state=study/'state';selected=load(state/'enabled.json')
    run=state/selected['run'];report=load(run/'report.json')
    protocol=stats.frozen_protocol(run,report,state)
    selection(state,report)
    instruments(run,report)
    sources=load(study/'sources.json')
    original=next(Path(name).parents[1] for name in sources if name.endswith('/scripts/goal_crew.py'))
    for name,digest in sources.items():
        require(sha(root/'source'/Path(name).relative_to(original))==digest, 'workflow source changed: '+name)
    require(len(sources)==74 and len(list((root/'source').rglob('*.*')))==74, 'incomplete workflow source archive')
    preregistration=load(study/'preregistration.json')
    require(preregistration['seed']==141601 and preregistration['retries']==0
            and protocol['minimum_pairs']==preregistration['pairs_per_phase']==6
            and protocol['minimum_cost_gain']==preregistration['minimum_cost_gain']==.15
            and protocol['trial_seconds']==preregistration['trial_seconds']==90
            and protocol['budget_seconds']==preregistration['budget_seconds']==900, 'evaluation thresholds changed')
    raw=[json.loads(line) for line in (run/'trials.jsonl').read_text().splitlines()]
    traces={p.name:load(p) for p in (study/'raw').glob('*.json')}
    used_traces=set();exposed=set();implementations=set()
    def grade_fixture(fixture):
        expected=load(run/'frozen'/fixture['expected'])
        output=(run/'frozen'/fixture['output']).read_bytes()
        if fixture['output'].startswith('bad-shape'):
            return dict(floor=False,horizon=False,score=0)
        else:
            matches=[name for name,t in traces.items() if t['case']==expected['id'] and t['output_sha256']==hashlib.sha256(output).hexdigest()]
            require(len(matches)==1,'calibration workflow missing/duplicated')
            value=project_trace(study/'raw',study/'raw'/matches[0],expected,recheck);used_traces.add(matches[0])
            return dict(floor=value['floor'],horizon=True,score=int(value['floor']))
    elapsed=calibration(run,protocol,report,grade_fixture)
    phases={}
    for phase in ('development','holdout'):
        record=report['phases'][phase];qualified=[]
        require(len(record['pairs'])==record['scheduled_pairs']==len(protocol[phase])==6,'incomplete phase')
        for index,pair in enumerate(record['pairs']):
            case=protocol[phase][index];expected=load(run/'frozen'/case['expected'])
            identity=sha(run/'frozen'/case['input'])
            require(pair['case']==identity==expected['input_sha256'] and identity not in exposed,'reused/misbound task')
            exposed.add(identity)
            for names in expected['jobs']:
                methods=[method(root,name) for name in names]
                require(not implementations.intersection(methods),'reused comparison method')
                implementations.update(methods)
            require(pair['order']==(['baseline','candidate'] if index%2==0 else ['candidate','baseline']),'paired order changed')
            row={}
            for side in ('baseline','candidate'):
                trial=pair[side];output=run/('%s-%s-%s.out'%(phase,index,side))
                require(sha(output)==trial['output_sha256'],'policy output changed')
                decision=load(output)
                require(decision['choice']==('baseline' if side=='baseline' else 'crew'),'no incremental action')
                matches=[name for name,t in traces.items() if t['case']==expected['id'] and t['output_sha256']==sha(output)]
                require(len(matches)==1,'missing/duplicate whole-workflow trial')
                value=project_trace(study/'raw',study/'raw'/matches[0],expected,recheck);used_traces.add(matches[0])
                require(value['mode']==('inline' if side=='baseline' else 'crew') and value['floor'] is True,'wrong or failed treatment')
                require(trial['worker_exit']==trial['grader_exit']==0 and trial['ok'] is True and trial['score']==1
                        and trial['floor'] is True and trial['horizon'] is True,'ineligible trial')
                require(json.loads(trial['grader_stdout'])==dict(floor=True,horizon=True,score=1),'grader false pass')
                require(hashlib.sha256(trial['grader_stdout'].encode()).hexdigest()==trial['grader_sha256'], 'grader output hash changed')
                require(value['elapsed_with_archive']<=trial['elapsed']<=protocol['trial_seconds'],'trial budget violation or omitted workflow cost')
                events=[r for r in raw if (r['phase'],r['index'],r['side'])==(phase,index,side)]
                require(len(events)==1 and events[0]['case']==identity and events[0]['result']==trial,'trial ledger mismatch')
                row[side]=dict(eligible=True,score=1,elapsed=trial['elapsed']);elapsed+=trial['elapsed']
            qualified.append(row)
        alpha=.05 if phase=='development' else .025
        phases[phase]=stats.compare(qualified,protocol,alpha,6,record['decision'])
        require(phases[phase]['pass_'],'cost benefit not established')
    require(len(raw)==24 and len(exposed)==12 and len(implementations)==72,'attempts or method coverage changed')
    require(set(load(state/'used-holdout.json'))==exposed and load(state/'statistical-budget.json')['evaluations']==1,'exposure/statistical history reset')
    require(report['holdout_evaluation']==1 and report['holdout_alpha']==.025,'wrong sequential alpha')
    require(elapsed<=report['elapsed']<=protocol['budget_seconds'] and report['within_budget'] is True,'run budget violation')
    later=load(study/'later-summary.json');cases=load(study/'later-cases.json');later_costs={'baseline':0,'learned':0}
    require(len(later['records'])==len(cases)==2,'missing later case')
    for index,(row,expected) in enumerate(zip(later['records'],cases)):
        require(row['case']==expected['id'] and row['order']==(['baseline','learned'] if index%2==0 else ['learned','baseline']),'later order changed')
        for names in expected['jobs']:
            methods=[method(root,name) for name in names]
            require(not implementations.intersection(methods),'later test was exposed');implementations.update(methods)
        for variant in ('baseline','learned'):
            matches=[name for name,t in traces.items() if t['case']==expected['id'] and (t['policy'] is not None)==(variant=='learned')]
            require(len(matches)==1,'missing later consumption')
            value=project_trace(study/'raw',study/'raw'/matches[0],expected,recheck);used_traces.add(matches[0])
            require(value['floor'] is True and (value['policy']==selected if variant=='learned' else value['policy'] is None),'different later policy consumed')
            require(row[variant]['grade']==dict(floor=True,horizon=True,score=1),'later grade changed')
            require(row[variant]['elapsed']>=value['elapsed_with_archive'],'later preparation/archiving omitted')
            later_costs[variant]+=row[variant]['elapsed']
    require(len(used_traces)==len(traces)==30,'an attempted workflow was omitted')
    return dict(pairs=12,complete_workflows=30,accepted_workflows=29,known_bad_artifacts_rejected=1,
                compared_test_implementations=72,later_new_implementations=12,
                development_gain=phases['development']['cost_gain'],holdout_gain=phases['holdout']['cost_gain'],
                later_costs=later_costs,later_gain=1-later_costs['learned']/later_costs['baseline'],
                learning_seconds=report['elapsed'],minimum_later_calls_to_repay_experiment_only=
                math.ceil(report['elapsed']/((later_costs['baseline']-later_costs['learned'])/2)))


def verify_upgrade(root):
    directory=root/'upgrade';state=directory/'state';current=load(state/'enabled.json');run=state/current['run'];report=load(run/'report.json')
    protocol=stats.frozen_protocol(run,report,state);selection(state,report)
    instruments(run,report)
    plan=load(directory/'plan.json');prior=load(directory/'prior-exposure.json')
    require(sha(directory/'prior-exposure.json')==plan['prior_exposure_sha256'],'prior exposure changed')
    require(current['policy']==plan['prior_pointer']['policy'] and 'qualification' not in plan['prior_pointer'],'archive changed rather than requalified')
    require(plan['prior_statistical_budget']['evaluations']==2 and report['holdout_evaluation']==3
            and report['holdout_alpha']==.05/12 and load(state/'statistical-budget.json')['evaluations']==3,'upgrade reset statistical history')
    def grade_fixture(fixture):
        expected=load(run/'frozen'/fixture['expected'])
        try:
            observed=load(run/'frozen'/fixture['output'])
            floor=observed==expected;horizon=type(observed) is list
        except ValueError:
            floor=horizon=False
        return dict(floor=floor,horizon=horizon,score=int(floor))
    elapsed=calibration(run,protocol,report,grade_fixture)
    raw=[json.loads(line) for line in (run/'trials.jsonl').read_text().splitlines()]
    exposed=set(prior);total=0
    for phase in ('development','holdout'):
        record=report['phases'][phase];qualified=[]
        require(len(record['pairs'])==record['scheduled_pairs']==20,'upgrade incomplete')
        for index,pair in enumerate(record['pairs']):
            case=protocol[phase][index];source=run/'frozen'/case['input'];identity=sha(source)
            require(identity==pair['case'] and identity not in exposed,'upgrade reused input')
            exposed.add(identity);gold=stats.oracle(load(source)['items'])
            require(load(run/'frozen'/case['expected'])==gold,'bad upgrade oracle')
            row={}
            for side in ('baseline','candidate'):
                output=run/('%s-%s-%s.out'%(phase,index,side))
                require(sha(output)==pair[side]['output_sha256'],'upgrade output changed')
                row[side]=stats.qualify(pair[side],output,gold)
                require(pair[side]['elapsed']<=protocol['trial_seconds'],'upgrade trial exceeded budget')
                elapsed+=pair[side]['elapsed']
                events=[r for r in raw if (r['phase'],r['index'],r['side'])==(phase,index,side)]
                require(len(events)==1 and events[0]['case']==identity and events[0]['result']==pair[side], 'upgrade trial ledger mismatch')
            qualified.append(row);total+=1
        require(stats.compare(qualified,protocol,.05 if phase=='development' else .05/12,20,record['decision'])['pass_'],'upgrade not qualified')
    require(set(load(state/'used-holdout.json'))==exposed and report['within_budget'] is True
            and len(raw)==80 and elapsed<=report['elapsed']<=protocol['budget_seconds'],'upgrade budget/exposure mismatch')
    return dict(pairs=total,same_program=True,statistical_evaluations_before=2,statistical_evaluations_after=3,
                holdout_gain=report['phases']['holdout']['decision']['cost_gain'])


def verify_benchmark(value):
    require(len(value['cases'])==6, 'missing hot-path comparison')
    for name,case in value['cases'].items():
        rows=case['pairs']
        require(len(rows)==15 and case['identities_equal'] is True, 'benchmark scope/identity changed')
        for index,row in enumerate(rows):
            require(row['order']==(['before','after'] if index%2==0 else ['after','before'])
                    and all(type(row[k]) in (int,float) and math.isfinite(row[k]) and row[k]>0
                            for k in ('before','after')), 'invalid benchmark pair')
        gain=1-sum(row['after'] for row in rows)/sum(row['before'] for row in rows)
        require(math.isclose(gain,case['cost_gain']) and
                sum(row['after']<row['before'] for row in rows)==case['after_faster_pairs'], 'benchmark aggregation changed')
        require(case['median_seconds']=={k:statistics.median(row[k] for row in rows) for k in ('before','after')}, 'benchmark median changed')
    return {name:case['cost_gain'] for name,case in value['cases'].items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--recheck-gates',action='store_true');args=parser.parse_args()
    archive=load(HERE/'archive.json');require(sha(HERE/archive['file'])==archive['sha256']
        and (HERE/archive['file']).stat().st_size==archive['bytes'],'archive checksum mismatch')
    with tempfile.TemporaryDirectory(prefix='goal-qualified-replay-') as tmp:
        with tarfile.open(HERE/archive['file']) as bundle:bundle.extractall(tmp,filter='data')
        root=Path(tmp);result=dict(verified=True,routing=verify_routing(root,args.recheck_gates),upgrade=verify_upgrade(root),
                                  hot_paths=verify_benchmark(load(HERE/'benchmark.json')),
                                  original_acceptance_rechecked=args.recheck_gates)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
