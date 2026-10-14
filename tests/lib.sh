# tests/lib.sh - shared helpers for the scenario suite. Pure functions only.
# The runner (run_tests.sh / shard scripts) must set: here, GATE, CTL, TEAM,
# T (temp project root), pass, failn — before using these.

ok(){ pass=$((pass+1)); echo "  ok   - $1"; }
no(){ failn=$((failn+1)); echo "  FAIL - $1"; }
assert_rc(){ [ "$3" = "$2" ] && ok "$1 (rc=$3)" || no "$1 (want rc=$2 got rc=$3)"; }
assert_has(){ printf '%s' "$3" | grep -qE -- "$2" && ok "$1" || no "$1"; }

# BSD/GNU portability (v2.9): `sed -i` with no extension is GNU-only (on
# macOS/BSD it swallows the expression as a backup suffix). One in-place
# substitution = transform to a sibling tmp + atomic mv.
sed_in(){ local s="$1" f="$2"; sed "$s" "$f" > "$f.tsedtmp" || { rm -f "$f.tsedtmp"; return 1; }; mv -f "$f.tsedtmp" "$f"; }

mkproj(){ p="$T/$1"; mkdir -p "$p"; bash "$CTL" init --project "$p" >/dev/null; }

contract(){ # $1 proj NAME under $T; $2.. = AC lines; optional FORGE=1 / TB=seconds / NOSTAMP=1 env
  local p="$T/$1"; shift
  forge_line=""; [ "${FORGE:-0}" = 1 ] && forge_line="exit: forge"
  {
    printf '# Goal contract - test\n\n## Objective\n\ntest objective\n\n'
    printf '## Acceptance criteria\n\n'
    for l in "$@"; do printf '%s\n' "$l"; done
    printf '\n%s\n\n## Out of scope\n\n- nothing\n\n## Approval\n\napproved: PENDING\n' "$forge_line"
  } > "$p/.goal/goal.md"
  [ "${NOSTAMP:-0}" = 1 ] || bash "$CTL" stamp --project "$p" --auto ${TB:+--time-budget=$TB} >/dev/null
}

bind_v(){ # $1 proj NAME under $T; $2 verdict-line with DIGEST placeholder
  local p="$T/$1"
  d=$(bash "$GATE" --digest --project "$p")
  printf '%s\n' "${2//DIGEST/$d}" | bash "$CTL" bind --project "$p" >/dev/null
}

close_iter(){ # $1 proj NAME under $T, rest passed to close-iteration (--no-gate implied)
  local p="$T/$1"; shift
  bash "$CTL" close-iteration --project "$p" --task T1 --files a.txt \
    --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
    --exit-signal yes "$@" --no-gate >/dev/null 2>&1
}

# --- suite-level globals (must exist in every shard) ---
AUDIT="${AUDIT:-$here/scripts/goal_audit.sh}"
LOOPT="${LOOPT:-$here/scripts/goal_loop.sh}"

# --- shared body helpers (defined in cases.inc.sh too; lib wins first) ---
stall(){ printf 'no_progress_streak=1\n' >> "$1/.goal/state.rec"; }
hblocks(){ local p="$T/$1/.goal/loop-log.md" n=1; : > "$p"
  shift
  while [ $# -ge 2 ]; do
    printf '## iteration %d\ntask=%s\nfiles_modified=a.txt\nchecks_pass=1\nchecks_fail=0\nchecks_unverifiable=0\nerror_signature=none\nprogress=yes\nexit_signal=no\nfalse_complete=no\ndigest=deadbeefcafe\nscore=none\nstrategy_delta=none\nstrategy=%s\n' "$n" "$1" "$2" >> "$p"; n=$((n+1)); shift 2 || break
  done; }
scorefile(){ local f="$T/$1/.goal/scores.rec"; : > "$f"; shift; local n=1 kv
  for kv in "$@"; do printf '%s|%s|none\n' "$n" "$kv" >> "$f"; n=$((n+1)); done; }
obj110(){ # $1 proj NAME under $T, optional $2 = tolerance token (inserted BEFORE expected)
  local p="$T/$1" tol=""
  [ -n "${2:-}" ] && tol=" $2 |"
  contract "$1" "- AC-1 | t | check: \`true\` |${tol} expected: maximize"
  printf 'objective: maximize AC-1\nhorizon-waived: toy slope fixture - blind spot immaterial\n' >> "$p/.goal/goal.md"
  bash "$CTL" stamp --project "$p" --auto >/dev/null 2>&1; }
