#!/usr/bin/env python3
"""Summarize preserved positions. Never runs models or changes eligibility."""
import argparse
import json
from pathlib import Path
import statistics


def qualified_settings(report):
    settings=[s for session in report.get('sessions',{}).values() for s in session.get('settings',[])]
    return bool(settings) and all(s.get('model')=='gpt-6.1-sol' and s.get('effort')=='max'
        and s.get('approval_policy')=='never' and s.get('sandbox_policy',{}).get('type')=='danger-full-access'
        and s.get('permission_profile',{}).get('type')=='disabled' for s in settings)


def aggregate(rows):
    finished=[r for r in rows if r['finished']]
    q=sum(r['qualified'] for r in finished)
    wall=sum(r['elapsed_seconds'] for r in finished)
    elapsed=[r['elapsed_seconds'] for r in finished]
    worker_unknown=sum(r['root_worker_seconds'] is None for r in finished)
    worker_observed=sum(r['root_worker_seconds'] for r in finished if r['root_worker_seconds'] is not None)
    worker_lower=sum(r.get('root_worker_seconds_lower_bound',r['root_worker_seconds'] or 0) for r in finished)
    return dict(positions=len(rows), finished=len(finished), qualified=q, total_seconds=wall,
        seconds_per_qualified=wall/q if q else None,
        median_attempt_seconds=statistics.median(elapsed) if elapsed else None,
        attempts_seconds=elapsed, root_worker_seconds=None if worker_unknown or not finished else worker_observed,
        root_worker_seconds_observed=worker_observed, root_worker_positions_unknown=worker_unknown,
        root_worker_seconds_lower_bound=worker_lower,
        internal_worker_seconds_terminal_observed=sum(r['internal_worker_seconds'] for r in finished),
        tokens=None,fees=None,service_compute=None,human_business_interventions=0)


def summarize(base, protocol_path):
    protocol=json.loads(protocol_path.read_text());rows=[]
    for original in protocol['order']:
        n=original['position'];capture=base/'positions'/f'{n:03d}'/'capture'
        path=capture/'report.json';row=dict(original,finished=path.exists())
        if path.exists():
            r=json.loads(path.read_text());settings_ok=qualified_settings(r)
            reasons=list(r['reasons'])
            if not settings_ok:reasons.append('actual model/effort/permissions differ or unknown')
            root=r.get('sessions',{}).get(r.get('session_id'),{})
            tasks=list(root.get('tasks',{}).values())
            root_seconds=sum(t['finished_epoch']-t['started_epoch'] for t in tasks if t['finished_epoch'] is not None)
            root_terminal=bool(tasks) and all(t['finished_epoch'] is not None for t in tasks)
            root_lower=root_seconds+sum(max(0,r['finished_epoch']-t['started_epoch']) for t in tasks if t['finished_epoch'] is None)
            finals=root.get('finals',[])
            row.update(qualified=bool(r['qualified'] and settings_ok),collector_qualified=r['qualified'],
                settings_ok=settings_ok,reasons=reasons,elapsed_seconds=r['elapsed_seconds'],
                normal_final=r['normal_final'],root_worker_seconds=root_seconds if root_terminal else None,
                root_worker_seconds_lower_bound=root_lower,
                internal_worker_seconds=r['internal_worker_seconds_terminal_observed'],
                peak_internal_workers=r['peak_internal_workers_observed'],
                session_id=r.get('session_id'),checks={name:dict(result=v.get('result'),
                    elapsed_seconds=v['finished']-v['started'] if 'finished' in v else None) for name,v in r['checks'].items()},
                native_tool_calls=sum(s.get('tool_calls',0) for s in r.get('sessions',{}).values()),
                opaque_tool_receipts=sum(s.get('opaque_tool_receipts',0) for s in r.get('sessions',{}).values()),
                tokens=None,fees=None,finals=finals)
        rows.append(row)
    groups={g:aggregate([r for r in rows if r['group']==g]) for g in 'ABC'}
    families={f:{g:aggregate([r for r in rows if r['family']==f and r['group']==g]) for g in 'ABC'}
              for f in sorted({r['family'] for r in rows})}
    complete=all(r['finished'] for r in rows)
    adoption=None
    if complete:
        a,b,c=(groups[g] for g in 'ABC')
        count_win=c['qualified']>=a['qualified']+2 and c['qualified']>=b['qualified']+2
        refs=[v['seconds_per_qualified'] for v in (a,b) if v['seconds_per_qualified'] is not None]
        reference=min(refs) if refs else None
        cost_win=bool(c['qualified']>=max(a['qualified'],b['qualified']) and c['seconds_per_qualified'] is not None
                      and reference is not None and c['seconds_per_qualified']<=.8*reference)
        family_rows={}
        for family,values in families.items():
            x,y,z=(values[g] for g in 'ABC')
            refs=[v['seconds_per_qualified'] for v in (x,y) if v['seconds_per_qualified'] is not None]
            ref=min(refs) if refs else None
            qualified=z['qualified']>=max(x['qualified'],y['qualified'])
            benefit=qualified and (z['qualified']>max(x['qualified'],y['qualified']) or
                (ref is not None and z['seconds_per_qualified'] is not None and z['seconds_per_qualified']<ref))
            bounded_regression=qualified and ref is not None and z['seconds_per_qualified'] is not None and z['seconds_per_qualified']<=1.1*ref
            family_rows[family]=dict(benefit=benefit,other_family_cost_guard=bounded_regression,
                                     better_reference_seconds_per_qualified=ref)
        family_gate=sum(v['benefit'] for v in family_rows.values())>=2 and all(
            v['benefit'] or v['other_family_cost_guard'] for v in family_rows.values())
        adoption=dict(count_win=count_win,cost_win=cost_win,family_gate=family_gate,
            family_details=family_rows,better_reference_seconds_per_qualified=reference,
            adopt=bool((count_win or cost_win) and family_gate),
            net_goal_achieved=bool((count_win or cost_win) and family_gate),
            decision='adopt tested opt-in scope' if (count_win or cost_win) and family_gate else 'retain baseline; net efficiency goal not achieved',
            break_even_tasks=None,break_even_reason='requires credible repeatable positive net savings and complete cost valuation; not established by this small single-pair study alone')
    return dict(complete=complete,finished=sum(r['finished'] for r in rows),max_positions=18,
        groups=groups,families=families,adoption=adoption,positions=rows,
        limits=protocol['limitations'],cost_unknowns='tokens, fees and service compute remain unknown; observed worker-seconds are not billing')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',required=True,type=Path)
    p.add_argument('--protocol',type=Path,default=Path(__file__).with_name('protocol.json'))
    p.add_argument('--output',type=Path)
    a=p.parse_args();r=summarize(a.base,a.protocol)
    if a.output:a.output.write_text(json.dumps(r,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:r[k] for k in ['complete','finished','groups','adoption']},ensure_ascii=False,indent=2))
