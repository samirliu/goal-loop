"""Explicit publication of hand-authored gate-semantic fixtures.

This is test setup, not a production migration/recovery path. Integration tests
must call real entrypoints directly and must not use this fixture publisher.
"""
import importlib.util
from pathlib import Path
import sys
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('semantic_fixture_store', ROOT / 'scripts/goal_store.py')
store = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(store)


def publish_fixture(project, permitted_root):
    project, permitted_root = Path(project).resolve(), Path(permitted_root).resolve()
    if not project.is_relative_to(permitted_root):
        return
    state = project / '.goal'
    if not state.is_dir() or (state / 'store/pending').exists():
        return
    commits = store.Store(state / 'store/commits')
    head, snapshot = commits.read()
    if head is None and not (state / 'state.rec').exists():
        return
    actual = store._capture_files(state, store._view_names(state))
    if (store._VIEW_META in snapshot and actual == store._committed_views(snapshot)
            and store.json.loads(snapshot[store._VIEW_META]).get('version') == 2
            and store.json.loads(snapshot[store._VIEW_META]).get('approved') == store.current_approval(state)):
        return
    # The fixture intentionally supplies a complete state, including negative
    # semantic examples. Publish that input without changing any view bytes.
    frame = {name: data for name, data in actual.items() if data is not None}
    frame[store._VIEW_META] = store._encode({'version': 2, 'approved': store.current_approval(state),
                                           'views': {name: store._hash(data) if data is not None else None
                                                     for name, data in actual.items()}})
    commits.commit('fixture-' + uuid.uuid4().hex, b'hand-authored semantic test input',
                   frame, expected_head=head, lock_timeout=0)


if __name__ == '__main__':
    project, root, args = '.', sys.argv[1], sys.argv[2:]
    value_flags = {'--project', '--operation-id', '--task', '--files', '--checks-pass', '--checks-fail',
                   '--checks-unverifiable', '--progress', '--exit-signal', '--error-signature',
                   '--false-complete', '--dry', '--score', '--judge-score', '--strategy-delta',
                   '--strategy', '--adversarial', '--adversarial-note', '--fault', '--fault-outcome', '--fault-note'}
    i, is_digest = 0, False
    while i < len(args):
        flag = args[i]
        if flag in value_flags and i + 1 < len(args):
            if flag == '--project':
                project = args[i + 1]
            i += 2
        else:
            is_digest = is_digest or flag == '--digest'
            i += 1
    if not is_digest:
        publish_fixture(project, root)
