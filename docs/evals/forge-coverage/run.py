#!/usr/bin/env python3
"""Keep production-entrypoint scenarios and raw versions through recovery."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('forge_scenarios', ROOT / 'tests/test_forge.py')
scenarios = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scenarios)

CASES = (
    'test_repeated_clear_records_stability_and_explicit_blind_spots',
    'test_declared_new_input_exposes_a_defect_missed_by_positive_only_probe',
    'test_exhausted_budget_preserves_unprobed_scope_and_cannot_earn_dry_credit',
    'test_open_critic_finding_and_stale_critic_cannot_earn_dry_credit',
    'test_acceptance_check_cannot_replace_the_archived_scope_during_close',
)


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    for name in CASES:
        test = scenarios.ForgeCoverage(name)
        folder = output / name
        folder.mkdir()
        calls, raw = [], {}
        original = test.call

        def capture(script, *args, **kwargs):
            started = time.monotonic()
            result = original(script, *args, **kwargs)
            versions = {}
            for path in (test.state / 'evidence/raw').glob('*.txt'):
                data = path.read_bytes()
                identity = hashlib.sha256(data).hexdigest()
                raw[identity] = base64.b64encode(data).decode('ascii')
                versions[path.name] = identity
            calls.append(dict(script=Path(script).name, args=args, result=result.returncode,
                              elapsed=time.monotonic() - started, stdout=result.stdout,
                              stderr=result.stderr, raw_versions=versions))
            return result

        test.call = capture
        try:
            test.setUp()
            getattr(test, name)()
            shutil.copytree(test.root, folder / 'project')
            (folder / 'calls.json').write_text(json.dumps(calls, indent=2) + '\n')
            (folder / 'raw-versions.json').write_text(json.dumps(raw, indent=2) + '\n')
            print(name + ': PASS', flush=True)
        finally:
            test.doCleanups()
    migration_faults(output)


def migration_faults(output):
    test = scenarios.ForgeCoverage('test_coverage_can_grow_without_dropping_earlier_cases_or_failures')
    try:
        test.setUp()
        test.stamp()
        test.close()
        (test.root / 'zero.json').write_text('[0,0,0]')
        test.plan['cases'].append(dict(id='zero', dimension='integer-sign', input='zero.json',
                                       command=[scenarios.sys.executable, '-B', 'probe.py']))
        test.plan_path.write_text(json.dumps(test.plan))
        bindir = test.root / 'fault-bin'
        bindir.mkdir()
        shim = bindir / 'python3'
        shim.write_text('#!' + scenarios.sys.executable + '\n' + '''
import importlib.util,os,sys
args=sys.argv[1:]
if len(args)>2 and args[0]=='-I' and args[1].endswith('/goal_forge.py') and args[2]=='adopt':
    spec=importlib.util.spec_from_file_location('forge_fault',args[1])
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    original=mod.store.Store.commit
    def commit(self,*a,**kw):
        def fault(point):
            if point==os.environ['FORGE_FAULT_POINT']: os._exit(71)
        kw['fault']=fault
        return original(self,*a,**kw)
    mod.store.Store.commit=commit
    sys.argv=[args[1]]+args[2:]
    sys.exit(mod.main())
os.execv(sys.executable,[sys.executable]+args)
''')
        shim.chmod(0o755)
        before = (test.state / 'store/commits/current').read_bytes()
        old_scope = (test.state / 'evidence/raw/0.txt').read_bytes()
        history = (test.state / 'loop-log.md').read_bytes()
        results = []
        for point in ('generation-published', 'pointer-published'):
            env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ['PATH'], FORGE_FAULT_POINT=point)
            result = test.call(scenarios.CTL, 'migrate', expected=4, env=env)
            test.assertTrue((test.state / 'store/pending').exists())
            test.call(scenarios.CTL, 'recover')
            test.assertEqual(history, (test.state / 'loop-log.md').read_bytes())
            current = (test.state / 'store/commits/current').read_bytes()
            if point == 'generation-published':
                test.assertEqual(before, current)
                test.assertEqual(old_scope, (test.state / 'evidence/raw/0.txt').read_bytes())
            else:
                test.assertNotEqual(before, current)
                test.assertNotEqual(old_scope, (test.state / 'evidence/raw/0.txt').read_bytes())
            results.append(dict(point=point, result=result.returncode, stdout=result.stdout, stderr=result.stderr))
        final = (test.state / 'store/commits/current').read_bytes()
        test.call(scenarios.CTL, 'migrate')
        test.assertEqual(final, (test.state / 'store/commits/current').read_bytes())
        folder = output / 'migration-faults'
        shutil.copytree(test.root, folder / 'project')
        (folder / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print('migration-faults: PASS', flush=True)
    finally:
        test.doCleanups()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
