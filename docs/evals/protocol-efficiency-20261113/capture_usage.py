#!/usr/bin/env python3
"""Supplement original reports with numeric native usage; no requalification."""
import argparse
import hashlib
import json
from pathlib import Path

FIELDS=('input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens',
        'reasoning_output_tokens','total_tokens')


def extract(session):
    source=Path(session['native_source'])
    with source.open('rb') as stream:data=stream.read(session['native_bytes_observed'])
    assert hashlib.sha256(data).hexdigest()==session['native_prefix_sha256'],'original native prefix changed'
    events=[]
    for number,line in enumerate(data.splitlines(),1):
        row=json.loads(line);p=row.get('payload',{})
        if row.get('type')!='event_msg' or p.get('type')!='token_count' or not isinstance(p.get('info'),dict):continue
        info=p['info'];total=info.get('total_token_usage');last=info.get('last_token_usage')
        if not isinstance(total,dict) or not isinstance(last,dict):continue
        events.append(dict(native_line=number,timestamp=row['timestamp'],
            total={k:total.get(k) for k in FIELDS},last={k:last.get(k) for k in FIELDS},
            last_usage_includes_reasoning=info.get('last_usage_includes_reasoning')))
    previous={k:0 for k in FIELDS};seen=[];issues=[]
    for event in events:
        total,last=event['total'],event['last']
        if not all(type(total[k]) is int and total[k]>=0 and type(last[k]) is int and last[k]>=0 for k in FIELDS):
            issues.append('missing/non-numeric usage field');continue
        if total==previous:continue
        if any(total[k]-previous[k]!=last[k] for k in FIELDS):issues.append('cumulative delta differs from last usage; fresh zero counter not established')
        if total['cached_input_tokens']>total['input_tokens']:issues.append('cache subset exceeds input')
        if total['total_tokens']!=total['input_tokens']+total['output_tokens']:issues.append('total/input/output relation differs')
        previous=total;seen.append(event)
    if not events:issues.append('no exposed numeric usage event')
    complete=bool(seen and not issues and session['terminal'] and session['status']=='completed')
    lower={k:sum(e['last'][k] for e in seen) for k in FIELDS} if seen and not issues else None
    return dict(session_id=session['metadata']['id'],native_prefix_sha256=session['native_prefix_sha256'],
        native_bytes_observed=session['native_bytes_observed'],source=str(source),
        complete_reported_usage=complete,issues=sorted(set(issues)),reported_totals=previous if complete else None,
        observed_lower_bound=lower,events=events,
        caveat='Reported host counters, including cached input; not billing. Reasoning is an output subset when the native flag says so. No reasoning text or account/rate-limit data copied.')


def capture(base,n):
    position=base/'positions'/f'{n:03d}';report=position/'capture/report.json'
    if not report.exists():return None
    original=json.loads(report.read_text());sessions={sid:extract(s) for sid,s in original['sessions'].items()}
    complete=bool(sessions) and all(s['complete_reported_usage'] for s in sessions.values())
    totals={k:sum(s['reported_totals'][k] for s in sessions.values()) for k in FIELDS} if complete else None
    lower={k:sum(s['observed_lower_bound'][k] for s in sessions.values() if s['observed_lower_bound']) for k in FIELDS}
    result=dict(kind='posthoc numeric usage supplement; original qualification and timing untouched',position=n,
        original_report_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
        complete_reported_usage=complete,totals=totals,observed_lower_bound=lower,sessions=sessions,fees=None,
        limitations='Missing/aborted/unflushed provider usage is unknown, not zero. These counters do not establish invoice cost or service compute.')
    (position/'native-usage.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    return {k:result[k] for k in ['position','complete_reported_usage','totals','fees']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--position',type=int)
    a=p.parse_args();rows=[capture(a.base,n) for n in ([a.position] if a.position else range(1,19))]
    print(json.dumps([r for r in rows if r],indent=2))
