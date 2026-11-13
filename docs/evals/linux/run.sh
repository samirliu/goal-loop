#!/usr/bin/env bash
# Run in a disposable python:3.12-slim container with /repo read-only and /out writable.
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update > /out/dependencies.txt 2>&1
apt-get install -y --no-install-recommends bash gawk git shellcheck >> /out/dependencies.txt 2>&1
{
  uname -a
  python3 --version
  git --version
  gawk --version
  shellcheck --version
} > /out/environment.txt
cd /repo
python3 -B -m unittest discover -s tests -p 'test_*.py' -v > /out/python.txt 2>&1 &
python_pid=$!
bash tests/run_tests.sh > /out/shell.txt 2>&1 &
shell_pid=$!
python_rc=0
shell_rc=0
wait "$python_pid" || python_rc=$?
wait "$shell_pid" || shell_rc=$?
printf 'python=%s\nshell=%s\n' "$python_rc" "$shell_rc" | tee /out/result.txt
test "$python_rc" -eq 0 && test "$shell_rc" -eq 0
