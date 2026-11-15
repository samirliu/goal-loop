#!/usr/bin/env python3
"""Local lifecycle diagnostic only: no model calls or delivery-effect claim."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trial(source, project, direct):
    project.mkdir()
    records=[]
    started=time.monotonic()

    def call(argv, phase, expected=0, request=None):
        before=time.monotonic()
        result=subprocess.run(argv, input=json.dumps(request) if request is not None else None,
                              cwd=project, capture_output=True, text=True, timeout=30)
        records.append(dict(command=argv, phase=phase, elapsed_seconds=time.monotonic()-before,
                            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
        assert result.returncode==expected, records[-1]
        return result

    def view():
        return json.loads(call(['bash', str(source/'scripts/goal_ctl.sh'), 'context',
                                '--project', str(project), '--auto'], 'protocol').stdout)

    def action(value, name, expected=0):
        return call(shlex.split(value['actions'][name]['command']), 'protocol', expected)

    argv=[sys.executable, '-I', str(source/'scripts/goal_host.py'), 'begin', str(project),
          'codex', 'explicit-local-mechanism-fixture', '120']
    if direct:
        argv+=['--context', '--auto']
        initial=json.loads(call(argv, 'protocol').stdout)['context']
    else:
        call(argv, 'protocol'); initial=view()
    template=initial['author_contract']['template']
    (project/'.goal/goal.md').write_text(template.replace('<outcome>', 'Repair answer').replace(
        '<yes/no statement>', 'answer equals the independent expected bytes').replace('<command>', 'python3 check.py'))
    (project/'.goal/work-plan.md').write_text('- [ ] T1 answer | owner=controller | files=answer\n')
    (project/'check.py').write_text('from pathlib import Path\nraise SystemExit(0 if Path("answer").read_bytes()==b"correct" else 1)\n')
    # Both paths must support an initially failing repair criterion.
    (project/'answer').write_bytes(b'wrong')
    authored=view()
    if direct:
        result=call(shlex.split(authored['submissions']['stamp']['command']), 'protocol')
        assert 'GATE: VERIFY AC-1|FAIL|' in result.stdout
    else:
        action(authored, 'verify', expected=2)
        action(view(), 'stamp')
    # Identical actual implementation and second-pass business check.
    (project/'answer').write_bytes(b'correct')
    (project/'.goal/work-plan.md').write_text('- [x] T1 answer | owner=controller | files=answer\n')
    call([sys.executable, '-B', 'check.py'], 'business-review')
    request=dict(progress='yes', exit_signal='yes', adversarial='clear',
                 adversarial_note='Actually executed check.py and reviewed exact answer bytes and checker source.')
    current=view()
    if direct:
        result=call(shlex.split(current['submissions']['close']['command']), 'protocol', request=request)
        submitted_fields=list(request)
    else:
        verification=action(current, 'verify')
        assert 'GATE: VERIFY AC-1|PASS|' in verification.stdout
        full=dict(current['close_input']['template'])
        full.update(request, checks_pass=1, checks_fail=0, checks_unverifiable=0)
        path=Path(current['close_input']['path']); path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(full))
        submitted_fields=list(full)
        action(view(), 'close')
        result=action(view(), 'receipt')
    receipts=[]
    for line in result.stdout.splitlines():
        try: value=json.loads(line)
        except ValueError: continue
        if isinstance(value, dict) and 'completion_verified' in value: receipts.append(value)
    assert len(receipts)==1 and receipts[0]['completion_verified']
    assert {k:v['result'] for k,v in receipts[0]['checks'].items()}=={'audit':0, 'gate':0}
    log=(project/'.goal/loop-log.md').read_text()
    assert log.count('## iteration')==1 and 'checks_pass=1\n' in log and 'checks_fail=0\n' in log
    return dict(path='direct-submit' if direct else 'documented-mapped-file-flow',
        elapsed_seconds=time.monotonic()-started,
        protocol_cli_calls=sum(r['phase']=='protocol' for r in records),
        protocol_cli_seconds=sum(r['elapsed_seconds'] for r in records if r['phase']=='protocol'),
        business_review_cli_calls=sum(r['phase']=='business-review' for r in records),
        model_submitted_fields=submitted_fields,
        model_authored_proposal_files=0 if direct else 1,
        completion_verified=True, records=records)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', required=True, type=Path)
    p.add_argument('--candidate', required=True, type=Path)
    p.add_argument('--work', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a=p.parse_args()
    assert not a.work.exists()
    a.work.mkdir()
    order=['baseline', 'candidate', 'candidate', 'baseline', 'baseline', 'candidate']
    sources={name:{str(path.relative_to(root)):digest(path) for path in sorted((root/'scripts').iterdir())
                   if path.is_file() and path.suffix in ('.py', '.sh', '.awk')}
             for name,root in [('baseline',a.baseline),('candidate',a.candidate)]}
    protocol=dict(kind='Local program-lifecycle diagnostic, no model or real-task utility evidence',
        source_hashes=sources, order=order, model_calls=0, real_complex_tasks=0,
        quality='Identical failing repair fixture, actual repair and second-pass check, original receipt/audit/Gate pass',
        metric='All local lifecycle seconds and external protocol CLI calls; not measured model turns, tokens, or billed cost',
        limits='Compares documented mapped file workflow; legacy low-level commands can be manually batched. This is not a lower bound on host calls or proof of end-to-end savings.')
    a.output.parent.mkdir(exist_ok=True)
    a.output.with_suffix('.protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    rows=[]
    for index,name in enumerate(order,1):
        row=trial(a.candidate if name=='candidate' else a.baseline,a.work/f'{index:03d}-{name}',name=='candidate')
        row['position']=index;rows.append(row)
        a.output.write_text(json.dumps(dict(protocol=protocol, trials=rows),indent=2)+'\n')
        print(json.dumps({k:v for k,v in row.items() if k!='records'}),flush=True)
