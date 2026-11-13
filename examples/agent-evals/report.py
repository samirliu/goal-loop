"""Describe every preregistered attempt, with failures in the denominator."""
import argparse
import json
from pathlib import Path
import statistics


def describe(root):
    manifest = json.loads((root / 'manifest.json').read_bytes())
    rows = []
    for name in manifest['trials']:
        # Archived roots may move; the UUID is stable, the absolute path is not.
        folder = root / 'trials' / Path(name).name
        config = json.loads((folder / 'trial.json').read_bytes())
        result = json.loads((folder / 'result.json').read_bytes()) if (folder / 'result.json').exists() else None
        rows.append(dict(id=folder.name, config=config, result=result))
    arms = {}
    for arm in manifest['arms']:
        planned = [r for r in rows if r['config']['arm'] == arm]
        finished = [r['result'] for r in planned if r['result'] is not None]
        accepted = [r for r in finished if r['accepted_within_budget']]
        times = [r['independent_finished_seconds'] for r in accepted]
        claims = []
        for result in finished:
            folder = root / 'trials' / next(r['id'] for r in planned if r['result'] is result)
            try:
                marker = json.loads((folder / 'DONE.json').read_bytes())
                claims.append(bool(marker.get('complete')) and not result['accepted_within_budget'])
            except (OSError, ValueError, AttributeError):
                claims.append(False)
        arms[arm] = dict(planned=len(planned), adjudicated=len(finished),
                         accepted_within_budget=len(accepted),
                         independently_correct=sum(r['accepted'] for r in finished),
                         protocol_compliant=sum(r['protocol_compliant'] for r in finished),
                         compliant_delivery=sum(r['protocol_compliant'] and r['accepted_within_budget'] for r in finished),
                         timeout=sum(r['terminal'] == 'timeout' for r in finished),
                         unverified_completion_claims=sum(claims),
                         false_acceptance=sum(not r['accepted'] and
                             (r['gate'] is not None and r['gate']['result'] == 0
                              or arm == 'native' and r['protocol_compliant']) for r in finished),
                         conditional_success_median_seconds=statistics.median(times) if times else None,
                         conditional_success_p90_seconds=sorted(times)[max(0, -(-9*len(times)//10)-1)] if times else None,
                         observed_seconds_per_delivery=(sum(r['independent_finished_seconds'] for r in finished)/len(accepted)
                                                        if accepted and len(finished) == len(planned) else None),
                         tokens='unknown across arms; native partial accounting retained per trial', money=None,
                         time_to_delivery={str(t): sum(r['accepted_within_budget'] and r['independent_finished_seconds'] <= t
                                                      for r in finished) for t in (120, 240, 360, 480, 600)})
    pairs = []
    for family in dict.fromkeys(r['config']['family'] for r in rows):
        for repetition in sorted({r['config']['repetition'] for r in rows}):
            group = {r['config']['arm']: r['result'] for r in rows
                     if r['config']['family'] == family and r['config']['repetition'] == repetition}
            if not group:
                continue
            comparison = {}
            for baseline in ('plain', 'native'):
                skill, base = group.get('skill'), group.get(baseline)
                both = skill is not None and base is not None
                comparable_time = both and skill['accepted_within_budget'] and base['accepted_within_budget']
                comparison[baseline] = dict(adjudicated=both,
                    delivery_difference=(int(skill['accepted_within_budget'])-int(base['accepted_within_budget']) if both else None),
                    seconds_difference=(skill['independent_finished_seconds']-base['independent_finished_seconds']
                                        if comparable_time else None))
            pairs.append(dict(family=family, repetition=repetition, comparisons=comparison))
    return dict(planned=len(rows), adjudicated=sum(r['result'] is not None for r in rows), arms=arms, pairs=pairs,
                interpretation='Descriptive matched observations; no general superiority or cross-arm token-cost inference.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(json.dumps(describe(args.root), indent=2))
