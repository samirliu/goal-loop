#!/usr/bin/env python3
"""Run six named mutations against unchanged regressions in disposable copies."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
PYTHON = [sys.executable, '-B']
SHELL = ['bash', 'tests/run_tests.sh', '--only']
MUTATIONS = (
    ('gate-claim', 'scripts/goal_gate.sh',
     '[ "$claim" = yes ] || [ "$mode" = checkpoint ] || fail "not-claimed"',
     ':',
     [*SHELL, '04'], 'FAIL - 04 not-claimed -> rc2 (want rc=2 got rc=0)'),
    ('bind-content', 'scripts/goal_tree_digest.py',
     'value.update(chunk)', "value.update(b'')",
     [*PYTHON, 'tests/test_worktree_scope.py', 'WorktreeScope.test_linked_worktree_uses_the_selected_worktree_bytes'],
     'AssertionError:'),
    ('prove-metric-exit', 'scripts/goal_gate.sh',
     '[ "$rc" -eq 0 ] || { printf \'%s|BROKEN|measurement command',
     '[ "$rc" -ge 0 ] || { printf \'%s|BROKEN|measurement command',
     [*SHELL, '160'], 'FAIL - 160 a numeric line from a failed command cannot deliver GO (want rc=2 got rc=0)'),
    ('gradient-water-mark', 'scripts/goal_gate.sh',
     'if [ -n "$best" ] && [ "$best" != "none" ]; then',
     'if false; then',
     [*SHELL, '54'], 'FAIL - 54 score-regressed -> rc2 (want rc=2 got rc=0)'),
    ('fence-rejected-batch', 'scripts/goal_store.py',
     "            raise StoreError('malformed bind row; no rows appended')",
     "            with (Path(state) / 'verdicts.rec').open('ab') as output:\n"
     "                output.write((lines[0] + '\\n').encode('utf-8'))\n"
     "            raise StoreError('malformed bind row; no rows appended')",
     [*PYTHON, 'tests/test_mutation_commit.py', 'MutationCommit.test_bind_batch_is_all_or_nothing_and_input_is_part_of_identity'],
     'self.assertEqual(before, self.all_files(project))'),
    ('shared-deadline', 'scripts/goal_runner.py',
     'cap = mono + (3 if expired and settlement else min(remaining)) if remaining else None',
     'cap = None',
     [*PYTHON, 'tests/test_gate_budget.py', 'GateBudget.test_expired_standalone_batch_does_not_give_every_ac_new_time'],
     'AssertionError: 0 != 2'),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observe(root, command, log):
    env = {name: value for name, value in os.environ.items() if not name.startswith('GOAL_')}
    result = subprocess.run(command, cwd=root, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=60)
    log.write_bytes(result.stdout)
    return result.returncode, result.stdout.decode('utf-8', errors='replace')


def campaign(out):
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    with tempfile.TemporaryDirectory(prefix='goal-invariant-mutations-') as scratch:
        reference = Path(scratch) / 'reference'
        for name in ('scripts', 'tests', 'assets'):
            shutil.copytree(ROOT / name, reference / name, ignore=shutil.ignore_patterns('__pycache__', '.DS_Store'))
        sources = {p.relative_to(reference).as_posix(): sha(p) for p in sorted(reference.rglob('*')) if p.is_file()}
        for name, path, old, new, command, expected in MUTATIONS:
            variant = Path(scratch) / name
            shutil.copytree(reference, variant)
            original = (reference / path).read_text()
            if original.count(old) != 1:
                raise RuntimeError(f'{name}: expected a unique mutation point in {path}')
            changed = original.replace(old, new)
            baseline_rc, _ = observe(reference, command, out / (name + '.clean.txt'))
            (variant / path).write_text(changed)
            patch = difflib.unified_diff(original.splitlines(keepends=True), changed.splitlines(keepends=True),
                                         fromfile='a/' + path, tofile='b/' + path)
            (out / (name + '.patch')).write_text(''.join(patch))
            mutant_rc, log = observe(variant, command, out / (name + '.mutated.txt'))
            detected = baseline_rc == 0 and mutant_rc == 1 and expected in log
            rows.append(dict(name=name, path=path, command=command, clean=baseline_rc, mutated=mutant_rc,
                             expected_failure=expected, detected=detected))
            print(name, 'detected' if detected else 'unverified', flush=True)
    (out / 'manifest.json').write_text(json.dumps(dict(sources=sources, mutations=rows), indent=2) + '\n')
    return all(row['detected'] for row in rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.exit(0 if campaign(args.output) else 1)
