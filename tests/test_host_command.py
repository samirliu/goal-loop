"""Exercise the production ticket wrapper with real command descendants."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('host_command_test', ROOT / 'scripts/goal_host.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


class HostCommand(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='goal-host-command-')
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.children = []
        self.addCleanup(self.cleanup)
        result = subprocess.run(['bash', str(ROOT / 'scripts/goal_ctl.sh'), 'init', '--project', str(self.project)],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        (self.project / '.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | bounded commands | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
        result = subprocess.run(['bash', str(ROOT / 'scripts/goal_ctl.sh'), 'stamp', '--auto', '--project', str(self.project)],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        host.begin(self.project, 'work', 'owned-command', 90)
        graph = self.project / 'graph.json'
        graph.write_text(json.dumps(dict(version=1, context={}, capacity=2,
            jobs=[dict(id='T'+str(n), files=[str(n)+'.ticks'], deps=[],
                       check=[sys.executable, '-c', 'from pathlib import Path; assert Path(%r).read_bytes()==b"valid"' % (str(n)+'.ticks')])
                  for n in (1, 2)],
            final_check=['true'], instruments=[], inputs=[])))
        wave = host.crew.begin(self.project, graph, 'crew', 'production-wrapper')
        self.items = [host.prepare(self.project, wave, 'T'+str(n)) for n in (1, 2)]

    def cleanup(self):
        for process in self.children:
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=4)

    def launch(self, index, code=None):
        marker = self.project / (str(index+1)+'.ticks')
        if code is None:
            heartbeat = ('from pathlib import Path; import time; p=Path(%r)\n'
                         'while True:\n with p.open("ab") as f: f.write(b"x"); f.flush()\n time.sleep(.02)\n') % str(marker)
            code = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-I","-c",%r]); time.sleep(20)' % heartbeat
        process = subprocess.Popen([sys.executable, '-I', str(ROOT / 'scripts/goal_host_command.py'),
            str(self.project), self.items[index]['ticket'], '--', sys.executable, '-I', '-c', code],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.children.append(process)
        return process, marker

    def wait_ready(self, process, marker):
        end = time.monotonic()+5
        while not marker.exists() or marker.stat().st_size < 2:
            if process.poll() is not None:
                out, err = process.communicate(timeout=1)
                self.fail('owned command exited %s: %r %r' % (process.returncode, out, err))
            self.assertLess(time.monotonic(), end)
            time.sleep(.02)

    def test_ticket_cancel_stops_descendants_and_keeps_sibling_and_parent_trace(self):
        first, a = self.launch(0)
        second, b = self.launch(1)
        self.wait_ready(first, a); self.wait_ready(second, b)
        host.cancel(self.project, self.items[0]['ticket'])
        out, err = first.communicate(timeout=4)
        self.assertEqual(first.returncode, 130, out+err)
        frozen, ongoing = a.stat().st_size, b.stat().st_size
        time.sleep(.15)
        self.assertEqual(a.stat().st_size, frozen)
        self.assertGreater(b.stat().st_size, ongoing)
        host.cancel(self.project, self.items[1]['ticket'])
        second.communicate(timeout=4)
        spans = host.trace.records(self.project)
        owned = [s for s in spans if s['label'] == 'host-owned-tool']
        self.assertEqual(len(owned), 2)
        self.assertEqual({s['parent'] for s in owned}, {i['trace'] for i in self.items})
        self.assertEqual({s['result'] for s in owned}, {130})

    def test_pre_cancel_never_releases_command(self):
        host.cancel(self.project, self.items[0]['ticket'])
        process, marker = self.launch(0, 'from pathlib import Path; Path(%r).touch()' % str(self.project/'1.ticks'))
        out, err = process.communicate(timeout=4)
        self.assertEqual(process.returncode, 130, out+err)
        self.assertFalse(marker.exists())

    def test_wrapper_rechecks_shortened_budget_instead_of_ticket_original_deadline(self):
        host.begin(self.project, 'work', 'owned-command', 1.8)
        started = time.monotonic()
        process, marker = self.launch(0)
        out, err = process.communicate(timeout=4)
        self.assertEqual(process.returncode, 124, out+err)
        self.assertLess(time.monotonic()-started, 3)
        self.assertTrue(marker.exists())
        frozen = marker.stat().st_size
        time.sleep(.12)
        self.assertEqual(marker.stat().st_size, frozen)

    def test_fixed_worker_check_uses_project_cwd_without_granting_adoption(self):
        marker = self.project/'1.ticks'
        marker.write_bytes(b'valid')
        command = host.shlex.split(self.items[0]['check_command'])
        first = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=5)
        self.assertEqual(first.returncode, 0, first.stdout+first.stderr)
        marker.write_bytes(b'changed')
        second = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=5)
        self.assertNotEqual(second.returncode, 0)
        row = host.get(host.folder(self.project)[1], self.items[0]['ticket'])[1]
        job = host.crew.load(host.crew.Wave(self.project, row['wave']).path)['jobs'][row['task']]
        self.assertIsNone(job['first_valid'])
        self.assertIsNone(job['adopted'])
        spans = [s for s in host.trace.records(self.project) if s['label']=='host-worker-check']
        self.assertEqual({s['result'] for s in spans}, {0, 1})
        self.assertEqual({s['kind'] for s in spans}, {'measurement'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
