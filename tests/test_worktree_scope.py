"""Content identity stays in scope and binds checked-out Gitlink contents."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

GATE = Path(__file__).resolve().parents[1] / 'scripts/goal_gate.sh'
CTL = GATE.with_name('goal_ctl.sh')


class WorktreeScope(unittest.TestCase):
    def git(self, project, *args):
        result = subprocess.run(['git', '-C', str(project), *args], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def commit(self, project, message='fixture'):
        self.git(project, '-c', 'user.name=test', '-c', 'user.email=test@example.invalid',
                 'commit', '--allow-empty', '-qm', message)

    def gitlink(self, parent, name='component'):
        child = parent / name
        child.mkdir()
        self.git(child, 'init', '-q')
        (child / 'artifact.txt').write_text('A\n')
        self.git(child, 'add', 'artifact.txt')
        self.commit(child)
        self.git(parent, 'add', '--', name)
        self.assertTrue(self.git(parent, 'ls-files', '--stage', '--', name).startswith('160000 '))
        return child

    def gitlink_project(self, name='component'):
        tmp = tempfile.TemporaryDirectory(prefix='goal-gitlink-')
        self.addCleanup(tmp.cleanup)
        parent = Path(tmp.name) / 'parent'; parent.mkdir()
        self.git(parent, 'init', '-q')
        return parent, self.gitlink(parent, name)

    def entry(self, script, project, *args, expected=0, env=None, input=None):
        result = subprocess.run(['bash', str(script), *args, '--project', str(project)],
                                env=env, input=input, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def digest(self, project, env=None):
        result = subprocess.run(['bash', str(GATE), '--digest', '--project', str(project)],
                                env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'^v2-[0-9a-f]{64}\n$')
        self.assertNotIn('unbound variable', result.stderr)
        return result.stdout

    def test_dirty_parent_files_do_not_bind_subproject(self):
        with tempfile.TemporaryDirectory(prefix='goal-subproject-') as tmp:
            root = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(root)], check=True, capture_output=True)
            child = root / 'component'; child.mkdir()
            (root / 'parent.txt').write_text('outside\n')
            artifact = child / 'artifact.txt'; artifact.write_text('inside\n')
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True, capture_output=True)
            before = self.digest(child)
            (root / 'parent.txt').write_text('outside changed\n')
            self.assertEqual(before, self.digest(child))
            artifact.write_text('inside changed\n')
            self.assertNotEqual(before, self.digest(child))

    def test_linked_worktree_uses_the_selected_worktree_bytes(self):
        with tempfile.TemporaryDirectory(prefix='goal-linked-tree-') as tmp:
            root, linked = Path(tmp) / 'root', Path(tmp) / 'linked'
            root.mkdir()
            subprocess.run(['git', 'init', '-q', str(root)], check=True, capture_output=True)
            (root / 'artifact.txt').write_text('original\n')
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=test', '-c', 'user.email=test@example.invalid',
                            'commit', '-qm', 'fixture'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'worktree', 'add', '-q', '-b', 'fixture-linked', str(linked)],
                           check=True, capture_output=True)
            self.assertTrue((linked / '.git').is_file())
            original, selected = self.digest(root), self.digest(linked)
            self.assertEqual(original, selected)
            (linked / 'artifact.txt').write_text('linked changed\n')
            self.assertNotEqual(selected, self.digest(linked))
            self.assertEqual(original, self.digest(root))

    def test_cleanup_handles_shell_special_temporary_directory_path(self):
        with tempfile.TemporaryDirectory(prefix='goal-temp-') as tmp:
            root = Path(tmp)
            project = root / 'project'; project.mkdir()
            (project / 'artifact.txt').write_text('artifact\n')
            scratch = root / "temporary ' quoted $() space"
            scratch.mkdir()
            (scratch / 'keep.txt').write_text('caller-owned\n')
            self.digest(project, env=dict(os.environ, TMPDIR=str(scratch)))
            self.assertEqual((scratch / 'keep.txt').read_text(), 'caller-owned\n')
            # macOS git/xcrun may also create its own cache in TMPDIR. Only
            # assert cleanup of the private prefixes this implementation owns.
            self.assertFalse(any(path.name.startswith(('goal-tree.', 'goal-watch.')) for path in scratch.iterdir()))

    def test_gitlink_tracked_untracked_and_deleted_bytes_are_bound(self):
        parent, child = self.gitlink_project('component with\nnewline')
        before = self.digest(parent)
        (child / 'artifact.txt').write_text('B\n')
        changed = self.digest(parent)
        self.assertNotEqual(before, changed)
        untracked = child / 'untracked \nfile'
        untracked.write_text('first\n')
        added = self.digest(parent)
        self.assertNotEqual(changed, added)
        untracked.write_text('second\n')
        edited = self.digest(parent)
        self.assertNotEqual(added, edited)
        (child / 'artifact.txt').unlink()
        self.assertNotEqual(edited, self.digest(parent))

    def test_gitlink_binds_checked_out_commit_and_parent_index_object(self):
        parent, child = self.gitlink_project()
        before = self.digest(parent)
        self.commit(child, 'new checked-out commit with the same files')
        committed = self.digest(parent)
        self.assertNotEqual(before, committed)
        self.git(parent, 'add', 'component')
        self.assertNotEqual(committed, self.digest(parent))

    def test_nested_gitlinks_bind_content_and_commit_with_awkward_names(self):
        parent, child = self.gitlink_project()
        nested = self.gitlink(child, 'nested repo\nname')
        before = self.digest(parent)
        (nested / 'artifact.txt').write_text('nested change\n')
        changed = self.digest(parent)
        self.assertNotEqual(before, changed)
        self.commit(nested, 'new nested commit')
        self.assertNotEqual(changed, self.digest(parent))

    def test_gitlink_nesting_limit_fails_closed(self):
        parent, child = self.gitlink_project()
        for _ in range(31):
            child = self.gitlink(child)
        self.digest(parent)  # 32 populated levels are supported.
        self.gitlink(child)
        result = self.entry(GATE, parent, '--digest', expected=4)
        self.assertEqual(result.stdout, '')
        self.assertIn('gitlink nesting exceeds supported depth (32)', result.stderr)

    def test_initialized_submodule_gitfile_binds_child_bytes(self):
        parent, child = self.gitlink_project()
        self.git(parent, 'config', '-f', '.gitmodules', 'submodule.component.path', 'component')
        self.git(parent, 'config', '-f', '.gitmodules', 'submodule.component.url', './component')
        self.git(parent, 'submodule', 'absorbgitdirs', 'component')
        self.assertTrue((child / '.git').is_file())
        before = self.digest(parent)
        (child / 'artifact.txt').write_text('changed in initialized submodule\n')
        self.assertNotEqual(before, self.digest(parent))

    def test_untracked_nested_repository_is_not_an_empty_directory(self):
        parent, child = self.gitlink_project()
        self.git(parent, 'rm', '-f', '--cached', '--', 'component')
        before = self.digest(parent)
        (child / 'artifact.txt').write_text('changed nested repository\n')
        self.assertNotEqual(before, self.digest(parent))

    def test_gitlink_ignored_files_require_explicit_watch(self):
        parent, child = self.gitlink_project()
        (child / '.gitignore').write_text('ignored/\n')
        self.git(child, 'add', '.gitignore')
        ignored = child / 'ignored'; ignored.mkdir()
        output = ignored / 'out file'; output.write_text('first\n')
        before = self.digest(parent)
        output.write_text('second\n')
        self.assertEqual(before, self.digest(parent))
        state = parent / '.goal'; state.mkdir()
        (state / 'goal.md').write_text(
            '## Acceptance criteria\n\n'
            '- AC-1 | output | check: `true` | watch: `component/ignored` | expected: exit=0\n')
        watched = self.digest(parent)
        output.write_text('third\n')
        changed = self.digest(parent)
        self.assertNotEqual(watched, changed)
        (ignored / 'new empty directory').mkdir()
        self.assertNotEqual(changed, self.digest(parent))

    def test_gitlink_tracked_symlink_hashes_target_without_following_it(self):
        parent, child = self.gitlink_project()
        outside = parent.parent / 'outside.txt'; outside.write_text('outside\n')
        link = child / 'link'; link.symlink_to(outside)
        self.git(child, 'add', 'link')
        before = self.digest(parent)
        outside.write_text('outside changed\n')
        self.assertEqual(before, self.digest(parent))
        link.unlink(); link.symlink_to('another\ntarget')
        self.assertNotEqual(before, self.digest(parent))

    def test_gitlink_tracked_path_cannot_follow_symlink_parent(self):
        parent, child = self.gitlink_project()
        directory = child / 'directory'; directory.mkdir()
        (directory / 'file').write_text('inside\n')
        self.git(child, 'add', 'directory/file')
        (directory / 'file').unlink(); directory.rmdir()
        outside = parent.parent / 'outside'; outside.mkdir()
        (outside / 'file').write_text('outside\n')
        directory.symlink_to(outside, target_is_directory=True)
        result = self.entry(GATE, parent, '--digest', expected=4)
        self.assertEqual(result.stdout, '')
        self.assertIn('symlink parent', result.stderr)

    def test_unmaterialized_replaced_or_cyclic_gitlink_fails_closed(self):
        for state in ('missing', 'empty', 'file', 'cycle', 'metadata-symlink', 'parent-metadata'):
            with self.subTest(state=state):
                parent, child = self.gitlink_project()
                if state in ('metadata-symlink', 'parent-metadata'):
                    shutil.rmtree(child / '.git')
                    if state == 'metadata-symlink':
                        (child / '.git').symlink_to(parent / '.git', target_is_directory=True)
                    else:
                        (child / '.git').write_text('gitdir: ../.git\n')
                else:
                    shutil.rmtree(child)
                    if state == 'empty':
                        child.mkdir()
                    elif state == 'file':
                        child.write_text('replaced checkout\n')
                    elif state == 'cycle':
                        child.symlink_to(parent, target_is_directory=True)
                result = self.entry(GATE, parent, '--digest', expected=4)
                self.assertEqual(result.stdout, '')
                self.assertIn('gitlink', result.stderr)

    @unittest.skipIf(os.geteuid() == 0, 'root can read chmod-000 files')
    def test_unreadable_gitlink_content_fails_closed(self):
        parent, child = self.gitlink_project()
        artifact = child / 'artifact.txt'; artifact.chmod(0)
        try:
            result = self.entry(GATE, parent, '--digest', expected=4)
            self.assertEqual(result.stdout, '')
            self.assertIn('Permission denied', result.stderr)
        finally:
            artifact.chmod(0o644)

    @unittest.skipIf(os.geteuid() == 0, 'root can read chmod-000 directories')
    def test_unreadable_untracked_gitlink_directory_fails_closed(self):
        parent, child = self.gitlink_project()
        directory = child / 'untracked'; directory.mkdir()
        (directory / 'artifact.txt').write_text('untracked content\n')
        directory.chmod(0)
        try:
            result = self.entry(GATE, parent, '--digest', expected=4)
            self.assertEqual(result.stdout, '')
            self.assertIn('gitlink discovery failed', result.stderr)
            self.assertIn('Permission denied', result.stderr)
        finally:
            directory.chmod(0o755)

    @unittest.skipIf(os.geteuid() == 0, 'root can read chmod-000 directories')
    def test_unreadable_top_level_directory_cannot_preserve_a_go(self):
        temporary = tempfile.TemporaryDirectory(prefix='goal-unreadable-inventory-')
        self.addCleanup(temporary.cleanup)
        parent = Path(temporary.name)
        self.git(parent, 'init', '-q')
        directory = parent/'untracked'; directory.mkdir()
        artifact = directory/'artifact.txt'; artifact.write_text('A\n')
        self.entry(CTL, parent, 'init')
        (parent/'.goal/goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | reviewed | check: `true` | expected: judged\n\n'
            '## Approval\n\napproved: PENDING\n')
        subject = parent/'judged.txt'; subject.write_text('review subject\n')
        self.entry(CTL, parent, 'stamp', '--auto')
        self.entry(CTL, parent, 'close-iteration', '--task', 'T1', '--files', 'untracked/artifact.txt',
                   '--checks-pass', '1', '--checks-fail', '0', '--checks-unverifiable', '0',
                   '--exit-signal', 'yes', '--adversarial', 'clear', '--adversarial-note', 'reviewed', '--no-gate')
        self.entry(CTL, parent, 'bind', input='AC-1|PASS|1|%s|cmd|artifact: judged.txt digest: %s\n' %
                   (self.digest(parent).strip(), hashlib.sha256(subject.read_bytes()).hexdigest()))
        self.assertIn('GATE: GO', self.entry(GATE, parent, '--check').stdout)
        # Hide a changed, in-scope file behind a directory Git only warns
        # about. Neither the prior verdict nor a partial digest is usable.
        artifact.write_text('B\n')
        directory.chmod(0)
        try:
            for action in ('--digest', '--check'):
                result = self.entry(GATE, parent, action, expected=4)
                self.assertNotIn('GATE: GO', result.stdout)
                self.assertIn('incomplete-git-inventory', result.stderr)
            tools = parent/'bin'; tools.mkdir()
            python = tools/'python3'; python.write_text('#!/bin/sh\nexit 1\n'); python.chmod(0o755)
            env = dict(os.environ, PATH=str(tools)+os.pathsep+os.environ['PATH'])
            result = self.entry(GATE, parent, '--digest', expected=4, env=env)
            self.assertEqual(result.stdout, '')
            self.assertIn('incomplete-git-inventory', result.stderr)
        finally:
            directory.chmod(0o755)

    def test_shell_fallback_refuses_gitlink_instead_of_partial_digest(self):
        parent, child = self.gitlink_project()
        tools = parent.parent / 'bin'; tools.mkdir()
        python = tools / 'python3'; python.write_text('#!/bin/sh\nexit 1\n'); python.chmod(0o755)
        env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'])
        result = self.entry(GATE, parent, '--digest', expected=4, env=env)
        self.assertEqual(result.stdout, '')
        self.assertIn('gitlink-requires-python', result.stderr)
        self.git(parent, 'rm', '-f', '--cached', '--', child.name)
        result = self.entry(GATE, parent, '--digest', expected=4, env=env)
        self.assertEqual(result.stdout, '')
        self.assertIn('gitlink-requires-python', result.stderr)

    def test_gate_verify_rejects_check_mutating_gitlink_content(self):
        parent, child = self.gitlink_project()
        self.entry(CTL, parent, 'init')
        (parent / '.goal/goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | no mutation | check: `printf "B\\n" > component/artifact.txt` | expected: exit=0\n\n'
            '## Approval\n\napproved: PENDING\n')
        self.entry(CTL, parent, 'stamp', '--auto')
        (child / 'artifact.txt').write_text('A\n')
        result = self.entry(GATE, parent, '--verify', expected=2)
        self.assertIn('check-mutated-tree', result.stdout + result.stderr)

    def test_gitlink_edit_invalidates_prior_judged_evidence(self):
        parent, child = self.gitlink_project()
        self.entry(CTL, parent, 'init')
        (parent / '.goal/goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | reviewed | check: `true` | expected: judged\n\n'
            '## Approval\n\napproved: PENDING\n')
        subject = parent / 'judged.txt'; subject.write_text('review subject\n')
        self.entry(CTL, parent, 'stamp', '--auto')
        self.entry(CTL, parent, 'close-iteration', '--task', 'T1', '--files', 'component/artifact.txt',
                   '--checks-pass', '1', '--checks-fail', '0', '--checks-unverifiable', '0',
                   '--progress', 'yes', '--exit-signal', 'yes', '--adversarial', 'clear',
                   '--adversarial-note', 'reviewed', '--no-gate')
        digest = self.digest(parent).strip()
        evidence = hashlib.sha256(subject.read_bytes()).hexdigest()
        self.entry(CTL, parent, 'bind', input='AC-1|PASS|1|%s|cmd|artifact: judged.txt digest: %s\n' %
                   (digest, evidence))
        self.assertIn('GATE: GO', self.entry(GATE, parent, '--check').stdout)
        (child / 'artifact.txt').write_text('B\n')
        result = self.entry(GATE, parent, '--check', expected=2)
        self.assertIn('verdicts-stale', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
