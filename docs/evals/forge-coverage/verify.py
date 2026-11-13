"""Verify archived probe inputs, outcomes and recovery without importing goal code."""
import base64
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parent


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def sha(data):
    return hashlib.sha256(data).hexdigest()


with tarfile.open(ROOT / 'raw-trials.tar.gz') as archive:
    members = {name.removeprefix('./'): name for name in archive.getnames()}

    def read(name):
        with archive.extractfile(members[name]) as stream:
            return stream.read()

    count = 0
    for name in members:
        if not name.endswith('/raw-versions.json'):
            continue
        folder = name.removesuffix('/raw-versions.json')
        frames = json.loads(read(name))
        scopes, reports = {}, []
        for identity, data in frames.items():
            raw = base64.b64decode(data, validate=True)
            assert sha(raw) == identity
            for line in raw.splitlines():
                if line.startswith(b'FORGE-SCOPE: '):
                    scope = json.loads(line[13:])
                    plan = base64.b64decode(scope['plan_base64'], validate=True)
                    assert json.loads(plan) == scope['definition']
                    files = {path: base64.b64decode(value, validate=True) for path, value in scope['files'].items()}
                    fingerprint = sha(encode({'plan': sha(plan), 'files': {path: sha(value) for path, value in files.items()}}))
                    assert fingerprint == scope['fingerprint']
                    scopes[fingerprint] = scope, files
                if line.startswith(b'FORGE: '):
                    reports.append(json.loads(line[7:]))
        for report in reports:
            scope, files = scopes[report['plan']]
            definition = scope['definition']
            critic = report['critic']
            if critic is not None:
                assert sha(critic['text'].encode()) == critic['sha256']
                lines = critic['text'].splitlines()
                assert 'ITERATION|' + str(report['iteration']) in lines
                assert 'ARTIFACT|' + report['artifact'] in lines
                assert 'PLAN|' + report['plan'] in lines
            cases = {case['id']: case for case in definition['cases']}
            for row in report['cases']:
                case = cases[row['id']]
                data = files[case['input']]
                assert sha(data) == row['input_sha256']
                stdout = base64.b64decode(row['stdout_base64'], validate=True)
                assert stdout.decode('utf-8', 'replace') == row['stdout']
                if row['result'] in (0, 1):
                    observed = json.loads(stdout)
                    expected = sorted(set(json.loads(data)))
                    assert observed['expected'] == expected
                    assert (observed['actual'] == expected) == (row['result'] == 0)
            if report['qualified']:
                assert not report['remaining'] and report['reason'] is None and not report['fatal']
                assert [row['id'] for row in report['cases']] == [case['id'] for case in definition['cases']]
                assert all(row['result'] == 0 for row in report['cases'])
                assert critic is not None and not critic['findings']
            count += 1
        if folder.endswith('test_repeated_clear_records_stability_and_explicit_blind_spots'):
            ordered = sorted(reports, key=lambda row: row['iteration'])
            assert [row['new_cases'] for row in ordered] == [2, 0, 0]
        if folder.endswith('test_exhausted_budget_preserves_unprobed_scope_and_cannot_earn_dry_credit'):
            assert any(row['remaining'] and not row['qualified'] for row in reports)
        if folder.endswith('test_declared_new_input_exposes_a_defect_missed_by_positive_only_probe'):
            assert all(not row['qualified'] for row in reports)
            assert any(row['result'] == 1 for report in reports for row in report['cases'])
    faults = json.loads(read('migration-faults/results.json'))
    assert [row['point'] for row in faults] == ['generation-published', 'pointer-published']
    assert all(row['result'] == 4 for row in faults)
    assert b'dry_streak=0\n' in read('migration-faults/project/.goal/state.rec')
    print('PASS: %s executed dry records, frozen materials, reference results, budget remainder, migration faults' % count)
