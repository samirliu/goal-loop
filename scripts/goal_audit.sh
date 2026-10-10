#!/usr/bin/env bash
# goal_audit.sh - controller-behavior self-audit (run BEFORE claiming exit).
# The gate judges the artifact; this script judges the CONTROLLER's ledger
# hygiene - the class of bug where the protocol is documented but the
# controller still quietly violated it (silent fallback, TeamDelete mid-run
# cover-up, shredded strategy_delta).
#   A1 every task= line matches the exact schema
#   A2 progress=no must carry a real strategy_delta (R10 mirror)
#   A3 fallback suffixes come from the closed vocabulary only
#   A4 no silent backend downgrade: a crew: wave inside a teams run without
#      a (fallback:...) suffix is a violation
#   A6 score= is none or a decimal number
# Usage: bash goal_audit.sh --project DIR
# Exit 0 = clean / 1 = violations (printed) / 4 = no ledger.
set -u
export LC_ALL=C.UTF-8

project="."
while [ $# -gt 0 ]; do
  case "$1" in
    --project) [ $# -ge 2 ] || { echo "AUDIT: ERROR missing-project-arg" >&2; exit 4; }; project="$2"; shift ;;
    --help|-h) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "AUDIT: ERROR unknown-arg:$1" >&2; exit 4 ;;
  esac
  shift
done
r(){ tr -d '\r'; }
sd="$project/.goal"
[ -d "$sd" ] || { echo "AUDIT: ERROR no-goal-dir" >&2; exit 4; }
[ -f "$sd/loop-log.md" ] || { echo "AUDIT: ERROR no-loop-log" >&2; exit 4; }
log=$(r < "$sd/loop-log.md")
fail=0
bad(){ fail=1; echo "AUDIT: VIOLATION $1"; }

# ---- A1 / A3 / A4 on task= lines ------------------------------------------
teams_seen=0
while IFS= read -r line; do
  case "$line" in
    task=*) ;;
    *) continue ;;
  esac
  t=${line#task=}
  if ! printf '%s' "$t" | grep -qE '^T[0-9]+\[(teams|crew):[0-9]+\]( *\(fallback:[a-z0-9-]+\))?$'; then
    bad "A1 task-schema:$t"; continue
  fi
  case "$t" in
    *'[teams:'*) teams_seen=1 ;;
    *'[crew:'*) teams_seen=$teams_seen ;;
  esac
  case "$t" in
    *'(fallback:'*)
      suf=$(printf '%s' "$t" | sed -nE 's/.*\(fallback:([a-z0-9-]+)\).*/\1/p')
      case "$suf" in
        teams-process-reaped|teams-unavailable) : ;;
        *) bad "A3 fallback-vocabulary:$suf" ;;
      esac ;;
    *'[crew:'*)
      [ "$teams_seen" = 1 ] && bad "A4 silent-downgrade:$t (teams run, crew wave without (fallback:...) suffix)"
      ;;
  esac
done <<< "$log"

# ---- A2 / A6 per iteration block ------------------------------------------
cur_prog=""; cur_sd=""; cur_score=""
flush(){
  [ -n "$cur_prog" ] || return 0
  if [ "$cur_prog" = no ]; then
    case "$cur_sd" in ''|none) bad "A2 progress-no-without-strategy-delta" ;; esac
  fi
  case "$cur_score" in
    none|'') : ;;
    *) printf '%s' "$cur_score" | grep -qE '^-?[0-9]+(\.[0-9]+)?$' || bad "A6 score-format:$cur_score" ;;
  esac
  cur_prog=""; cur_sd=""; cur_score=""
}
while IFS= read -r line; do
  case "$line" in
    '## iteration '*) flush ;;
    progress=*) cur_prog=${line#progress=} ;;
    strategy_delta=*) cur_sd=${line#strategy_delta=} ;;
    score=*) cur_score=${line#score=} ;;
  esac
done <<< "$log"
flush

if [ "$fail" -eq 0 ]; then
  echo "AUDIT: clean (controller ledger hygiene OK)"; exit 0
fi
echo "AUDIT: FAILED - fix the ledger/report before claiming exit (R12)"; exit 1
