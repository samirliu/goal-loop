"""Registered state inherits guards and exact recovery without extra lists."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('registry_host', ROOT/'scripts/goal_host.py')
host = importlib.util.module_from_spec(spec); spec.loader.exec_module(host)
store = host.store


class StateRegistry(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='goal-state-registry-')
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name).resolve()
        host.begin(self.project, 'claude', 'registry-fixture', 180, request='Exercise registered state protection.')
        self.state = self.project/'.goal'
        raw = self.state/'evidence/raw/0.txt'; raw.parent.mkdir(exist_ok=True)
        raw.write_bytes(b'controlled raw evidence')
        self.commits = store.Store(self.state/'store/commits')
        head, snapshot = self.commits.read()
        self.commits.commit('registry-fixture', b'raw view fixture',
                            store.attach_views(self.state, snapshot), expected_head=head)

    def test_all_registered_guards_detect_writes_including_absent_author_inputs(self):
        for name, field in store.STATE_FIELDS.items():
            if not field.guard:
                continue
            with self.subTest(field=name):
                path = self.state/name
                before = path.read_bytes() if path.exists() else None
                digest = store.guard_digest(self.state)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((before or b'')+b'changed by checker')
                self.assertNotEqual(store.guard_digest(self.state), digest)
                path.unlink() if before is None else path.write_bytes(before)
                self.assertEqual(store.guard_digest(self.state), digest)
        store.verify_views(self.state)

    def test_every_committed_view_refuses_mutation_and_recovers_exact_bytes_or_absence(self):
        _, snapshot = self.commits.read()
        expected = store._committed_views(snapshot)
        self.assertIn(store.CONTROL_FILE, expected)
        self.assertTrue(set(store.writer_fields('runner')) <= set(expected))
        for name, original in expected.items():
            with self.subTest(field=name):
                path = self.state/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((original or b'')+b'changed')
                with self.assertRaisesRegex(store.StoreError, 'ledger-view-mismatch'):
                    store.verify_views(self.state)
                store.restore_committed_views(self.state)
                self.assertEqual(path.read_bytes() if path.exists() else None, original)
                store.verify_views(self.state)

    def test_one_new_field_declaration_supplies_guard_capture_publication_and_recovery(self):
        name = 'new-phase.json'
        with patch.dict(store.STATE_FIELDS, {name:store.StateField(view='bound', writers=('phase',))}):
            # Optional fields keep old manifests readable until the next commit.
            head = store.verify_views(self.state)
            _, snapshot = self.commits.read()
            head = self.commits.commit('introduce-phase', b'new registered field',
                                       store.attach_views(self.state, snapshot), expected_head=head)
            _, snapshot = self.commits.read()
            self.assertIsNone(json.loads(snapshot[store._VIEW_META])['views'][name])
            before = store.guard_digest(self.state)
            (self.state/name).write_bytes(b'uncommitted')
            self.assertNotEqual(store.guard_digest(self.state), before)
            with self.assertRaisesRegex(store.StoreError, 'ledger-view-mismatch'):
                store.verify_views(self.state)
            store.restore_committed_views(self.state)
            self.assertFalse((self.state/name).exists())
            store.publish_views(self.state, 'phase', {name:b'committed phase'},
                                'publish-phase', b'phase intent', expected_head=head)
            (self.state/name).write_bytes(b'corrupt')
            store.restore_committed_views(self.state)
            self.assertEqual((self.state/name).read_bytes(), b'committed phase')
            store.verify_views(self.state)

    def test_shared_publisher_refuses_unknown_mixed_or_incomplete_writer_scopes(self):
        head = store.verify_views(self.state)
        for writer, files in [('unknown', {'new.json':b'bad'}),
                              ('runner', {'runner.json':b'incomplete'}),
                              ('control', {store.CONTROL_FILE:b'bad', 'state.rec':b'bad'})]:
            with self.subTest(writer=writer):
                with self.assertRaisesRegex(store.StoreError, 'writer scope'):
                    store.publish_views(self.state, writer, files, 'bad-scope', b'intent', expected_head=head)
                self.assertEqual(store.verify_views(self.state), head)


if __name__ == '__main__':
    unittest.main()
