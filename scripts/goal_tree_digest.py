#!/usr/bin/env python3
"""POSIX implementation of the v2 worktree record hash.

The shell owns initial discovery, explicit-scope validation and selection.
This helper expands initialized Gitlinks through Git's own file inventory,
without hashing metadata or following worktree symlinks. Ordinary entries use
the shell fallback's record format; Gitlinks require this implementation.
"""
import hashlib
import os
import stat
import subprocess
import sys


def nul_items(data):
    if data and not data.endswith(b'\0'):
        raise ValueError('truncated NUL manifest')
    return data[:-1].split(b'\0') if data else []


def items(path):
    with open(path, 'rb') as stream:
        return nul_items(stream.read())


def normalized(path):
    path = (path[2:] if path.startswith(b'./') else path).rstrip(b'/')
    if path.startswith(b'/') or any(p in (b'', b'.', b'..') for p in path.split(b'/')):
        raise ValueError('unsafe worktree path')
    return path


def gitlinks(index):
    links = {}
    for entry in index:
        header, separator, path = entry.partition(b'\t')
        fields = header.split(b' ')
        if not separator or len(fields) != 3:
            raise ValueError('malformed Git index manifest')
        if fields[0] == b'160000':
            if fields[2] != b'0' or path in links:
                raise ValueError('unmerged gitlink')
            if len(fields[1]) not in (40, 64) or any(c not in b'0123456789abcdef' for c in fields[1]):
                raise ValueError('invalid gitlink object')
            links[normalized(path)] = fields[1]
    return links


def git(root, *args):
    # A caller's Git overrides must not redirect child discovery into another
    # index/worktree. Git itself resolves standard submodule/worktree gitfiles;
    # we neither read nor walk .git internals.
    env = {k: v for k, v in os.environ.items() if k not in (
        'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
        'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_PREFIX')}
    result = subprocess.run([b'git', b'--no-optional-locks', b'-c', b'core.fsmonitor=false',
                             b'-C', root, *(os.fsencode(a) for a in args)],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # ls-files can return success after warning that an unreadable untracked
    # directory was skipped. Such an inventory cannot bind the full subtree.
    if result.returncode or result.stderr:
        raise ValueError('gitlink discovery failed: %r: %s' %
                         (root, result.stderr.decode('utf-8', 'backslashreplace').strip()))
    return result.stdout


def gitlink_fingerprint(root, info, ancestors):
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('gitlink is not a checked-out directory: %r' % root)
    if len(ancestors) > 32:
        raise ValueError('gitlink nesting exceeds supported depth (32)')
    try:
        metadata = os.lstat(root + b'/.git')
    except FileNotFoundError:
        raise ValueError('gitlink is not initialized: %r' % root) from None
    if not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
        raise ValueError('unsupported gitlink metadata (symlink or special file): %r' % root)
    if git(root, 'rev-parse', '--is-inside-work-tree', '--show-prefix') != b'true\n\n':
        raise ValueError('gitlink does not select its own worktree: %r' % root)
    head = git(root, 'rev-parse', '--verify', 'HEAD^{commit}')
    paths = git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z')
    deleted = git(root, 'ls-files', '--deleted', '-z')
    index = git(root, 'ls-files', '--stage', '-z')
    digest = fingerprint(nul_items(paths), [], nul_items(deleted), nul_items(index), root, ancestors)
    # A checkout/commit during discovery must not pair an old HEAD with new
    # bytes. Metadata is only queried through Git, never included as content.
    if head != git(root, 'rev-parse', '--verify', 'HEAD^{commit}'):
        raise ValueError('gitlink HEAD changed while hashing: %r' % root)
    after = os.lstat(root)
    if (info.st_dev, info.st_ino, info.st_mode) != (after.st_dev, after.st_ino, after.st_mode):
        raise ValueError('gitlink directory changed while hashing: %r' % root)
    return head.rstrip(b'\n'), digest.encode('ascii')


def fingerprint(paths, watched_missing, deleted, index=(), root=b'.', ancestors=()):
    if hashlib.sha256(b'').hexdigest() != 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855':
        raise ValueError('SHA-256 self-test failed')
    if hashlib.sha256(b'abc').hexdigest() != 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad':
        raise ValueError('SHA-256 self-test failed')
    identity = os.lstat(root)
    identity = (identity.st_dev, identity.st_ino)
    if identity in ancestors:
        raise ValueError('cyclic gitlink worktree')
    ancestors = (*ancestors, identity)
    links = gitlinks(index)
    paths = sorted({normalized(p) for p in paths})
    if links.keys() - set(paths):
        raise ValueError('gitlink missing from worktree manifest')
    allowed_missing = {normalized(p) for p in (*watched_missing, *deleted)}
    result = hashlib.sha256()
    for path in paths:
        if path in (b'.goal', b'.git') or path.startswith((b'.goal/', b'.git/')):
            continue
        file = root + b'/' + path
        parent = root
        for component in path.split(b'/')[:-1]:
            parent += b'/' + component
            try:
                parent_info = os.lstat(parent)
            except (FileNotFoundError, NotADirectoryError):
                break
            if stat.S_ISLNK(parent_info.st_mode):
                raise ValueError('symlink parent')
        try:
            info = os.lstat(file)
        except (FileNotFoundError, NotADirectoryError):
            if path in links:
                raise ValueError('gitlink is not initialized: %r' % file) from None
            if path not in allowed_missing:
                raise ValueError('worktree entry vanished')
            result.update(b'deleted\0' + path + b'\0')
            continue
        mode = format(stat.S_IMODE(info.st_mode), 'o').encode('ascii')
        if path in links or (stat.S_ISDIR(info.st_mode) and os.path.lexists(file + b'/.git')):
            head, digest = gitlink_fingerprint(file, info, ancestors)
            result.update(b'gitlink\0' + path + b'\0' + mode + b'\0' +
                          links.get(path, b'') + b'\0' + head + b'\0' + digest + b'\0')
        elif stat.S_ISLNK(info.st_mode):
            target = os.readlink(file)
            # readlink(1) appends a newline, including for newline-ending links.
            digest = hashlib.sha256(target + b'\n').hexdigest().encode('ascii')
            result.update(b'link\0' + path + b'\0' + mode + b'\0' + digest + b'\0')
        elif stat.S_ISREG(info.st_mode):
            fd = os.open(file, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_dev, opened.st_ino, opened.st_mode) != (info.st_dev, info.st_ino, info.st_mode):
                    raise ValueError('worktree entry changed while opening')
                value = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    value.update(chunk)
                after = os.fstat(stream.fileno())
                if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns):
                    raise ValueError('worktree entry changed while hashing')
            result.update(b'file\0' + path + b'\0' + mode + b'\0' + value.hexdigest().encode('ascii') + b'\0')
        elif stat.S_ISDIR(info.st_mode):
            result.update(b'dir\0' + path + b'\0' + mode + b'\0')
        else:
            raise ValueError('unsupported worktree entry')
    return 'v2-' + result.hexdigest()


if __name__ == '__main__':
    try:
        if os.name != 'posix' or not hasattr(os, 'O_NOFOLLOW'):
            raise ValueError('required POSIX capabilities unavailable')
        print(fingerprint(*(items(arg) for arg in sys.argv[1:5])))
    except (OSError, ValueError, TypeError) as exc:
        print('GATE: ERROR tree-hash-failed: ' + str(exc), file=sys.stderr)
        sys.exit(4)
