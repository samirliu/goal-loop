#!/usr/bin/env bash
# tests/run_tests.sh - scenario suite for goal_gate.sh / goal_ctl.sh (v1.2).
# Builds throwaway projects in a temp dir; no network, no API, no jq.
#   bash tests/run_tests.sh
# Exit 0 = all green. Every scenario asserts an exit code and, where the
# reason matters, greps the gate's stderr/stdout for the reason token.
set -u
export LC_ALL=C.UTF-8

here=$(cd "$(dirname "$0")/.." && pwd)   # skill root
GATE="$here/scripts/goal_gate.sh"
CTL="$here/scripts/goal_ctl.sh"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

pass=0; failn=0
ok(){ pass=$((pass+1)); echo "  ok   - $1"; }
no(){ failn=$((failn+1)); echo "  FAIL - $1"; }
assert_rc(){ [ "$3" = "$2" ] && ok "$1 (rc=$3)" || no "$1 (want rc=$2 got rc=$3)"; }
assert_has(){ printf '%s' "$3" | grep -qE "$2" && ok "$1" || no "$1"; }

mkproj(){ p="$T/$1"; mkdir -p "$p"; bash "$CTL" init --project "$p" >/dev/null; }

contract(){ # $1 proj NAME under $T; $2.. = AC lines; optional FORGE=1 / TB=seconds env
  local p="$T/$1"; shift
  forge_line=""; [ "${FORGE:-0}" = 1 ] && forge_line="exit: forge"
  {
    printf '# Goal contract - test\n\n## Objective\n\ntest objective\n\n'
    printf '## Acceptance criteria\n\n'
    for l in "$@"; do printf '%s\n' "$l"; done
    printf '\n%s\n\n## Out of scope\n\n- nothing\n\n## Approval\n\napproved: PENDING\n' "$forge_line"
  } > "$p/.goal/goal.md"
  bash "$CTL" stamp --project "$p" --auto ${TB:+--time-budget=$TB} >/dev/null
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

echo "== goal_gate.sh / goal_ctl.sh v1.2 scenario suite =="

# 01 help
out=$(bash "$GATE" --help 2>&1); assert_rc "01 help exits 0" 0 $?
assert_has "01 help mentions --verify" '\-\-verify' "$out"

# 02 no-goal-dir
mkdir -p "$T/empty"
bash "$GATE" --check --project "$T/empty" >/dev/null 2>&1; assert_rc "02 no-goal-dir -> rc4" 4 $?

# 03 threshold GO, deterministic only (stored verdicts NOT required)
mkproj t03; contract t03 \
  "- AC-1 | file exists | check: \`test -f a.txt\` | expected: exit=0" \
  "- AC-2 | metric | check: \`echo 7\` | expected: >=5"
echo hi > "$T/t03/a.txt"
close_iter t03
out=$(bash "$GATE" --check --project "$T/t03" 2>&1); assert_rc "03 threshold GO deterministic" 0 $?
assert_has "03 GO line says mode=threshold" 'mode=threshold' "$out"

# 04 not-claimed
mkproj t04; contract t04 "- AC-1 | f | check: \`true\` | expected: exit=0"
close_iter t04 --exit-signal no
bash "$GATE" --check --project "$T/t04" >/dev/null 2>&1; assert_rc "04 not-claimed -> rc2" 2 $?

# 05 verdicts-stale after artifact touched post-block
mkproj t05; contract t05 "- AC-1 | f | check: \`test -f a.txt\` | expected: exit=0"
echo v1 > "$T/t05/a.txt"; close_iter t05
echo v2 > "$T/t05/a.txt"
out=$(bash "$GATE" --check --project "$T/t05" 2>&1); assert_rc "05 stale -> rc2" 2 $?
assert_has "05 reason verdicts-stale" 'verdicts-stale' "$out"

# 06 judged open-FAIL
mkproj t06; contract t06 "- AC-1 | judged | check: \`true\` | expected: judged"
close_iter t06
bind_v t06 'AC-1|FAIL|1|DIGEST|cmd|some evidence'
bash "$GATE" --check --project "$T/t06" >/dev/null 2>&1; assert_rc "06 judged open-FAIL -> rc2" 2 $?

# 07 judged PASS without evidence is void
mkproj t07; contract t07 "- AC-1 | judged | check: \`true\` | expected: judged"
close_iter t07
bind_v t07 'AC-1|PASS|1|DIGEST|cmd|'
bash "$GATE" --check --project "$T/t07" >/dev/null 2>&1; assert_rc "07 evidence-missing -> rc2" 2 $?

# 08 unverifiable dumping
mkproj t08; contract t08 \
  "- AC-1 | j1 | check: \`true\` | expected: judged" \
  "- AC-2 | j2 | check: \`true\` | expected: judged" \
  "- AC-3 | j3 | check: \`true\` | expected: judged"
close_iter t08
bind_v t08 'AC-1|PASS|1|DIGEST|cmd|"ok line"'
bind_v t08 'AC-2|UNVERIFIABLE|1|DIGEST|-|PROBE=x REASON=y'
bind_v t08 'AC-3|UNVERIFIABLE|1|DIGEST|-|PROBE=x REASON=y'
bash "$GATE" --check --project "$T/t08" >/dev/null 2>&1; assert_rc "08 unverifiable-excessive -> rc2" 2 $?

# 09 contract tamper after stamp
mkproj t09; contract t09 "- AC-1 | f | check: \`true\` | expected: exit=0"
sed -i 's/^approved:/&\n- AC-2 | smuggled | check: `true` | expected: exit=0/' "$T/t09/.goal/goal.md" 2>/dev/null
printf -- '- AC-2 | smuggled | check: `true` | expected: exit=0\n' >> "$T/t09/.goal/goal.md"
close_iter t09
bash "$GATE" --check --project "$T/t09" >/dev/null 2>&1; assert_rc "09 contract-tampered -> rc2" 2 $?

# 10 metric gate-rerun FAIL
mkproj t10; contract t10 "- AC-1 | m | check: \`echo 3\` | expected: >=5"
close_iter t10
out=$(bash "$GATE" --check --project "$T/t10" 2>&1); assert_rc "10 metric FAIL -> rc2" 2 $?
assert_has "10 reason open-FAIL w/ gate rerun" 'open-FAIL:AC-1 \(gate rerun' "$out"

# 11a command not executable -> check-broken
mkproj t11a; contract t11a "- AC-1 | f | check: \`definitely_missing_cmd_xyz\` | expected: exit=0"
close_iter t11a
out=$(bash "$GATE" --check --project "$T/t11a" 2>&1); assert_rc "11a check-broken rc127 -> rc2" 2 $?
assert_has "11a reason check-broken" 'check-broken:AC-1' "$out"

# 11b metric last line not numeric -> check-broken
mkproj t11b; contract t11b "- AC-1 | m | check: \`echo abc\` | expected: >=5"
close_iter t11b
out=$(bash "$GATE" --check --project "$T/t11b" 2>&1); assert_rc "11b non-numeric metric -> rc2" 2 $?
assert_has "11b reason check-broken" 'check-broken:AC-1' "$out"

# 12 mutating check caught by digest guard
mkproj t12; contract t12 "- AC-1 | mutates | check: \`echo mut >> a.txt\` | expected: exit=0"
echo base > "$T/t12/a.txt"; close_iter t12
out=$(bash "$GATE" --verify --project "$T/t12" 2>&1); assert_rc "12 --verify mutated-tree -> rc2" 2 $?
assert_has "12 reason check-mutated-tree" 'check-mutated-tree' "$out"

# 13 forge not-dry (floors pass, exhaustion not reached)
FORGE=1 mkproj t13; FORGE=1 contract t13 "- AC-1 | f | check: \`test -f a.txt\` | expected: exit=0"
echo x > "$T/t13/a.txt"; close_iter t13 --dry yes
out=$(bash "$GATE" --check --project "$T/t13" 2>&1); assert_rc "13 forge not-dry -> rc2" 2 $?
assert_has "13 reason not-dry" 'not-dry' "$out"

# 14 forge GO at dry_streak >= limit
sed -i 's/^dry_streak=.*/dry_streak=3/' "$T/t13/.goal/state.rec"
out=$(bash "$GATE" --check --project "$T/t13" 2>&1); assert_rc "14 forge GO -> rc0" 0 $?
assert_has "14 GO line says mode=forge" 'mode=forge' "$out"

# 15 forge budget is a fuse -> rc3
mkproj t15; FORGE=1 contract t15 "- AC-1 | f | check: \`true\` | expected: exit=0"
close_iter t15 --dry yes
sed -i 's/^iteration=.*/iteration=13/' "$T/t15/.goal/state.rec"
out=$(bash "$GATE" --check --project "$T/t15" 2>&1); assert_rc "15 budget-fuse -> rc3" 3 $?
assert_has "15 reason budget-fuse" 'budget-fuse' "$out"

# 16 v1.1 prose expectation routes to judged (backward compat)
mkproj t16; contract t16 "- AC-1 | v11 | check: \`test -f a.txt\` | expected: the diff is empty"
echo x > "$T/t16/a.txt"; close_iter t16
bind_v t16 'AC-1|PASS|1|DIGEST|cmd|"the diff is empty"'
bash "$GATE" --check --project "$T/t16" >/dev/null 2>&1; assert_rc "16 prose->judged GO -> rc0" 0 $?

# 17a forge close without --dry refused, and WITHOUT leaving an orphan block
mkproj t17a; FORGE=1 contract t17a "- AC-1 | f | check: \`true\` | expected: exit=0"
bash "$CTL" close-iteration --project "$T/t17a" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --no-gate >/dev/null 2>&1
assert_rc "17a forge close w/o --dry -> rc4" 4 $?
[ ! -s "$T/t17a/.goal/loop-log.md" ] && ok "17a refusal leaves no orphan loop-log block" || no "17a orphan loop-log block after refusal"

# 17b dry=yes with open FAIL refused, also no orphan block
mkproj t17b; FORGE=1 contract t17b "- AC-1 | f | check: \`true\` | expected: exit=0"
bash "$CTL" close-iteration --project "$T/t17b" --task T1 --files a.txt \
  --checks-pass 0 --checks-fail 1 --checks-unverifiable 0 --dry yes --no-gate >/dev/null 2>&1
assert_rc "17b --dry yes + fail -> rc4" 4 $?
[ ! -s "$T/t17b/.goal/loop-log.md" ] && ok "17b refusal leaves no orphan loop-log block" || no "17b orphan loop-log block after refusal"

# 18 forge state without dry keys -> state error
mkproj t18; FORGE=1 contract t18 "- AC-1 | f | check: \`true\` | expected: exit=0"
close_iter t18 --dry yes
grep -v '^dry_streak=' "$T/t18/.goal/state.rec" > "$T/t18/.goal/state.rec.new" && mv "$T/t18/.goal/state.rec.new" "$T/t18/.goal/state.rec"
bash "$GATE" --check --project "$T/t18" >/dev/null 2>&1; assert_rc "18 missing dry_streak -> rc4" 4 $?

# 19 dry_streak accumulates across dry rounds
mkproj t19; FORGE=1 contract t19 "- AC-1 | f | check: \`true\` | expected: exit=0"
close_iter t19 --dry yes; close_iter t19 --dry yes
s=$(grep '^dry_streak=' "$T/t19/.goal/state.rec" | cut -d= -f2)
[ "$s" = 2 ] && ok "19 dry_streak=2 after two dry rounds" || no "19 dry_streak got=$s"

# 20 --verify all-pass and judged skip
mkproj t20; contract t20 \
  "- AC-1 | f | check: \`test -f a.txt\` | expected: exit=0" \
  "- AC-2 | j | check: \`true\` | expected: judged"
echo x > "$T/t20/a.txt"
out=$(bash "$GATE" --verify --project "$T/t20" 2>&1); assert_rc "20 --verify OK -> rc0" 0 $?
assert_has "20 --verify skips judged" 'AC-2\|SKIP\|judged' "$out"
assert_has "20 --verify reruns deterministic" 'AC-1\|PASS' "$out"

# 21 --verify single-id filter
out=$(bash "$GATE" --verify --project "$T/t20" AC-1 2>&1); assert_rc "21 --verify AC-1 only -> rc0" 0 $?
if printf '%s' "$out" | grep -q 'AC-2'; then no "21 filtered run mentioned AC-2"; else ok "21 filtered run omitted AC-2"; fi

# 22 ctl init seeds the v1.2 keys
mkproj t22
for k in dry_streak dry_limit check_timeout; do
  grep -q "^$k=" "$T/t22/.goal/state.rec" && ok "22 state seeds $k" || no "22 state missing $k"
done

# 23 exit-policy lines are covered by the stamp (v1.2.1)
FORGE=1 mkproj t23; FORGE=1 contract t23 "- AC-1 | f | check: \`true\` | expected: exit=0"
sed -i 's/^exit: forge/exit: threshold/' "$T/t23/.goal/goal.md"   # now threshold: no --dry needed
close_iter t23
out=$(bash "$GATE" --check --project "$T/t23" 2>&1); assert_rc "23a exit flip after stamp -> rc2" 2 $?
assert_has "23a reason contract-tampered" 'contract-tampered' "$out"
mkproj t24; contract t24 "- AC-1 | f | check: \`true\` | expected: exit=0"
sed -i 's/^## Out of scope/exit: forge\n## Out of scope/' "$T/t24/.goal/goal.md"
close_iter t24 --dry yes        # line now reads forge to ctl too - keep it writable
out=$(bash "$GATE" --check --project "$T/t24" 2>&1); assert_rc "23b exit line smuggled -> rc2" 2 $?
assert_has "23b reason contract-tampered" 'contract-tampered' "$out"

# 24 negative assertion exit=N passes; --verify path too
mkproj t25; contract t25 "- AC-1 | crash absent | check: \`false\` | expected: exit=1"
close_iter t25
out=$(bash "$GATE" --check --project "$T/t25" 2>&1); assert_rc "24 exit=1 negative GO -> rc0" 0 $?
out=$(bash "$GATE" --verify --project "$T/t25" 2>&1); assert_has "24 --verify PASS on rc match" 'AC-1\|PASS' "$out"

# 25 negative assertion wrong rc -> FAIL
mkproj t26; contract t26 "- AC-1 | w | check: \`false\` | expected: exit=3"
close_iter t26
out=$(bash "$GATE" --check --project "$T/t26" 2>&1); assert_rc "25 exit=3 vs rc1 -> rc2" 2 $?
assert_has "25 reason open-FAIL w/ expect" 'open-FAIL:AC-1' "$out"

# 26 carry-forward: same digest, later iteration -> GO without re-seat
mkproj t27; contract t27 "- AC-1 | j | check: \`true\` | expected: judged"
close_iter t27; bind_v t27 'AC-1|PASS|1|DIGEST|cmd|"ok"'
close_iter t27; bind_v t27 'AC-1|PASS|2|DIGEST|cmd|"ok carried=yes"'
out=$(bash "$GATE" --check --project "$T/t27" 2>&1); assert_rc "26 carry-forward GO -> rc0" 0 $?

# 27 no sharding: after digest moved, re-bind at stale digest -> not-covered
dOld=$(bash "$GATE" --digest --project "$T/t27")
echo new > "$T/t27/b.txt"; close_iter t27
printf 'AC-1|PASS|3|%s|cmd|"ok carried=yes"\n' "$dOld" | bash "$CTL" bind --project "$T/t27" >/dev/null
out=$(bash "$GATE" --check --project "$T/t27" 2>&1); assert_rc "27 stale re-bind -> rc2" 2 $?
assert_has "27 reason not-covered" 'not-covered:AC-1' "$out"

# 28 time-budget fuse fires when expired (rc=3, graceful class)
mkproj t28 >/dev/null; TB=1 contract t28 "- AC-1 | f | check: \`true\` | expected: exit=0"
sleep 1.3
close_iter t28
out=$(bash "$GATE" --check --project "$T/t28" 2>&1); assert_rc "28 expired time-budget -> rc3" 3 $?
assert_has "28 reason time-budget-exhausted" 'time-budget-exhausted' "$out"

# 29 time-budget in the future: loop runs normally -> GO
mkproj t29 >/dev/null; TB=3600 contract t29 "- AC-1 | f | check: \`true\` | expected: exit=0"
close_iter t29
bash "$GATE" --check --project "$T/t29" >/dev/null 2>&1; assert_rc "29 future deadline GO -> rc0" 0 $?

# 30 close-iteration preserves the time-budget keys
mkproj t30 >/dev/null; TB=60 contract t30 "- AC-1 | f | check: \`true\` | expected: exit=0"
close_iter t30
grep -q '^time_budget=60$' "$T/t30/.goal/state.rec" && ok "30 close preserves time_budget" || no "30 time_budget lost on close"
d=$(grep '^deadline=' "$T/t30/.goal/state.rec" | cut -d= -f2)
[ -n "$d" ] && [ "$d" -gt 0 ] && ok "30 close preserves deadline" || no "30 deadline lost on close"

echo
echo "== results: pass=$pass fail=$failn =="
[ "$failn" -eq 0 ] && exit 0 || exit 1
