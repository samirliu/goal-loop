"""A native agent can be cancelled while its process/tool owner stays alive."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

BOUNDED = Path(__file__).resolve().parents[1] / 'scripts/goal_bounded.py'


@unittest.skipUnless(os.name == 'posix', 'POSIX supervision required')
class HostCancellation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='goal-native-cancel-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.children = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
            child.communicate(timeout=4)

    def launch(self, name, *options, code=None):
        marker = self.root / (name + '.ticks')
        if code is None:
            # The heartbeat is a grandchild; stopping just the first command
            # would leave observable writes behind.
            heartbeat = ('import time; from pathlib import Path; p=Path(%r)\n'
                         'while True:\n with p.open("ab") as f: f.write(b"x"); f.flush()\n time.sleep(.02)\n') % str(marker)
            code = ('import subprocess,sys,time\nsubprocess.Popen([sys.executable,"-I","-c",%r])\n'
                    'time.sleep(30)\n') % heartbeat
        command = [sys.executable, '-I', str(BOUNDED), '--owner', str(os.getpid()),
                   '--seconds', '30', *options, '--', sys.executable, '-I', '-c', code]
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.children.append(child)
        return child, marker

    def started(self, child, marker):
        until = time.monotonic() + 5
        while not marker.exists() or marker.stat().st_size < 2:
            self.assertIsNone(child.poll())
            self.assertLess(time.monotonic(), until, 'worker did not produce heartbeat')
            time.sleep(.02)

    def test_cancel_stops_owned_descendants_and_preserves_other_worker(self):
        one_token, two_token = self.root / 'one.cancel', self.root / 'two.cancel'
        one, first = self.launch('first', '--cancel-file', str(one_token))
        two, second = self.launch('second', '--cancel-file', str(two_token))
        self.started(one, first)
        self.started(two, second)
        one_token.touch()
        out, err = one.communicate(timeout=3)
        self.assertEqual(one.returncode, 130, out + err)
        frozen, ongoing = first.stat().st_size, second.stat().st_size
        time.sleep(.16)
        self.assertEqual(frozen, first.stat().st_size)
        self.assertGreater(second.stat().st_size, ongoing)
        self.assertIsNone(two.poll())
        two_token.touch()
        two.communicate(timeout=3)
        self.assertEqual(two.returncode, 130)

    def test_cancelled_ticket_never_releases_a_new_command(self):
        token = self.root / 'already.cancel'
        token.touch()
        target = self.root / 'forbidden'
        child, _ = self.launch('before-start', '--cancel-file', str(token),
                               code='from pathlib import Path; Path(%r).touch()' % str(target))
        out, err = child.communicate(timeout=3)
        self.assertEqual(child.returncode, 130, out + err)
        self.assertFalse(target.exists())

    def test_host_deadline_caps_longer_command_allowance(self):
        child, marker = self.launch('deadline', '--deadline-epoch', str(time.time() + .5))
        out, err = child.communicate(timeout=3)
        self.assertEqual(child.returncode, 124, out + err)
        self.assertTrue(marker.exists())
        frozen = marker.stat().st_size
        time.sleep(.12)
        self.assertEqual(frozen, marker.stat().st_size)


if __name__ == '__main__':
    unittest.main(verbosity=2)
