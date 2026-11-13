"""Posthoc CI diagnostics; never runs or changes a check or its deadline."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gate_observation_trace', ROOT/'scripts/goal_trace.py')
trace = importlib.util.module_from_spec(spec); spec.loader.exec_module(trace)
project = Path(sys.argv[1])
rows = trace.records(project)
roots = [r for r in rows if r['kind'] == 'acceptance' and r['label'] == 'check']
last = max(roots, key=lambda r:r['start_monotonic']) if roots else None
spans = [r for r in rows if last and (r['id'] == last['id'] or r['parent'] == last['id'])]
print('GATE_SETTLEMENT_OBSERVATION '+json.dumps(dict(kind='posthoc; no time granted', case=project.name,
    gate_output=sys.argv[2], cpu_count=os.cpu_count(), python=sys.version.split()[0],
    spans=[{k:r[k] for k in ('kind','label','start_monotonic','elapsed','result','state')} for r in spans],
    sources={name:hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest()
             for name in ('goal_gate.sh','goal_parse.sh','goal_runner.py')}), sort_keys=True))
