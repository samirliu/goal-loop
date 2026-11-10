import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('goal_store', Path(__file__).resolve().parents[1] / 'scripts/goal_store.py')
store_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(store_module)
Store, StoreError, Conflict = store_module.Store, store_module.StoreError, store_module.Conflict


class CloseDurability(unittest.TestCase):
    def test_failed_view_sync_preserves_recovery_marker_and_old_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / 'store').mkdir()
            (state / 'state.rec').write_bytes(b'iteration=0\n')
            (state / 'loop-log.md').write_bytes(b'old\n')
            store_module.close_journal(state, 'begin')
            marker = (state / 'store/pending').read_bytes()
            (state / 'state.rec').write_bytes(b'iteration=1\n')
            with mock.patch.object(store_module.os, 'fsync', side_effect=OSError('injected I/O failure')):
                with self.assertRaises(OSError):
                    store_module.close_journal(state, 'finish')
            self.assertEqual((state / 'store/pending').read_bytes(), marker)
            store_module.close_journal(state, 'recover')
            self.assertEqual((state / 'state.rec').read_bytes(), b'iteration=0\n')

    def test_finish_syncs_file_and_directory_before_removing_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / 'store').mkdir()
            (state / 'state.rec').write_bytes(b'iteration=0\n')
            store_module.close_journal(state, 'begin')
            pending = state / 'store/pending'
            real_sync = os.fsync
            observations = []
            def sync(fd):
                observations.append(pending.exists())
                return real_sync(fd)
            with mock.patch.object(store_module.os, 'fsync', side_effect=sync):
                store_module.close_journal(state, 'finish')
            self.assertGreaterEqual(len(observations), 4)
            self.assertTrue(all(observations[:-1]))
            self.assertFalse(observations[-1])

    def test_begin_refuses_symlink_evidence_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'state'
            state.mkdir()
            (state / 'store').mkdir()
            (state / 'state.rec').write_bytes(b'iteration=0\n')
            outside = Path(tmp) / 'outside'
            outside.mkdir()
            (state / 'evidence').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(StoreError):
                store_module.close_journal(state, 'begin')
            self.assertFalse((state / 'store/pending').exists())


def crash_writer(root, head, point):
    def fault(where):
        if where == point:
            os._exit(73)
    Store(root).commit('operation', b'intent', {'state.rec': b'new', 'loop-log.md': b'new'}, head, fault)


def competing_writer(root, head, name, queue):
    try:
        queue.put(('ok', Store(root).commit(name, name.encode(), {'state.rec': name.encode()}, head)))
    except Conflict:
        queue.put(('conflict', name))


def hold_writer_lock(root, ready, release):
    with Store(root)._lock():
        ready.set()
        release.wait(10)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def test_initial_migration_and_idempotency(self):
        self.assertEqual(self.store.read(), (None, {}))
        files = {'state.rec': b'old\n', 'loop-log.md': b'\x00\xff'}
        head = self.store.commit('migration', b'legacy baseline', files)
        self.assertEqual(self.store.read(), (head, files))
        self.assertEqual(self.store.commit('migration', b'legacy baseline', files), head)
        with self.assertRaises(Conflict):
            self.store.commit('migration', b'changed', files)
        next_head = self.store.commit('next', b'change', {'state.rec': b'new'}, head)
        self.assertEqual(self.store.commit('migration', b'legacy baseline', files), head)
        self.assertEqual(self.store.read()[0], next_head)

    def test_open_and_read_never_create_store_files(self):
        missing = Path(self.temp.name) / 'missing' / 'store'
        reader = Store(missing)
        self.assertEqual(reader.read(), (None, {}))
        self.assertFalse(missing.parent.exists())
        empty = Path(self.temp.name) / 'empty'; empty.mkdir()
        self.assertEqual(Store(empty).read(), (None, {}))
        self.assertEqual(list(empty.iterdir()), [])

    def test_nested_paths_are_preserved_and_unsafe_names_rejected(self):
        files = {'evidence/raw/1.txt': b'raw', 'state.rec': b'state'}
        head = self.store.commit('nested', b'intent', files)
        self.assertEqual(self.store.read(), (head, files))
        for name in ('/a', 'a//b', 'a/./b', 'a/../b', './a', 'a/', 'a\\b', 'a\x00b'):
            with self.subTest(name=name), self.assertRaises(StoreError):
                self.store.commit('unsafe', b'x', {name: b'x'}, head)

    def test_crash_before_and_after_pointer(self):
        for point in ('generation-published', 'pointer-published'):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as root:
                s = Store(root)
                before = s.commit('base', b'base', {'state.rec': b'old', 'loop-log.md': b'old'})
                p = mp.Process(target=crash_writer, args=(root, before, point)); p.start(); p.join(10)
                self.assertEqual(p.exitcode, 73)
                head, files = s.read()
                self.assertEqual(files, {'state.rec': b'old' if point == 'generation-published' else b'new', 'loop-log.md': b'old' if point == 'generation-published' else b'new'})
                s.recover()
                self.assertEqual(s.read(), (head, files))
                if point == 'generation-published':
                    head = s.commit('operation', b'intent', {'state.rec': b'new', 'loop-log.md': b'new'}, before)
                self.assertEqual(s.commit('operation', b'intent', {'state.rec': b'new', 'loop-log.md': b'new'}, before), head)

    def test_first_generation_crash_recovers(self):
        p = mp.Process(target=crash_writer, args=(self.temp.name, None, 'generation-published')); p.start(); p.join(10)
        self.assertEqual(p.exitcode, 73)
        self.assertEqual(self.store.read(), (None, {}))
        self.store.recover()
        self.assertEqual(self.store.read(), (None, {}))

    def test_simultaneous_writers_compare_and_swap(self):
        head = self.store.commit('base', b'base', {'state.rec': b'base'})
        queue = mp.Queue()
        processes = [mp.Process(target=competing_writer, args=(self.temp.name, head, str(i), queue)) for i in range(2)]
        for p in processes: p.start()
        for p in processes: p.join(10); self.assertEqual(p.exitcode, 0)
        results = [queue.get(timeout=2)[0] for _ in processes]
        self.assertEqual(sorted(results), ['conflict', 'ok'])
        self.assertIn(self.store.read()[1]['state.rec'], [b'0', b'1'])

    def test_lock_symlink_is_not_followed(self):
        target = Path(self.temp.name) / 'outside-target'
        target.write_bytes(b'unchanged')
        before = target.stat()
        self.store.lock.symlink_to(target)
        with self.assertRaises(StoreError):
            self.store.commit('x', b'intent', {'state.rec': b'x'})
        self.assertEqual(target.read_bytes(), b'unchanged')
        self.assertEqual(target.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertFalse(self.store.pointer.exists())
        self.assertEqual(list(self.store.generations.iterdir()), [])

    def test_missing_nofollow_fails_closed(self):
        with mock.patch.object(store_module.os, 'O_NOFOLLOW', 0):
            with self.assertRaises(StoreError):
                self.store.commit('x', b'intent', {'state.rec': b'x'})
        self.assertFalse(self.store.pointer.exists())
        self.assertFalse(self.store.lock.exists())

    def test_lock_timeout_does_not_publish(self):
        ready, release = mp.Event(), mp.Event()
        p = mp.Process(target=hold_writer_lock, args=(self.temp.name, ready, release))
        p.start()
        try:
            self.assertTrue(ready.wait(5))
            start = time.monotonic()
            with self.assertRaisesRegex(StoreError, 'lock timeout'):
                self.store.commit('x', b'intent', {'state.rec': b'x'}, lock_timeout=0.1)
            self.assertGreaterEqual(time.monotonic() - start, 0.08)
            self.assertFalse(self.store.pointer.exists())
            self.assertEqual(list(self.store.generations.iterdir()), [])
            with self.assertRaisesRegex(StoreError, 'lock timeout'):
                self.store.recover(lock_timeout=0)
        finally:
            release.set(); p.join(5)
        self.assertEqual(p.exitcode, 0)
        self.assertTrue(self.store.commit('x', b'intent', {'state.rec': b'x'}, lock_timeout=1))

    def test_invalid_lock_timeout_rejected(self):
        for timeout in (-1, float('nan'), float('inf'), True, '1'):
            with self.subTest(timeout=timeout), self.assertRaises(StoreError):
                self.store.commit('x', b'intent', {}, lock_timeout=timeout)
        self.assertFalse(self.store.pointer.exists())

    def test_lock_timeout_preserves_existing_head_and_generations(self):
        head = self.store.commit('base', b'base', {'state.rec': b'old'})
        pointer_before = self.store.pointer.read_bytes()
        generations_before = sorted(p.name for p in self.store.generations.iterdir())
        ready, release = mp.Event(), mp.Event()
        p = mp.Process(target=hold_writer_lock, args=(self.temp.name, ready, release))
        p.start()
        try:
            self.assertTrue(ready.wait(5))
            with self.assertRaisesRegex(StoreError, 'lock timeout'):
                self.store.commit('next', b'next', {'state.rec': b'new'}, head, lock_timeout=0.05)
            self.assertEqual(self.store.pointer.read_bytes(), pointer_before)
            self.assertEqual(sorted(p.name for p in self.store.generations.iterdir()), generations_before)
            self.assertEqual(self.store.read(), (head, {'state.rec': b'old'}))
        finally:
            release.set(); p.join(5)
        self.assertEqual(p.exitcode, 0)

    def test_concurrent_readers_never_mix_views(self):
        head = self.store.commit('base', b'base', {'state.rec': b'base', 'loop-log.md': b'base'})
        p = mp.Process(target=crash_writer, args=(self.temp.name, head, 'pointer-published')); p.start()
        while p.is_alive():
            _, files = self.store.read()
            self.assertEqual(files['state.rec'], files['loop-log.md'])
        p.join(10); self.assertEqual(p.exitcode, 73)
        _, files = self.store.read(); self.assertEqual(files['state.rec'], files['loop-log.md'])

    def test_corruption_and_missing_pointer_fail_closed(self):
        head = self.store.commit('base', b'base', {'state.rec': b'base'})
        (self.store.generations / head).write_bytes(b'corrupt')
        with self.assertRaises(StoreError): self.store.read()
        with self.assertRaises(StoreError): self.store.recover()
        self.store.pointer.unlink()
        with self.assertRaises(StoreError): self.store.read()
        with self.assertRaises(StoreError): self.store.recover()

    def test_invalid_names_and_torn_pointer(self):
        for key in ('../state', '..', ''):
            with self.subTest(key=key), self.assertRaises(StoreError):
                self.store.commit('x', b'x', {key: b'x'})
        self.store.pointer.write_bytes(b'{"version":')
        with self.assertRaises(StoreError): self.store.read()
        with self.assertRaises(StoreError): self.store.commit('x', b'x', {})
        self.store.pointer.write_bytes(b'{"version":true,"head":null}')
        with self.assertRaises(StoreError): self.store.read()

    def test_missing_committed_predecessor_is_not_an_empty_history(self):
        head = self.store.commit('base', b'base', {'state.rec': b'base'})
        head = self.store.commit('second', b'next', {'state.rec': b'next'}, head)
        obj = json.loads((self.store.generations / head).read_bytes())
        (self.store.generations / obj['previous']).unlink()
        with self.assertRaises(StoreError): self.store.read()
        with self.assertRaises(StoreError): self.store.recover()

    def test_recover_preserves_unknown_and_corrupt_entries(self):
        self.store.commit('base', b'base', {'state.rec': b'base'})
        orphan = self.store.generations / 'future-version.dat'
        orphan.write_bytes(b'valuable unknown data')
        owned_temp = self.store.generations / '.goal-store-v1-abcdefgh'
        owned_temp.write_bytes(b'partial')
        with self.assertRaises(StoreError): self.store.recover()
        self.assertEqual(orphan.read_bytes(), b'valuable unknown data')
        self.assertTrue(owned_temp.exists())
        orphan.unlink()
        corrupt = self.store.generations / ('a' * 64)
        corrupt.write_bytes(b'not a valid generation')
        with self.assertRaises(StoreError): self.store.recover()
        self.assertTrue(corrupt.exists())
        self.assertTrue(owned_temp.exists())
        corrupt.unlink()
        unknown_temp = self.store.root / '.goal-store-v1-unrecognized'
        unknown_temp.write_bytes(b'preserve')
        with self.assertRaises(StoreError): self.store.recover()
        self.assertTrue(unknown_temp.exists())
        self.assertTrue(owned_temp.exists())
        unknown_temp.unlink()
        self.store.recover()
        self.assertFalse(owned_temp.exists())


if __name__ == '__main__':
    unittest.main()
