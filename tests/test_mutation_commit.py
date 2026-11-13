"""Real controller faults for initialization, approval stamping and seat binding."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CTL = ROOT / 'scripts/goal_ctl.sh'
STORE = ROOT / 'scripts/goal_store.py'
SCOPES = {'init': ('state.rec', 'loop-log.md', 'verdicts.rec', 'work-plan.md'),
          'stamp': ('state.rec', 'goal.md', 'check_freeze', 'pre-reg.md'),
          'bind': ('verdicts.rec',)}


class MutationCommit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='goal-mutation-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def call(self, project, args, *, input='', env=None, expected=None):
        result = subprocess.run(['bash', str(CTL), *args, '--project', str(project)],
                                input=input, env=env, capture_output=True, text=True, timeout=20)
        if expected is not None:
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def prepare(self, name, kind):
        project = self.root / name
        project.mkdir()
        if kind != 'init':
            self.call(project, ['init'], expected=0)
        if kind == 'stamp':
            (project / '.goal/goal.md').write_text(
                '# Goal\n\n## Acceptance criteria\n\n'
                '- AC-1 | pass | check: `true` | expected: exit=0\n\n'
                '## Budget\n\nmax_iterations=7\n\n'
                '## Approval\n\napproved: PENDING\n')
        args = [kind, '--operation-id', kind + '-stable']
        if kind == 'stamp':
            args += ['--auto', '--time-budget=120']
        stdin = 'AC-1|PASS|1|digest|cmd|first\nAC-2|FAIL|1|digest|cmd|second\n' if kind == 'bind' else ''
        return project, args, stdin

    def owned(self, project, kind):
        state = project / '.goal'
        return {name: (state / name).read_bytes() if (state / name).exists() else None for name in SCOPES[kind]}

    def all_files(self, project):
        state = project / '.goal'
        return {str(p.relative_to(state)): p.read_bytes() for p in state.rglob('*') if p.is_file()}

    def fault_env(self, project, point):
        bindir = project / 'fault-bin'
        bindir.mkdir()
        shim = bindir / 'python3'
        shim.write_text('#!' + sys.executable + '\n' + '''
import importlib.util, os, signal, sys
sys.dont_write_bytecode = True
args = sys.argv[1:]
match = len(args) >= 3 and args[0] == '-I' and args[1] == os.environ['TEST_STORE']
finish = match and ((args[2] == 'mutation-journal' and len(args) >= 5 and args[4] == 'finish') or args[2] == 'bind-mutation')
if finish:
    spec = importlib.util.spec_from_file_location('mutation_fault_store', args[1])
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    point = os.environ['TEST_MUTATION_POINT']
    def die():
        os.kill(int(os.environ['GOAL_ACCESS_OWNER_PID']), signal.SIGKILL)
        os._exit(73)
    original = mod.Store.commit
    def fault(where):
        if where == point: die()
    def commit(self, *a, **kw):
        kw['fault'] = fault
        return original(self, *a, **kw)
    mod.Store.commit = commit
    if args[2] == 'bind-mutation':
        mod.bind_mutation(args[3], args[4:], sys.stdin.buffer.read())
    else:
        mod.mutation_journal(args[3], 'finish')
    die()
os.execv(sys.executable, [sys.executable] + args)
''')
        shim.chmod(0o755)
        return dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ['PATH'],
                    TEST_STORE=str(STORE), TEST_MUTATION_POINT=point)

    def test_all_writers_recover_at_each_side_of_pointer_and_lost_ack(self):
        for kind in SCOPES:
            for point in ('generation-published', 'pointer-published', 'ack'):
                with self.subTest(kind=kind, point=point):
                    project, args, stdin = self.prepare(kind + '-' + point, kind)
                    before = self.owned(project, kind)
                    killed = self.call(project, args, input=stdin, env=self.fault_env(project, point))
                    self.assertNotEqual(killed.returncode, 0)
                    pending = project / '.goal/store/pending'
                    if point != 'ack':
                        self.assertTrue(pending.is_file())
                        self.call(project, ['status'], expected=4)
                    else:
                        self.assertFalse(pending.exists())
                    self.call(project, ['recover'], expected=0)
                    if point == 'generation-published':
                        self.assertEqual(before, self.owned(project, kind))
                        self.call(project, args, input=stdin, expected=0)
                    else:
                        self.assertNotEqual(before, self.owned(project, kind))
                    stable = self.all_files(project)
                    replay = self.call(project, args, input=stdin, expected=0)
                    self.assertIn('CTL: REPLAY', replay.stdout)
                    self.assertEqual(stable, self.all_files(project))
                    self.call(project, ['recover'], expected=0)
                    self.assertEqual(stable, self.all_files(project))

    def test_bind_batch_is_all_or_nothing_and_input_is_part_of_identity(self):
        project, args, stdin = self.prepare('batch', 'bind')
        before = self.all_files(project)
        failed = self.call(project, args, input=stdin + 'invalid|row\n', expected=4)
        self.assertIn('no rows appended', failed.stderr)
        self.assertEqual(before, self.all_files(project))
        self.call(project, args, input=stdin, expected=0)
        committed = self.all_files(project)
        self.call(project, args, input=stdin, expected=0)
        self.assertEqual(committed, self.all_files(project))
        self.call(project, args, input=stdin.replace('first', 'changed'), expected=4)
        self.assertEqual(committed, self.all_files(project))

    def test_stamp_missing_approval_placeholder_is_preflight_only(self):
        project, args, _ = self.prepare('placeholder', 'stamp')
        goal = project / '.goal/goal.md'
        goal.write_text(goal.read_text().replace('approved: PENDING\n', ''))
        before = self.all_files(project)
        self.call(project, args, expected=4)
        self.assertEqual(before, self.all_files(project))


if __name__ == '__main__':
    unittest.main()
