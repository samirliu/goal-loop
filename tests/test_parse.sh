#!/usr/bin/env bash
# tests/test_parse.sh - hostile-input unit tests for scripts/goal_parse.sh.
# The rule: every grammar rule in the shared parser gets one good case AND one
# adversarial case for each defect class that ever bit the probe campaigns
# (CRLF, spaces in paths, negatives, backtick decoys, prose expectations,
# version-suffix scores). run_tests.sh stays the integration suite; this file
# is the unit floor for the parsing layer introduced in v2.7.
set -u
export LC_ALL=C.UTF-8

here=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../scripts/goal_parse.sh
. "$here/scripts/goal_parse.sh"

P=$(mktemp -d); trap 'rm -rf "$P"' EXIT
# BSD/GNU portability (v2.9): in-place sed = shared parser's transform+mv.
sed_in(){ gp_sed_inplace "$1" "$2"; }
pass=0; failn=0
ok(){ pass=$((pass+1)); echo "  ok   - $1"; }
no(){ failn=$((failn+1)); echo "  FAIL - $1"; }
t(){ [ "$3" = "$2" ] && ok "$1" || no "$1 (want [$2] got [$3])"; }

echo "== goal_parse.sh unit suite =="

# --- validators -------------------------------------------------------------
for v in 7 7.5 -10 0 -0.25; do
  gp_is_score "$v" && ok "score valid: $v" || no "score valid: $v"
done
for v in 1.2.3 --5 "" -.5 1e3 abc; do
  gp_is_score "$v" && no "score INVALID accepted: $v" || ok "score rejected: $v"
done
gp_is_natural 12 && ok "natural valid: 12" || no "natural valid: 12"
gp_is_natural "" && no "natural INVALID accepted: empty" || ok "natural rejected: empty"
gp_is_natural -3 && no "natural INVALID accepted: -3" || ok "natural rejected: -3"
gp_is_natural 1.5 && no "natural INVALID accepted: 1.5" || ok "natural rejected: 1.5"

# --- classify_expected -------------------------------------------------------
t "classify exit=0"  exit0    "$(gp_classify_expected 'exit=0')"
t "classify empty"   exit0    "$(gp_classify_expected '')"
t "classify judged"  judged   "$(gp_classify_expected 'judged')"
t "classify maximize" maximize "$(gp_classify_expected 'maximize')"
t "classify minimize" minimize "$(gp_classify_expected 'minimize')"
t "classify prose"   judged   "$(gp_classify_expected 'it looks pretty good')"
t "classify >=5"     "metric >= 5" "$(gp_classify_expected '>= 5')"
t "classify exit=2"  "rc 2"   "$(gp_classify_expected 'exit=2')"
t "classify spaces"  judged   "$(gp_classify_expected ' judi \n sed ')"   # still not a token

# --- contract extraction (CRLF + decoys) ------------------------------------
p="$P/ctr"; mkdir -p "$p/.goal"
printf '# G\n\n## Acceptance criteria\n\n- AC-1 | file | check: `test -f a b.txt` | expected: exit=0\n- AC-2 | m | check: `cat out.log` | metric: `score: ([0-9]+)` | probe: `test -x bin/m` | baseline: delta | tolerance: 0.05 | expected: >=60\n- AC-3 | j | check: `grep -q "calib:" doc.md` | expected: judged\n\r\n## Approval\n\napproved: PENDING\n' > "$p/.goal/goal.md"
t "ids" "AC-1 AC-2 AC-3" "$(gp_all_ac_ids "$p" | sort | tr '\n' ' ' | sed -E 's/^ //;s/ $//')"
t "cmd with space"   "test -f a b.txt"  "$(gp_ac_check_cmd "$p" AC-1)"
t "check decoy: AC-3 with literal calib: in command is NOT a calib declaration" "no" "$(gp_ac_calib_declared "$p" AC-3)"
t "metric regex"     "score: ([0-9]+)"  "$(gp_ac_metric_re "$p" AC-2)"
t "probe"            "test -x bin/m"    "$(gp_ac_probe_cmd "$p" AC-2)"
t "baseline"         "delta"            "$(gp_ac_baseline_marker "$p" AC-2)"
t "tolerance"        "0.05"             "$(gp_ac_tolerance "$p" AC-2)"
t "expected numeric" ">=60"             "$(gp_ac_expected "$p" AC-2)"
t "CRLF clean expected" "exit=0"        "$(gp_ac_expected "$p" AC-1 | tr -d '\r\n')"

# --- objective + frozen hash -------------------------------------------------
p2="$P/obj"; mkdir -p "$p2/.goal"
printf '# G\n\nobjective: maximize AC-1\n\n## Acceptance criteria\n\n- AC-1 | m | check: `true` | expected: maximize\n\n## Approval\n\napproved: PENDING\n' > "$p2/.goal/goal.md"
t "objective ac"  "AC-1" "$(gp_objective_ac "$p2")"
t "objective dir" "maximize" "$(gp_objective_dir "$p2")"
sed_in 's/^objective: maximize/objective: minimize/' "$p2/.goal/goal.md"
t "objective dir minimize" "minimize" "$(gp_objective_dir "$p2")"
# body hash must change when objective changes (R3: frozen surface)
h1=$(gp_ac_body_hash "$p2")
printf 'exit: forge\n' >> "$p2/.goal/goal.md"
h2=$(gp_ac_body_hash "$p2")
[ "$h1" != "$h2" ] && ok "body hash moves on exit: line" || no "body hash ignores exit: line"

# --- metric extraction -------------------------------------------------------
t "extract with capture" 42 "$(gp_extract_metric $'noise score: 42 end' 'score: ([0-9]+)')"
t "extract negative"     -10 "$(gp_extract_metric 'delta: -10' 'delta: (-?[0-9]+)')"
t "extract keeps minus through strip" -10 "$(gp_extract_metric "$(printf 'x -10\n')" '(-?[0-9]+)')"
t "extract no match empty" "" "$(gp_extract_metric 'nothing here' 'zz ([0-9]+)')"
t "extract empty regex empty" "" "$(gp_extract_metric 'text' '')"
# ANSI must be strippable end-to-end
ansi=$(printf '\033[32mscore: 7\033[0m\n')
t "ansi strip" 7 "$(gp_extract_metric "$(printf '%s' "$ansi" | gp_strip_ansi)" 'score: ([0-9]+)')"

# --- verdict evidence --------------------------------------------------------
t "artifact simple" "img.png" "$(gp_ev_artifact 'looks good artifact: img.png digest: sha256:abcd1234abcd1234')"
t "artifact with spaces" "out/my artifact v2.png" "$(gp_ev_artifact 'great artifact: out/my artifact v2.png digest: abcd1234abcd1234')"
t "digest hex"   "abcd1234abcd1234" "$(gp_ev_digest 'x artifact: y digest: sha256:abcd1234abcd1234 z')"
t "no artifact"  "" "$(gp_ev_artifact 'no binding at all')"

# --- task ids ----------------------------------------------------------------
gp_task_ok "T1[crew:3]" && ok "task crew ok" || no "task crew ok"
gp_task_ok "T2[teams:1] (fallback:teams-process-reaped)" && ok "task fallback ok" || no "task fallback ok"
gp_task_ok "T1" && no "bare task accepted" || ok "bare task rejected (normalize first)"
gp_task_ok "banana" && no "banana accepted" || ok "banana rejected"
gp_task_ok "T1[crew:3](fallback:evil mode)" && no "space fallback accepted" || ok "fallback with space rejected"
t "fallback token" "teams-unavailable" "$(gp_task_fallback 'T1[crew:1] (fallback:teams-unavailable)')"
t "backend" "teams" "$(gp_task_backend 'T1[teams:2]')"

# recovery suffix grammar (teams runtime robustness)
gp_task_ok "T2[teams:3] (stall-recovered)" && ok "task stall-recovered ok" || no "task stall-recovered ok"
gp_task_ok "T2[teams:2] (tool-error-fixed)" && ok "task tool-error-fixed ok" || no "task tool-error-fixed ok"
gp_task_ok "T2[crew:1] (re-run:stall)" && ok "task re-run:stall ok" || no "task re-run:stall ok"
gp_task_ok "T2[crew:1] (re-run:tool-error)" && ok "task re-run:tool-error ok" || no "task re-run:tool-error ok"
gp_task_ok "T2[crew:1] (re-run:death)" && ok "task re-run:death ok" || no "task re-run:death ok"
gp_task_ok "T2[teams:3] (re-run:evil)" && no "bad re-run token accepted" || ok "bad re-run token rejected"
gp_task_ok "T2[teams:3] (fallback:teams-unavailable)" && ok "fallback still ok" || no "fallback still ok"
[ "$(gp_task_recovery 'T2[teams:3] (stall-recovered)')" = "stall-recovered" ] && ok "recovery extract" || no "recovery extract"
[ "$(gp_task_recovery 'T2[teams:3] (re-run:stall)')" = "re-run:stall" ] && ok "re-run extract" || no "re-run extract"
[ "$(gp_task_recovery 'T2[teams:3]')" = "" ] && ok "recovery empty when none" || no "recovery empty when none"

# --- verdict grammar + latest-wins + conflict -------------------------------
pv="$P/verd"; mkdir -p "$pv/.goal"
# 6-field rows: id|verdict|iter|digest|command|evidence
printf 'AC-1|PASS|1|dig1|cmd|evidence one\nAC-1|FAIL|1|dig1|cmd|retracted\nAC-1|PASS|1|dig1|cmd|final answer\nAC-2|PASS|2|dig2|c|e\n' > "$pv/.goal/verdicts.rec"
# same iter: LATER file row wins (ledger order), not gawk hash order
t "latest wins by file order" "final answer" "$(gp_latest_verdicts "$pv" | gawk -F'|' '$1=="AC-1"{print $5}')"
t "latest keeps higher iter" "dig2" "$(gp_latest_verdicts "$pv" | gawk -F'|' '$1=="AC-2"{print $4}')"
# conflict: two DISTINCT verdicts bound to the same (iter,digest)
t "conflict same binding" yes "$(gp_verdict_conflict "$pv" AC-1 1 dig1)"
t "no conflict across bindings" no "$(gp_verdict_conflict "$pv" AC-1 1 dig2)"
printf 'AC-3|PASS|9|d9|c|e\n' > "$pv/.goal/verdicts.rec"
t "single row no conflict" no "$(gp_verdict_conflict "$pv" AC-3 9 d9)"
t "unknown id no conflict" no "$(gp_verdict_conflict "$pv" AC-8 1 dig1)"
gp_verdict_ok "AC-1|PASS|1|dig|cmd|ev" && ok "verdict 6 fields ok" || no "verdict 6 fields ok"
gp_verdict_ok "AC-1|PASS|1|dig|cmd" && no "5-field verdict accepted" || ok "5-field verdict rejected"
printf 'AC-1|PASS|1|dig1|cmd|ev\r\nAC-1|FAIL|1|dig1|cmd|ev2\r\n' > "$pv/.goal/verdicts.rec"
t "CRLF rows conflict-detected" yes "$(gp_verdict_conflict "$pv" AC-1 1 dig1)"
printf 'AC-1|PASS|1|dig1|cmd|ev\r\nAC-1|PASS|1|dig1|cmd|ev2\r\n' > "$pv/.goal/verdicts.rec"
t "same verdict twice is not a conflict" no "$(gp_verdict_conflict "$pv" AC-1 1 dig1)"

# --- state_get ---------------------------------------------------------------
p3="$P/st"; mkdir -p "$p3/.goal"
printf 'iteration=7\r\nbreaker=OPEN\r\nx=1\n' > "$p3/.goal/state.rec"
t "state crlf"  "7"    "$(gp_state_get "$p3" iteration)"
t "state word"  "OPEN" "$(gp_state_get "$p3" breaker)"
t "state empty key" "" "$(gp_state_get "$p3" nope)"
p4="$P/st4"; mkdir -p "$p4/.goal"; echo x > "$p4/.goal/goal.md"
t "state no file" "" "$(gp_state_get "$p4" iteration)"

echo "== goal_parse unit: pass=$pass fail=$failn =="
[ "$failn" -eq 0 ]
