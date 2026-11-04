"""Create fresh, identical trial workspaces. Standard library only."""
import argparse
from pathlib import Path

TASK = '''Implement a standard-library Python package logtool, invoked as:
python3 -m logtool stats PATH [--service NAME]
python3 -m logtool query PATH [--service NAME] [--min-status N]
PATH '-' reads stdin. Input is UTF-8 JSONL; ignore blank lines.
Every nonblank line must be an object with service (nonempty string), status
(integer 100..599, excluding bool), latency_ms (finite nonnegative number,
excluding bool). Retain extra fields in query results. Validate ALL records
before filtering; invalid input exits 2 with physical line number on stderr
and EMPTY stdout, even if earlier records were valid. Missing files exit 2.
Stats emits exactly one JSON object: {"count":N,"errors":E,"p50_ms":P,
"p95_ms":Q,"services":{service:count,...}}. Errors count statuses >=500.
Quantiles use nearest rank ceil(p*N), indexed from 1; empty quantiles are null.
Query emits matching original objects as JSONL in input order; --min-status
is inclusive. Empty query prints nothing. --service uses exact equality.
Use separate parser.py, stats.py, and __main__.py modules with a documented
interface. Do not add dependencies or alter TASK.md or verify/. Only edit
logtool/ and optionally your own tests. You may use at most two concurrent
workers with disjoint writes. Do not inspect evaluation code or other trial
workspaces. Finish within 240 seconds of starting, including verification;
report exact checks, remaining issues and whether delivery is complete.
'''
PUBLIC = '''import json, subprocess, sys

def invoke(args, data):
    return subprocess.run([sys.executable, '-m', 'logtool', *args],
                          input=data, text=True, capture_output=True)
rows = [{'service':'api','status':200,'latency_ms':10},
        {'service':'api','status':500,'latency_ms':30},
        {'service':'web','status':201,'latency_ms':20},
        {'service':'web','status':503,'latency_ms':40}]
s = ''.join(json.dumps(r)+'\\n' for r in rows)
checks=[]
r=invoke(['stats','-'],s)
try: checks.append(r.returncode==0 and json.loads(r.stdout)==dict(count=4,errors=2,p50_ms=20,p95_ms=40,services={'api':2,'web':2}))
except Exception: checks.append(False)
r=invoke(['query','-','--service','api','--min-status','500'],s)
try: checks.append(r.returncode==0 and [json.loads(x) for x in r.stdout.splitlines()]==[rows[1]])
except Exception: checks.append(False)
r=invoke(['stats','-'],'')
try: checks.append(r.returncode==0 and json.loads(r.stdout)==dict(count=0,errors=0,p50_ms=None,p95_ms=None,services={}))
except Exception: checks.append(False)
r=invoke(['query','-'],s+'{broken\\n')
checks.append(r.returncode==2 and not r.stdout and '5' in r.stderr)
if '--score' in sys.argv: print(sum(checks)); sys.exit(0)
print('public:',sum(checks),'/',len(checks), checks)
sys.exit(0 if all(checks) else 1)
'''

def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    (root/'logtool').mkdir()
    (root/'verify').mkdir()
    (root/'TASK.md').write_text(TASK)
    (root/'verify/public.py').write_text(PUBLIC)
    (root/'logtool/__init__.py').write_text('')
    (root/'logtool/parser.py').write_text('def parse(stream):\n    raise NotImplementedError("implement JSONL validation")\n')
    (root/'logtool/stats.py').write_text('def summarize(rows):\n    raise NotImplementedError("implement statistics")\n')
    (root/'logtool/__main__.py').write_text('raise SystemExit("not implemented")\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('root',type=Path)
    prepare(p.parse_args().root)
