"""Frozen task families for matched real-agent trials. Standard library only."""
import hashlib
import json
from pathlib import Path


TASKS = {
    'small': """Implement solution.merge_ranges(ranges). Input is a list of [start,end] integer
pairs representing half-open intervals. Reject bools, non-integers, malformed
pairs and start>end with ValueError. Ignore empty intervals. Return a sorted
list of nonempty [start,end] lists, merging overlaps and touching endpoints.
Preserve the input. Support negative and arbitrarily large integer bounds.
Only edit solution.py and optional tests you create. Run python3 public.py.
""",
    'medium': """Implement the standard-library auditlog package with codec.py, aggregate.py,
__main__.py and __init__.py. codec.parse_line(line) returns a dict containing
the original key and amount, or raises ValueError. Valid records are JSON
objects with a nonempty string key and integer amount (bool is invalid).
Extra fields are ignored. aggregate.summarize(records) accepts an iterable
and returns key-sorted dicts with key,count,total,min,max.
python3 -m auditlog --input PATH --output PATH [--skip-bad] reads UTF-8 JSONL.
Ignore blank lines. Output one JSON object per group. Strict invalid input
exits 2, names the physical line on stderr and preserves an existing output.
With --skip-bad, skip invalid rows and print {"skipped":N} on stderr.
Missing input exits 2. Empty input produces an empty output file.
Publish output atomically. Only edit auditlog/ and optional tests you create.
Run python3 public.py. No third-party dependencies.
""",
    'optimization': """Optimize solution.count_cover(intervals,points), returning the number of
half-open [left,right) intervals covering each point in original order.
Inputs are integer pairs and integer points. Empty intervals count zero.
Raise ValueError on malformed pairs, bools, non-integers, or left>right.
Preserve inputs and support duplicate endpoints, negative and large integers.
The starter is correct on its ordinary input domain but quadratic.
Keep correctness and improve the supplied workload by at least 5x over the
naive reference. public.py reports five noisy timing samples and their
dispersion. Retain raw measurements in BENCHMARK.md. Use repeated readings.
Only edit solution.py, BENCHMARK.md and optional tests. Run python3 public.py.
""",
    'recovery': """Finish job.run(source,output,state), processing UTF-8 JSONL objects with
integer id and string text. job.transform(row) returns {"id":id,"text":text.upper()}.
Persist a checkpoint {"next":N,"offset":B,"source_sha256":HEX} for completed
rows and output byte length. An earlier process crashed after the checkpoint:
seed-data/output.jsonl contains two committed rows and an uncommitted torn tail.
Resume by truncating the tail to offset, then transform only uncommitted rows.
Flush and fsync output before atomically replacing each checkpoint. A crash
before checkpoint publication may redo that uncommitted row. Repeated runs
and concurrent processes must produce exactly one output row per source row.
Reject changed source, malformed checkpoint or truncated committed output
with ValueError before changing output/state. A fresh run may have no state.
Use a stable flock lock file next to state. Preserve committed prefix bytes.
Only edit job.py and optional tests. Run python3 public.py and also recover
the supplied seed-data/output.jsonl/state.json. No third-party dependencies.
""",
}

STARTERS = {
    'small': {'solution.py': 'def merge_ranges(ranges):\n    raise NotImplementedError\n'},
    'medium': {
        'auditlog/__init__.py': '',
        'auditlog/codec.py': 'def parse_line(line):\n    raise NotImplementedError\n',
        'auditlog/aggregate.py': 'def summarize(records):\n    raise NotImplementedError\n',
        'auditlog/__main__.py': 'raise SystemExit("not implemented")\n',
    },
    'optimization': {'solution.py': '''def count_cover(intervals, points):
    return [sum(left <= point < right for left, right in intervals) for point in points]
'''},
    'recovery': {'job.py': '''import json
def transform(row):
    return {"id": row["id"], "text": row["text"].upper()}
def run(source, output, state):
    raise NotImplementedError("resume the committed prefix safely")
'''},
}

PUBLIC = {
    'small': '''from solution import merge_ranges
original=[[4,8],[1,4],[2,3],[-4,-1],[9,9]]
assert merge_ranges(original)==[[-4,-1],[1,8]]
assert original==[[4,8],[1,4],[2,3],[-4,-1],[9,9]]
assert merge_ranges([[10**30,10**30+2]])==[[10**30,10**30+2]]
for bad in ([[3,1]], [[True,4]], [[1,2,3]]):
    try: merge_ranges(bad)
    except ValueError: pass
    else: raise AssertionError(bad)
print("PUBLIC PASS")
''',
    'medium': '''import json,subprocess,sys,tempfile
from pathlib import Path
from auditlog.codec import parse_line
from auditlog.aggregate import summarize
assert parse_line('{"key":"a","amount":2,"extra":4}')=={"key":"a","amount":2}
assert summarize(iter([{"key":"b","amount":3},{"key":"b","amount":-2}]))==[{"key":"b","count":2,"total":1,"min":-2,"max":3}]
with tempfile.TemporaryDirectory() as tmp:
    source,out=Path(tmp)/"in",Path(tmp)/"out"
    source.write_text('{"key":"a","amount":2}\\n{broken\\n')
    out.write_text("keep")
    args=[sys.executable,"-B","-m","auditlog","--input",str(source),"--output",str(out)]
    result=subprocess.run(args,capture_output=True,text=True)
    assert result.returncode==2 and out.read_text()=="keep" and "2" in result.stderr
    result=subprocess.run(args+["--skip-bad"],capture_output=True,text=True)
    assert result.returncode==0 and json.loads(out.read_text())["total"]==2
    assert json.loads(result.stderr)=={"skipped":1}
print("PUBLIC PASS")
''',
    'optimization': '''import random,statistics,time
from solution import count_cover
assert count_cover([[-2,2],[0,3],[3,3]],[-2,0,2,3])==[1,2,1,0]
for intervals,points in (([[True,2]],[1]),([[3,1]],[1]),([[0,3]],[False])):
    try: count_cover(intervals,points)
    except ValueError: pass
    else: raise AssertionError((intervals,points))
rng=random.Random(713)
intervals=[sorted([rng.randrange(-5000,5000),rng.randrange(-5000,5000)]) for _ in range(3500)]
points=[rng.randrange(-5000,5000) for _ in range(1500)]
start=time.perf_counter()
expected=[sum(a<=p<b for a,b in intervals) for p in points]
reference=time.perf_counter()-start
samples=[]
for index in range(5):
    start=time.perf_counter(); actual=count_cover(intervals,points)
    elapsed=time.perf_counter()-start
    assert actual==expected
    samples.append(elapsed*(.85+random.Random(713+index).random()*.3))
print({"reference_seconds":reference,"samples_seconds":samples,"sd":statistics.stdev(samples),"speedup":reference/statistics.median(samples)})
assert reference/statistics.median(samples)>=5
print("PUBLIC PASS")
''',
    'recovery': '''import hashlib,json,tempfile
from pathlib import Path
import job
with tempfile.TemporaryDirectory() as tmp:
    source,out,state=[Path(tmp)/name for name in ("in","out","state")]
    rows=[{"id":i,"text":"aBc"+str(i)} for i in range(5)]
    source.write_text("".join(json.dumps(row)+"\\n" for row in rows))
    prefix=json.dumps(job.transform(rows[0]))+"\\n"
    out.write_text(prefix+'{"torn":')
    state.write_text(json.dumps({"next":1,"offset":len(prefix.encode()),"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest()}))
    calls=[]; original=job.transform
    def observed(row): calls.append(row["id"]); return original(row)
    job.transform=observed
    job.run(source,out,state); job.run(source,out,state)
    assert calls==[1,2,3,4],calls
    assert [json.loads(line) for line in out.read_text().splitlines()]==[original(row) for row in rows]
print("PUBLIC PASS")
''',
}


def prepare(root, family, seed):
    root.mkdir(parents=True, exist_ok=False)
    for name, code in STARTERS[family].items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code)
    (root / 'TASK.md').write_text(TASKS[family])
    (root / 'public.py').write_text(PUBLIC[family])
    if family == 'recovery':
        folder = root / 'seed-data'
        folder.mkdir()
        rows = [{'id': i, 'text': 'seed%s-row%s' % (seed, i)} for i in range(8)]
        source = folder / 'source.jsonl'
        source.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        prefix = ''.join(json.dumps(dict(id=row['id'], text=row['text'].upper())) + '\n' for row in rows[:2])
        (folder / 'output.jsonl').write_text(prefix + '{"unfinished":')
        (folder / 'state.json').write_text(json.dumps(dict(next=2, offset=len(prefix.encode()),
                                                          source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())))
