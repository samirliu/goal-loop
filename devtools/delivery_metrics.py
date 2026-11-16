"""All-attempt, matched-cohort metrics; absent accounting stays unknown."""
import math


def number(value, name, integer=False):
    if (type(value) not in ((int,) if integer else (int, float)) or value < 0
            or type(value) is int and value > 2**63-1
            or type(value) is float and not math.isfinite(value)):
        raise RuntimeError('invalid '+name)
    return value


def accounting(value, model, session):
    """An explicit host/provider receipt, never an inferred dollar price."""
    if value is None:
        return dict(tokens=None, money=None, currency=None, source=None)
    if (not isinstance(value, dict) or set(value) !=
            {'model', 'session', 'tokens', 'money', 'currency', 'source', 'scope'}
            or value['model'] != model or value['session'] != session
            or value['scope'] != 'whole-attempt' or not isinstance(value['source'], str)
            or not value['source'].strip()):
        raise RuntimeError('accounting receipt identity/scope differs')
    for key in ('tokens', 'money'):
        if value[key] is not None:
            number(value[key], key, integer=key=='tokens')
    if value['money'] is not None and (
            not isinstance(value['currency'], str) or len(value['currency']) != 3
            or not value['currency'].isascii() or not value['currency'].isupper()
            or not value['currency'].isalpha()):
        raise RuntimeError('monetary receipt needs an explicit currency')
    return {key:value[key] for key in ('tokens', 'money', 'currency', 'source')}


def aggregate(rows):
    attempts = len(rows)
    qualified = sum(bool(row['qualified']) for row in rows)
    wall = sum(number(row['seconds'], 'attempt seconds') for row in rows)
    result = dict(attempts=attempts, qualified=qualified,
                  success_rate=qualified/attempts if attempts else None,
                  failed=attempts-qualified, all_attempt_wall_seconds=wall,
                  wall_seconds_per_qualified=wall/qualified if qualified else None)
    for key in ('tokens', 'money', 'human_interventions'):
        observed = [number(row[key], key, integer=key!='money')
                    for row in rows if row.get(key) is not None]
        covered = len(observed)
        total = sum(observed) if covered == attempts and attempts else None
        if key == 'money' and len({row.get('currency') for row in rows if row.get('money') is not None}) != 1:
            total = None
        result[key] = total
        result[key+'_coverage'] = dict(observed=covered, attempts=attempts)
        if key in ('tokens', 'money'):
            result[key+'_per_qualified'] = total/qualified if total is not None and qualified else None
    result['currency'] = next(iter({row.get('currency') for row in rows if row.get('money') is not None}), None)
    if result['money'] is None:
        result['currency'] = None
    return result


def cohort(rows, protocol):
    variants = sorted({row['variant'] for row in rows})
    totals = {variant:aggregate([row for row in rows if row['variant']==variant]) for variant in variants}
    families = {case['id']:case['family'] for case in protocol['cases']}
    by_family = {family:{variant:aggregate([row for row in rows
                    if row['variant']==variant and families[row['case']]==family]) for variant in variants}
                 for family in sorted(set(families.values()))}
    indexed = {(row['case'], row['variant']):row for row in rows}
    paired = {}
    for variant in variants:
        if variant == 'bare':
            continue
        pairs = [(indexed.get((case['id'], 'bare')), indexed.get((case['id'], variant)))
                 for case in protocol['cases']]
        complete = all(a is not None and b is not None for a,b in pairs)
        matched = [(a,b) for a,b in pairs if a is not None and b is not None]
        wins = sum(not a['qualified'] and b['qualified'] for a,b in matched)
        losses = sum(a['qualified'] and not b['qualified'] for a,b in matched)
        base, candidate = totals.get('bare', {}), totals[variant]
        cost = base.get('wall_seconds_per_qualified')
        candidate_cost = candidate['wall_seconds_per_qualified']
        gain = 1-candidate_cost/cost if cost and candidate_cost is not None and complete else None
        enough = all(sum(families[a['case']]==family for a,b in matched) >= protocol.get('minimum_pairs',3)
                     for family in by_family)
        eligible = (complete and enough and protocol.get('evidence_kind') == 'live-native'
                    and all(row.get('settings_verified', True) for row in rows))
        paired[variant] = dict(pairs=len(matched), delivery_wins=wins, delivery_losses=losses,
            delivery_ties=len(matched)-wins-losses, all_attempt_wall_gain=gain,
            criteria_met=bool(eligible and losses==0 and gain is not None
                              and gain>=protocol.get('minimum_cost_gain',.2)),
            eligible_for_cohort_decision=eligible,
            interpretation='descriptive matched cohort only; no general superiority claim')
    return dict(totals=totals, by_family=by_family, paired=paired)
