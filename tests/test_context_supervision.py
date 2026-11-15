"""Original check timeouts remain authoritative when no total budget exists."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('context_supervision', ROOT/'scripts/goal_context.py')
context = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context)


class ContextSupervision(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='goal-context-supervision-')
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.fd = os.open(self.project, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)

    def command(self, code, cap=None, **kwargs):
        return context.protected(self.project, [sys.executable, '-c', code], cap, self.fd, **kwargs)

    def test_unbudgeted_verification_can_finish_after_thirty_seconds(self):
        result = self.command('import time; time.sleep(31); print("original check completed")')
        self.assertEqual(result['result'], 0, result)
        self.assertIn('original check completed', result['stdout'])

    def test_original_failure_is_not_turned_into_a_successful_receipt(self):
        result = self.command('raise SystemExit(7)')
        self.assertEqual(result['result'], 7)

    def test_existing_deadline_still_cancels_and_prevents_late_writes(self):
        marker = self.project/'late'
        result = self.command('import time; from pathlib import Path; time.sleep(1); Path(%r).touch()' % str(marker),
                              time.monotonic()+.15)
        self.assertEqual(result['result'], 124, result)
        self.assertFalse(marker.exists())

    def test_read_only_map_preparation_keeps_its_explicit_limit(self):
        result = self.command('import time; time.sleep(1)', max_seconds=.15)
        self.assertEqual(result['result'], 124, result)


if __name__ == '__main__':
    unittest.main()
