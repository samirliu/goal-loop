"""Portable recheck of trial material bindings and independent outcome grading."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root, regrade=False):
    manifest = json.loads((root / 'manifest.json').read_bytes())
    original_root = Path(manifest['trials'][0]).parent.parent
    for name, digest in manifest['frozen'].items():
        assert sha(root / Path(name).relative_to(original_root)) == digest, name
    if not manifest['pilot']:
        assert len(manifest['trials']) == 36
    initial, counts, judged, rechecked = {}, Counter(), 0, []
    for name in manifest['trials']:
        folder = root / 'trials' / Path(name).name
        config = json.loads((folder / 'trial.json').read_bytes())
        assert sha(folder / 'BRIEF.md') == config['brief_sha256']
        key = config['family'], config['repetition']
        if key in initial:
            assert initial[key] == config['initial'], key
        initial[key] = config['initial']
        counts[config['arm']] += 1
        if not (folder / 'result.json').exists():
            continue
        result = json.loads((folder / 'result.json').read_bytes())
        judged += 1
        for field in ('arm', 'family', 'seed', 'budget_seconds'):
            assert result[field] == config[field]
        assert result['accepted_within_budget'] == (result['accepted'] and result['timely'])
        assert result['timely'] == (result['independent_finished_seconds'] <= config['budget_seconds'])
        assert result['money'] is None
        protected = all((folder / 'snapshot' / name).is_file() and sha(folder / 'snapshot' / name) == value
                        for name, value in config['protected'].items())
        assert protected == result['protected']
        if result['arm'] != 'native':
            assert result['tokens'] is None
        elif result['protocol_compliant']:
            receipt = result['native_goal']
            assert receipt['status'] == 'complete'
            assert receipt['objective'] == (folder / 'snapshot/TASK.md').read_text()
            raw = [v['goal'] for k, v in receipt.items()
                   if isinstance(v, dict) and isinstance(v.get('goal'), dict)]
            assert any(r['status'] == 'active' for r in raw), 'missing native create/read receipt'
            assert any(r['status'] == 'complete' for r in raw), 'missing native completion receipt'
            assert all(r['threadId'] == receipt['thread_id'] and r['objective'].strip() == receipt['objective'].strip()
                       for r in raw)
        if regrade:
            with tempfile.TemporaryDirectory() as tmp:
                snapshot = Path(tmp) / 'work'
                shutil.copytree(folder / 'snapshot', snapshot)
                command = [sys.executable, '-I', str(root / 'skill/scripts/goal_bounded.py'),
                           '--owner', str(os.getpid()), '--seconds', '20', '--', sys.executable,
                           '-I', '-B', str(root / 'oracle/grade.py'), '--project', str(snapshot),
                           '--family', config['family'], '--seed', str(config['seed'])]
                proc = subprocess.run(command, capture_output=True, text=True, timeout=24)
                try:
                    current = json.loads(proc.stdout)
                except ValueError:
                    current = dict(ok=False, error=proc.stderr)
                expected = bool(result['quality'] and result['quality']['ok'])
                rechecked.append(dict(trial=folder.name, original_ok=expected, replay=current, result=proc.returncode))
                assert bool(current['ok']) == expected, rechecked[-1]
    if not manifest['pilot']:
        assert counts == dict(plain=12, skill=12, native=12)
    return dict(planned=len(manifest['trials']), adjudicated=judged, bindings='PASS', rechecked=rechecked)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--regrade', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(args.root.resolve(), args.regrade), indent=2))
