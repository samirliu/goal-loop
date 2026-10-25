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
echo ok > "$T/t08/jart.txt"          # the artifact the judged seat reviewed
close_iter t08
S=$(sha256sum "$T/t08/jart.txt" | cut -c1-64)
bind_v t08 "AC-1|PASS|1|DIGEST|cmd|\"ok line\" artifact: jart.txt digest: $S"
bind_v t08 'AC-2|UNVERIFIABLE|1|DIGEST|-|PROBE=x REASON=y'
bind_v t08 'AC-3|UNVERIFIABLE|1|DIGEST|-|PROBE=x REASON=y'
bash "$GATE" --check --project "$T/t08" >/dev/null 2>&1; assert_rc "08 unverifiable-excessive -> rc2" 2 $?

# 09 contract tamper after stamp
mkproj t09; contract t09 "- AC-1 | f | check: \`true\` | expected: exit=0"
sed_in 's/^approved:/&\n- AC-2 | smuggled | check: `true` | expected: exit=0/' "$T/t09/.goal/goal.md" 2>/dev/null
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
sed_in 's/^dry_streak=.*/dry_streak=3/' "$T/t13/.goal/state.rec"
out=$(bash "$GATE" --check --project "$T/t13" 2>&1); assert_rc "14 forge GO -> rc0" 0 $?
assert_has "14 GO line says mode=forge" 'mode=forge' "$out"

# 15 forge budget is a fuse -> rc3
mkproj t15; FORGE=1 contract t15 "- AC-1 | f | check: \`true\` | expected: exit=0"
close_iter t15 --dry yes
sed_in 's/^iteration=.*/iteration=13/' "$T/t15/.goal/state.rec"
out=$(bash "$GATE" --check --project "$T/t15" 2>&1); assert_rc "15 budget-fuse -> rc3" 3 $?
assert_has "15 reason budget-fuse" 'budget-fuse' "$out"

# 16 v1.1 prose expectation routes to judged (backward compat)
mkproj t16; contract t16 "- AC-1 | v11 | check: \`test -f a.txt\` | expected: the diff is empty"
echo x > "$T/t16/a.txt"; close_iter t16
S16=$(sha256sum "$T/t16/a.txt" | cut -c1-64)
bind_v t16 "AC-1|PASS|1|DIGEST|cmd|\"the diff is empty\" artifact: a.txt digest: $S16"
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
sed_in 's/^exit: forge/exit: threshold/' "$T/t23/.goal/goal.md"   # now threshold: no --dry needed
close_iter t23
out=$(bash "$GATE" --check --project "$T/t23" 2>&1); assert_rc "23a exit flip after stamp -> rc2" 2 $?
assert_has "23a reason contract-tampered" 'contract-tampered' "$out"
mkproj t24; contract t24 "- AC-1 | f | check: \`true\` | expected: exit=0"
sed_in 's/^## Out of scope/exit: forge\n## Out of scope/' "$T/t24/.goal/goal.md"
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
echo ok > "$T/t27/jart.txt"
S27=$(sha256sum "$T/t27/jart.txt" | cut -c1-64)
close_iter t27; bind_v t27 "AC-1|PASS|1|DIGEST|cmd|\"ok\" artifact: jart.txt digest: $S27"
close_iter t27; bind_v t27 "AC-1|PASS|2|DIGEST|cmd|\"ok carried=yes\" artifact: jart.txt digest: $S27"
out=$(bash "$GATE" --check --project "$T/t27" 2>&1); assert_rc "26 carry-forward GO -> rc0" 0 $?

# 27 no sharding: after digest moved, re-bind at stale digest -> not-covered
dOld=$(bash "$GATE" --digest --project "$T/t27")
echo new > "$T/t27/b.txt"; close_iter t27
printf 'AC-1|PASS|3|%s|cmd|"ok carried=yes"\n' "$dOld" | bash "$CTL" bind --project "$T/t27" >/dev/null
out=$(bash "$GATE" --check --project "$T/t27" 2>&1); assert_rc "27 stale re-bind -> rc2" 2 $?
assert_has "27 reason not-covered" 'not-covered:AC-1' "$out"

# 28 expired wallclock + GREEN claim still delivers (fuse is not a delivery veto)
mkproj t28 >/dev/null; TB=1 contract t28 "- AC-1 | f | check: \`true\` | expected: exit=0"
# deterministically expired: deadline=1 (epoch 1) is always in the past - no
# reliance on machine speed (a fast runner used to hit the same-second
# boundary and wrongly answer GO)
sed_in 's/^deadline=.*/deadline=1/' "$T/t28/.goal/state.rec"
close_iter t28
out=$(bash "$GATE" --check --project "$T/t28" 2>&1); assert_rc "28 expired green claim -> GO" 0 $?
assert_has "28 NOTE fuse" 'time-budget-exhausted' "$out"
assert_has "28 still GO" 'GATE: GO' "$out"

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

# 31 evidence_cache: measurement-once semantics (references/patterns.md section 11)
mkproj t31 >/dev/null
printf 'v1\n' > "$T/t31/in.txt"
cd "$T/t31"
EC="bash $here/assets/evidence_cache.sh t31cache -- in.txt --"
cmd31='c=$(cat counter 2>/dev/null || echo 0); c=$((c+1)); printf "%s" "$c" > counter; echo run#$c; echo 42'
out1=$($EC -- "$cmd31"); c1=$(cat counter)
out2=$($EC -- "$cmd31"); c2=$(cat counter)
assert_has "31a cache hit replays metric 42" '42' "$out2"
[ "$c1" = "$c2" ] && ok "31b command ran once for unchanged input" || no "31b ran twice (c1=$c1 c2=$c2)"
[ -f .goal/evidence/t31cache.out ] && ok "31c stdout archived under .goal/evidence" || no "31c archive missing"
printf 'v2\n' >> in.txt
out3=$($EC -- "$cmd31"); c3=$(cat counter)
assert_has "31d rerun after input change" 'run#2' "$out3"
cd "$here"

# 32 docs_consistency: the skill's own docs stay mechanically consistent
bash "$here/tests/docs_consistency.sh" >/dev/null 2>&1
assert_rc "32 docs consistency" 0 $?

# 33 external linter (shellcheck) - run when available, skip silently otherwise.
# Severity parity with CI: warnings and errors block; info-level style hints
# stay visible in CI logs but do not fail (single definition of green).
if command -v shellcheck >/dev/null 2>&1; then
  shellcheck --severity=warning "$here/scripts/goal_gate.sh" "$here/scripts/goal_loop.sh" "$here/scripts/goal_ctl.sh" "$here/scripts/goal_hook.sh" \
    && ok "33 shellcheck clean" || no "33 shellcheck findings"
else
  ok "33 shellcheck skipped (not installed)"
fi

# 34-39: Stop hook (goal_hook.sh) - the physical tooth. The hook reads
# .goal/ relative to its cwd; run each scenario from inside the fixture.
# 34 no .goal/ -> allow (rc0)
mkdir -p "$T/h34"
(cd "$T/h34" && bash "$here/scripts/goal_hook.sh") >/dev/null 2>&1
assert_rc "34 hook no-goal allows stop" 0 $?

# 35 claimed + gate GO -> allow
mkproj h35 >/dev/null; contract h35 "- AC-1 | f | check: \`true\` | expected: exit=0"
close_iter h35
(cd "$T/h35" && bash "$here/scripts/goal_hook.sh") >/dev/null 2>&1
assert_rc "35 hook claimed+GO allows stop" 0 $?

# 36 claimed + gate rc2 -> BLOCK (rc2), sanitized reason with prefix
mkproj h36 >/dev/null; contract h36 "- AC-1 | f | check: \`false\` | expected: exit=0"
close_iter h36
(cd "$T/h36" && bash "$here/scripts/goal_hook.sh") >/dev/null 2>"$T/h36.err"
assert_rc "36 hook claimed+NO-GO blocks (rc2)" 2 $?
grep -q 'GOAL_LOOP_GATE' "$T/h36.err" && ok "36 block reason carries GOAL_LOOP_GATE prefix" || no "36 missing GOAL_LOOP_GATE prefix"
grep -qE 'open-FAIL:AC-1' "$T/h36.err" && ok "36 gate reason preserved in block message" || no "36 gate reason lost"

# 37 unclaimed stop -> allow
mkproj h37 >/dev/null; contract h37 "- AC-1 | f | check: \`true\` | expected: exit=0"
bash "$CTL" close-iteration --project "$T/h37" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --exit-signal no --no-gate >/dev/null 2>&1
two_pass h37
(cd "$T/h37" && bash "$here/scripts/goal_hook.sh") >/dev/null 2>&1
assert_rc "37 hook unclaimed allows stop" 0 $?

# 38 BLOCKED state (breaker OPEN, rc3) -> allow: user decision, not a grind
mkproj h38 >/dev/null; contract h38 "- AC-1 | f | check: \`true\` | expected: exit=0"
close_iter h38
sed_in 's/^breaker=.*/breaker=OPEN/' "$T/h38/.goal/state.rec"
(cd "$T/h38" && bash "$here/scripts/goal_hook.sh") >/dev/null 2>&1
assert_rc "38 hook rc3 state allows stop" 0 $?

# 39 broken state (state.rec gone, rc4) -> fail-open
mkproj h39 >/dev/null; contract h39 "- AC-1 | f | check: \`true\` | expected: exit=0"
close_iter h39
rm "$T/h39/.goal/state.rec"
(cd "$T/h39" && bash "$here/scripts/goal_hook.sh") >/dev/null 2>&1
assert_rc "39 hook rc4 fail-open allows stop" 0 $?

# 40-45: baseline enforcement (forge contracts, v1.5)
# 40 stamp refused without baseline.md, goal.md left unstamped
NOSTAMP=1 mkproj h40 >/dev/null; FORGE=1 NOSTAMP=1 contract h40 "- AC-1 | m | check: \`echo 7\` | baseline: delta | expected: >=5"
bash "$CTL" stamp --project "$T/h40" --auto >/dev/null 2>&1
assert_rc "40 stamp without baseline refused rc2" 2 $?
grep -qE '^approved: [0-9a-f]{6,}' "$T/h40/.goal/goal.md" && no "40 stamped despite refusal" || ok "40 goal.md left unstamped"

# 41 valid baseline -> stamp ok -> forge GO (dry_streak forced to limit)
printf 'AC-1 | observed=7 | repeats=3 | cmd=echo 7\n' > "$T/h40/.goal/baseline.md"
bash "$CTL" stamp --project "$T/h40" --auto >/dev/null 2>&1
assert_rc "41 stamp with baseline ok" 0 $?
echo x > "$T/h40/a.txt"; close_iter h40 --dry yes
sed_in 's/^dry_streak=.*/dry_streak=3/' "$T/h40/.goal/state.rec"
bash "$GATE" --check --project "$T/h40" >/dev/null 2>&1
assert_rc "41 forge GO with baseline satisfied" 0 $?

# 42 cmd mismatch -> baseline-cmd-mismatch
NOSTAMP=1 mkproj h42 >/dev/null; FORGE=1 NOSTAMP=1 contract h42 "- AC-1 | m | check: \`echo 9\` | baseline: delta | expected: >=5"
printf 'AC-1 | observed=7 | repeats=3 | cmd=echo 8\n' > "$T/h42/.goal/baseline.md"
bash "$GATE" --baseline-check --project "$T/h42" >/dev/null 2>&1
assert_rc "42 cmd mismatch rc2" 2 $?
bash "$GATE" --baseline-check --project "$T/h42" 2>&1 | grep -q baseline-cmd-mismatch && ok "42 reason baseline-cmd-mismatch" || no "42 wrong reason"

# 43 abs marker: new capability, no baseline owed -> stamp ok + GO
NOSTAMP=1 mkproj h43 >/dev/null; FORGE=1 NOSTAMP=1 contract h43 "- AC-1 | m | check: \`echo 7\` | baseline: abs | expected: >=5"
bash "$CTL" stamp --project "$T/h43" --auto >/dev/null 2>&1
assert_rc "43 abs stamp ok without baseline" 0 $?
close_iter h43 --dry yes; sed_in 's/^dry_streak=.*/dry_streak=3/' "$T/h43/.goal/state.rec"
bash "$GATE" --check --project "$T/h43" >/dev/null 2>&1
assert_rc "43 abs forge GO" 0 $?

# 44 threshold contracts ignore baseline entirely
mkproj h44 >/dev/null; contract h44 "- AC-1 | m | check: \`echo 7\` | baseline: delta | expected: >=5"
bash "$GATE" --baseline-check --project "$T/h44" >/dev/null 2>&1
assert_rc "44 baseline-check not-forge ok" 0 $?
close_iter h44
bash "$GATE" --check --project "$T/h44" >/dev/null 2>&1
assert_rc "44 threshold GO without baseline" 0 $?

# 45 repeats=1 -> baseline-weak refused
NOSTAMP=1 mkproj h45 >/dev/null; FORGE=1 NOSTAMP=1 contract h45 "- AC-1 | m | check: \`echo 7\` | baseline: delta | expected: >=5"
printf 'AC-1 | observed=7 | repeats=1 | cmd=echo 7\n' > "$T/h45/.goal/baseline.md"
bash "$GATE" --baseline-check --project "$T/h45" >/dev/null 2>&1
assert_rc "45 single-run baseline refused rc2" 2 $?

# 46 status subcommand: human progress summary
mkproj h46 >/dev/null; contract h46 "- AC-1 | f | check: \`true\` | expected: exit=0"
printf -- '- [ ] T1 | do the thing\n' > "$T/h46/.goal/work-plan.md"
close_iter h46
out=$(bash "$CTL" status --project "$T/h46" 2>&1)
assert_has "46 status prints iteration line" 'CTL: STATUS iter=1/' "$out"
assert_has "46 status prints last block" 'CTL: LAST task=T1\[crew:1\]' "$out"
assert_has "46 status prints next task" 'CTL: NEXT T1 | do the thing' "$out"

# 47 teams-backend wave marker survives normalization (teams wave passes through)
mkproj t47; contract t47 "- AC-1 | f | check: \`true\` | expected: exit=0"
bash "$CTL" close-iteration --project "$T/t47" --task 'T2[teams:3]' --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --no-gate >/dev/null 2>&1
two_pass t47
out=$(bash "$CTL" status --project "$T/t47" 2>&1)
assert_has "47 status echoes teams wave marker" 'CTL: LAST task=T2\[teams:3\]' "$out"

# 48-52 portable team layer (goal_team.sh) — cc-haha-shaped file protocol
mkproj t48
out=$(bash "$TEAM" init --project "$T/t48" --team goal --description 'run' 2>&1)
assert_rc "48 team init ok" 0 $?
assert_has "48 init echoes team" 'TEAM: INIT ok team=goal' "$out"
[ -f "$T/t48/.goal/team/config.json" ] && ok "48 config.json written" || no "48 config.json missing"
[ -d "$T/t48/.goal/team/inboxes" ] && ok "48 inboxes dir" || no "48 inboxes dir missing"

out=$(bash "$TEAM" init --project "$T/t48" --team goal 2>&1); assert_rc "48b double init refused" 2 $?

out=$(bash "$TEAM" roster --project "$T/t48" --add --name w1 --role backend \
  --prompt 'do X' --scope 'src/api' 2>&1)
assert_rc "49 roster add" 0 $?
assert_has "49 roster add echoes name" 'ROSTER add name=w1' "$out"
out=$(bash "$TEAM" roster --project "$T/t48" --add --name w1 --role other --prompt 'x' 2>&1)
assert_rc "49b duplicate name refused" 2 $?

bash "$TEAM" roster --project "$T/t48" --add --name w2 --role frontend --prompt 'do Y' >/dev/null
out=$(bash "$TEAM" send --project "$T/t48" --from w1 --to w2 \
  --text 'field renamed' --summary 'rename notice' 2>&1)
assert_rc "50 send to w2" 0 $?
assert_has "50 send echoes to" 'SEND ok to=w2' "$out"
grep -q 'field renamed' "$T/t48/.goal/team/inboxes/w2.jsonl" && ok "50 inbox has text" || no "50 inbox missing text"
grep -q '"from":"w1"' "$T/t48/.goal/team/inboxes/w2.jsonl" && ok "50 message from field" || no "50 from field missing"
grep -q '"read":false' "$T/t48/.goal/team/inboxes/w2.jsonl" && ok "50 unread flag" || no "50 read flag wrong"

out=$(bash "$TEAM" send --project "$T/t48" --from controller --to '*' --text 'wave note' 2>&1)
assert_rc "51 broadcast" 0 $?
assert_has "51 broadcast delivered=2" 'delivered=2' "$out"
grep -q 'wave note' "$T/t48/.goal/team/inboxes/w1.jsonl" && ok "51 w1 got broadcast" || no "51 w1 missed broadcast"
grep -q 'wave note' "$T/t48/.goal/team/inboxes/w2.jsonl" && ok "51 w2 got broadcast" || no "51 w2 missed broadcast"

out=$(bash "$TEAM" inbox --project "$T/t48" --name w2 --unread 2>&1)
assert_has "52 unread listing" 'field renamed' "$out"
out=$(bash "$TEAM" inbox --project "$T/t48" --name w2 --mark-read 2>&1)
assert_rc "52 mark-read" 0 $?
grep -q '"read":true' "$T/t48/.goal/team/inboxes/w2.jsonl" && ok "52 marked read" || no "52 not marked read"
out=$(bash "$TEAM" status --project "$T/t48" 2>&1)
assert_has "52 status shows roster" 'w1' "$out"

bash "$TEAM" delete --project "$T/t48" >/dev/null
[ ! -d "$T/t48/.goal/team" ] && ok "52b delete removes team dir" || no "52b team dir remains"

# 52c status unread count must be a single integer (grep -c zero-match trap)
mkproj t52c
bash "$TEAM" init --project "$T/t52c" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t52c" --add --name w1 --role r --prompt p >/dev/null
bash "$TEAM" send --project "$T/t52c" --from c --to w1 --text 'hello' >/dev/null
bash "$TEAM" inbox --project "$T/t52c" --name w1 --mark-read >/dev/null
out=$(bash "$TEAM" status --project "$T/t52c" 2>&1)
assert_has "52c status shows unread=0" 'unread=0' "$out"
printf '%s' "$out" | grep -qE 'w1\.jsonl: total=1 unread=0$' && ok "52c unread is single integer" || no "52c unread polluted: [$out]"

# 53 maximize objective + score-regressed (R11)
mkproj t53
{
  printf '# Goal contract - test\n\n## Objective\n\ntest\n\n'
  printf 'objective: maximize AC-1\nhorizon-waived: toy single-metric contract - blind spot immaterial\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | score | check: `echo 7` | expected: maximize\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t53/.goal/goal.md"
bash "$CTL" stamp --project "$T/t53" --auto >/dev/null
bash "$CTL" close-iteration --project "$T/t53" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --score 7 --strategy probe-first --no-gate >/dev/null 2>&1
two_pass t53
out=$(bash "$GATE" --check --project "$T/t53" 2>&1); assert_rc "53 maximize GO at score 7" 0 $?
assert_has "53 GO line carries score" 'score=7' "$out"
grep -q 'best_score=7' "$T/t53/.goal/state.rec" && ok "53 best_score stored" || no "53 best_score missing"

# 54 score-regressed claim refused
sed_in 's/^iteration=.*/iteration=1/' "$T/t53/.goal/state.rec"
# rewrite last block score and claim again with a lower gate rerun: lower echo
# simulate by bumping best_score above the check's 7
sed_in 's/^best_score=.*/best_score=9/' "$T/t53/.goal/state.rec"
out=$(bash "$GATE" --check --project "$T/t53" 2>&1); assert_rc "54 score-regressed -> rc2" 2 $?
assert_has "54 reason score-regressed" 'score-regressed' "$out"

# 55 probe-failed untrusts the metric (R9)
mkproj t55
{
  printf '# Goal contract - test\n\n## Objective\n\ntest\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | metric | check: `echo 9` | probe: `false` | expected: >=1\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t55/.goal/goal.md"
bash "$CTL" stamp --project "$T/t55" --auto >/dev/null
bash "$CTL" close-iteration --project "$T/t55" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --no-gate >/dev/null 2>&1
out=$(bash "$GATE" --check --project "$T/t55" 2>&1); assert_rc "55 probe-failed -> rc2" 2 $?
assert_has "55 reason check-broken probe" 'probe-failed' "$out"

# 55b probe passes -> metric trusted
mkproj t55b
{
  printf '# Goal contract - test\n\n## Objective\n\ntest\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | metric | check: `echo 9` | probe: `true` | expected: >=1\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t55b/.goal/goal.md"
bash "$CTL" stamp --project "$T/t55b" --auto >/dev/null
bash "$CTL" close-iteration --project "$T/t55b" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --no-gate >/dev/null 2>&1
two_pass t55b
out=$(bash "$GATE" --check --project "$T/t55b" 2>&1); assert_rc "55b probe-ok GO" 0 $?

# 56 HALF_OPEN requires strategy_delta (R10)
mkproj t56
out=$(bash "$CTL" close-iteration --project "$T/t56" --task T1 --files a.txt \
  --checks-pass 0 --checks-fail 0 --checks-unverifiable 0 --progress no \
  --exit-signal no --no-gate 2>&1)
assert_rc "56 progress=no without strategy_delta refused" 4 $?
assert_has "56 error names strategy-delta" 'missing-strategy-delta' "$out"

bash "$CTL" close-iteration --project "$T/t56" --task T1 --files a.txt \
  --checks-pass 0 --checks-fail 0 --checks-unverifiable 0 --progress no \
  --exit-signal no --strategy-delta 'switch camera to side view' --no-gate >/dev/null 2>&1
grep -q 'strategy_delta=switch camera' "$T/t56/.goal/loop-log.md" && ok "56 strategy_delta recorded" || no "56 strategy_delta missing"

# 57 objective: line is frozen by the stamp (R11 cannot be patched away)
mkproj t57
{
  printf '# Goal contract - t\n\n## Objective\n\nt\n\n'
  printf 'objective: maximize AC-1\nhorizon-waived: toy single-metric contract - blind spot immaterial\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | s | check: `echo 3` | expected: maximize\n'
  printf '\n## Out of scope\n\n- n\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t57/.goal/goal.md"
bash "$CTL" stamp --project "$T/t57" --auto >/dev/null
sed_in 's/^objective: maximize AC-1/objective: maximize AC-2/' "$T/t57/.goal/goal.md"
bash "$CTL" close-iteration --project "$T/t57" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --score 3 --strategy probe-first --no-gate >/dev/null 2>&1
out=$(bash "$GATE" --check --project "$T/t57" 2>&1); assert_rc "57 tampered objective -> rc2" 2 $?
assert_has "57 reason contract-tampered" 'contract-tampered' "$out"

# 58 strategy_delta newline is flattened (must not shred loop-log block)
mkproj t58
bash "$CTL" close-iteration --project "$T/t58" --task T1 --files a.txt \
  --checks-pass 0 --checks-fail 0 --checks-unverifiable 0 --progress no \
  --exit-signal no --strategy-delta $'line1\nline2' --no-gate >/dev/null 2>&1
grep -q 'strategy_delta=line1 line2' "$T/t58/.goal/loop-log.md" && ok "58 strategy_delta single line" || no "58 strategy_delta multi-line leaked"
grep -c '^## iteration' "$T/t58/.goal/loop-log.md" | grep -qx '1' && ok "58 loop-log block intact" || no "58 loop-log block shredded"

# 59 bad score rejected
mkproj t59
bash "$CTL" close-iteration --project "$T/t59" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --score '1.2.3' --no-gate >/dev/null 2>&1
assert_rc "59 bad-score refused" 4 $?

# 60 status shows best_score
mkproj t60
{
  printf '# Goal contract - t\n\n## Objective\n\nt\n\n'
  printf 'objective: maximize AC-1\nhorizon-waived: toy single-metric contract - blind spot immaterial\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | s | check: `echo 5` | expected: maximize\n'
  printf '\n## Out of scope\n\n- n\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t60/.goal/goal.md"
bash "$CTL" stamp --project "$T/t60" --auto >/dev/null
bash "$CTL" close-iteration --project "$T/t60" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --score 5 --strategy probe-first --no-gate >/dev/null 2>&1
out=$(bash "$CTL" status --project "$T/t60" 2>&1)
assert_has "60 status best_score" 'best_score=5' "$out"

# 61 score is MEASURED, not self-reported: a wrong claim is overridden
mkproj t61
{
  printf '# Goal contract - t\n\n## Objective\n\nt\n\n'
  printf 'objective: maximize AC-1\nhorizon-waived: toy single-metric contract - blind spot immaterial\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | s | check: `echo 42` | expected: maximize\n'
  printf '\n## Out of scope\n\n- n\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t61/.goal/goal.md"
bash "$CTL" stamp --project "$T/t61" --auto >/dev/null
out=$(bash "$CTL" close-iteration --project "$T/t61" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --score 7 --strategy probe-first --no-gate 2>&1)
assert_has "61 mismatch noted" 'score-measured-override' "$out"
grep -q '^score=42$' "$T/t61/.goal/loop-log.md" && ok "61 measured score recorded" || no "61 recorded claimed score"
grep -q '^best_score=42$' "$T/t61/.goal/state.rec" && ok "61 best_score from measurement" || no "61 best_score wrong"

# 62 unmeasurable objective records none (gate will refuse the claim later)
mkproj t62
{
  printf '# Goal contract - t\n\n## Objective\n\nt\n\n'
  printf 'objective: maximize AC-1\nhorizon-waived: toy single-metric contract - blind spot immaterial\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | s | check: `cat missing_file_xyz` | expected: maximize\n'
  printf '\n## Out of scope\n\n- n\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t62/.goal/goal.md"
bash "$CTL" stamp --project "$T/t62" --auto >/dev/null
out=$(bash "$CTL" close-iteration --project "$T/t62" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --score 9 --strategy probe-first --no-gate 2>&1)
two_pass t62
assert_rc "62 unmeasurable records ok rc0" 0 $?
assert_has "62 warns unmeasurable" 'objective-unmeasurable' "$out"
grep -q '^score=none$' "$T/t62/.goal/loop-log.md" && ok "62 score=none recorded" || no "62 score not none"

# 63-65 goal_audit.sh (R12 controller self-audit)
AUDIT="$here/scripts/goal_audit.sh"
mkproj t63
printf '## iteration 1\ntask=T1[teams:3]\nprogress=yes\nexit_signal=no\nscore=99.5\nstrategy_delta=none\n' > "$T/t63/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t63" 2>&1); rc=$?
assert_rc "63 clean ledger rc0" 0 $rc
assert_has "63 clean said" 'AUDIT: clean' "$out"

mkproj t64
printf '## iteration 1\ntask=T1[teams:3]\nprogress=yes\nexit_signal=no\nscore=1\nstrategy_delta=none\n## iteration 2\ntask=T2[crew:3]\nprogress=yes\nexit_signal=no\nscore=2\nstrategy_delta=none\n' > "$T/t64/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t64" 2>&1); rc=$?
assert_rc "64 silent-downgrade rc1" 1 $rc
assert_has "64 names silent-downgrade" 'silent-downgrade' "$out"

mkproj t65
printf '## iteration 1\ntask=T1[teams:3](fallback:evil-mode)\nprogress=no\nexit_signal=no\nscore=1.2.3\nstrategy_delta=none\n' > "$T/t65/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t65" 2>&1); rc=$?
assert_rc "65 bad vocab+score+delta rc1" 1 $rc
assert_has "65 vocab" 'fallback-vocabulary' "$out"
assert_has "65 score-format" 'score-format' "$out"
assert_has "65 missing strategy_delta" 'progress-no-without-strategy-delta' "$out"

# 65a-e A3 recovery allowlist + A4 across crew:/teams: (round-1 fix pins)
# 65a invented recovery token on crew: is rejected (A1 closed grammar)
mkproj t65a
printf '## iteration 1\ntask=T2[crew:1] (re-run:evil)\nprogress=yes\nexit_signal=no\nscore=none\nstrategy_delta=none\n' > "$T/t65a/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t65a" 2>&1); rc=$?
assert_rc "65a crew invented recovery rc1" 1 $rc
assert_has "65a rejected at schema gate" 'A1 task-schema' "$out"
# 65b A4 still fires for crew+recovery inside a teams run (recovery does not
#     explain a backend downgrade - only fallback: does)
mkproj t65b
printf '## iteration 1\ntask=T1[teams:3]\nprogress=yes\nexit_signal=no\nscore=1\nstrategy_delta=none\n## iteration 2\ntask=T2[crew:3] (stall-recovered)\nprogress=yes\nexit_signal=no\nscore=2\nstrategy_delta=none\n' > "$T/t65b/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t65b" 2>&1); rc=$?
assert_rc "65b crew+recovery inside teams run rc1" 1 $rc
assert_has "65b names silent-downgrade" 'silent-downgrade' "$out"
# 65c crew+fallback inside a teams run stays exempt from A4
mkproj t65c
printf '## iteration 1\ntask=T1[teams:3]\nprogress=yes\nexit_signal=no\nscore=1\nstrategy_delta=none\n## iteration 2\ntask=T2[crew:3] (fallback:teams-unavailable)\nprogress=yes\nexit_signal=no\nscore=2\nstrategy_delta=none\n' > "$T/t65c/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t65c" 2>&1); rc=$?
assert_rc "65c crew+fallback exempt from A4" 0 $rc
assert_has "65c clean" 'AUDIT: clean' "$out"
# 65d valid recovery suffix on teams: is A3-clean
mkproj t65d
printf '## iteration 1\ntask=T2[teams:2] (re-run:death)\nprogress=yes\nexit_signal=no\nscore=none\nstrategy_delta=none\n' > "$T/t65d/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t65d" 2>&1); rc=$?
assert_rc "65d teams recovery suffix clean" 0 $rc
assert_has "65d clean" 'AUDIT: clean' "$out"
# 65e valid recovery suffix on crew: (no teams run) is A3-clean, no A4
mkproj t65e
printf '## iteration 1\ntask=T2[crew:2] (re-run:stall)\nprogress=yes\nexit_signal=no\nscore=none\nstrategy_delta=none\n' > "$T/t65e/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t65e" 2>&1); rc=$?
assert_rc "65e crew recovery suffix clean" 0 $rc
assert_has "65e clean" 'AUDIT: clean' "$out"

# 66-68 R13 score<->judge divergence guard
mkproj t66
{
  printf '# Goal contract - t\n\n## Objective\n\nt\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | s | check: `true` | expected: exit=0\n'
  printf '\n## Out of scope\n\n- n\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t66/.goal/goal.md"
bash "$CTL" stamp --project "$T/t66" --auto >/dev/null
bash "$CTL" close-iteration --project "$T/t66" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --no-gate --judge-score 4 >/dev/null 2>&1
bash "$CTL" close-iteration --project "$T/t66" --task T2 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --no-gate --judge-score 2 >/dev/null 2>&1
# last block claims; no objective AC so score=none both rows -> A8-free but
# R13 needs numeric score side; fabricate comparable points then check
printf '1|10|4\n2|20|2\n' >> "$T/t66/.goal/scores.rec"
# close again so last block is the claim with exit_signal=yes (t66 last was yes)
out=$(bash "$GATE" --check --project "$T/t66" 2>&1); rc=$?
assert_rc "66 divergence refuses claim rc2" 2 $rc
assert_has "66 names DIVERGENCE" 'DIVERGENCE:score-vs-judge' "$out"

mkproj t67
{
  printf '# Goal contract - t\n\n## Objective\n\nt\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | s | check: `true` | expected: exit=0\n'
  printf '\n## Out of scope\n\n- n\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t67/.goal/goal.md"
bash "$CTL" stamp --project "$T/t67" --auto >/dev/null
bash "$CTL" close-iteration --project "$T/t67" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --no-gate >/dev/null 2>&1
printf '1|10|2\n2|20|4\n' >> "$T/t67/.goal/scores.rec"
bash "$CTL" close-iteration --project "$T/t67" --task T2 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --no-gate --judge-score 4 >/dev/null 2>&1
# last scores.rec row: 2|none|4 (no objective) - that's not comparable, so
# pair is 1|10|2 vs earlier... append a clean agreeing pair as the tail
printf '3|30|5\n4|40|5\n' >> "$T/t67/.goal/scores.rec"
two_pass t67
out=$(bash "$GATE" --check --project "$T/t67" 2>&1); rc=$?
assert_has "67 no DIVERGENCE on same-direction" 'GATE: GO' "$out"
printf '%s' "$out" | grep -q 'DIVERGENCE' && no "67 unexpected DIVERGENCE" || ok "67 no DIVERGENCE token"

mkproj t68
{
  printf '# Goal contract - t\n\n## Objective\n\nt\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | s | check: `true` | expected: judged\n'
  printf '\n## Out of scope\n\n- n\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t68/.goal/goal.md"
bash "$CTL" stamp --project "$T/t68" --auto >/dev/null
bash "$CTL" close-iteration --project "$T/t68" --task 'T1[crew:1]' --files a.txt \
  --checks-pass 0 --checks-fail 0 --checks-unverifiable 1 --progress yes \
  --exit-signal no --no-gate >/dev/null 2>&1
two_pass t68
out=$(bash "$AUDIT" --project "$T/t68" 2>&1); rc=$?
assert_rc "68 A8 warn does not block rc0" 0 $rc
assert_has "68 A8 warns judge-score-unrecorded" 'A8 judge-score-unrecorded' "$out"

# 69 minimize: classify as deterministic objective, not judged
mkproj t69
{
  printf '# Goal contract - test\n\n## Objective\n\ntest\n\n'
  printf 'objective: minimize AC-1\nhorizon-waived: toy single-metric contract - blind spot immaterial\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | score | check: `echo 7` | expected: minimize\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t69/.goal/goal.md"
bash "$CTL" stamp --project "$T/t69" --auto >/dev/null
bash "$CTL" close-iteration --project "$T/t69" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --score 7 --strategy probe-first --no-gate >/dev/null 2>&1
two_pass t69
out=$(bash "$GATE" --verify AC-1 --project "$T/t69" 2>&1)
assert_has "69 minimize classified deterministic" 'AC-1|PASS|observed=7' "$out"
printf '%s' "$out" | grep -q '|SKIP|judged' && no "69 minimize misrouted to judged" || ok "69 not judged"
out=$(bash "$GATE" --check --project "$T/t69" 2>&1); assert_rc "69 minimize GO at score 7" 0 $?
grep -q 'best_score=7' "$T/t69/.goal/state.rec" && ok "69 best_score stored" || no "69 best_score missing"

# 70 minimize low-water mark: higher score is regression
sed_in 's/^best_score=.*/best_score=5/' "$T/t69/.goal/state.rec"
out=$(bash "$GATE" --check --project "$T/t69" 2>&1); assert_rc "70 score-regressed (minimize 7>5) -> rc2" 2 $?
assert_has "70 reason score-regressed" 'score-regressed' "$out"
assert_has "70 direction named" 'dir=minimize' "$out"

# 70b minimize accepts an improved (lower) score
mkproj t70b
{
  printf '# Goal contract - test\n\n## Objective\n\ntest\n\n'
  printf 'objective: minimize AC-1\nhorizon-waived: toy single-metric contract - blind spot immaterial\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | score | check: `echo 3` | expected: minimize\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t70b/.goal/goal.md"
bash "$CTL" stamp --project "$T/t70b" --auto >/dev/null
bash "$CTL" close-iteration --project "$T/t70b" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --score 3 --strategy probe-first --no-gate >/dev/null 2>&1
two_pass t70b
out=$(bash "$GATE" --check --project "$T/t70b" 2>&1); assert_rc "70b minimize GO at improved score 3" 0 $?

# 71 R13 divergence direction-aware for minimize
# NOTE: ctl re-measures --score via gate --verify (self-report is a hint), so
# fabricate the scores.rec pair the way t66/t67 do - the point under test is
# the direction math, not the measurement path.
mkproj t71
{
  printf '# Goal contract - test\n\n## Objective\n\ntest\n\n'
  printf 'objective: minimize AC-1\nhorizon-waived: toy single-metric contract - blind spot immaterial\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | score | check: `echo 10` | expected: minimize\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t71/.goal/goal.md"
bash "$CTL" stamp --project "$T/t71" --auto >/dev/null
bash "$CTL" close-iteration --project "$T/t71" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --no-gate --judge-score 8 --strategy probe-first --score 20 >/dev/null 2>&1
bash "$CTL" close-iteration --project "$T/t71" --task T2 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --no-gate --judge-score 3 --strategy probe-first >/dev/null 2>&1
# score improved (20->10, lower=better) but judge fell (8->3) -> DIVERGENCE
printf '1|20|8\n2|10|3\n' >> "$T/t71/.goal/scores.rec"
out=$(bash "$GATE" --check --project "$T/t71" 2>&1); assert_rc "71 minimize divergence -> rc2" 2 $?
assert_has "71 DIVERGENCE token" 'DIVERGENCE:score-vs-judge' "$out"
assert_has "71 dir named" 'dir=minimize' "$out"

# 72 minimize score+judge both improve -> GO
mkproj t72
{
  printf '# Goal contract - test\n\n## Objective\n\ntest\n\n'
  printf 'objective: minimize AC-1\nhorizon-waived: toy single-metric contract - blind spot immaterial\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | score | check: `echo 10` | expected: minimize\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t72/.goal/goal.md"
bash "$CTL" stamp --project "$T/t72" --auto >/dev/null
bash "$CTL" close-iteration --project "$T/t72" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --no-gate --judge-score 3 --strategy probe-first --score 20 >/dev/null 2>&1
two_pass t72
bash "$CTL" close-iteration --project "$T/t72" --task T2 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --no-gate --judge-score 8 --strategy probe-first >/dev/null 2>&1
two_pass t72
printf '1|20|3\n2|10|8\n' >> "$T/t72/.goal/scores.rec"
out=$(bash "$GATE" --check --project "$T/t72" 2>&1); assert_rc "72 minimize agree -> GO" 0 $?
printf '%s' "$out" | grep -q 'DIVERGENCE' && no "72 unexpected DIVERGENCE" || ok "72 no DIVERGENCE"

# 73 budget knobs in goal.md bind at stamp (were decorative)
mkproj t73
{
  printf '# Goal contract - test\n\n## Objective\n\ntest\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | s | check: `true` | expected: exit=0\n'
  printf '\n## Out of scope\n\n- none\n\n'
  printf '## Budget knobs\n\nmax_iterations=10  no_progress_limit=2  max_replans=2\n'
  printf 'per_check_fail_cap=3  panel_max=4  dry_limit=3  check_timeout=60\n'
  printf 'wallclock=99\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t73/.goal/goal.md"
bash "$CTL" stamp --project "$T/t73" --auto >/dev/null
grep -q '^max_iterations=10$' "$T/t73/.goal/state.rec" && ok "73 max_iterations bound" || no "73 max_iterations not bound"
grep -q '^check_timeout=60$' "$T/t73/.goal/state.rec" && ok "73 check_timeout bound" || no "73 check_timeout not bound"
grep -q '^time_budget=99$' "$T/t73/.goal/state.rec" && ok "73 wallclock bound" || no "73 wallclock not bound"
grep -q '^deadline=' "$T/t73/.goal/state.rec" && ok "73 deadline seeded" || no "73 deadline missing"

# 74 gate NO-GO carries a mechanical routing hint
mkproj t74
{
  printf '# Goal contract - test\n\n## Objective\n\ntest\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | s | check: `true` | expected: exit=0\n'
  printf -- '- AC-2 | j | check: `true` | expected: judged\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t74/.goal/goal.md"
bash "$CTL" stamp --project "$T/t74" --auto >/dev/null
bash "$CTL" close-iteration --project "$T/t74" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 1 --progress yes \
  --exit-signal yes --no-gate >/dev/null 2>&1
out=$(bash "$GATE" --check --project "$T/t74" 2>&1); assert_rc "74 not-covered -> rc2" 2 $?
assert_has "74 reason not-covered" 'not-covered:AC-2' "$out"
assert_has "74 hint bind-seat" 'hint=bind-seat' "$out"

# 75 status lists ALL open work-plan items
printf -- '- [ ] T1 | w1 | first | files: a\n- [ ] T2 | w2 | second | files: b\n' > "$T/t74/.goal/work-plan.md"
out=$(bash "$CTL" status --project "$T/t74" 2>&1)
assert_has "75 status shows T1" 'T1' "$out"
assert_has "75 status shows T2" 'T2' "$out"
assert_has "75 status counts 2 open" 'OPEN \(2 items\)' "$out"
printf -- '- [x] T1 | w1 | first | files: a\n- [ ] T2 | w2 | second | files: b\n' > "$T/t74/.goal/work-plan.md"
out=$(bash "$CTL" status --project "$T/t74" 2>&1)
assert_has "75 status drops ticked T1" 'OPEN \(1 items\)' "$out"
printf '%s' "$out" | grep -q 'T1 |' && no "75 ticked item still listed" || ok "75 ticked item hidden"

# 76 expired wallclock still delivers a green claim (fuse != delivery veto)
mkproj t76
{
  printf '# Goal contract - test\n\n## Objective\n\ntest\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | s | check: `true` | expected: exit=0\n'
  printf '\n## Out of scope\n\n- none\n\n'
  printf '## Budget knobs\n\nmax_iterations=12  wallclock=1\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t76/.goal/goal.md"
bash "$CTL" stamp --project "$T/t76" --auto >/dev/null
# force deadline into the past
sed_in 's/^deadline=.*/deadline=1/' "$T/t76/.goal/state.rec"
bash "$CTL" close-iteration --project "$T/t76" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --no-gate >/dev/null 2>&1
two_pass t76
out=$(bash "$GATE" --check --project "$T/t76" 2>&1); assert_rc "76 expired wallclock green claim -> GO" 0 $?
assert_has "76 NOTE fuse" 'time-budget-exhausted' "$out"
assert_has "76 still GO" 'GATE: GO' "$out"

# 77 expired wallclock + failing claim escalates to BLOCKED (stop grinding)
mkproj t77
{
  printf '# Goal contract - test\n\n## Objective\n\ntest\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | s | check: `false` | expected: exit=0\n'
  printf '\n## Out of scope\n\n- none\n\n'
  printf '## Budget knobs\n\nmax_iterations=12  wallclock=1\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t77/.goal/goal.md"
bash "$CTL" stamp --project "$T/t77" --auto >/dev/null
sed_in 's/^deadline=.*/deadline=1/' "$T/t77/.goal/state.rec"
bash "$CTL" close-iteration --project "$T/t77" --task T1 --files a.txt \
  --checks-pass 0 --checks-fail 1 --checks-unverifiable 0 --progress no \
  --strategy-delta 'try next' --exit-signal yes --no-gate >/dev/null 2>&1
out=$(bash "$GATE" --check --project "$T/t77" 2>&1); assert_rc "77 expired+fail -> BLOCKED rc3" 3 $?
assert_has "77 BLOCKED fuse" 'time-budget-exhausted' "$out"

# ============================================================================
# v2.5 - eval hardening mechanisms ported from the DSH-plugin analysis
# ============================================================================

# 78 metric: regex with one capture group beats last-line, immune to noise+ANSI
mkproj t78
{
  printf '# Goal contract - test\n\n## Objective\n\ntest\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | m | check: `bash noisy.sh` | metric: `score: ([0-9.]+)` | expected: >=40\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t78/.goal/goal.md"
printf '#!/usr/bin/env bash\nprintf "\\033[32mnoise 9\\033[0m score: 42.5 done\\n"\n' > "$T/t78/noisy.sh"
chmod +x "$T/t78/noisy.sh" 2>/dev/null
bash "$CTL" stamp --project "$T/t78" --auto >/dev/null
out=$(bash "$GATE" --verify --project "$T/t78" 2>&1)
assert_has "78 metric regex extracts through ANSI" 'AC-1|PASS|observed=42.5' "$out"
# regex mismatch -> BROKEN (fail-loud, not a silent last-line fallback lie)
sed_in 's/metric: [^|]*| expected/metric: `nosuch=([0-9]+)` | expected/' "$T/t78/.goal/goal.md"
out=$(bash "$GATE" --verify --project "$T/t78" 2>&1)
assert_has "78b regex miss -> BROKEN named" 'regex matched nothing' "$out"

# 79 tolerance: inside noise band the water-mark holds (no false regression)
mkproj t79
{
  printf '# Goal contract - test\n\n## Objective\n\nt\n\nobjective: maximize AC-1\nhorizon-waived: toy single-metric contract - blind spot immaterial\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | perf | check: `cat n.txt` | tolerance: 0.1 | expected: maximize\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t79/.goal/goal.md"
printf '100\n' > "$T/t79/n.txt"
bash "$CTL" stamp --project "$T/t79" --auto >/dev/null
bash "$CTL" close-iteration --project "$T/t79" --task T1 --files n.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --no-gate --score 100 --strategy tune-params >/dev/null 2>&1
two_pass t79
printf '96\n' > "$T/t79/n.txt"   # 4% noise, inside 10% band
bash "$CTL" close-iteration --project "$T/t79" --task T2 --files n.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --no-gate --score 96 --strategy tune-params >/dev/null 2>&1
two_pass t79
out=$(bash "$GATE" --check --project "$T/t79" 2>&1); assert_rc "79 noise-band holds -> GO" 0 $?
# 80 below band -> score-regressed names the tolerance
printf '80\n' > "$T/t79/n.txt"
bash "$CTL" close-iteration --project "$T/t79" --task T3 --files n.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --no-gate --score 80 --strategy rewrite-hot >/dev/null 2>&1
out=$(bash "$GATE" --check --project "$T/t79" 2>&1); assert_rc "80 below band -> rc2" 2 $?
assert_has "80 regressed names tol" 'tol=0.1' "$out"

# 81 judged PASS without artifact/digest binding -> verdict-unbound
mkproj t81
{
  printf '# Goal contract - test\n\n## Objective\n\nt\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | j | check: `true` | expected: judged\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t81/.goal/goal.md"
bash "$CTL" stamp --project "$T/t81" --auto >/dev/null
close_iter t81
bind_v t81 'AC-1|PASS|1|DIGEST|cmd|"looks good to me"'
out=$(bash "$GATE" --check --project "$T/t81" 2>&1); assert_rc "81 unbound PASS -> rc2" 2 $?
assert_has "81 verdict-unbound named" 'verdict-unbound:AC-1' "$out"
# 82 properly bound artifact -> GO
echo judged > "$T/t81/jart.txt"
close_iter t81                      # iter 2 (iter 1 from 81)
S=$(sha256sum "$T/t81/jart.txt" | cut -c1-64)
bind_v t81 "AC-1|PASS|2|DIGEST|cmd|\"ok\" artifact: jart.txt digest: $S"
out=$(bash "$GATE" --check --project "$T/t81" 2>&1); assert_rc "82 bound artifact GO -> rc0" 0 $?
# 82b stale evidence: tree moved (file edited) and the REBIND copies the old
# sha256 line - tree digest matches, artifact hash does not -> unbound
echo changed > "$T/t81/jart.txt"
close_iter t81                      # iter 3, digest follows the edit
bind_v t81 "AC-1|PASS|3|DIGEST|cmd|\"ok\" artifact: jart.txt digest: $S"
out=$(bash "$GATE" --check --project "$T/t81" 2>&1); assert_rc "82b stale artifact hash -> rc2" 2 $?
assert_has "82b mismatch named" 'verdict-unbound' "$out"
# 83 false-complete ratchet: two caught claims, gate auto-counts, third BLOCKS
mkproj t83
{
  printf '# Goal contract - test\n\n## Objective\n\nt\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | f | check: `false` | expected: exit=0\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t83/.goal/goal.md"
bash "$CTL" stamp --project "$T/t83" --auto >/dev/null
out=$(bash "$CTL" close-iteration --project "$T/t83" --task T1 --files a.txt \
  --checks-pass 0 --checks-fail 1 --checks-unverifiable 0 --progress yes \
  --exit-signal yes 2>&1); rc1=$?
assert_has "83 catch1 auto-counted" 'false-complete-counted=1' "$out"
out=$(bash "$CTL" close-iteration --project "$T/t83" --task T2 --files a.txt \
  --checks-pass 0 --checks-fail 1 --checks-unverifiable 0 --progress yes \
  --exit-signal yes 2>&1); rc2=$?
assert_has "83 catch2 auto-counted" 'false-complete-counted=2' "$out"
out=$(bash "$CTL" close-iteration --project "$T/t83" --task T3 --files a.txt \
  --checks-pass 0 --checks-fail 1 --checks-unverifiable 0 --progress yes \
  --exit-signal yes 2>&1); rc3=$?
assert_rc "83 third claim frozen -> rc3" 3 $rc3
# progress=no landings must NOT count as false completes (no claim): recheck
grep -q 'false_completes=2' "$T/t83/.goal/state.rec" && ok "83 state holds count" || no "83 counter not in state"

# 84 advisory notes: tautology suspect + metric-flat (never block)
mkproj t84
{
  printf '# Goal contract - test\n\n## Objective\n\nt\n\nobjective: maximize AC-1\nhorizon-waived: toy single-metric contract - blind spot immaterial\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | m | check: `cat n.txt` | expected: maximize\n'
  printf -- '- AC-2 | t | check: `true` | expected: exit=0\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t84/.goal/goal.md"
printf '10\n' > "$T/t84/n.txt"
bash "$CTL" stamp --project "$T/t84" --auto >/dev/null
close_iter t84 --score 10 --strategy probe-first
printf '10\n' > "$T/t84/n2.txt"; # same digest not needed; just append score rows
printf '2|10|none|probe-first\n3|10|none|probe-first\n' >> "$T/t84/.goal/scores.rec"
close_iter t84 --score 10 --strategy probe-first
out=$(bash "$GATE" --check --project "$T/t84" 2>&1); assert_rc "84 notes never block -> GO" 0 $?
assert_has "84 tautology suspect named" 'tautology-suspect:AC-2' "$out"

# 84b judged artifact path containing spaces must bind whole
mkproj t84b
{
  printf '# Goal contract - test\n\n## Objective\n\nt\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | j | check: `cat "out/my artifact.svg"` | expected: judged\n'
  printf '\n## Approval\n\napproved: PENDING\n'
} > "$T/t84b/.goal/goal.md"
bash "$CTL" stamp --project "$T/t84b" --auto >/dev/null
mkdir -p "$T/t84b/out" && printf '<svg/>' > "$T/t84b/out/my artifact.svg"
close_iter t84b
bind_v t84b "AC-1|PASS|1|DIGEST|cmd|artifact: out/my artifact.svg digest: $(sha256sum "$T/t84b/out/my artifact.svg" | cut -c1-64)"
out=$(bash "$GATE" --check --project "$T/t84b" 2>&1); assert_rc "84b artifact with spaces -> GO" 0 $?

# 85 probe campaign (2026-10-12): duplicate AC id must never silently resolve
mkproj t85
{
  printf '# Goal contract - test\n\n## Objective\n\nt\n\n## Exit policy\n\nexit: threshold\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | foo | check: `false` | expected: exit=0\n'
  printf -- '- AC-1 | foo | check: `true` | expected: exit=0\n'
  printf '\n## Approval\n\napproved: PENDING\n'
} > "$T/t85/.goal/goal.md"
bash "$CTL" stamp --project "$T/t85" --auto >/dev/null
close_iter t85
out=$(bash "$GATE" --check --project "$T/t85" 2>&1); assert_rc "85 duplicate AC id -> rc2" 2 $?
assert_has "85 duplicate named" 'duplicate AC id' "$out"

# 86 --verify with an unknown AC id is a usage error, not an all-clear
mkproj t86
contract t86 '- AC-1 | x | check: `true` | expected: exit=0'
out=$(bash "$GATE" --verify AC-99 --project "$T/t86" 2>&1); assert_rc "86 verify unknown id -> rc4" 4 $?
assert_has "86 unknown id named" 'unknown-ac-id:AC-99' "$out"

# 87 letters in numeric state keys never reach arithmetic
mkproj t87
contract t87 '- AC-1 | x | check: `true` | expected: exit=0'
close_iter t87
sed_in 's/^iteration=.*/iteration=banana/' "$T/t87/.goal/state.rec"
out=$(bash "$GATE" --check --project "$T/t87" 2>&1); assert_rc "87 alpha numeric-key -> rc4" 4 $?
assert_has "87 offending key named" 'unparseable-state:iteration' "$out"

# 88 negative scores: metric capture AND the tolerance band must survive '-'
mkproj t88
{
  printf '# Goal contract - test\n\n## Objective\n\nt\n\nobjective: maximize AC-1\nhorizon-waived: toy single-metric contract - blind spot immaterial\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | m | check: `printf "score=-10\\n"` | metric: `score=(-?[0-9.]+)` | tolerance: 0.1 | expected: maximize\n'
  printf '\n## Approval\n\napproved: PENDING\n'
} > "$T/t88/.goal/goal.md"
bash "$CTL" stamp --project "$T/t88" --auto >/dev/null
out=$(bash "$GATE" --verify --project "$T/t88" 2>&1)
assert_has "88 negative score extracted with sign" 'observed=-10' "$out"
close_iter t88 --score -10 --strategy probe-first
out=$(bash "$GATE" --check --project "$T/t88" 2>&1); assert_rc "88 negative band holds -> GO" 0 $?

# 89 ledger guard: a check that rewrites goal.md mid-run is caught in-run
mkproj t89
{
  printf '# Goal contract - test\n\n## Objective\n\nt\n\n## Exit policy\n\nexit: threshold\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | mutates | check: `echo x >> .goal/verdicts.rec; true` | expected: exit=0\n'
  printf '\n## Approval\n\napproved: PENDING\n'
} > "$T/t89/.goal/goal.md"
# (verdicts.rec is ledger, digest-excluded - the tree guard is blind there;
#  the --check batch ends with the same stamp check --verify got for free)
bash "$CTL" stamp --project "$T/t89" --auto >/dev/null
close_iter t89
out=$(bash "$GATE" --check --project "$T/t89" 2>&1); rc89=$?
[ "$rc89" -ne 0 ] && ok "89 ledger-mutating check never ends GO (rc=$rc89)" || no "89 ledger-mutating check ended GO"
# --verify mode must also refuse a self-rewriting check in-run
printf '# Goal contract - test\n\n## Objective\n\nt\n\n## Exit policy\n\nexit: threshold\n\n## Acceptance criteria\n\n- AC-1 | mutates | check: `sed "s/PENDING/PENX/" .goal/goal.md > .goal/goal.md.mt && mv .goal/goal.md.mt .goal/goal.md` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n' > "$T/t89/.goal/goal.md"
out=$(bash "$GATE" --verify --project "$T/t89" 2>&1); assert_rc "89b verify self-rewrite caught" 2 $?
assert_has "89b ledger mutation named" 'check-mutated-ledger' "$out"

# 90 manual false-complete flag + mechanical ratchet must not double-count
mkproj t90
{
  printf '# Goal contract - test\n\n## Objective\n\nt\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | f | check: `false` | expected: exit=0\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t90/.goal/goal.md"
bash "$CTL" stamp --project "$T/t90" --auto >/dev/null
out=$(bash "$CTL" close-iteration --project "$T/t90" --task T1 --files a.txt \
  --checks-pass 0 --checks-fail 1 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --false-complete yes 2>&1); rc90=$?
assert_has "90 manual flag noted not double-counted" 'false-complete-flag-ignored' "$out"
grep -q '^false_completes=1$' "$T/t90/.goal/state.rec" && ok "90 fc counted exactly 1" || no "90 fc double-counted"

# 91 stamp: objective pointing at a non-metric AC is refused at t=0
mkproj t91
{
  printf '# Goal contract - test\n\n## Objective\n\nt\n\nobjective: maximize AC-1\nhorizon-waived: toy single-metric contract - blind spot immaterial\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | judged obj | check: `true` | expected: judged\n'
  printf '\n## Approval\n\napproved: PENDING\n'
} > "$T/t91/.goal/goal.md"
out=$(bash "$CTL" stamp --project "$T/t91" --auto 2>&1); assert_rc "91 objective-on-judged refused" 2 $?
assert_has "91 stamp refusal names the AC" 'never produce a score' "$out"
# and stamp with NO approved: placeholder line fails loud, not silent
mkproj t92
printf '# c\n## Acceptance criteria\n\n- AC-1 | x | check: `true` | expected: exit=0\n' > "$T/t92/.goal/goal.md"
out=$(bash "$CTL" stamp --project "$T/t92" --auto 2>&1); assert_rc "92 stamp without placeholder rc4" 4 $?
assert_has "92 placeholder refusal named" 'stamp-refused' "$out"

# 93 breaker state-machine arc (probe campaign 2 / S2): CLOSED -> HALF_OPEN ->
# claim at HALF_OPEN without strategy owes R10 -> progress resets -> claim at
# OPEN blocked. Drives ctl+gate as a sequence, not one rule.
mkproj t93
contract t93 "- AC-1 | ok | check: \`test -f a.txt\` | expected: exit=0"
printf 'x' > "$T/t93/a.txt"
close_iter t93 --progress yes --exit-signal no
out=$(bash "$CTL" close-iteration --project "$T/t93" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress no --no-gate 2>&1)
assert_rc "93a no-progress alone refused (R10)" 4 $?
out=$(bash "$CTL" close-iteration --project "$T/t93" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress no \
  --strategy-delta "change tack" --no-gate 2>&1); rc93=$?
[ "$rc93" = 0 ] && grep -q '^breaker=HALF_OPEN$' "$T/t93/.goal/state.rec" \
  && ok "93b no-progress+delta -> HALF_OPEN" || no "93b breaker arc"
# manual block: claim at HALF_OPEN whose strategy_delta is none owes R10
{ printf '## iteration 4\ntask=T1[crew:1]\nfiles_modified=a.txt\nchecks_pass=1\nchecks_fail=0\nchecks_unverifiable=0\nerror_signature=none\nprogress=no\nexit_signal=yes\nfalse_complete=no\ndigest=%s\nscore=none\nstrategy_delta=none\n' \
    "$(bash "$GATE" --digest --project "$T/t93")"; } >> "$T/t93/.goal/loop-log.md"
out=$(bash "$GATE" --check --project "$T/t93" 2>&1); assert_rc "93c HALF_OPEN claim w/o strategy -> rc2" 2 $?
assert_has "93c R10 duty named" 'missing-strategy-delta' "$out"
close_iter t93 --progress yes
out=$(bash "$CTL" close-iteration --project "$T/t93" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes 2>&1)
two_pass t93
assert_rc "93d progress reset + claim GO" 0 $?
grep -q '^breaker=CLOSED$' "$T/t93/.goal/state.rec" && ok "93d breaker back CLOSED" || no "93d breaker stuck"
# OPEN: three consecutive no-progress (limit 2)
for i in 1 2 3; do close_iter t93 --progress no --strategy-delta "try $i"; done
grep -q '^no_progress_streak=3$' "$T/t93/.goal/state.rec" && grep -q '^breaker=OPEN$' "$T/t93/.goal/state.rec" \
  && ok "93e streak 3>2 -> OPEN" || no "93e OPEN arc"
out=$(bash "$CTL" close-iteration --project "$T/t93" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress no \
  --strategy-delta "x" --exit-signal yes 2>&1); rc93=$?
assert_rc "93f claim at OPEN -> rc3" 3 $rc93
assert_has "93f breaker-open named" 'breaker-open' "$out"

# 94 repeated-error grind: two blocks with the same non-none error_signature
# -> BLOCKED (grind detector); none-signatures never trip it.
mkproj t94
contract t94 "- AC-1 | ok | check: \`test -f a.txt\` | expected: exit=0"
printf 'x' > "$T/t94/a.txt"
close_iter t94 --progress yes --error-signature "boom"
out=$(bash "$CTL" close-iteration --project "$T/t94" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --error-signature "boom" --exit-signal yes 2>&1); rc94=$?
assert_rc "94 two same error_signature -> rc3" 3 $rc94
assert_has "94 grind detector named" 'repeated-error' "$out"
close_iter t94 --progress yes --error-signature none
close_iter t94 --progress yes --error-signature none
out=$(bash "$CTL" close-iteration --project "$T/t94" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --error-signature none --exit-signal yes 2>&1)
two_pass t94
assert_rc "94b none signatures never trip" 0 $?

# 95 hint routing beyond bind-seat (probe campaign 2 / S6): score-regressed ->
# restore-best, contract-tampered -> proposal-to-user. NO-GO lines must carry
# actionable routing or the controller stalls on dead pointers.
mkproj t95
{
  printf '# Goal contract - test\n\n## Objective\n\nt\n\nobjective: maximize AC-1\nhorizon-waived: toy single-metric contract - blind spot immaterial\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | v | check: `cat v.txt` | metric: `v=(-?[0-9]+)` | expected: maximize\n'
  printf '\n## Out of scope\n\n- none\n\n## Approval\n\napproved: PENDING\n'
} > "$T/t95/.goal/goal.md"
printf 'v=10\n' > "$T/t95/v.txt"
bash "$CTL" stamp --project "$T/t95" --auto >/dev/null
close_iter t95 --score 10 --strategy tune-params
sed_in 's/^best_score=.*/best_score=99/' "$T/t95/.goal/state.rec"
printf 'v=50\n' > "$T/t95/v.txt"
out=$(bash "$CTL" close-iteration --project "$T/t95" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --score 50 --strategy tune-params --exit-signal yes 2>&1); rc95=$?
assert_rc "95a regression -> rc2" 2 $rc95
assert_has "95a hint restore-best" 'hint=restore-best' "$out"
sed_in 's/- AC-1 | v |/- AC-1 | tampered |/' "$T/t95/.goal/goal.md"
out=$(bash "$GATE" --check --project "$T/t95" 2>&1); assert_rc "95b tampered -> rc2" 2 $?
assert_has "95b hint proposal-to-user" 'hint=proposal-to-user' "$out"

# 96 forge dry-streak round sequence (probe campaign 2 / S1): dry rounds
# accumulate, a premature claim is refused AND counted by the ratchet, an
# exhausted dry streak allows GO.
mkproj t96; FORGE=1 contract t96 "- AC-1 | ok | check: \`test -f a.txt\` | expected: exit=0"
printf 'x' > "$T/t96/a.txt"
# dry_limit defaults to 3; dry_streak increments when --dry yes lands.
close_iter t96 --dry yes          # dry_streak 1
close_iter t96 --dry yes          # dry_streak 2
two_pass t96
out=$(bash "$CTL" close-iteration --project "$T/t96" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --dry yes --exit-signal yes 2>&1); rc96=$?
# lands at dry_streak=3 >= dry_limit=3 -> dry exhausted -> claim allowed
assert_rc "96a claim at dry=limit (3>=3) GO" 0 $rc96
assert_has "96a forge GO line" 'GATE: GO' "$out"
grep -q '^dry_streak=3$' "$T/t96/.goal/state.rec" && ok "96a dry_streak reached limit" || no "96a dry_streak: $(grep dry_streak "$T/t96/.goal/state.rec")"
# reset with a fix round, then claim too early (dry=1 < 3)
close_iter t96 --dry no           # dry_streak 0
close_iter t96 --dry yes          # dry_streak 1
out=$(bash "$CTL" close-iteration --project "$T/t96" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --dry yes --exit-signal yes 2>&1); rc96=$?
assert_rc "96b premature forge claim (dry 2<3) rc2" 2 $rc96
assert_has "96b not-dry named" 'not-dry' "$out"
assert_has "96b counted by ratchet" 'false-complete-counted=1' "$out"

# 97 A8 warn is quiet about a missing scores.rec (probe campaign 2 / D10):
# judged AC present, scores.rec never created -> WARN on stdout, no reader
# error leaking to stderr. (close-iteration always creates the sidecar, so
# the ledger is hand-written without it.)
mkproj t97
contract t97 "- AC-1 | s | check: \`true\` | expected: judged"
printf '## iteration 1\ntask=T1[crew:1]\nprogress=yes\nexit_signal=no\nscore=none\nstrategy_delta=none\n' > "$T/t97/.goal/loop-log.md"
rm -f "$T/t97/.goal/scores.rec"
out=$(bash "$AUDIT" --project "$T/t97" 2>/dev/null)
assert_has "97 A8 warns (stdout)" 'A8 judge-score-unrecorded' "$out"
err=$(bash "$AUDIT" --project "$T/t97" 2>&1 >/dev/null)
printf '%s' "$err" | grep -qE 'No such file|not found' && no "97 stderr leaks reader error" || ok "97 no stderr noise for missing scores.rec"

# 98 heavy-dir prune (v2.6 perf): node_modules/build are invisible to the
# non-git tree digest (same spirit as .gitignore on git), while real sources
# stay visible. Pruning must never let a REAL change slip past the guard.
mkproj t98; contract t98 "- AC-1 | f | check: \`test -f src/a.txt\` | expected: exit=0"
mkdir -p "$T/t98/src" "$T/t98/node_modules" "$T/t98/build"
echo hi > "$T/t98/src/a.txt"; echo lib > "$T/t98/node_modules/p.js"; echo o > "$T/t98/build/out.js"
d1=$(bash "$GATE" --digest --project "$T/t98")
printf lib2 > "$T/t98/node_modules/p.js"; printf o2 > "$T/t98/build/out.js"
d2=$(bash "$GATE" --digest --project "$T/t98")
[ "$d1" = "$d2" ] && ok "98a pruned dir change invisible" || no "98a prune leak (d1=$d1 d2=$d2)"
echo hi2 > "$T/t98/src/a.txt"
d3=$(bash "$GATE" --digest --project "$T/t98")
[ "$d3" != "$d2" ] && ok "98b real source change still detected" || no "98b prune swallowed a real change"
d4=$(bash "$GATE" --digest --project "$T/t98"); [ "$d4" = "$d3" ] && ok "98c digest deterministic" || no "98c nondeterministic"
# 99 .goalignore adds prune names; GOAL_PRUNE overrides the whole set.
mkdir -p "$T/t98/data"; echo dat > "$T/t98/data.csv"; echo x > "$T/t98/data/big.dat"
printf 'data\n' > "$T/t98/.goalignore"
e1=$(bash "$GATE" --digest --project "$T/t98"); echo y > "$T/t98/data/big.dat"
e2=$(bash "$GATE" --digest --project "$T/t98")
[ "$e1" = "$e2" ] && ok "99a .goalignore prunes named dir" || no "99a .goalignore ignored"
rm -f "$T/t98/.goalignore"
f1=$(GOAL_PRUNE="node_modules src build data" bash "$GATE" --digest --project "$T/t98")
f2=$(GOAL_PRUNE="node_modules src build data" bash "$GATE" --digest --project "$T/t98")
[ "$f1" = "$f2" ] && ok "99b GOAL_PRUNE override deterministic" || no "99b override unstable"
printf z > "$T/t98/src/a.txt"
f3=$(GOAL_PRUNE="node_modules src build data" bash "$GATE" --digest --project "$T/t98")
[ "$f3" = "$f2" ] && ok "99c GOAL_PRUNE drops src from watch" || no "99c override not honored"
# 103 status NEXT= mechanical routing (v2.6): close-iteration stores the gate's
# last reason/hint; status turns it into one routing sentence - the controller
# no longer re-parses reason strings from memory.
mkproj t103; contract t103 "- AC-1 | m | check: \`echo 3\` | expected: >=5"
# real close-iteration (runs the gate, --no-gate NOT implied) - gate will NO-GO
bash "$CTL" close-iteration --project "$T/t103" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no >/dev/null 2>&1
out=$(bash "$CTL" status --project "$T/t103" 2>&1)
assert_has "103a status prints NEXT" '^CTL: NEXT ' "$out"
assert_has "103a NEXT names the hint" 'hint=' "$out"
assert_has "103a NEXT is one actionable sentence" '\-> ' "$out"
# after a clean pass the NEXT line reports nothing pending
mkproj t104; contract t104 "- AC-1 | f | check: \`test -f ok.txt\` | expected: exit=0"
echo ok > "$T/t104/ok.txt"
two_pass t104
bash "$CTL" close-iteration --project "$T/t104" --task T1 --files ok.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes >/dev/null 2>&1
out=$(bash "$CTL" status --project "$T/t104" 2>&1)
assert_has "103b clean claim => nothing pending" 'NEXT \(nothing pending' "$out"

# 100 calibration fixtures (v2.6): a judged AC that declares calib: needs
# correct grades on BOTH fixtures (good=PASS bad=FAIL, same iter+digest)
# before its verdict can carry a claim. A seat that cannot reject the known-
# bad case cannot be trusted on the real one.
mkproj t100
echo good > "$T/t100/g.txt"; echo bad > "$T/t100/b.txt"; echo real > "$T/t100/subject.png"
contract t100 "- AC-1 | art quality | check: \`true\` | calib: good=g.txt bad=b.txt | expected: judged"
close_iter t100
S=$(sha256sum "$T/t100/subject.png" | cut -c1-64)
# 100a claim with the real verdict only -> calibration-missing
bind_v t100 "AC-1|PASS|1|DIGEST|cmd|\"looks great\" artifact: subject.png digest: $S"
out=$(bash "$GATE" --check --project "$T/t100" 2>&1); assert_rc "100a calib declared, no grades -> rc2" 2 $?
assert_has "100a reason calibration-missing" 'calibration-missing:AC-1/good' "$out"
assert_has "100a hint routes the controller" 'hint=bind-calib-grades' "$out"
# 100b bad fixture graded PASS (too-lenient seat) -> refused
bind_v t100 "AC-1#good|PASS|1|DIGEST|-|\"clean render\" g.txt"
bind_v t100 "AC-1#bad|PASS|1|DIGEST|-|\"looks fine\" b.txt"
out=$(bash "$GATE" --check --project "$T/t100" 2>&1); assert_rc "100b lenient seat -> rc2" 2 $?
assert_has "100b names the bad fixture" 'calibration-missing:AC-1/bad' "$out"
# 100c correct grades (evidence quotes the fixture it read) -> GO
bind_v t100 "AC-1#bad|FAIL|1|DIGEST|-|\"broken as shipped\" b.txt"
bash "$GATE" --check --project "$T/t100" >/dev/null 2>&1; assert_rc "100c calibrated claim -> GO" 0 $?
# 100e an UNBOUND grade (evidence never names the fixture) is invented -> refused
bind_v t100 "AC-1#good|PASS|1|DIGEST|-|\"it is good\" unrelated.txt"
out=$(bash "$GATE" --check --project "$T/t100" 2>&1); assert_rc "100e unbound grade -> rc2" 2 $?
assert_has "100e reason good side" 'calibration-missing:AC-1/good' "$out"
bind_v t100 "AC-1#good|PASS|1|DIGEST|-|\"clean render\" g.txt"   # rebind correctly for 100d
# 100d stale grades (next iteration, digest move) void them too: the real
# verdict is freshly rebound (iter 2), the calib lines stay bound to iter 1.
echo v2 > "$T/t100/subject.png"; close_iter t100
bind_v t100 "AC-1|PASS|2|DIGEST|cmd|\"v2 still great\" artifact: subject.png digest: $(sha256sum "$T/t100/subject.png" | cut -c1-64)"
out=$(bash "$GATE" --check --project "$T/t100" 2>&1); assert_rc "100d stale grades voided -> rc2" 2 $?
assert_has "100d stale calibration flagged" 'calibration-missing' "$out"

# 101 stamp-time calibration validation (t=0 exposure, no mid-loop surprises)
mkproj t101
echo g > "$T/t101/g.txt"; echo b > "$T/t101/b.txt"
# non-judged + calib -> stamp refused
printf '# Goal contract

## Acceptance criteria

- AC-1 | j | check: `true` | calib: good=g.txt bad=b.txt | expected: >=5

## Approval

approved: PENDING
' > "$T/t101/.goal/goal.md"
out=$(bash "$CTL" stamp --project "$T/t101" --auto 2>&1); assert_rc "101a calib on non-judged AC -> stamp refused" 2 $?
assert_has "101a reason named" 'not judged' "$out"
# missing fixture file -> stamp refused
printf '# Goal contract

## Acceptance criteria

- AC-1 | j | check: `true` | calib: good=g.txt bad=MISSING.txt | expected: judged

## Approval

approved: PENDING
' > "$T/t101/.goal/goal.md"
out=$(bash "$CTL" stamp --project "$T/t101" --auto 2>&1); assert_rc "101b missing bad fixture -> stamp refused" 2 $?
assert_has "101b names the fixture" 'bad fixture' "$out"
# one-sided calib -> stamp refused
printf '# Goal contract

## Acceptance criteria

- AC-1 | j | check: `true` | calib: good=g.txt | expected: judged

## Approval

approved: PENDING
' > "$T/t101/.goal/goal.md"
out=$(bash "$CTL" stamp --project "$T/t101" --auto 2>&1); assert_rc "101c one-sided calib -> stamp refused" 2 $?
assert_has "101c needs both" 'BOTH' "$out"
# same file named twice -> one ruler claiming both directions, refused at stamp
printf '# Goal contract\n\n## Acceptance criteria\n\n- AC-1 | j | check: `true` | calib: good=g.txt bad=g.txt | expected: judged\n\n## Approval\n\napproved: PENDING\n' > "$T/t101/.goal/goal.md"
out=$(bash "$CTL" stamp --project "$T/t101" --auto 2>&1); assert_rc "101d one ruler both ends -> stamp refused" 2 $?
assert_has "101d names the single-ruler problem" 'SAME file' "$out"
# 101e the literal "calib:" inside a backtick check command is command text,
# not a calibration declaration - a deterministic AC that GREPS for it must
# stamp clean, never trip the not-judged refusal (found by self-audit)
mkproj t101e
printf '# Goal contract\n\n## Acceptance criteria\n\n- AC-1 | docs | check: `grep -q "calib:" refs.md` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n' > "$T/t101e/.goal/goal.md"
printf 'calib: good=x bad=y\n' > "$T/t101e/refs.md"
out=$(bash "$CTL" stamp --project "$T/t101e" --auto 2>&1); assert_rc "101e calib literal inside check -> stamps clean" 0 $?
out=$(bash "$GATE" --check --project "$T/t101e" 2>&1)
printf '%s' "$out" | grep -qE 'calibration' && no "101e gate must not invent calibration" || ok "101e gate must not invent calibration"

# 102 gate-side fixture decay: stamp with both fixtures, then the bad one
# disappears mid-loop -> fail-closed BROKEN instrument, never silent exemption
mkproj t102
printf '# Goal contract

## Acceptance criteria

- AC-1 | j | check: `true` | calib: good=g.txt bad=b.txt | expected: judged

## Approval

approved: PENDING
' > "$T/t102/.goal/goal.md"
echo g > "$T/t102/g.txt"; echo b > "$T/t102/b.txt"; echo subj > "$T/t102/subject.png"
bash "$CTL" stamp --project "$T/t102" --auto >/dev/null
rm -f "$T/t102/b.txt"           # fixture decay before the iteration block lands,
close_iter t102                 # so the block digest is current and the check
bind_v t102 "AC-1|PASS|1|DIGEST|cmd|\"ok\" artifact: subject.png digest: $(sha256sum "$T/t102/subject.png" | cut -c1-64)"   # reaches the calibration rule
out=$(bash "$GATE" --check --project "$T/t102" 2>&1); assert_rc "102 dead fixture -> rc2" 2 $?
assert_has "102 reason calibration-broken" 'calibration-broken' "$out"
assert_has "102 hint routes" 'hint=fix-calib-fixture' "$out"

# 99d empty project still digests (rc=0, well-formed) - the xargs-empty path
mkdir -p "$T/t98e"; g1=$(bash "$GATE" --digest --project "$T/t98e"); rc=$?
assert_rc "99d empty project digest rc0" 0 $rc
assert_has "99d empty digest well-formed" '^[0-9a-f]{12}$' "$g1"

# 103b? no - 103 done. 105: ledger task= is normalized/validated at WRITE time
# so R12 never surprises the controller after the fact (caught by self-audit)
mkproj t105; contract t105 "- AC-1 | t | check: \`true\` | expected: exit=0"
bash "$CTL" close-iteration --project "$T/t105" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --no-gate >/dev/null 2>&1
grep -q 'task=T1\[crew:1\]' "$T/t105/.goal/loop-log.md" && ok "105a bare T1 normalizes to crew:1" || no "105a bare T1 normalizes to crew:1"
# free-form junk is refused at write (not silently ledgered for the audit to catch)
out=$(bash "$CTL" close-iteration --project "$T/t105" --task SELF-AUDIT --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --no-gate 2>&1); assert_rc "105b free-form task -> write refused" 4 $?
assert_has "105b names the task schema" 'schema' "$out"
grep -q 'task=SELF-AUDIT' "$T/t105/.goal/loop-log.md" && no "105c junk task must not be ledgered" || ok "105c junk task kept out of ledger"

# 104 goal_loop.sh unattended outer loop: README promises --dry-run rehearses
# without API and the loop trusts ONLY gate rc. Pin the three exits here.
LOOPT="$here/scripts/goal_loop.sh"
# init seeds the template; second init refuses (contract editing = re-approval)
mkproj t104i
out=$(bash "$LOOPT" --init --project "$T/t104i" 2>&1); assert_rc "104a init seeds contract" 0 $?
[ -f "$T/t104i/.goal/goal.md" ] && ok "104a goal.md seeded from template" || no "104a goal.md seeded from template"
out=$(bash "$LOOPT" --init --project "$T/t104i" 2>&1); assert_rc "104a re-init -> rc2" 2 $?
assert_has "104a re-init points at R3" 'R3' "$out"
# dry-run, nothing claimed: gate says NO-GO every round -> fuse trips, rc3
mkproj t104b; contract t104b "- AC-1 | t | check: \`true\` | expected: exit=0"
out=$(bash "$LOOPT" --continue --dry-run --max-iterations=2 --project "$T/t104b" 2>&1)
assert_rc "104b unclaimed -> iterations-exhausted" 3 $?
assert_has "104b loops without API (dry-run plan line)" 'DRY-RUN iter=' "$out"
assert_has "104b fuse reason" 'iterations-exhausted' "$out"
# dry-run with a valid claim on disk: first round's gate check is GO -> deliver
mkproj t104c; contract t104c "- AC-1 | t | check: \`true\` | expected: exit=0"
close_iter t104c
out=$(bash "$LOOPT" --continue --dry-run --max-iterations=5 --project "$T/t104c" 2>&1)
assert_rc "104c claim verified -> DELIVERED" 0 $?
assert_has "104c delivery line" 'DELIVERED iter=1' "$out"
# no-contract continue refuses (rc4) - state error, not an iteration
mkdir -p "$T/t104d"
bash "$LOOPT" --continue --dry-run --project "$T/t104d" >/dev/null 2>&1; assert_rc "104d continue without contract -> rc4" 4 $?

# 106 verdict-conflict (v2.7): two distinct seat verdicts bound to the SAME
# (iter, digest) contradict each other on unchanged tree state (R2) - the
# claim is mechanically refused. A same-verdict rebind is NOT a conflict
# (latest wins by ledger order); clearing a real conflict moves state: the
# old disagreeing pair stays as history on its old binding while the fresh
# agreeing verdict binds the new (iter, digest).
mkproj t106; contract t106 "- AC-1 | j | check: \`true\` | expected: judged"
echo v1 > "$T/t106/x.txt"; S1=$(sha256sum "$T/t106/x.txt" | cut -c1-64)
close_iter t106
bind_v t106 "AC-1|PASS|1|DIGEST|cmd|\"a seat: good work\" artifact: x.txt digest: $S1"
bind_v t106 "AC-1|FAIL|1|DIGEST|cmd|\"other seat: broken\" artifact: x.txt digest: $S1"
out=$(bash "$GATE" --check --project "$T/t106" 2>&1); assert_rc "106a disagreeing same-binding pair -> rc2" 2 $?
assert_has "106a reason verdict-conflict" 'verdict-conflict:AC-1' "$out"
assert_has "106a hint routes rebind" 'hint=rebind-judged' "$out"
# same verdict twice is a rebind, not a conflict: latest wins, no violation
mkproj t106b; contract t106b "- AC-1 | j | check: \`true\` | expected: judged"
echo ok > "$T/t106b/x.txt"; SB=$(sha256sum "$T/t106b/x.txt" | cut -c1-64)
close_iter t106b
bind_v t106b "AC-1|PASS|1|DIGEST|cmd|\"first\" artifact: x.txt digest: $SB"
bind_v t106b "AC-1|PASS|1|DIGEST|cmd|\"confirmed\" artifact: x.txt digest: $SB"
out=$(bash "$GATE" --check --project "$T/t106b" 2>&1); assert_rc "106b identical double-bind is NOT a conflict" 0 $?
# conflict clearing: move state, bind ONE agreeing verdict on the new binding
mkproj t106c; contract t106c "- AC-1 | j | check: \`true\` | expected: judged"
echo v1 > "$T/t106c/x.txt"; SC=$(sha256sum "$T/t106c/x.txt" | cut -c1-64)
close_iter t106c
bind_v t106c "AC-1|PASS|1|DIGEST|cmd|\"a\" artifact: x.txt digest: $SC"
bind_v t106c "AC-1|FAIL|1|DIGEST|cmd|\"b\" artifact: x.txt digest: $SC"
echo v2 > "$T/t106c/x.txt"; SC2=$(sha256sum "$T/t106c/x.txt" | cut -c1-64)
bash "$CTL" close-iteration --project "$T/t106c" --task T2 --files x.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --no-gate >/dev/null 2>&1
two_pass t106c
bind_v t106c "AC-1|PASS|2|DIGEST|cmd|\"resolved by fresh seat\" artifact: x.txt digest: $SC2"
out=$(bash "$GATE" --check --project "$T/t106c" 2>&1); assert_rc "106c conflict cleared by fresh binding on new state" 0 $?

# 107 status STEP line (v2.7): the loop's current step is DERIVED from ledger
# facts so "what do I do next" is answered without recalling the four-step
# loop from memory, at any point (not only after a NO-GO).
mkproj t107; printf '# G\n\n## Acceptance criteria\n\n- AC-1 | t | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n' > "$T/t107/.goal/goal.md"
out=$(bash "$CTL" status --project "$T/t107" 2>&1)
assert_has "107a unstamped => step 1" 'STEP 1-contract' "$out"
bash "$CTL" stamp --project "$T/t107" --auto >/dev/null
out=$(bash "$CTL" status --project "$T/t107" 2>&1)
assert_has "107b stamped, no work => step 2" 'STEP 2-dispatch' "$out"
bash "$CTL" close-iteration --project "$T/t107" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --no-gate >/dev/null 2>&1
out=$(bash "$CTL" status --project "$T/t107" 2>&1)
assert_has "107c work unclaimed => step 3" 'STEP 3-join' "$out"
bash "$CTL" close-iteration --project "$T/t107" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --no-gate >/dev/null 2>&1
out=$(bash "$CTL" status --project "$T/t107" 2>&1)
assert_has "107d claimed => step 4" 'STEP 4-branch' "$out"

# 108 R12 tooth AT THE GATE (v2.7): a claiming block whose task= id violates
# the ledger law is refused by the arbiter itself, not only by ctl's writer
# or the audit. A v1.x bare id still claims, with a NOTE (read compat).
mkproj t108; contract t108 "- AC-1 | t | check: \`true\` | expected: exit=0"
printf '## iteration 1\ntask=SELF-AUDIT\nfiles_modified=a.txt\nchecks_pass=1\nchecks_fail=0\nchecks_unverifiable=0\nerror_signature=none\nprogress=yes\nexit_signal=yes\nfalse_complete=no\ndigest=X\nscore=none\nstrategy_delta=none\n' > "$T/t108/.goal/loop-log.md"
d=$(bash "$GATE" --digest --project "$T/t108")
sed_in "s/^digest=X$/digest=$d/" "$T/t108/.goal/loop-log.md"
out=$(bash "$GATE" --check --project "$T/t108" 2>&1); assert_rc "108a claim with illegal task id -> rc2" 2 $?
assert_has "108a names bad-task" 'bad-task:' "$out"
assert_has "108a hint routes the fix" 'hint=write-ledger-block' "$out"
# v1.x bare id claims (read compat) with an explicit NOTE
mkproj t108b; contract t108b "- AC-1 | t | check: \`true\` | expected: exit=0"
printf '## iteration 1\ntask=T5\nfiles_modified=a.txt\nchecks_pass=1\nchecks_fail=0\nchecks_unverifiable=0\nerror_signature=none\nprogress=yes\nexit_signal=yes\nfalse_complete=no\ndigest=X\nscore=none\nstrategy_delta=none\n' > "$T/t108b/.goal/loop-log.md"
d=$(bash "$GATE" --digest --project "$T/t108b")
sed_in "s/^digest=X$/digest=$d/" "$T/t108b/.goal/loop-log.md"
two_pass t108b
out=$(bash "$GATE" --check --project "$T/t108b" 2>&1); assert_rc "108b bare legacy id still claims" 0 $?
assert_has "108b legacy NOTE emitted" 'task-id-legacy' "$out"

# ---------------------------------------------------------------------------
# v2.8 eval-drive: --strategy attribution + EFFICIENCY (advisory, rc-neutral)
# ---------------------------------------------------------------------------

# helper: stall the ledger without touching gate semantics
stall(){ printf 'no_progress_streak=1\n' >> "$1/.goal/state.rec"; }
# handwritten ledger blocks: $1 proj, $2.. alternating STRAT/TASK per block
hblocks(){ local p="$T/$1/.goal/loop-log.md" n=1; : > "$p"
  shift
  while [ $# -ge 2 ]; do
    printf '## iteration %d\ntask=%s\nfiles_modified=a.txt\nchecks_pass=1\nchecks_fail=0\nchecks_unverifiable=0\nerror_signature=none\nprogress=yes\nexit_signal=no\nfalse_complete=no\ndigest=deadbeefcafe\nscore=none\nstrategy_delta=none\nstrategy=%s\n' "$n" "$1" "$2" >> "$p"; n=$((n+1)); shift 2 || break
  done; }
scorefile(){ local f="$T/$1/.goal/scores.rec"; : > "$f"; shift; local n=1 kv
  for kv in "$@"; do printf '%s|%s|none\n' "$n" "$kv" >> "$f"; n=$((n+1)); done; }

# 109a --strategy writes a strategy= line
mkproj t109a; contract t109a "- AC-1 | t | check: \`true\` | expected: exit=0"
bash "$CTL" close-iteration --project "$T/t109a" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --strategy cache-rework --no-gate >/dev/null 2>&1
assert_has "109a strategy written" 'strategy=cache-rework' "$(cat "$T/t109a/.goal/loop-log.md")"
# 109b omitted => strategy=none
mkproj t109b; contract t109b "- AC-1 | t | check: \`true\` | expected: exit=0"
bash "$CTL" close-iteration --project "$T/t109b" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --no-gate >/dev/null 2>&1
assert_has "109b default strategy none" 'strategy=none' "$(cat "$T/t109b/.goal/loop-log.md")"
# 109c newline+tab fold to single line; gate rc unchanged on a claiming run
mkproj t109c; contract t109c "- AC-1 | t | check: \`true\` | expected: exit=0"
bash "$CTL" close-iteration --project "$T/t109c" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --exit-signal yes \
  --strategy "$(printf 'x\ny\tz')" --no-gate >/dev/null 2>&1
two_pass t109c
assert_has "109c folded to one line" '^strategy=x y z$' "$(cat "$T/t109c/.goal/loop-log.md")"
[ "$(grep -cE '^## iteration' "$T/t109c/.goal/loop-log.md")" = 1 ] \
  && ok "109c no block shred" || no "109c label shredded the block"
out=$(bash "$GATE" --check --project "$T/t109c" 2>&1); assert_rc "109c gate still GO with folded label" 0 $?
# 109d edge whitespace trimmed
mkproj t109d; contract t109d "- AC-1 | t | check: \`true\` | expected: exit=0"
bash "$CTL" close-iteration --project "$T/t109d" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --strategy "  pad  " --no-gate >/dev/null 2>&1
two_pass t109d
assert_has "109d label trimmed" '^strategy=pad$' "$(cat "$T/t109d/.goal/loop-log.md")"
# 109e legacy block without strategy reads fine + attribution-unused (objective)
mkproj t109e; contract t109e "- AC-1 | t | check: \`true\` | expected: maximize"
printf 'objective: maximize AC-1\nhorizon-waived: toy label fixture - blind spot immaterial\n' >> "$T/t109e/.goal/goal.md"
bash "$CTL" stamp --project "$T/t109e" --auto >/dev/null 2>&1
printf '## iteration 1\ntask=T1[crew:1]\nfiles_modified=a.txt\nchecks_pass=1\nchecks_fail=0\nchecks_unverifiable=0\nerror_signature=none\nprogress=yes\nexit_signal=no\nfalse_complete=no\ndigest=deadbeefcafe\nscore=none\nstrategy_delta=none\n' > "$T/t109e/.goal/loop-log.md"
out=$(bash "$CTL" status --project "$T/t109e" 2>&1); assert_rc "109e legacy block status rc0" 0 $?
assert_has "109e attribution-unused fires" 'attribution-unused:' "$out"
# 109f audit stays clean with strategy present
mkproj t109f; contract t109f "- AC-1 | t | check: \`true\` | expected: exit=0"
bash "$CTL" close-iteration --project "$T/t109f" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --strategy probe-first --no-gate >/dev/null 2>&1
two_pass t109f
out=$(bash "$here/scripts/goal_audit.sh" --project "$T/t109f" 2>&1); assert_rc "109f audit clean w/ strategy" 0 $?
assert_has "109f audit says clean" 'AUDIT: clean' "$out"
# 109g R10 unchanged: progress=no still demands --strategy-delta
mkproj t109g; contract t109g "- AC-1 | t | check: \`true\` | expected: exit=0"
bash "$CTL" close-iteration --project "$T/t109g" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress no --strategy label-only --no-gate >/dev/null 2>&1
assert_rc "109g strategy label does not excuse R10" 4 $?

# 110 slope math - deterministic ledgers via handwritten blocks + scores.rec
obj110(){ # $1 proj NAME under $T, optional $2 = tolerance token (inserted BEFORE expected)
  local p="$T/$1" tol=""
  [ -n "${2:-}" ] && tol=" $2 |"
  contract "$1" "- AC-1 | t | check: \`true\` |${tol} expected: maximize"
  printf 'objective: maximize AC-1\nhorizon-waived: toy slope fixture - blind spot immaterial\n' >> "$p/.goal/goal.md"
  bash "$CTL" stamp --project "$p" --auto >/dev/null 2>&1; }
# 110a anchors over none rows: scores 10,none,11 => +0.5 /2 exploit
mkproj t110a; obj110 t110a ""; hblocks t110a T1[crew:1] A T1[crew:1] A T1[crew:1] A; scorefile t110a 10 none 11
out=$(bash "$CTL" status --project "$T/t110a" 2>&1); assert_rc "110a rc0" 0 $?
assert_has "110a slope +0.5 over span 2" 'strategy=A \+0.5 /2 iters -> exploit' "$out"
# 110b window of none scores => unmeasured (needs other numeric data)
mkproj t110b; obj110 t110b ""; hblocks t110b T1[crew:1] A T1[crew:1] A T1[crew:1] B T1[crew:1] B; scorefile t110b none none 5 6
out=$(bash "$CTL" status --project "$T/t110b" 2>&1)
assert_has "110b unmeasured window" 'strategy=A n=0 unmeasured' "$out"
assert_has "110b numeric window still slopes" 'strategy=B \+1.0 /1 iters -> exploit' "$out"
# 110c single numeric point => no divide
mkproj t110c; obj110 t110c ""; hblocks t110c T1[crew:1] A T1[crew:1] A T1[crew:1] A; scorefile t110c none 12 none
out=$(bash "$CTL" status --project "$T/t110c" 2>&1)
assert_has "110c n=1 unmeasured" 'strategy=A n=1 unmeasured' "$out"
# 110d negative scores format (maximize, negative slope => no advisory)
mkproj t110d; obj110 t110d ""; hblocks t110d T1[crew:1] A T1[crew:1] A T1[crew:1] A T1[crew:1] A; scorefile t110d -5 -7 -11 -12.5
out=$(bash "$CTL" status --project "$T/t110d" 2>&1)
assert_has "110d negative slope format" 'strategy=A \-2.5 /3 iters$' "$out"
printf '%s' "$out" | grep -qE '-> exploit|-> prune' && no "110d no advisory on negative maximize" || ok "110d no advisory on negative maximize"
# 110e minimize objective flips exploit
mkproj t110e; contract t110e "- AC-1 | t | check: \`true\` | expected: maximize" NOSTAMP=1; printf 'objective: minimize AC-1\nhorizon-waived: toy slope fixture - blind spot immaterial\n' >> "$T/t110e/.goal/goal.md"; bash "$CTL" stamp --project "$T/t110e" --auto >/dev/null 2>&1
hblocks t110e T1[crew:1] A T1[crew:1] A; scorefile t110e 100 90
out=$(bash "$CTL" status --project "$T/t110e" 2>&1)
assert_has "110e minimize direction exploit" 'strategy=A \-10.0 /1 iters -> exploit' "$out"
# 110f label returns later => two windows (window order = file order)
mkproj t110f; obj110 t110f ""; hblocks t110f T1[crew:1] A T1[crew:1] A T1[crew:1] B T1[crew:1] A T1[crew:1] A; scorefile t110f 1 2 3 4 5
out=$(bash "$CTL" status --project "$T/t110f" 2>&1)
nA=$(printf '%s\n' "$out" | grep -c '^CTL: EFFICIENCY strategy=A')
nB=$(printf '%s\n' "$out" | grep -c '^CTL: EFFICIENCY strategy=B')
[ "$nA" = 2 ] && [ "$nB" = 1 ] && ok "110f two A windows + one B window" || no "110f two A windows + one B window (A=$nA B=$nB)"
i1=$(printf '%s' "$out" | grep -n 'strategy=A' | head -1 | cut -d: -f1)
i2=$(printf '%s' "$out" | grep -n 'strategy=B' | head -1 | cut -d: -f1)
i3=$(printf '%s' "$out" | grep -n 'strategy=A' | tail -1 | cut -d: -f1)
[ -n "$i1" ] && [ -n "$i2" ] && [ -n "$i3" ] && [ "$i1" -lt "$i2" ] && [ "$i2" -lt "$i3" ] \
  && ok "110f window order follows file order" || no "110f window order follows file order"
# 110g flat D>=3 => prune
mkproj t110g; obj110 t110g ""; hblocks t110g T1[crew:1] A T1[crew:1] A T1[crew:1] A T1[crew:1] A; scorefile t110g 12 12 12 12
assert_has "110g flat prune" 'strategy=A \+0.0 /3 iters -> prune \(flat 3 iters\)' "$(bash "$CTL" status --project "$T/t110g" 2>&1)"
# 110h tolerance band: tiny drift within tol => flat prune
mkproj t110h; obj110 t110h "| tolerance: .1"; hblocks t110h T1[crew:1] A T1[crew:1] A T1[crew:1] A T1[crew:1] A; scorefile t110h 12.0 12.05 12.1 12.15
assert_has "110h tol-band flat prune" '-> prune \(flat 3 iters\)' "$(bash "$CTL" status --project "$T/t110h" 2>&1)"
# 110i negative water mark with tight tol => NOT flat (abs band regression)
mkproj t110i; obj110 t110i "| tolerance: .01"; hblocks t110i T1[crew:1] A T1[crew:1] A T1[crew:1] A T1[crew:1] A; scorefile t110i -10.0 -10.1 -10.3 -10.4
out=$(bash "$CTL" status --project "$T/t110i" 2>&1)
assert_has "110i negative slope shown" 'strategy=A \-0.1 /3 iters' "$out"
printf '%s' "$out" | grep -qE '-> prune' && no "110i abs-band keeps tight tol honest" || ok "110i abs-band keeps tight tol honest"
# 111a threshold + unstalled => no EFFICIENCY section at all
mkproj t111a; contract t111a "- AC-1 | t | check: \`true\` | expected: exit=0"
hblocks t111a T1[crew:1] x T1[crew:1] y; scorefile t111a 1 2
printf '%s\n' "$(bash "$CTL" status --project "$T/t111a" 2>&1)" | grep -qE 'EFFICIENCY|eval-gap|promote:|attribution-unused' \
  && no "111a healthy loop prints no efficiency block" || ok "111a healthy loop prints no efficiency block"
# 111b forge dry_streak=1 fires the block
mkproj t111b; FORGE=1 contract t111b "- AC-1 | t | check: \`true\` | expected: exit=0"
printf 'dry_streak=1\n' >> "$T/t111b/.goal/state.rec"
out=$(bash "$CTL" status --project "$T/t111b" 2>&1)
assert_has "111b forge stall fires" 'CTL: EFFICIENCY score-data: none recorded' "$out"
# 111c orphan score row (iter without block) skipped, rc0
mkproj t111c; obj110 t111c ""; hblocks t111c T1[crew:1] A T1[crew:1] A; scorefile t111c 10 none
printf '99|7|none\n' >> "$T/t111c/.goal/scores.rec"
out=$(bash "$CTL" status --project "$T/t111c" 2>&1); assert_rc "111c orphan row rc0" 0 $?
assert_has "111c slope from real blocks only" 'strategy=A n=1 unmeasured' "$out"

# 112 eval-gap: flat objective scores while stalled
mkproj t112a; obj110 t112a ""; hblocks t112a T1[crew:1] f T1[crew:1] f T1[crew:1] f; scorefile t112a 50 50 50; stall "$T/t112a"
out=$(bash "$CTL" status --project "$T/t112a" 2>&1)
assert_has "112a eval-gap fires" 'eval-gap:' "$out"
assert_has "112a names goal-critic" 'goal-critic' "$out"
mkproj t112b; obj110 t112b ""; hblocks t112b T1[crew:1] f T1[crew:1] f; scorefile t112b 50 50; stall "$T/t112b"
printf '%s\n' "$(bash "$CTL" status --project "$T/t112b" 2>&1)" | grep -qE 'eval-gap' && no "112b two points stay silent" || ok "112b two points stay silent"
mkproj t112c; obj110 t112c ""; hblocks t112c T1[crew:1] f T1[crew:1] f T1[crew:1] f; scorefile t112c 50 50 50
printf '%s\n' "$(bash "$CTL" status --project "$T/t112c" 2>&1)" | grep -qE 'eval-gap' && no "112c unstalled stays silent" || ok "112c unstalled stays silent"
mkproj t112d; contract t112d "- AC-1 | t | check: \`true\` | expected: exit=0"
hblocks t112d T1[crew:1] f T1[crew:1] f T1[crew:1] f; scorefile t112d 50 50 50; stall "$T/t112d"
printf '%s\n' "$(bash "$CTL" status --project "$T/t112d" 2>&1)" | grep -qE 'eval-gap' && no "112d no objective stays silent" || ok "112d no objective stays silent"
mkproj t112e; obj110 t112e "| tolerance: .1"; hblocks t112e T1[crew:1] f T1[crew:1] f T1[crew:1] f; scorefile t112e 12.0 12.05 12.1; stall "$T/t112e"
assert_has "112e tol-band flat fires" 'eval-gap:' "$(bash "$CTL" status --project "$T/t112e" 2>&1)"

# 113 promote: same task domain 3 consecutive waves while stalled
mkproj t113a; contract t113a "- AC-1 | t | check: \`true\` | expected: exit=0"
hblocks t113a T1[crew:1] s T1[crew:1] s T1[crew:1] s; stall "$T/t113a"
assert_has "113a promote after 3 waves" 'promote: T1 \(3 consecutive waves\) - consider' "$(bash "$CTL" status --project "$T/t113a" 2>&1)"
# 113b backend/fallback suffixes are transport not identity
mkproj t113b; contract t113b "- AC-1 | t | check: \`true\` | expected: exit=0"
hblocks t113b T1[crew:1] s 'T1[teams:2](fallback:teams-unavailable)' s T1 s; stall "$T/t113b"
assert_has "113b normalized ids count as one domain" 'promote: T1 \(3 consecutive waves\)' "$(bash "$CTL" status --project "$T/t113b" 2>&1)"
mkproj t113c; contract t113c "- AC-1 | t | check: \`true\` | expected: exit=0"
hblocks t113c T1[crew:1] s T2[crew:1] s T1[crew:1] s; stall "$T/t113c"
printf '%s\n' "$(bash "$CTL" status --project "$T/t113c" 2>&1)" | grep -qE 'promote:' && no "113c interleaved stays silent" || ok "113c interleaved stays silent"
mkproj t113d; contract t113d "- AC-1 | t | check: \`true\` | expected: exit=0"
hblocks t113d T1[crew:1] s T1[crew:1] s; stall "$T/t113d"
printf '%s\n' "$(bash "$CTL" status --project "$T/t113d" 2>&1)" | grep -qE 'promote:' && no "113d run of two stays silent" || ok "113d run of two stays silent"
printf '%s\n' "$(bash "$CTL" status --project "$T/t113a" 2>&1 | grep promote)" | grep -qE 'consider' && ok "113e promote wording is consider" || no "113e promote wording is consider"
# (unstalled silence covered by 111a pattern; 113a's sibling t113c is stalled-interleaved)
mkproj t113f; contract t113f "- AC-1 | t | check: \`true\` | expected: exit=0"
hblocks t113f T1[crew:1] s T1[crew:1] s T1[crew:1] s
printf '%s\n' "$(bash "$CTL" status --project "$T/t113f" 2>&1)" | grep -qE 'promote:' && no "113f unstalled promote silent" || ok "113f unstalled promote silent"

# 114 peer-notes: digest-blind evidence (protocol is doc-side; teeth here)
mkproj t114a; contract t114a "- AC-1 | t | check: \`true\` | expected: exit=0"
close_iter t114a
d1=$(bash "$GATE" --digest --project "$T/t114a")
out1=$(bash "$GATE" --check --project "$T/t114a" 2>&1); rc1=$?
mkdir -p "$T/t114a/.goal/evidence/peer-notes"
printf 'iter 1: API boundary shifted vs brief\n' >> "$T/t114a/.goal/evidence/peer-notes/T1.md"
d2=$(bash "$GATE" --digest --project "$T/t114a")
out2=$(bash "$GATE" --check --project "$T/t114a" 2>&1); rc2=$?
assert_rc "114a gate still GO with peer-note present" 0 $?
[ "$d1" = "$d2" ] && ok "114a tree digest blind to peer-notes" || no "114a digest moved by peer-note"
[ "$rc1" = "$rc2" ] && ok "114a rc stable across peer-note" || no "114a rc shifted by peer-note"
# docs teeth
grep -qE 'peer-notes' "$here/references/gate.md" && ok "114c gate.md documents peer-notes" || no "114c gate.md documents peer-notes"
grep -qE 'peer-notes' "$here/references/crew.md" && ok "114c crew.md documents peer-notes" || no "114c crew.md documents peer-notes"
grep -qE 'never WRITE' "$here/references/gate.md" && ok "114c R6 never-WRITE clause intact" || no "114c R6 never-WRITE clause intact"
out=$(bash "$here/tests/docs_consistency.sh" 2>&1); assert_rc "114d docs consistency green" 0 $?
assert_has "114e patterns C3 for section 12" 'CONSISTENT' "$out"

# 115 regressions
# 115a T46 literals survive with the efficiency block compiled in
mkproj h115a >/dev/null; contract h115a "- AC-1 | f | check: \`true\` | expected: exit=0"
printf -- '- [ ] T1 | do the thing\n' > "$T/h115a/.goal/work-plan.md"
close_iter h115a
out=$(bash "$CTL" status --project "$T/h115a" 2>&1); assert_rc "115a status rc0" 0 $?
assert_has "115a iteration line intact" 'CTL: STATUS iter=1/' "$out"
assert_has "115a last block intact" 'CTL: LAST task=T1\[crew:1\]' "$out"
assert_has "115a work-plan NEXT intact" 'CTL: NEXT T1 | do the thing' "$out"
# 115b STEP derivation unchanged
mkproj h115b >/dev/null; contract h115b "- AC-1 | f | check: \`true\` | expected: exit=0"
close_iter h115b
assert_has "115b step line intact" 'STEP 4-branch' "$(bash "$CTL" status --project "$T/h115b" 2>&1)"
# 115c NEXT routing line unchanged under a NO-GO hint
mkproj h115c >/dev/null; contract h115c "- AC-1 | f | check: \`true\` | expected: exit=0"
printf 'last_reason=open-FAIL:AC-1\nlast_hint=fix-AC\n' >> "$T/h115c/.goal/state.rec"
out=$(bash "$CTL" status --project "$T/h115c" 2>&1)
assert_has "115c NEXT routes fix-AC" 'hint=fix-AC' "$out"
assert_has "115c NEXT sentence present" 'dispatch a fixer' "$out"
# 115d fresh stamped objective project with no scores yet
mkproj h115d; obj110 h115d ""
out=$(bash "$CTL" status --project "$T/h115d" 2>&1); assert_rc "115d empty-score status rc0" 0 $?
assert_has "115d score-data none" 'CTL: EFFICIENCY score-data: none recorded' "$out"
# 115e garbage scores.rec rows skipped
mkproj h115e; obj110 h115e ""; hblocks h115e T1[crew:1] A T1[crew:1] A
printf 'x|y|z\n' >> "$T/h115e/.goal/scores.rec"
printf '1|5|none\n2|6|none\n' >> "$T/h115e/.goal/scores.rec"
out=$(bash "$CTL" status --project "$T/h115e" 2>&1); assert_rc "115e garbage row skipped rc0" 0 $?
assert_has "115e slope still computed" 'strategy=A \+1.0 /1 iters -> exploit' "$out"
# 115f legacy v2.7-shaped ledger: zero new lines (golden guard)
mkdir -p "$T/g115f"; bash "$CTL" init --project "$T/g115f" >/dev/null
{ printf '# Goal contract - test\n\n## Objective\n\ntest objective\n\n## Acceptance criteria\n\n- AC-1 | f | check: `true` | expected: exit=0\n\n\n## Out of scope\n\n- nothing\n\n## Approval\n\napproved: PENDING\n'; } > "$T/g115f/.goal/goal.md"
bash "$CTL" stamp --project "$T/g115f" --auto >/dev/null
d=$(bash "$GATE" --digest --project "$T/g115f")
printf '%s\n' "## iteration 1" "task=T1[crew:1]" "files_modified=a.txt" "checks_pass=1" "checks_fail=0" "checks_unverifiable=0" "error_signature=none" "progress=yes" "exit_signal=no" "false_complete=no" "digest=$d" "score=none" "strategy_delta=none" >> "$T/g115f/.goal/loop-log.md"
printf -- '- [ ] T1 | golden task\n' > "$T/g115f/.goal/work-plan.md"
out=$(bash "$CTL" status --project "$T/g115f" 2>&1)
assert_has "115f golden STEP present" 'CTL: STEP 3-join' "$out"
assert_has "115f golden NEXT present" 'NEXT \(nothing pending' "$out"
printf '%s\n' "$out" | grep -qE 'EFFICIENCY|eval-gap|promote:|attribution-unused' \
  && no "115f no v2.8 lines on legacy ledger" || ok "115f no v2.8 lines on legacy ledger"
# 115g all three advisories together, deterministic order (slope lines sorted by window start)
# A window (2 blocks, climbing -> exploit) then B window (4 flat blocks -> prune);
# last 3 numeric scores flat -> eval-gap; same task 6 waves -> promote.
mkproj h115g; obj110 h115g ""; hblocks h115g T1[crew:1] A T1[crew:1] A T1[crew:1] B T1[crew:1] B T1[crew:1] B T1[crew:1] B; scorefile h115g 10 16 10 10 10 10; stall "$T/h115g"
out=$(bash "$CTL" status --project "$T/h115g" 2>&1)
i1=$(printf '%s' "$out" | grep -n 'strategy=A .*> exploit' | head -1 | cut -d: -f1)
i2=$(printf '%s' "$out" | grep -n 'strategy=B .*prune' | head -1 | cut -d: -f1)
i3=$(printf '%s' "$out" | grep -n 'eval-gap' | head -1 | cut -d: -f1)
i4=$(printf '%s' "$out" | grep -n 'promote:' | head -1 | cut -d: -f1)
[ -n "$i1" ] && [ -n "$i2" ] && [ -n "$i3" ] && [ -n "$i4" ] && [ "$i1" -lt "$i2" ] && [ "$i2" -lt "$i3" ] && [ "$i3" -lt "$i4" ] \
  && ok "115g advisory order deterministic" || no "115g advisory order deterministic"
assert_has "115g promote present too" 'promote: T1' "$out"

# 116 horizon hard constraint (v2.9): objective contracts must carry a
# horizon layer (judged AC + calib) or an explicit waiver - Goodhart guard.
# 116a objective without horizon and without waiver -> stamp refused
mkproj t116a
{ printf '# Goal contract - t\n\n## Objective\n\nt\n\nobjective: maximize AC-1\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | s | check: `echo 5` | expected: maximize\n'
  printf '\n## Approval\n\napproved: PENDING\n'; } > "$T/t116a/.goal/goal.md"
out=$(bash "$CTL" stamp --project "$T/t116a" --auto 2>&1); assert_rc "116a horizon-less objective -> rc2" 2 $?
assert_has "116a refusal names horizon" 'no horizon layer' "$out"
# 116b same contract WITH a horizon-waived: line -> stamps
{ printf '# Goal contract - t\n\n## Objective\n\nt\n\nobjective: maximize AC-1\nhorizon-waived: single benchmark, blind spot declared\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | s | check: `echo 5` | expected: maximize\n'
  printf '\n## Approval\n\napproved: PENDING\n'; } > "$T/t116a/.goal/goal.md"
bash "$CTL" stamp --project "$T/t116a" --auto >/dev/null 2>&1; assert_rc "116b waived stamps -> rc0" 0 $?
# 116c objective + one judged AC carrying calib: -> stamps without waiver
mkproj t116b
{ printf '# Goal contract - t\n\n## Objective\n\nt\n\nobjective: maximize AC-1\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | s | check: `echo 5` | expected: maximize\n'
  printf -- '- AC-2 | j | check: `true` | calib: good=g.txt bad=b.txt | expected: judged\n'
  printf '\n## Approval\n\napproved: PENDING\n'; } > "$T/t116b/.goal/goal.md"
printf 'good\n' > "$T/t116b/g.txt"; printf 'bad\n' > "$T/t116b/b.txt"
bash "$CTL" stamp --project "$T/t116b" --auto >/dev/null 2>&1; assert_rc "116c judged+calib horizon stamps" 0 $?
# 116d waiver is part of the frozen surface: patching it away = contract-tampered
close_iter t116a --score 5
sed_in '/^horizon-waived:/d' "$T/t116a/.goal/goal.md"
out=$(bash "$GATE" --check --project "$T/t116a" 2>&1); assert_rc "116d waiver strip -> rc2" 2 $?
assert_has "116d tamper named" 'contract-tampered' "$out"

# 117 external/deferred check surface (v2.9): AC settles against out-of-tree
# sources; rc=75 defers; window: caches so a day-to-settle fact costs one
# query per window, not one per gate exit.
# 117a external PASS -> GO; 117b source revoked -> FAIL. The out-of-tree
# marker lives under .goal/evidence/ (digest-exempt) so flipping it changes
# neither tree nor ledger digest - an external fact must flip without the
# claim going stale for a reason unrelated to the external source.
mkproj t117a
{ printf '# Goal contract - t\n\n## Objective\n\nt\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | biz | check: `true` | external: `test -f .goal/evidence/settled` | window: 3600 | expected: exit=0\n'
  printf '\n## Approval\n\napproved: PENDING\n'; } > "$T/t117a/.goal/goal.md"
bash "$CTL" stamp --project "$T/t117a" --auto >/dev/null
printf 'settled\n' > "$T/t117a/.goal/evidence/settled"
close_iter t117a
out=$(bash "$GATE" --check --project "$T/t117a" 2>&1); assert_rc "117a external PASS -> GO" 0 $?
rm -f "$T/t117a/.goal/evidence/settled" "$T/t117a/.goal/evidence/deferred.rec"
out=$(bash "$GATE" --check --project "$T/t117a" 2>&1); assert_rc "117b external FAIL -> rc2" 2 $?
assert_has "117b external fail named" 'external' "$out"
# 117c rc=75 -> DEFERRED, claim blocked as deferred-pending (not FAIL)
mkproj t117c
{ printf '# Goal contract - t\n\n## Objective\n\nt\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | biz | check: `true` | external: `exit 75` | expected: exit=0\n'
  printf '\n## Approval\n\napproved: PENDING\n'; } > "$T/t117c/.goal/goal.md"
bash "$CTL" stamp --project "$T/t117c" --auto >/dev/null
close_iter t117c
out=$(bash "$GATE" --check --project "$T/t117c" 2>&1); assert_rc "117c rc75 -> deferred rc2" 2 $?
assert_has "117c deferred routing" 'deferred-pending:AC-1' "$out"
assert_has "117c wait hint" 'hint=wait-for-source' "$out"
# 117d window caching: PASS is cached; second --check must NOT rerun the
# external command (counter stays 1 inside the window)
mkproj t117d
# counter lands in .goal/evidence/ - that's the only directory a check may
# write during --check (tree-digest-safe by design, like deferred.rec itself)
{ printf '# Goal contract - t\n\n## Objective\n\nt\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | biz | check: `true` | external: `mkdir -p .goal/evidence; c=$(cat .goal/evidence/calls 2>/dev/null||echo 0); echo $((c+1)) > .goal/evidence/calls; exit 0` | window: 3600 | expected: exit=0\n'
  printf '\n## Approval\n\napproved: PENDING\n'; } > "$T/t117d/.goal/goal.md"
bash "$CTL" stamp --project "$T/t117d" --auto >/dev/null
close_iter t117d                              # check #1: query (calls=1)
bash "$GATE" --check --project "$T/t117d" >/dev/null 2>&1   # inside window: cached
c=$(cat "$T/t117d/.goal/evidence/calls" 2>/dev/null || echo 0)
[ "$c" = 1 ] && ok "117d window cache: one query per window" || no "117d external reran inside window (calls=$c)"
# 117e expired window -> re-query: overwrite the cache with an aged row
# (latest-wins reader takes it; now-1e6 > window, so the gate re-queries)
printf 'AC-1|PASS|1000000|aged\n' > "$T/t117d/.goal/evidence/deferred.rec"
bash "$GATE" --check --project "$T/t117d" >/dev/null 2>&1
c=$(cat "$T/t117d/.goal/evidence/calls" 2>/dev/null || echo 0)
[ "$c" -ge 2 ] && ok "117e expired window re-queries" || no "117e stale cache not refreshed (calls=$c)"
# 117f window: without external: is refused at stamp
mkproj t117f
{ printf '# Goal contract - t\n\n## Objective\n\nt\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | biz | check: `true` | window: 600 | expected: exit=0\n'
  printf '\n## Approval\n\napproved: PENDING\n'; } > "$T/t117f/.goal/goal.md"
out=$(bash "$CTL" stamp --project "$T/t117f" --auto 2>&1); assert_rc "117f window-without-external -> rc2" 2 $?
assert_has "117f refusal names window/external" 'window:.*external|declare both' "$out"
# 117g external DEFERRED row never masks a FAILing in-tree floor
mkproj t117g
{ printf '# Goal contract - t\n\n## Objective\n\nt\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | biz | check: `false` | external: `exit 75` | expected: exit=0\n'
  printf '\n## Approval\n\napproved: PENDING\n'; } > "$T/t117g/.goal/goal.md"
bash "$CTL" stamp --project "$T/t117g" --auto >/dev/null
close_iter t117g
out=$(bash "$GATE" --check --project "$T/t117g" 2>&1); assert_rc "117g floor FAIL beats DEFERRED" 2 $?
printf '%s' "$out" | grep -qE 'deferred-pending' && no "117g DEFERRED masked a FAIL" || ok "117g in-tree FAIL surfaced not masked"

# 118 significance band from data (v2.9): sd: gives the objective its own
# noise floor - regressions inside z*spread are noise, not regressions.
mkproj t118
{ printf '# Goal contract - t\n\n## Objective\n\nt\n\nobjective: maximize AC-1\nhorizon-waived: toy significance fixture\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | perf | check: `cat n.txt` | metric: `^([0-9]+)` | sd: `sd=([0-9.]+)` | expected: maximize\n'
  printf '\n## Approval\n\napproved: PENDING\n'; } > "$T/t118/.goal/goal.md"
printf '100\nsd=2\n' > "$T/t118/n.txt"
bash "$CTL" stamp --project "$T/t118" --auto >/dev/null
bash "$CTL" close-iteration --project "$T/t118" --task T1 --files n.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --no-gate --score 100 --strategy base >/dev/null 2>&1
two_pass t118
# drift 100 -> 95: inside z=2 band (band = 2*2/100 = 4%... 5% drift!) pick
# inside: 100 -> 97 (3% <= 4% band)
printf '97\nsd=2\n' > "$T/t118/n.txt"
bash "$CTL" close-iteration --project "$T/t118" --task T2 --files n.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --no-gate --score 97 --strategy base >/dev/null 2>&1
two_pass t118
out=$(bash "$GATE" --check --project "$T/t118" 2>&1); assert_rc "118a drift inside z-band -> GO" 0 $?
# 118b beyond the band (100 -> 91, 9% > 4% z-band) -> regressed names the band
printf '91\nsd=2\n' > "$T/t118/n.txt"
bash "$CTL" close-iteration --project "$T/t118" --task T3 --files n.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes --no-gate --score 91 --strategy rewrite >/dev/null 2>&1
out=$(bash "$GATE" --check --project "$T/t118" 2>&1); assert_rc "118b drift beyond z-band -> rc2" 2 $?
assert_has "118b band source named" 'band=z2\*spread' "$out"
# 118c declared sd that matches nothing is a broken instrument, not a silent
# band-less compare (fail-loud law of R9). Flip the harness's spread line so
# the declared sd regex no longer sees "sd=" (data drift = instrument rot).
printf '100\nstddev=2\n' > "$T/t118/n.txt"
out=$(bash "$GATE" --verify --project "$T/t118" 2>&1); assert_has "118c silent sd -> BROKEN" 'sd regex matched nothing' "$out"

# 119 attribution writer tooth (v2.9): objective waves MUST carry a strategy
# label or the eval plane cannot attribute slope to anything.
mkproj t119
{ printf '# Goal contract - t\n\n## Objective\n\nt\n\nobjective: maximize AC-1\nhorizon-waived: toy attribution fixture\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | m | check: `cat n.txt` | expected: maximize\n'
  printf '\n## Approval\n\napproved: PENDING\n'; } > "$T/t119/.goal/goal.md"
printf '5\n' > "$T/t119/n.txt"
bash "$CTL" stamp --project "$T/t119" --auto >/dev/null
out=$(bash "$CTL" close-iteration --project "$T/t119" --task T1 --files n.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --no-gate --score 5 2>&1); assert_rc "119a objective unlabeled wave refused" 4 $?
assert_has "119a names the strategy duty" 'missing-strategy-label' "$out"
# 119b labeled wave lands AND records the label in scores.rec (attribution
# data is real by construction - no silent 'none' windows for objective loops)
bash "$CTL" close-iteration --project "$T/t119" --task T1 --files n.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal no --no-gate --score 5 --strategy cache-warm >/dev/null 2>&1
grep -qE '^1\|5\|none\|cache-warm$' "$T/t119/.goal/scores.rec" \
  && ok "119b scores.rec carries the strategy column" || no "119b strategy column missing: $(cat "$T/t119/.goal/scores.rec")"

# 120 legacy 3-field scores.rec rows stay readable by every v2.9 reader
mkproj t120
{ printf '# Goal contract - t\n\n## Objective\n\nt\n\nobjective: maximize AC-1\nhorizon-waived: legacy reader fixture\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | m | check: `cat n.txt` | expected: maximize\n'
  printf '\n## Approval\n\napproved: PENDING\n'; } > "$T/t120/.goal/goal.md"
printf '7\n' > "$T/t120/n.txt"
bash "$CTL" stamp --project "$T/t120" --auto >/dev/null
printf '1|7|none\n2|7|none\n' >> "$T/t120/.goal/scores.rec"
close_iter t120 --score 7 --strategy legacy-note
out=$(bash "$GATE" --check --project "$T/t120" 2>&1); assert_rc "120a legacy rows parse, claim GO" 0 $?
printf '%s' "$(bash "$CTL" status --project "$T/t120" 2>&1)" | grep -qE 'EFFICIENCY|error' \
  && ok "120b status survives mixed-field ledger" || no "120b status crashed on legacy rows"

# 121 deferred honesty: an external-deferred claim is patience, not a lie -
# the false-complete ratchet must not count waits (R18 meets R1).
mkproj t121
{ printf '# Goal contract - t\n\n## Objective\n\nt\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | biz | check: `true` | external: `exit 75` | window: 3600 | expected: exit=0\n'
  printf '\n## Approval\n\napproved: PENDING\n'; } > "$T/t121/.goal/goal.md"
bash "$CTL" stamp --project "$T/t121" --auto >/dev/null
out=$(bash "$CTL" close-iteration --project "$T/t121" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes \
  --exit-signal yes 2>&1); rc121=$?
assert_rc "121a deferred claim -> rc2" 2 $rc121
assert_has "121a waits, not counted" 'deferred-wait-not-counted' "$out"
grep -q '^false_completes=0$' "$T/t121/.goal/state.rec" \
  && ok "121a ratchet stayed at 0" || no "121a deferred was counted: $(grep false_completes "$T/t121/.goal/state.rec")"
# 121b a REAL failing claim still counts (the exemption is scoped to waits)
mkproj t121b
{ printf '# Goal contract - t\n\n## Objective\n\nt\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | f | check: `false` | expected: exit=0\n'
  printf '\n## Approval\n\napproved: PENDING\n'; } > "$T/t121b/.goal/goal.md"
bash "$CTL" stamp --project "$T/t121b" --auto >/dev/null
out=$(bash "$CTL" close-iteration --project "$T/t121b" --task T1 --files a.txt \
  --checks-pass 0 --checks-fail 1 --checks-unverifiable 0 --progress yes \
  --exit-signal yes 2>&1)
assert_has "121b real FAIL still counted" 'false-complete-counted=1' "$out"

# 122 teams runtime health probe (robustness v1)
# 122a health lists members and empty err when healthy
mkproj t122a
bash "$TEAM" init --project "$T/t122a" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122a" --add --name w1 --role backend --prompt 'x' --scope 'src' >/dev/null
mkdir -p "$T/t122a/.goal/team/heartbeat" "$T/t122a/src"
date -u +%Y-%m-%dT%H:%M:%SZ > "$T/t122a/.goal/team/heartbeat/w1.ts"
echo x > "$T/t122a/src/a.txt"
out=$(bash "$TEAM" health --project "$T/t122a" 2>&1); assert_rc "122a health rc0" 0 $?
assert_has "122a health has w1 row" 'w1\|' "$out"
assert_has "122a idle is numeric" 'w1\|[a-z]+\|[0-9]+' "$out"
printf '%s' "$out" | grep -qE 'w1\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|$' \
  && ok "122a healthy has empty err_tag" || no "122a unexpected err_tag: $out"

# 122b stall fires when idle_s exceeds GOAL_STALL_SEC
# (needs open_items>0; age heartbeat + inbox + scope so last_touch stays ancient).
# Raise GOAL_ZERO_WRITE_SEC so zero-write does not steal the tag — both
# classes share "open work + old scope"; zsec selects which fuse speaks.
mkproj t122b
bash "$TEAM" init --project "$T/t122b" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122b" --add --name w1 --role backend --prompt 'x' --scope 'src' >/dev/null
mkdir -p "$T/t122b/.goal/team/heartbeat" "$T/t122b/src"
printf -- '- [ ] T1 | w1 | pending | files: a\n' > "$T/t122b/.goal/work-plan.md"
# ancient heartbeat
printf '2020-01-01T00:00:00Z\n' > "$T/t122b/.goal/team/heartbeat/w1.ts"
echo old > "$T/t122b/src/a.txt"
touch -t 202001010000 "$T/t122b/src/a.txt"
touch -t 202001010000 "$T/t122b/.goal/team/inboxes/w1.jsonl"
out=$(GOAL_STALL_SEC=1 bash "$TEAM" health --project "$T/t122b" 2>&1); assert_rc "122b health rc0" 0 $?
assert_has "122b stall tag" 'stall$' "$out"
printf '%s' "$out" | grep -qE 'w1\|.*\|stall$' && ok "122b stall named" || no "122b stall missing: $out"

# 122c tool-error vocab hits
mkproj t122c
bash "$TEAM" init --project "$T/t122c" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122c" --add --name w1 --role backend --prompt 'x' --scope 'src' >/dev/null
printf '{"from":"w1","text":"Error: command not found","timestamp":"2026-10-14T00:00:00Z","read":true}\n' \
  > "$T/t122c/.goal/team/inboxes/w1.jsonl"
out=$(bash "$TEAM" health --project "$T/t122c" 2>&1)
printf '%s' "$out" | grep -q 'tool-error' && ok "122c tool-error tag" || no "122c tool-error missing: $out"

# 122d tool-error vocab false friend (no hit)
mkproj t122d
bash "$TEAM" init --project "$T/t122d" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122d" --add --name w1 --role backend --prompt 'x' --scope 'src' >/dev/null
printf '{"from":"w1","text":"no errors here, all good","timestamp":"2026-10-14T00:00:00Z","read":true}\n' \
  > "$T/t122d/.goal/team/inboxes/w1.jsonl"
out=$(bash "$TEAM" health --project "$T/t122d" 2>&1)
printf '%s' "$out" | grep -q 'tool-error' && no "122d false friend hit" || ok "122d false friend clean"

# 122e open_items from work-plan
mkproj t122e
bash "$TEAM" init --project "$T/t122e" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122e" --add --name w1 --role backend --prompt 'x' --scope 'src' >/dev/null
printf -- '- [ ] T1 | w1 | first | files: a\n- [x] T2 | w1 | done | files: b\n' > "$T/t122e/.goal/work-plan.md"
out=$(bash "$TEAM" health --project "$T/t122e" 2>&1)
assert_has "122e open_items=1" 'w1\|[^|]*\|[^|]*\|[^|]*\|1\|' "$out"

# 122f send touches heartbeat
mkproj t122f
bash "$TEAM" init --project "$T/t122f" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122f" --add --name w1 --role backend --prompt 'x' >/dev/null
bash "$TEAM" send --project "$T/t122f" --from controller --to w1 --text 'wake' >/dev/null
[ -f "$T/t122f/.goal/team/heartbeat/w1.ts" ] && ok "122f heartbeat written on send" || no "122f heartbeat missing"

# 122g no signal at all → idle_s=0 (last_s=now), never epoch-0 false stall
mkproj t122g
bash "$TEAM" init --project "$T/t122g" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122g" --add --name w1 --role backend --prompt 'x' >/dev/null
# roster --add creates an empty inbox (a real mtime signal) - remove so the
# probe sees NO heartbeat / inbox / scope signal at all
rm -f "$T/t122g/.goal/team/inboxes/w1.jsonl"
printf -- '- [ ] T1 | w1 | pending | files: a\n' > "$T/t122g/.goal/work-plan.md"
out=$(GOAL_STALL_SEC=1 bash "$TEAM" health --project "$T/t122g" 2>&1); assert_rc "122g health rc0" 0 $?
assert_has "122g idle_s=0 when no signal" 'w1\|[^|]*\|0\|' "$out"
printf '%s' "$out" | grep -qE '^[a-z0-9_]+\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|stall$' && no "122g false stall with no signal: $out" || ok "122g no false stall when silent"

# 122h garbage heartbeat ISO must not freeze last_s=0 (giant idle_s / false stall)
mkproj t122h
bash "$TEAM" init --project "$T/t122h" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122h" --add --name w1 --role backend --prompt 'x' >/dev/null
rm -f "$T/t122h/.goal/team/inboxes/w1.jsonl"
mkdir -p "$T/t122h/.goal/team/heartbeat"
printf 'garbage-not-iso\n' > "$T/t122h/.goal/team/heartbeat/w1.ts"
printf -- '- [ ] T1 | w1 | pending | files: a\n' > "$T/t122h/.goal/work-plan.md"
out=$(GOAL_STALL_SEC=1 bash "$TEAM" health --project "$T/t122h" 2>&1); assert_rc "122h health rc0" 0 $?
assert_has "122h idle_s=0 after ISO parse fail" 'w1\|[^|]*\|0\|' "$out"
assert_has "122h last_touch is ISO now, not garbage" 'w1\|[^|]*\|0\|[0-9]{4}-[0-9]{2}-[0-9]{2}T' "$out"
printf '%s' "$out" | grep -qE '^[a-z0-9_]+\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|stall$' && no "122h false stall after parse fail: $out" || ok "122h no false stall after parse fail"

# 122i open_items = exact assignee field (w12 rows must not count for w1)
mkproj t122i
bash "$TEAM" init --project "$T/t122i" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122i" --add --name w1 --role backend --prompt 'x' >/dev/null
bash "$TEAM" roster --project "$T/t122i" --add --name w12 --role backend --prompt 'x' >/dev/null
printf -- '- [ ] T1 | w12 | first | files: a\n- [ ] T2 | w12 | second | files: b\n- [x] T3 | w1 | done | files: c\n' > "$T/t122i/.goal/work-plan.md"
out=$(bash "$TEAM" health --project "$T/t122i" 2>&1)
assert_has "122i w1 open_items=0 (w12 rows are not w1)" 'w1\|[^|]*\|[^|]*\|[^|]*\|0\|' "$out"
assert_has "122i w12 open_items=2" 'w12\|[^|]*\|[^|]*\|[^|]*\|2\|' "$out"

# 122j tree digest ignores .goal/ heartbeat (R6 digest-exempt sidecar)
mkproj t122j
bash "$TEAM" init --project "$T/t122j" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122j" --add --name w1 --role backend --prompt 'x' >/dev/null
mkdir -p "$T/t122j/.goal/team/heartbeat"
date -u +%Y-%m-%dT%H:%M:%SZ > "$T/t122j/.goal/team/heartbeat/w1.ts"
echo x > "$T/t122j/src.txt"
d1=$(bash "$GATE" --digest --project "$T/t122j")
date -u +%Y-%m-%dT%H:%M:%SZ > "$T/t122j/.goal/team/heartbeat/w1.ts"
d2=$(bash "$GATE" --digest --project "$T/t122j")
[ "$d1" = "$d2" ] && ok "122j digest unchanged by heartbeat touch" || no "122j heartbeat moved digest (d1=$d1 d2=$d2)"
echo y >> "$T/t122j/src.txt"
d3=$(bash "$GATE" --digest --project "$T/t122j")
[ "$d3" != "$d2" ] && ok "122j real source change still moves digest" || no "122j digest blind to source change"

# 123 audit recovery-suffix acceptance + invented-token rejection (T123a-c).
# 65a-e pin: re-run:evil on crew (A1), crew+recovery A4, crew+fallback exempt,
# re-run:death on teams, re-run:stall on crew. These pin the remaining
# combinations end-to-end through goal_audit.sh: the BARE recovery token
# (stall-recovered) on teams:, re-run:stall on teams:, and a wholly invented
# tag SHAPE (invented:oops - neither fallback: nor a recovery token).
# 123a bare recovery token on teams: is audit-clean
mkproj t123a
printf '## iteration 1\ntask=T2[teams:2] (stall-recovered)\nfiles_modified=a.txt\nchecks_pass=1\nchecks_fail=0\nchecks_unverifiable=0\nerror_signature=none\nprogress=yes\nexit_signal=no\nfalse_complete=no\ndigest=x\nscore=none\nstrategy_delta=none\n' > "$T/t123a/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t123a" 2>&1); rc=$?
assert_rc "123a recovery suffix clean" 0 $rc
assert_has "123a clean said" 'AUDIT: clean' "$out"
# 123b re-run:stall on teams: is audit-clean (teams x re-run:stall pairing)
mkproj t123b
printf '## iteration 1\ntask=T2[teams:2] (re-run:stall)\nfiles_modified=a.txt\nchecks_pass=1\nchecks_fail=0\nchecks_unverifiable=0\nerror_signature=none\nprogress=yes\nexit_signal=no\nfalse_complete=no\ndigest=x\nscore=none\nstrategy_delta=none\n' > "$T/t123b/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t123b" 2>&1); rc=$?
assert_rc "123b re-run suffix clean" 0 $rc
assert_has "123b clean said" 'AUDIT: clean' "$out"
# 123c invented tag shape must fail: A1 closed grammar catches it today; the
# pattern allows A3 recovery-vocabulary as the backstop if a looser suffix
# pattern ever slips past gp_task_ok (brief step 3: A1 OR A3)
mkproj t123c
printf '## iteration 1\ntask=T2[teams:2] (invented:oops)\nfiles_modified=a.txt\nchecks_pass=1\nchecks_fail=0\nchecks_unverifiable=0\nerror_signature=none\nprogress=yes\nexit_signal=no\nfalse_complete=no\ndigest=x\nscore=none\nstrategy_delta=none\n' > "$T/t123c/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t123c" 2>&1); rc=$?
assert_rc "123c invented suffix fails A1/A3" 1 $rc
assert_has "123c rejected at schema/vocab gate" 'A1 task-schema|A3 recovery-vocabulary' "$out"

# 124 stamp-time AC grammar (SB-1) + contract-defect ratchet exemption (SB-2).
# 124a multi-line AC (expected: on a continuation) is stamp-refused at t=0
mkproj t124a
{
  printf '# Goal contract - test\n\n## Objective\n\nt\n\n'
  printf '## Acceptance criteria\n\n'
  # deliberately wrap the check so expected: is not on the AC line
  printf -- '- AC-1 | wrapped | check: `echo a\n  echo b` | expected: exit=0\n'
  printf '\n## Approval\n\napproved: PENDING\n'
} > "$T/t124a/.goal/goal.md"
out=$(bash "$CTL" stamp --project "$T/t124a" --auto 2>&1); assert_rc "124a multi-line AC stamp refused" 2 $?
assert_has "124a refusal names single-line" 'single-line AC' "$out"
grep -qE '^approved: [0-9a-f]{6,}' "$T/t124a/.goal/goal.md" \
  && no "124a bad contract still got stamped" || ok "124a left unstamped"

# 124b missing expected: on the AC line is stamp-refused
mkproj t124b
{
  printf '# Goal contract - test\n\n## Objective\n\nt\n\n'
  printf '## Acceptance criteria\n\n'
  printf -- '- AC-1 | no exp | check: `true`\n'
  printf '\n## Approval\n\napproved: PENDING\n'
} > "$T/t124b/.goal/goal.md"
out=$(bash "$CTL" stamp --project "$T/t124b" --auto 2>&1); assert_rc "124b missing expected refused" 2 $?
assert_has "124b names expected" 'expected:' "$out"

# 124c contract-malformed claim must NOT advance the false-complete ratchet
mkproj t124c
# stamp a clean contract first, then corrupt the AC after stamp so the gate
# sees contract-malformed on a claimed iteration (the SB-2 path)
contract t124c "- AC-1 | ok | check: \`test -f a.txt\` | expected: exit=0"
printf 'x' > "$T/t124c/a.txt"
# force a malformed claim: remove expected: from the frozen AC (gate will
# also see contract-tampered; craft via a fresh unstamped-like parse path
# instead: close-iteration on a contract that gate reports as contract-malformed)
# Build the exact SB-2 shape: unstamped project cannot close; so use a stamped
# contract whose AC line is still single-line but gate fails a check, then a
# SECOND claim against a contract that gate classifies contract-malformed.
# Easiest pin: call close-iteration --exit-signal yes on a project whose
# goal.md AC lost its expected: token while still carrying approved: (tampers
# to contract-malformed:AC-1 before contract-tampered is checked... gate order
# checks form first). Re-stamp is forbidden; so simulate via direct state.
printf 'y' > "$T/t124c/a.txt"
rm -f "$T/t124c/a.txt"
out=$(bash "$CTL" close-iteration --project "$T/t124c" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes --exit-signal yes 2>&1)
rc124c=$?
# first catch: real FAIL (missing a.txt) IS counted
assert_has "124c real FAIL counted" 'false-complete-counted=1' "$out"
# now break the AC grammar without breaking the stamp hash? hash will move.
# Direct unit: the ratchet branch must special-case contract-malformed
# Re-create the branch condition by making the gate report contract-malformed:
# write an AC without expected: into a NEW unstamped project and claim via
# a synthetic loop-log + close with --no-gate, then invoke the gate path
# through close-iteration by stamping a valid contract and then... 
# Simpler teeth: grep the source for the exemption (mechanical) AND run the
# gate on a malformed contract to confirm reason= contract-malformed
mkproj t124c2
{
  printf '# c\n\n## Acceptance criteria\n\n'
  printf -- '- AC-1 | bad | check: `true` | expected: exit=0\n'
  printf -- '- AC-2 | wrapped | check: `echo x\n  echo y`\n'
  printf '\n## Approval\n\napproved: PENDING\n'
} > "$T/t124c2/.goal/goal.md"
# stamp will refuse AC-2; stamp AC-only-1 by removing AC-2 then break after stamp
printf '# c\n\n## Acceptance criteria\n\n- AC-1 | ok | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n' > "$T/t124c2/.goal/goal.md"
bash "$CTL" stamp --project "$T/t124c2" --auto >/dev/null 2>&1
# inject a malformed AC line after stamp (gate form-check runs before tamper hash)
printf -- '- AC-2 | wrapped | check: `echo x\n  echo y`\n' >> "$T/t124c2/.goal/goal.md"
out=$(bash "$CTL" close-iteration --project "$T/t124c2" --task T1 --files x.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes --exit-signal yes 2>&1)
assert_has "124c2 contract-defect not counted" 'contract-defect-not-counted' "$out"
grep -q '^false_completes=0$' "$T/t124c2/.goal/state.rec" \
  && ok "124c2 ratchet stayed 0 on contract defect" || no "124c2 ratchet moved on contract defect: $(grep false_completes "$T/t124c2/.goal/state.rec")"

# 125 team health taxonomy (SB-10/11 from 2026-10-16 Mira Teams incident).
# 125a provider-fatal (NoRoom / stream max) must not look like a plain death
mkproj t125a
bash "$TEAM" init --project "$T/t125a" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t125a" --add --name w1 --role backend --prompt 'x' --scope 'src' >/dev/null
mkdir -p "$T/t125a/src" "$T/t125a/.goal/team/inboxes"
printf 'idle failed API Error: NoRoom\n' > "$T/t125a/.goal/team/inboxes/w1.jsonl"
out=$(bash "$TEAM" health --project "$T/t125a" 2>&1)
assert_has "125a NoRoom tagged provider-fatal" 'provider-fatal' "$out"
printf '%s' "$out" | grep -q 'w1|.*|provider-fatal' && ok "125a row is provider-fatal" || no "125a wrong tag: $out"

# 125b stream-max duration is provider-fatal too
mkproj t125b
bash "$TEAM" init --project "$T/t125b" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t125b" --add --name w1 --role backend --prompt 'x' --scope 'src' >/dev/null
mkdir -p "$T/t125b/src"
printf 'API Error: Stream max duration exceeded - thinking_delta\n' > "$T/t125b/.goal/team/inboxes/w1.jsonl"
out=$(bash "$TEAM" health --project "$T/t125b" 2>&1)
assert_has "125b stream-max tagged provider-fatal" 'provider-fatal' "$out"

# 125c zero-write: live member (fresh heartbeat) + open work + stale scope
# — the "thinking-only, Write=0" shape from the Mira Teams incident.
mkproj t125c
bash "$TEAM" init --project "$T/t125c" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t125c" --add --name w1 --role backend --prompt 'x' --scope 'src' >/dev/null
mkdir -p "$T/t125c/src" "$T/t125c/.goal/team/heartbeat"
printf -- '- [ ] T1 task | w1 | files=x\n' >> "$T/t125c/.goal/work-plan.md"
# LIVE signal: heartbeat now → idle_s < stall
date -u +%Y-%m-%dT%H:%M:%SZ > "$T/t125c/.goal/team/heartbeat/w1.ts"
# scope never really written (ancient file)
printf 'x' > "$T/t125c/src/old.txt"
touch -t 202001010000 "$T/t125c/src/old.txt"
GOAL_ZERO_WRITE_SEC=1 GOAL_STALL_SEC=300 out=$(bash "$TEAM" health --project "$T/t125c" 2>&1)
assert_has "125c zero-write tagged" 'zero-write' "$out"

# 125d provider-fatal beats stall: dark + NoRoom => provider-fatal not stall
mkproj t125d
bash "$TEAM" init --project "$T/t125d" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t125d" --add --name w1 --role backend --prompt 'x' --scope 'src' >/dev/null
mkdir -p "$T/t125d/src"
printf -- '- [ ] T1 task | w1 | files=x\n' >> "$T/t125d/.goal/work-plan.md"
printf 'API Error: NoRoom\n' > "$T/t125d/.goal/team/inboxes/w1.jsonl"
GOAL_STALL_SEC=1 GOAL_ZERO_WRITE_SEC=1 out=$(bash "$TEAM" health --project "$T/t125d" 2>&1)
assert_has "125d provider-fatal wins" 'provider-fatal' "$out"
printf '%s' "$out" | grep -qE 'w1\|.*\|stall$' && no "125d mis-tagged stall" || ok "125d not stall"

# 125e fallback:provider-fatal is a legal task suffix
mkproj t125e
printf '## iteration 1\ntask=T1[teams:2] (fallback:provider-fatal)\nfiles_modified=a.txt\nchecks_pass=1\nchecks_fail=0\nchecks_unverifiable=0\nerror_signature=none\nprogress=yes\nexit_signal=no\nfalse_complete=no\ndigest=x\nscore=none\nstrategy_delta=none\n' > "$T/t125e/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t125e" 2>&1); rc=$?
assert_rc "125e provider-fatal suffix accepted" 0 $rc
assert_has "125e audit clean" 'AUDIT: clean' "$out"

# ---------------------------------------------------------------------------
# 126 STRATEGY-PICK: attribution must drive the next wave (eval->action)
# Pre-reg: docs/deepen-2026-10-24.md — fail lines: missing pick / NEXT without
# prefer= on replan-or-stop / gate rc-hint drift.
# ---------------------------------------------------------------------------

# 126a A flat (prune) + B rising (exploit) => prefer=B avoid=A
mkproj t126a; obj110 t126a ""
hblocks t126a T1[crew:1] A T1[crew:1] A T1[crew:1] A T1[crew:1] A T1[crew:1] B T1[crew:1] B
scorefile t126a 12 12 12 12 10 20
out=$(bash "$CTL" status --project "$T/t126a" 2>&1); assert_rc "126a rc0" 0 $?
assert_has "126a STRATEGY-PICK prefer=B avoid=A" 'STRATEGY-PICK prefer=B avoid=A' "$out"

# 126b only prune => prefer=none avoid=A
mkproj t126b; obj110 t126b ""
hblocks t126b T1[crew:1] A T1[crew:1] A T1[crew:1] A T1[crew:1] A
scorefile t126b 12 12 12 12
out=$(bash "$CTL" status --project "$T/t126b" 2>&1)
assert_has "126b prune-only pick" 'STRATEGY-PICK prefer=none avoid=A' "$out"

# 126c only exploit => prefer=B avoid=none
mkproj t126c; obj110 t126c ""
hblocks t126c T1[crew:1] B T1[crew:1] B T1[crew:1] B
scorefile t126c 10 20 30
out=$(bash "$CTL" status --project "$T/t126c" 2>&1)
assert_has "126c exploit-only pick" 'STRATEGY-PICK prefer=B avoid=none' "$out"

# 126d replan-or-stop NEXT must carry prefer=
mkproj t126d; obj110 t126d ""
hblocks t126d T1[crew:1] A T1[crew:1] A T1[crew:1] A T1[crew:1] A T1[crew:1] B T1[crew:1] B
scorefile t126d 12 12 12 12 10 20
printf 'last_reason=repeated-error:x\nlast_hint=replan-or-stop\n' >> "$T/t126d/.goal/state.rec"
out=$(bash "$CTL" status --project "$T/t126d" 2>&1)
assert_has "126d NEXT carries pick" 'prefer=B' "$out"
assert_has "126d NEXT hint intact" 'hint=replan-or-stop' "$out"

# 126e write-strategy-delta NEXT must carry prefer=
mkproj t126e; obj110 t126e ""
hblocks t126e T1[crew:1] A T1[crew:1] A T1[crew:1] A T1[crew:1] A T1[crew:1] B T1[crew:1] B
scorefile t126e 12 12 12 12 10 20
printf 'last_reason=missing-strategy-delta\nlast_hint=write-strategy-delta\n' >> "$T/t126e/.goal/state.rec"
out=$(bash "$CTL" status --project "$T/t126e" 2>&1)
assert_has "126e NEXT carries pick" 'prefer=B' "$out"
assert_has "126e NEXT hint intact" 'hint=write-strategy-delta' "$out"

# 126f pick must not move gate authority
mkproj t126f; obj110 t126f ""
hblocks t126f T1[crew:1] A T1[crew:1] A T1[crew:1] A T1[crew:1] A T1[crew:1] B T1[crew:1] B
scorefile t126f 12 12 12 12 10 20
printf 'no_progress_streak=1\n' >> "$T/t126f/.goal/state.rec"
out=$(bash "$CTL" status --project "$T/t126f" 2>&1)
assert_has "126f pick present while stalled" 'STRATEGY-PICK prefer=B avoid=A' "$out"
# gate check on a healthy claim path is independent of pick text
mkproj t126f2; contract t126f2 "- AC-1 | t | check: \`true\` | expected: exit=0"
close_iter t126f2 --strategy demo
d=$(bash "$GATE" --digest --project "$T/t126f2")
sed_in "s/^digest=.*/digest=$d/" "$T/t126f2/.goal/loop-log.md"
out=$(bash "$GATE" --check --project "$T/t126f2" 2>&1); assert_rc "126f2 gate GO untouched by pick work" 0 $?
printf '%s' "$out" | grep -qE 'STRATEGY-PICK|prefer=' && no "126f2 gate must not speak STRATEGY-PICK" || ok "126f2 gate silent on pick"

# 126g no attribution data => no pick line
mkproj t126g; contract t126g "- AC-1 | t | check: \`true\` | expected: exit=0"
hblocks t126g T1[crew:1] x T1[crew:1] y
scorefile t126g 1 2
printf '%s\n' "$(bash "$CTL" status --project "$T/t126g" 2>&1)" | grep -qE 'STRATEGY-PICK' \
  && no "126g threshold without objective prints no pick" || ok "126g threshold without objective prints no pick"

# 126h docs: gradient must say pick supplies the next wave (not gate-adjacent)
grep -qE 'STRATEGY-PICK' "$here/references/packs/gradient.md" \
  && ok "126h gradient documents STRATEGY-PICK" || no "126h gradient documents STRATEGY-PICK"
grep -qE 'STRATEGY-PICK' "$here/references/crew.md" \
  && ok "126h crew briefs cite STRATEGY-PICK" || no "126h crew briefs cite STRATEGY-PICK"
grep -qE 'STRATEGY-PICK' "$here/references/teams.md" \
  && ok "126h teams briefs cite STRATEGY-PICK" || no "126h teams briefs cite STRATEGY-PICK"

# ---------------------------------------------------------------------------
# 127 parse hygiene: missing goal.md is pre-stamp legal, status must stay quiet
# ---------------------------------------------------------------------------
mkproj t127a
# goal.md not written yet (STEP 1-contract). status must rc0 and not spray parse errors.
out=$(bash "$CTL" status --project "$T/t127a" 2>&1); assert_rc "127a status rc0 without goal.md" 0 $?
assert_has "127a STEP says fill contract" 'goal.md not stamped' "$out"
printf '%s' "$out" | grep -qE 'No such file or directory' && no "127a parse sprayed missing-goal.md" || ok "127a parse silent on missing goal.md"
printf '%s' "$out" | grep -qE 'goal_parse.sh:' && no "127a parse path leaked" || ok "127a no goal_parse.sh traceback"

# ---------------------------------------------------------------------------
# 128 wallclock vs human panel wait: deadline burned while review_pending
# must not permanently fuse the run at iter 0. First ledger write rebases it.
# ---------------------------------------------------------------------------
mkproj t128a; contract t128a "- AC-1 | t | check: \`true\` | expected: exit=0" TB=2
# simulate: stamp bound a 2s budget, then a long Teams panel wait expired it
printf 'iteration=0\n' > /dev/null
# force deadline into the past the way a multi-hour panel wait would
sed_in "s/^deadline=.*/deadline=1/" "$T/t128a/.goal/state.rec"
sed_in "s/^time_budget=.*/time_budget=2/" "$T/t128a/.goal/state.rec"
out=$(bash "$CTL" status --project "$T/t128a" 2>&1)
assert_has "128a expired deadline visible" 'time_left=-' "$out"
# first close-iteration at iter 0 rewrites deadline from remaining budget once
out=$(bash "$CTL" close-iteration --project "$T/t128a" --task T1[teams:2] --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --strategy panel-wait \
  --no-gate 2>&1)
dl=$(grep -E '^deadline=' "$T/t128a/.goal/state.rec" | cut -d= -f2)
now=$(date +%s)
[ "$dl" -gt "$now" ] && ok "128a deadline rebased after panel wait" || no "128a deadline still past (dl=$dl now=$now)"
assert_has "128a rebase note" 'deadline-rebased' "$out"
# second close must NOT rebase again (budget is real)
sleep 1
out=$(bash "$CTL" close-iteration --project "$T/t128a" --task T2[teams:2] --files b.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --strategy panel-wait \
  --no-gate 2>&1)
printf '%s' "$out" | grep -qE 'deadline-rebased' && no "128a rebased twice" || ok "128a rebase is one-shot"

# 128b plain crew close must NOT resurrect an intentionally expired deadline
mkproj t128b; contract t128b "- AC-1 | t | check: \`true\` | expected: exit=0" TB=2
sed_in "s/^deadline=.*/deadline=1/" "$T/t128b/.goal/state.rec"
out=$(bash "$CTL" close-iteration --project "$T/t128b" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --strategy plain \
  --no-gate 2>&1)
printf '%s' "$out" | grep -qE 'deadline-rebased' && no "128b crew must not rebase" || ok "128b crew must not rebase"
dl=$(grep -E '^deadline=' "$T/t128b/.goal/state.rec" | cut -d= -f2)
[ "$dl" = "1" ] && ok "128b deadline still 1" || no "128b deadline moved (dl=$dl)"

# ---------------------------------------------------------------------------
# 129 live-run defects (b62e4d06 business retest): pick at n=1, PROVIDER bind,
# bare T under teams roster
# ---------------------------------------------------------------------------
# 129a n=1 labeled score still prints STRATEGY-PICK
mkproj t129a; obj110 t129a ""
hblocks t129a T1[teams:2] rule-tuning
scorefile t129a 100.0
out=$(bash "$CTL" status --project "$T/t129a" 2>&1)
assert_has "129a pick at n=1" 'STRATEGY-PICK prefer=rule-tuning avoid=none' "$out"
assert_has "129a efficiency unmeasured" 'unmeasured' "$out"

# 129b PROVIDER must not latch an unrelated newest team dir
mkproj t129b; contract t129b "- AC-1 | t | check: \`true\` | expected: exit=0"
# plant a decoy roster whose cwd is NOT this project
decoy="$HOME/.claude/teams/t129b-decoy-$$"
mkdir -p "$decoy"
printf '{"name":"t129b-decoy","cwd":"/tmp/not-this-project","members":[]}\n' > "$decoy/config.json"
# plant a matching roster
good="$HOME/.claude/teams/t129b-good-$$"
mkdir -p "$good"
printf '{"name":"t129b-good","cwd":"%s","providerName":"ProvX","model":"m1","members":[]}\n' "$T/t129b" > "$good/config.json"
out=$(bash "$CTL" status --project "$T/t129b" 2>&1)
assert_has "129b binds matching roster" 'team=t129b-good' "$out"
printf '%s' "$out" | grep -qE 't129b-decoy' && no "129b leaked decoy team" || ok "129b decoy ignored"
rm -rf "$decoy" "$good"

# 129c bare T under teams roster is refused (would lie as crew:1)
mkproj t129c; contract t129c "- AC-1 | t | check: \`true\` | expected: exit=0"
mkdir -p "$T/t129c/.goal/team"
printf '{"name":"t129c-team","cwd":"%s"}\n' "$T/t129c" > "$T/t129c/.goal/team/config.json"
out=$(bash "$CTL" close-iteration --project "$T/t129c" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --strategy x --no-gate 2>&1); rc=$?
two_pass t129c
assert_rc "129c bare T refused under teams" 4 $rc
assert_has "129c names teams-missing" 'task-teams-missing' "$out"
# explicit tag is legal
out=$(bash "$CTL" close-iteration --project "$T/t129c" --task T1[teams:2] --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --strategy x --no-gate 2>&1); rc=$?
two_pass t129c
assert_rc "129c explicit teams tag ok" 0 $rc
assert_has "129c ledger has teams tag" 'task=T1\[teams:2\]' "$(cat "$T/t129c/.goal/loop-log.md")"

# ---------------------------------------------------------------------------
# 130 two-pass adversarial receipt (claim needs a second pass bound to digest)
# ---------------------------------------------------------------------------
mkproj t130a; contract t130a "- AC-1 | t | check: \`true\` | expected: exit=0"
close_iter t130a
rm -f "$T/t130a/.goal/evidence/adversarial.rec"
out=$(bash "$GATE" --check --project "$T/t130a" 2>&1); rc=$?
assert_rc "130a claim without adversarial is NO-GO" 2 $rc
assert_has "130a reason adversarial-missing" 'adversarial-missing' "$out"
# write a receipt for the CURRENT digest
d=$(bash "$GATE" --digest --project "$T/t130a")
mkdir -p "$T/t130a/.goal/evidence"
printf '1|%s|clear|no gaming found\n' "$d" > "$T/t130a/.goal/evidence/adversarial.rec"
out=$(bash "$GATE" --check --project "$T/t130a" 2>&1); rc=$?
assert_rc "130a GO with bound adversarial receipt" 0 $rc
assert_has "130a GO line" 'GATE: GO' "$out"

# 130b receipt on a stale digest is void
mkproj t130b; contract t130b "- AC-1 | t | check: \`true\` | expected: exit=0"
close_iter t130b
mkdir -p "$T/t130b/.goal/evidence"
printf '1|deadbeef|clear|stale\n' > "$T/t130b/.goal/evidence/adversarial.rec"
out=$(bash "$GATE" --check --project "$T/t130b" 2>&1); rc=$?
assert_rc "130b stale receipt refuses claim" 2 $rc
assert_has "130b still adversarial-missing" 'adversarial-missing' "$out"

# 130c adversarial finding blocks until cleared
mkproj t130c; contract t130c "- AC-1 | t | check: \`true\` | expected: exit=0"
close_iter t130c
d=$(bash "$GATE" --digest --project "$T/t130c")
printf '1|%s|finding|metric tautology\n' "$d" > "$T/t130c/.goal/evidence/adversarial.rec"
out=$(bash "$GATE" --check --project "$T/t130c" 2>&1); rc=$?
assert_rc "130c finding refuses claim" 2 $rc
assert_has "130c reason adversarial-finding" 'adversarial-finding' "$out"
printf '1|%s|clear|rechecked\n' "$d" > "$T/t130c/.goal/evidence/adversarial.rec"
out=$(bash "$GATE" --check --project "$T/t130c" 2>&1); rc=$?
assert_rc "130c clear receipt GO" 0 $rc

# ---------------------------------------------------------------------------
# 131 dual-encode: check/probe scripts frozen at stamp (metric body mechanical)
# ---------------------------------------------------------------------------
mkproj t131a
cat > "$T/t131a/check.sh" <<'EOS'
#!/usr/bin/env bash
exit 0
EOS
chmod +x "$T/t131a/check.sh"
contract t131a "- AC-1 | t | check: \`bash check.sh\` | expected: exit=0"
# mutate AFTER stamp but BEFORE close so tree digest stays self-consistent -
# this is the silent metric-swap hole (goal.md unchanged, script body swapped)
echo 'exit 0 # swapped body' > "$T/t131a/check.sh"
close_iter t131a
d=$(bash "$GATE" --digest --project "$T/t131a")
printf '1|%s|clear|x\n' "$d" > "$T/t131a/.goal/evidence/adversarial.rec"
mkdir -p "$T/t131a/.goal/evidence/raw"
printf 'GATE: VERIFY AC-1|PASS|exit=0\n' > "$T/t131a/.goal/evidence/raw/1.txt"
out=$(bash "$GATE" --check --project "$T/t131a" 2>&1); rc=$?
assert_rc "131a check-script mutation refuses claim" 2 $rc
assert_has "131a reason check-script-tampered" 'check-script-tampered' "$out"

# 131b no script-backed checks => freeze empty, no false positive
mkproj t131b; contract t131b "- AC-1 | t | check: \`true\` | expected: exit=0"
close_iter t131b
d=$(bash "$GATE" --digest --project "$T/t131b")
printf '1|%s|clear|x\n' "$d" > "$T/t131b/.goal/evidence/adversarial.rec"
out=$(bash "$GATE" --check --project "$T/t131b" 2>&1); rc=$?
assert_rc "131b builtin check still GO" 0 $rc

# ---------------------------------------------------------------------------
# 132 raw sensor output: claim needs evidence/raw/<iter>.txt
# ---------------------------------------------------------------------------
mkproj t132a; contract t132a "- AC-1 | t | check: \`true\` | expected: exit=0"
close_iter t132a
d=$(bash "$GATE" --digest --project "$T/t132a")
printf '1|%s|clear|x\n' "$d" > "$T/t132a/.goal/evidence/adversarial.rec"
# close-iteration auto-writes evidence/raw; remove it to prove the gate tooth
rm -f "$T/t132a/.goal/evidence/raw/1.txt"
out=$(bash "$GATE" --check --project "$T/t132a" 2>&1); rc=$?
assert_rc "132a claim without raw dump is NO-GO" 2 $rc
assert_has "132a reason raw-evidence-missing" 'raw-evidence-missing' "$out"
mkdir -p "$T/t132a/.goal/evidence/raw"
printf 'GATE: VERIFY AC-1|PASS|exit=0\n' > "$T/t132a/.goal/evidence/raw/1.txt"
out=$(bash "$GATE" --check --project "$T/t132a" 2>&1); rc=$?
assert_rc "132a GO with raw dump" 0 $rc
# auto-write path: a fresh close leaves a non-empty raw for its iter
mkproj t132c; contract t132c "- AC-1 | t | check: \`true\` | expected: exit=0"
close_iter t132c
[ -s "$T/t132c/.goal/evidence/raw/1.txt" ] && ok "132c close auto-writes raw" || no "132c close auto-writes raw"
d=$(bash "$GATE" --digest --project "$T/t132c")
printf '1|%s|clear|x\n' "$d" > "$T/t132c/.goal/evidence/adversarial.rec"
out=$(bash "$GATE" --check --project "$T/t132c" 2>&1); assert_rc "132c GO after auto raw + adv" 0 $?

# 132b empty raw file is not evidence
mkproj t132b; contract t132b "- AC-1 | t | check: \`true\` | expected: exit=0"
close_iter t132b
d=$(bash "$GATE" --digest --project "$T/t132b")
printf '1|%s|clear|x\n' "$d" > "$T/t132b/.goal/evidence/adversarial.rec"
mkdir -p "$T/t132b/.goal/evidence/raw"
: > "$T/t132b/.goal/evidence/raw/1.txt"
out=$(bash "$GATE" --check --project "$T/t132b" 2>&1); rc=$?
assert_rc "132b empty raw still NO-GO" 2 $rc
assert_has "132b raw-evidence-missing" 'raw-evidence-missing' "$out"

# ---------------------------------------------------------------------------
# 133 goal-agnostic run defaults: pre-reg seed, cold-start score, zero-bookkeeping
# ---------------------------------------------------------------------------
# 133a stamp seeds .goal/pre-reg.md from assets template (idempotent)
mkproj t133a; contract t133a "- AC-1 | t | check: \`true\` | expected: exit=0"
[ -f "$T/t133a/.goal/pre-reg.md" ] && ok "133a pre-reg seeded at stamp" || no "133a pre-reg missing after stamp"
assert_has "133a has kill lines" 'Kill lines|杀点|iteration=0' "$(cat "$T/t133a/.goal/pre-reg.md" 2>/dev/null)"
assert_has "133a has strategy slot" 'Strategy labels|策略' "$(cat "$T/t133a/.goal/pre-reg.md" 2>/dev/null)"

# 133b objective first close needs --score (cold-start baseline)
mkproj t133b; obj110 t133b ""
out=$(bash "$CTL" close-iteration --project "$T/t133b" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --strategy boot \
  --no-gate 2>&1); rc=$?
assert_rc "133b first close without --score refused" 4 $rc
assert_has "133b names missing-score" 'missing-score' "$out"
out=$(bash "$CTL" close-iteration --project "$T/t133b" --task T1 --files a.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --strategy boot --score 1 \
  --no-gate 2>&1); rc=$?
assert_rc "133b first close with --score ok" 0 $rc

# 133c A9 zero-bookkeeping: work-plan ticked but no iteration blocks
mkproj t133c; contract t133c "- AC-1 | t | check: \`true\` | expected: exit=0"
printf -- '- [x] T1 done | owner=w1 | files=a.txt\n' > "$T/t133c/.goal/work-plan.md"
out=$(bash "$here/scripts/goal_audit.sh" --project "$T/t133c" 2>&1); rc=$?
assert_rc "133c audit fails on ticked-but-unbooked" 1 $rc
assert_has "133c A9 named" 'A9' "$out"

# 133d A9b: iteration=0 past half wallclock -> fail (loop never turned)
mkproj t133d; contract t133d "- AC-1 | t | check: \`true\` | expected: exit=0" TB=100
# deadline = now+100 at stamp; pretend 60s already burned by moving deadline closer
sed_in "s/^deadline=.*/deadline=$(( $(date +%s) + 30 ))/" "$T/t133d/.goal/state.rec"
sed_in "s/^time_budget=.*/time_budget=100/" "$T/t133d/.goal/state.rec"
out=$(bash "$here/scripts/goal_audit.sh" --project "$T/t133d" 2>&1); rc=$?
assert_rc "133d audit fails on zero-bookkeeping under clock" 1 $rc
assert_has "133d A9 clock named" 'A9' "$out"

# 133e status hard-routes close-iteration when books empty but work ticked
mkproj t133e; contract t133e "- AC-1 | t | check: \`true\` | expected: exit=0"
printf -- '- [x] T1 done | owner=w1 | files=a.txt\n' > "$T/t133e/.goal/work-plan.md"
out=$(bash "$CTL" status --project "$T/t133e" 2>&1)
assert_has "133e NEXT forces close-iteration" 'close-iteration' "$out"
printf '%s' "$out" | grep -qE 'NEXT.*claim when ready' && no "133e soft NEXT while unbooked" || ok "133e not soft-claim NEXT"

# 133f healthy close clears A9 (bookkeeping exists)
close_iter t133c --strategy boot --score 1
out=$(bash "$here/scripts/goal_audit.sh" --project "$T/t133c" 2>&1); rc=$?
assert_rc "133f audit clean after close" 0 $rc
