#!/usr/bin/env python3
"""Fast POSIX implementation of the v2 worktree record hash.

The shell owns discovery, explicit-scope validation and algorithm selection.
This helper consumes NUL-delimited manifests and must match the shell format.
It is an optional accelerator; environments without the required Python/OS
capabilities use the shell implementation instead.
"""
import hashlib
import os
import stat
import sys


def items(path):
    with open(path, 'rb') as stream:
        data = stream.read()
    if data and not data.endswith(b'\0'):
        raise ValueError('truncated NUL manifest')
    return data[:-1].split(b'\0') if data else []


def fingerprint(paths, watched_missing, deleted):
    if hashlib.sha256(b'').hexdigest() != 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855':
        raise ValueError('SHA-256 self-test failed')
    if hashlib.sha256(b'abc').hexdigest() != 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad':
        raise ValueError('SHA-256 self-test failed')
    allowed_missing = set(watched_missing) | {(p[2:] if p.startswith(b'./') else p) for p in deleted}
    result = hashlib.sha256()
    for path in paths:
        path = path[2:] if path.startswith(b'./') else path
        if path in (b'.goal', b'.git') or path.startswith((b'.goal/', b'.git/')):
            continue
        file = b'./' + path
        parent = b'.'
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
            if path not in allowed_missing:
                raise ValueError('worktree entry vanished')
            result.update(b'deleted\0' + path + b'\0')
            continue
        mode = format(stat.S_IMODE(info.st_mode), 'o').encode('ascii')
        if stat.S_ISLNK(info.st_mode):
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
        print(fingerprint(*(items(arg) for arg in sys.argv[1:4])))
    except (OSError, ValueError, TypeError) as exc:
        print('GATE: ERROR tree-hash-failed: ' + str(exc), file=sys.stderr)
        sys.exit(4)
