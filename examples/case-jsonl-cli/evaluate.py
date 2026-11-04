"""Independent outcome grader. Keep outside trial workspaces/worker briefs."""
import argparse
import collections
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys


def grade(project):
    checks=[]
    def call(args, data):
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run([sys.executable,'-m','logtool',*args],cwd=project,
                              input=data,text=True,capture_output=True,timeout=8,env=env)
    def check(name, args, data, expected=None, bad=False, line=None, query=False):
        try:
            r=call(args,data)
            if bad:
                passed=r.returncode==2 and not r.stdout and bool(r.stderr) and (line is None or str(line) in r.stderr)
            else:
                got=[json.loads(x) for x in r.stdout.splitlines()] if query else json.loads(r.stdout)
                passed=r.returncode==0 and got==expected
            checks.append(dict(name=name,passed=passed,stdout=r.stdout,stderr=r.stderr,rc=r.returncode))
        except Exception as e:
            checks.append(dict(name=name,passed=False,error=str(e)))
    def stats(rows):
        vals=sorted(r['latency_ms'] for r in rows)
        return dict(count=len(rows),errors=sum(r['status']>=500 for r in rows),
                    p50_ms=vals[math.ceil(.5*len(vals))-1] if vals else None,
                    p95_ms=vals[math.ceil(.95*len(vals))-1] if vals else None,
                    services=dict(collections.Counter(r['service'] for r in rows)))
    rng=random.Random(731901)
    for n in (0,1,2,4,19,20,21,41):
        rows=[dict(service=rng.choice(['api','web','你好']),status=rng.choice([100,200,499,500,599]),
                   latency_ms=rng.choice([0,0.125,10,20.5,999]),extra={'i':i}) for i in range(n)]
        raw='\n'+''.join(json.dumps(r,ensure_ascii=False)+'\n\n' for r in rows)
        check(f'stats-{n}',['stats','-'],raw,stats(rows))
        selected=[r for r in rows if r['service']=='你好']
        check(f'filtered-stats-{n}',['stats','-','--service','你好'],raw,stats(selected))
        selected=[r for r in rows if r['service']=='api' and r['status']>=500]
        check(f'query-{n}',['query','-','--service','api','--min-status','500'],raw,selected,query=True)
    good=json.dumps(dict(service='ok',status=200,latency_ms=0))
    invalid=[None,[],{},dict(service='',status=200,latency_ms=0),
             dict(service=7,status=200,latency_ms=0),dict(service='x',status=True,latency_ms=0),
             dict(service='x',status=200.0,latency_ms=0),dict(service='x',status=99,latency_ms=0),
             dict(service='x',status=600,latency_ms=0),dict(service='x',status=200,latency_ms=True),
             dict(service='x',status=200,latency_ms=-1),dict(service='x',status=200,latency_ms=float('nan')),
             dict(service='x',status=200,latency_ms=float('inf'))]
    for i,row in enumerate(invalid):
        # Validation must occur BEFORE service filtering, with atomic stdout.
        raw=good+'\n\n'+json.dumps(row)+'\n'
        check(f'invalid-{i}',['query','-','--service','ok'],raw,bad=True,line=3)
    check('bad-json',['stats','-'],good+'\n{\n',bad=True,line=2)
    check('missing-path',['stats','does-not-exist.jsonl'],'',bad=True)
    check('empty-query',['query','-'],'\n\n',[],query=True)
    # Read an actual UTF-8 path, not only stdin.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='logtool-fixture-') as d:
        f=Path(d)/'含 空格.jsonl'; f.write_text(good+'\n',encoding='utf-8')
        check('file-path',['stats',str(f)],'',stats([json.loads(good)]))
    return dict(passed=sum(c['passed'] for c in checks),total=len(checks),checks=checks)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('project',type=Path);p.add_argument('--output',type=Path)
    args=p.parse_args(); result=grade(args.project)
    if args.output: args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False) if not args.output else f"{result['passed']}/{result['total']}")
    sys.exit(0 if result['passed']==result['total'] else 1)
