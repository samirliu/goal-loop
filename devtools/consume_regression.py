#!/usr/bin/env python3
"""Consume one qualified local rule on preregistered later regression cases."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('output already exists; preserve the earlier attempt')
    spec=importlib.util.spec_from_file_location('later_regression',ROOT/'examples/learning-regression/run.py')
    workflow=importlib.util.module_from_spec(spec);spec.loader.exec_module(workflow)
    cases=json.loads((args.experiment/'later-cases.json').read_bytes())
    expected=json.loads((args.experiment/'preregistration.json').read_bytes())['later_cases']
    if (type(expected) is not int or expected<=0 or not isinstance(cases,list)
            or len(cases)!=expected or len({case['id'] for case in cases})!=expected):
        parser.error('later cases must cover the nonempty preregistered set exactly')
    records=[]
    for index,case in enumerate(cases):
        order=['baseline','learned'] if index%2==0 else ['learned','baseline']
        row=dict(case=case['id'],order=order);records.append(row)
        for variant in order:
            row[variant]=dict(status='running',elapsed=None,grade=None)
            args.output.write_text(json.dumps(dict(records=records,all_attempts_retained=True),indent=2)+'\n')
            started=time.monotonic()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    grade=workflow.workflow(case,policy_state=args.experiment/'state' if variant=='learned' else None)
                row[variant].update(status='complete',grade=grade)
            except Exception as exc:
                row[variant].update(status='failed',error=str(exc))
            row[variant]['elapsed']=time.monotonic()-started
            args.output.write_text(json.dumps(dict(records=records,all_attempts_retained=True),indent=2)+'\n')
    successful=all(row[variant].get('grade')==dict(floor=True,horizon=True,score=1)
                   for row in records for variant in ('baseline','learned'))
    print(json.dumps(dict(accepted=successful,report=str(args.output),
                         scope='local complete workflows; no model or agent-provider cost claim')))
    return 0 if successful else 1


if __name__=='__main__':
    raise SystemExit(main())
