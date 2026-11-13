"""Reject forged pilot conclusions without changing any sealed input files."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
from unittest import mock


def require(value,message):
    if not value:raise RuntimeError(message)


def main(root,source):
    spec=importlib.util.spec_from_file_location('independent_entry',source)
    verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
    positive=verifier.verify(root)
    require(positive['accepted']==3 and positive['normal_deliveries']==3,'real pilot classification changed')
    original=verifier.read
    outcomes=[]
    for mutation in ('forged-missing-contract-go','source-hash-replaced','failed-position-dropped','deadline-flag-forged'):
        def altered(path):
            value=original(path)
            if mutation=='source-hash-replaced' and path.name=='source-hashes.json':
                value['after']['SKILL.md']='0'*64
            if path.name=='report.json':
                if mutation=='failed-position-dropped' and 'records' in value:
                    value['records']=[r for r in value['records'] if r['position']!=3]
                rows=value['records'] if 'records' in value else [value]
                for row in rows:
                    position=row.get('position',int(path.parent.name[0]) if path.parent.name[:1].isdigit() else None)
                    if mutation=='forged-missing-contract-go' and position==3:
                        row['accepted']=True
                        row['checks']['gate'].update(result=0,stdout='GATE: GO fabricated receipt\n')
                    if mutation=='deadline-flag-forged' and position==1:
                        entry=original(root/'1-before/manifest.json')['entry']
                        row['checks']['gate'].update(finished=entry+361,within_budget=True)
            return value
        rejected=False;reason=None
        with mock.patch.object(verifier,'read',side_effect=altered):
            try:verifier.verify(root)
            except RuntimeError as e:rejected=True;reason=str(e)
        require(rejected,'verifier accepted '+mutation)
        outcomes.append(dict(mutation=mutation,rejected=rejected,reason=reason))
    return dict(positive_verified=True,accepted=positive['accepted'],mutants=outcomes,
                scope='memory-only mutations; original SDK events, reports and frozen sources unchanged')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('trials',type=Path);p.add_argument('verifier',type=Path)
    p.add_argument('--output',type=Path);args=p.parse_args()
    value=main(args.trials.resolve(),args.verifier.resolve());text=json.dumps(value,indent=2,sort_keys=True)+'\n'
    if args.output:args.output.write_text(text)
    print(text,end='')
