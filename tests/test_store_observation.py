"""Performance changes must not cache away corruption or stop validation early."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('observation_store', Path(__file__).resolve().parents[1]/'scripts/goal_store.py')
store = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(store)


class Observations(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='goal-store-observation-')
        self.addCleanup(temporary.cleanup)
        self.reader = store.Store(temporary.name)
        self.old = self.reader.commit('old', b'old', {'state.rec': b'old'})
        self.head = self.reader.commit('head', b'head', {'state.rec': b'head'}, self.old)

    def corrupt(self, identity):
        path = self.reader.generations/identity
        info = path.stat()
        raw = path.read_bytes()
        path.write_bytes(raw.replace(b'"version":1', b'"version":2'))
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))

    def test_each_read_revalidates_even_same_size_and_mtime(self):
        self.assertEqual(self.reader.read(), (self.head, {'state.rec': b'head'}))
        self.corrupt(self.head)
        with self.assertRaisesRegex(store.StoreError, 'checksum'):
            self.reader.read()

    def test_selected_current_or_old_operation_cannot_skip_corrupt_ancestry(self):
        self.assertEqual(self.reader.lookup('head'), (self.head, {'state.rec': b'head'}))
        self.corrupt(self.old)
        for operation in ('head', 'old', 'missing'):
            with self.subTest(operation=operation), self.assertRaises(store.StoreError):
                self.reader.lookup(operation)
        with self.assertRaises(store.StoreError):
            self.reader.read()

    def test_writers_and_recovery_recheck_prior_observations(self):
        self.reader.read()
        self.corrupt(self.old)
        pointer = self.reader.pointer.read_bytes()
        for action in (lambda: self.reader.commit('next', b'next', {}, self.head), self.reader.recover):
            with self.assertRaises(store.StoreError):
                action()
            self.assertEqual(self.reader.pointer.read_bytes(), pointer)

    def test_future_head_is_observed_by_same_store_instance(self):
        self.reader.read()
        writer = store.Store(self.reader.root)
        new = writer.commit('next', b'next', {'state.rec': b'next'}, self.head)
        self.assertEqual(self.reader.read(), (new, {'state.rec': b'next'}))
        self.assertEqual(self.reader.lookup('old'), (self.old, {'state.rec': b'old'}))


if __name__ == '__main__':
    unittest.main()
