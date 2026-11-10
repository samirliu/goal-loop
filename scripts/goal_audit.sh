#!/usr/bin/env bash
# goal_audit.sh - controller-behavior self-audit (run BEFORE claiming exit).
# The gate judges the artifact; this script judges the CONTROLLER's ledger
# hygiene - the class of bug where the protocol is documented but the
# controller still quietly violated it (silent fallback, shredded
# strategy_delta).
#   A1 every task= line matches the exact schema
#   A2 progress=no must carry a real strategy_delta (R10 mirror)
#   A3 task= suffixes come from closed vocabularies only: fallback:
#      (provider-fatal) plus recovery
#      (stall-recovered|tool-error-fixed|re-run:stall|re-run:tool-error|re-run:death)
#   A6 score= is none or a decimal number
#   A11 worker-fault bookkeeping: every task= suffix is backed by a fault row
#      (.goal/evidence/faults.rec) and every fault row is booked by a ledger
#      block carrying the same suffix - a self-declared recovery and a
#      swallowed worker drop are both violations
# Usage: bash goal_audit.sh --project DIR
# Exit 0 = clean / 1 = violations (printed) / 4 = no ledger.
set -u
export LC_ALL=C.UTF-8

project="."
_goal_audit_args=("$@")
while [ $# -gt 0 ]; do
  case "$1" in
    --project) [ $# -ge 2 ] || { echo "AUDIT: ERROR missing-project-arg" >&2; exit 4; }; project="$2"; shift ;;
    --help|-h) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "AUDIT: ERROR unknown-arg:$1" >&2; exit 4 ;;
  esac
  shift
done
r(){ tr -d '\r'; }
here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=goal_parse.sh
. "$here/goal_parse.sh"       # task grammar + score validator shared (v2.7)
sd="$project/.goal"
if [ -d "$sd" ] && [ "${GOAL_ACCESS_EXEC_PID:-}" != "$$" ]; then
  exec python3 -I "$here/goal_store.py" access-exec "$sd" read "$here/goal_audit.sh" "${_goal_audit_args[@]}"
fi
[ ! -e "$sd/store/pending" ] || { echo 'AUDIT: ERROR recovery-required' >&2; exit 4; }
[ -d "$sd" ] || { echo "AUDIT: ERROR no-goal-dir" >&2; exit 4; }
[ -f "$sd/loop-log.md" ] || { echo "AUDIT: ERROR no-loop-log" >&2; exit 4; }
log=$(r < "$sd/loop-log.md")
fail=0
bad(){ fail=1; echo "AUDIT: VIOLATION $1"; }

# ---- A1 / A3 on task= lines ----------------------------------------------
while IFS= read -r line; do
  case "$line" in
    task=*) ;;
    *) continue ;;
  esac
  t=${line#task=}
  if ! gp_task_ok "$t"; then
    bad "A1 task-schema:$t"; continue
  fi
  # A3: fallback vocabulary, then recovery vocabulary - one independent check
  # per tag class so [crew:] lines cannot skip the recovery allowlist.
  case "$t" in
    *'(fallback:'*)
      suf=$(gp_task_fallback "$t")
      case "$suf" in
        provider-fatal) : ;;
        *) bad "A3 fallback-vocabulary:$suf" ;;
      esac ;;
    *'('*)
      # recovery tags also come from a closed list
      rsuf=$(gp_task_recovery "$t")
      case "$rsuf" in
        '' ) bad "A3 recovery-vocabulary:$t" ;;
        stall-recovered|tool-error-fixed|re-run:stall|re-run:tool-error|re-run:death) : ;;
        *) bad "A3 recovery-vocabulary:$rsuf" ;;
      esac ;;
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

# ---- A8 (WARN only, never blocks): judged score not recorded ---------------
# Divergence guard (R13) needs judge scores. Missing them degrades it to a
# no-op; say so loudly instead of silently losing the tooth.
if grep -qE 'expected: *judged' "$sd/goal.md" 2>/dev/null; then
  # scores.rec may legitimately not exist yet (first rounds) - a missing file
  # means zero judge scores, not a reader error leaking to stderr.
  has_j=0
  [ -f "$sd/scores.rec" ] && has_j=$(r < "$sd/scores.rec" | awk -F'|' '$3 ~ /^-?[0-9]+(\.[0-9]+)?$/ {c++} END{print c+0}')
  [ "${has_j:-0}" -gt 0 ] || echo "AUDIT: WARN A8 judge-score-unrecorded (judged ACs present but no numeric judge= in scores.rec; pass --judge-score to close-iteration - R13 divergence guard is inert)"
fi

# ---- A9 zero-bookkeeping (goal-agnostic loop law) --------------------------
# Work without a close-iteration row is an unbooked wave - the eval plane
# never turns (no scores.rec, no STRATEGY-PICK). Seen live: dispatch for hours
# with iteration=0. Two independent teeth: ticks without books; half-clock.
blocks=$(printf '%s\n' "$log" | grep -cE '^## iteration' 2>/dev/null || echo 0)
case "$blocks" in ''|*[!0-9]*) blocks=0 ;; esac
ticked=0
[ -f "$sd/work-plan.md" ] && ticked=$(grep -cE '^- \[x\]' "$sd/work-plan.md" 2>/dev/null || echo 0)
case "$ticked" in ''|*[!0-9]*) ticked=0 ;; esac
if [ "$blocks" -eq 0 ] && [ "$ticked" -gt 0 ]; then
  bad "A9 unbooked-wave (work-plan has $ticked ticked item(s) but loop-log has no iteration - close-iteration before claiming)"
fi
tb=$(grep -E '^time_budget=' "$sd/state.rec" 2>/dev/null | tail -1 | cut -d= -f2-)
dl=$(grep -E '^deadline=' "$sd/state.rec" 2>/dev/null | tail -1 | cut -d= -f2-)
case "$tb" in ''|*[!0-9]*) tb=0 ;; esac
case "$dl" in ''|*[!0-9]*) dl=0 ;; esac
if [ "$blocks" -eq 0 ] && [ "$tb" -gt 0 ] && [ "$dl" -gt 0 ]; then
  now=$(date +%s)
  if [ "$((dl - now))" -lt "$((tb / 2))" ]; then
    bad "A9 zero-bookkeeping-under-clock (iteration=0 and >50% wallclock spent - close-iteration or degrade-deliver)"
  fi
fi

# ---- A10 false-tick (work-plan [x] without landed files=) -----------------
# A tick is a claim that the wave's files landed. `files=a..b` ranges and
# missing paths cannot be proven on disk - refuse the tick (seen live: a
# worker "completed" ch-001..012 that never existed).
if [ -f "$sd/work-plan.md" ]; then
  while IFS= read -r wp; do
    case "$wp" in
      '- [x]'*|'- [X]'*) ;;
      *) continue ;;
    esac
    fp=$(printf '%s' "$wp" | sed -nE 's/.*files=([^|]*).*/\1/p' | tail -1)
    [ -n "$fp" ] || continue
    for f in $(printf '%s' "$fp" | tr ',' ' '); do
      [ -n "$f" ] || continue
      case "$f" in
        *..*) bad "A10 false-tick:unverifiable-range:$f (write concrete paths; ranges cannot be proven on disk)" ;;
        *)
          # glob ok only if it matches at least one existing path under $project
          set +f
          matched=0
          for m in $f; do
            [ -e "$m" ] || [ -e "$project/$m" ] && matched=1
          done
          set -f
          [ "$matched" = 1 ] || bad "A10 false-tick:missing-file:$f"
          ;;
      esac
    done
  done < "$sd/work-plan.md"
fi

# ---- A11 worker-fault bookkeeping (suffix <-> fault row) -------------------
# The task= suffix is not a free-text badge: ctl derives it from a declared
# fault (class x outcome) and writes the fault row next to the block. This
# check closes both directions - a suffix with no fault row is a self-declared
# recovery, a fault row with no block is a dropped worker that was swallowed.
faultf="$sd/evidence/faults.rec"
lt_pairs=""
while IFS= read -r t; do
  s=$(gp_task_recovery "$t")
  if [ -z "$s" ]; then fb=$(gp_task_fallback "$t"); [ -n "$fb" ] && s="fallback:$fb"; fi
  [ -n "$s" ] || continue
  b=$(printf '%s' "$t" | sed -E 's/ *\([^)]*\)$//')
  lt_pairs="$lt_pairs$b|$s
"
done <<< "$(printf '%s\n' "$log" | grep -E '^task=' | sed -nE 's/^task=//p')"
while IFS='|' read -r b s; do
  [ -n "${s:-}" ] || continue
  if [ -f "$faultf" ] && awk -F'|' -v t="$b" -v s="$s" \
      '$1==t && $3==s {found=1} END{exit !found}' "$faultf"; then :; else
    bad "A11 unbacked-suffix:$b($s) (no fault record backs this suffix - declare it: close-iteration --fault CLASS --fault-outcome OUTCOME)"
  fi
done <<< "$lt_pairs"
if [ -f "$faultf" ]; then
  while IFS='|' read -r ft _fc fs _fn _ftz; do
    [ -n "${ft:-}" ] || continue
    printf '%s\n' "$lt_pairs" | grep -qF -- "$ft|$fs" \
      || bad "A11 unbooked-fault:$ft($fs) (a recorded worker fault never reached a ledger block)"
  done < "$faultf"
fi

if [ "$fail" -eq 0 ]; then
  echo "AUDIT: clean (controller ledger hygiene OK)"; exit 0
fi
echo "AUDIT: FAILED - fix the ledger/report before claiming exit (R12)"; exit 1
