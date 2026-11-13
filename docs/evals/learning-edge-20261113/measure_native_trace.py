#!/usr/bin/env python3
"""Derive descriptive overhead counts from the four frozen native traces."""
import argparse
from collections import Counter
import json
from pathlib import Path


def measure(root):
    trials = []
    for folder in sorted(root.glob('[1-4]-*')):
        manifest = json.loads((folder/'manifest.json').read_text())
        report = json.loads((folder/'report.json').read_text())
        rows = [json.loads(line) for line in (folder/'events.jsonl').read_text().splitlines()]
        calls = {b['id']: b for row in rows for b in row.get('content', [])
                 if b.get('type') == 'tool_use' and b.get('id')}
        if len(calls) != report['tool_calls']:
            raise RuntimeError('tool count mismatch: '+folder.name)
        plugin = manifest['plugin']
        lookups = sum(b['name'] in ('Read', 'Grep', 'Glob') and
                      plugin in json.dumps(b.get('input', {})) for b in calls.values())
        if lookups != report['protocol_lookups']:
            raise RuntimeError('lookup count mismatch: '+folder.name)
        reads, projections = Counter(), Counter()
        for b in calls.values():
            if b['name'] != 'Read':
                continue
            arg = b.get('input', {})
            path = arg.get('file_path', '').replace('/private/tmp/', '/tmp/')
            reads[path] += 1
            projections[(path, arg.get('offset'), arg.get('limit'))] += 1
        terminal = report.get('reported_terminal') or {}
        trials.append(dict(position=folder.name, tools=len(calls), protocol_lookups=lookups,
            sdk_reported_models=sorted({r['model'] for r in rows if r.get('model')}),
            tool_errors=report['tool_errors'],
            read_calls=sum(reads.values()),
            repeated_read_calls=sum(max(0, n-1) for n in reads.values()),
            repeated_same_projection=sum(max(0, n-1) for n in projections.values()),
            repeated_paths={k: v for k, v in reads.items() if v > 1},
            native_agent_calls=sum(b['name'] == 'Agent' for b in calls.values()),
            human_interventions=report['human_interventions'],
            cli_result=report['cli_result'], cli_seconds=report['cli_elapsed'],
            checked_seconds=report['finished_elapsed'],
            accepted=report['accepted'], normal_final_delivery=report['normal_final_delivery'],
            sdk_reported_api_ms=terminal.get('duration_api_ms'),
            sdk_reported_usage=terminal.get('usage'),
            sdk_reported_model_usage=terminal.get('modelUsage'),
            tokens=None, money=None))
    if len(trials) != 4:
        raise RuntimeError('retain all four attempts')
    return dict(scope='descriptive trace counts; no model calls or billing verification',
        definitions=dict(protocol_lookups='Read/Grep/Glob whose JSON arguments contain the frozen plugin path; Bash source reads excluded',
            repeated_read_calls='Read calls after the first call to the same path; /private/tmp normalized to /tmp',
            repeated_same_projection='Read calls with the same normalized path, offset and limit after the first',
            coordination='native Agent calls only; no claim to isolate every planning or coordination interval',
            sdk_usage='unverified SDK estimates, missing on the timeout; actual billed totals remain unknown'),
        trials=trials)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = measure(args.root)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps([dict(position=r['position'], tools=r['tools'],
        lookups=r['protocol_lookups'], reads=r['read_calls'],
        repeat=r['repeated_read_calls'], agents=r['native_agent_calls']) for r in result['trials']]))
