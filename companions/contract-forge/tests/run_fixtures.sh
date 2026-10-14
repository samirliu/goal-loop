#!/usr/bin/env bash
# tests/run_fixtures.sh - smoke lint_contract.sh against fixtures.
set -u
export LC_ALL=C.UTF-8
here=$(cd "$(dirname "$0")" && pwd)
LINT="$here/../scripts/lint_contract.sh"
FIX="$here/fixtures"
pass=0 fail=0

run(){
  local name="$1" expect_rc="$2" pattern="${3:-}"
  local out rc
  out=$(bash "$LINT" "$FIX/$name.md" 2>&1); rc=$?
  if [ "$rc" -ne "$expect_rc" ]; then
    echo "FAIL $name rc=$rc want=$expect_rc"
    echo "$out" | sed 's/^/  /'
    fail=$((fail+1)); return
  fi
  if [ -n "$pattern" ] && ! printf '%s' "$out" | grep -q "$pattern"; then
    echo "FAIL $name missing pattern /$pattern/"
    echo "$out" | sed 's/^/  /'
    fail=$((fail+1)); return
  fi
  echo "ok   $name"
  pass=$((pass+1))
}

# usage
if bash "$LINT" >/dev/null 2>&1; then
  echo "FAIL usage should exit 2"; fail=$((fail+1))
else
  rc=$?
  # re-run to capture
  bash "$LINT" >/dev/null 2>&1 || rc=$?
  if bash "$LINT" >/dev/null 2>&1; then rc=0; else rc=$?; fi
  if [ "$rc" -eq 2 ]; then echo "ok   usage rc=2"; pass=$((pass+1)); else echo "FAIL usage rc=$rc"; fail=$((fail+1)); fi
fi

run good-threshold 0
run good-objective-forge 0
run good-pipe-in-backtick 0
run bad-no-horizon 1 horizon
run bad-pipe-spec 1 spec-pipe
run bad-calib-on-metric 1 calib-judged-only
run bad-window-no-external 1 window-external
run bad-objective-target 1 objective-target

# CRLF fixture
crlf="$FIX/_crlf-threshold.md"
tr -d '\r' < "$FIX/good-threshold.md" | sed 's/$/\r/' > "$crlf"
out=$(bash "$LINT" "$crlf" 2>&1); rc=$?
if [ "$rc" -eq 0 ]; then echo "ok   crlf-threshold"; pass=$((pass+1)); else
  echo "FAIL crlf-threshold rc=$rc"; echo "$out" | sed 's/^/  /'; fail=$((fail+1))
fi
rm -f "$crlf"

echo "== fixtures: pass=$pass fail=$fail =="
[ "$fail" -eq 0 ] || exit 1
exit 0
