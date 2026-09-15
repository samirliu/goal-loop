#!/usr/bin/env bash
# goal_loop.sh - OPTIONAL unattended outer loop of goal-loop (opt-in, never
# default). Trusts ONLY the exit code of goal_gate.sh, never any textual claim.
# Usage:
#   bash goal_loop.sh --init [--project DIR]
#   bash goal_loop.sh --continue [--max-iterations=N] [--wallclock=SEC] [--dry-run]
#                     [--check-only] [--resume] [--project DIR]
set -u
export LC_ALL=C.UTF-8

here=$(cd "$(dirname "$0")" && pwd)
claude_bin="${CLAUDE_BIN:-claude}"
template="$here/../assets/goal.contract.md"
project="." mode="" max_iterations=12 wallclock=1800 rate=5 dry=0 resume=0

while [ $# -gt 0 ]; do
  case "$1" in
    --init) mode=init ;;
    --continue) mode=continue ;;
    --check-only) mode=check ;;
    --max-iterations=*) max_iterations="${1#*=}" ;;
    --wallclock=*) wallclock="${1#*=}" ;;
    --dry-run) dry=1 ;;
    --resume) resume=1 ;;
    --project) [ $# -ge 2 ] || { echo "GOAL_LOOP: ERROR missing-project-arg" >&2; exit 4; }; project="$2"; shift ;;
    --help|-h) sed -n '4,8p' "$0"; exit 0 ;;
    *) echo "GOAL_LOOP: ERROR unknown-flag:$1" >&2; exit 4 ;;
  esac
  shift
done

sd="$project/.goal"
gate(){ bash "$here/goal_gate.sh" --check --project "$project"; }

rotate(){                                                 # 10MB, keep 4
  local log="$sd/logs/loop.log" size
  [ -f "$log" ] || return 0
  size=$(wc -c < "$log" | tr -d ' ')
  if [ "${size:-0}" -gt 10485760 ]; then
    local i
    for i in 3 2 1; do [ -f "$log.$i" ] && mv -f "$log.$i" "$log.$((i+1))"; done
    mv -f "$log" "$log.1"
  fi
}

acquire_lock(){
  local lf="$sd/lock" pid age now
  if [ -f "$lf" ]; then
    pid=$(head -1 "$lf" | tr -d '\r'); now=$(date +%s)
    age=$(( now - $(sed -n '2p' "$lf" | tr -d '\r' | tr -d ' ') ))
    if kill -0 "$pid" 2>/dev/null && [ "$age" -lt $((wallclock+120)) ] && [ "$resume" -ne 1 ]; then
      echo "GOAL_LOOP: BLOCKED live-lock pid=$pid age=${age}s (if stale: --resume)" >&2; exit 4
    fi
    echo "GOAL_LOOP: NOTE reclaiming stale/overridden lock pid=$pid age=${age}s" >&2
  fi
  mkdir -p "$sd/logs"; printf '%s\n%s\n' "$$" "$(date +%s)" > "$lf"
}
release_lock(){ rm -f "$sd/lock" 2>/dev/null || true; }
trap release_lock EXIT INT TERM

run_claude(){
  local cmd=("$claude_bin" -p "/goal-loop --continue" --output-format json)
  if command -v timeout >/dev/null 2>&1; then
    timeout "$wallclock" "${cmd[@]}"
  else
    "${cmd[@]}"
  fi
}

case "$mode" in
  init)
    mkdir -p "$sd/logs"
    if [ -f "$sd/goal.md" ]; then
      echo "GOAL_LOOP: already initialized ($sd/goal.md) - editing the contract means re-approval (R3)" >&2; exit 2
    fi
    [ -f "$template" ] || { echo "GOAL_LOOP: ERROR template-missing $template" >&2; exit 4; }
    cp "$template" "$sd/goal.md"
    printf 'iteration=0\nbreaker=CLOSED\nfalse_completes=0\nreplans=0\nno_progress_streak=0\nlast_progress_iteration=0\nmax_iterations=%s\nno_progress_limit=2\nmax_replans=2\nper_check_fail_cap=3\npanel_max=4\ndry_streak=0\ndry_limit=3\ncheck_timeout=120\ntime_budget=0\ndeadline=0\n' "$max_iterations" > "$sd/state.rec"
    : > "$sd/loop-log.md"; : > "$sd/verdicts.rec"; : > "$sd/work-plan.md"
    echo "GOAL_LOOP: INIT ok - fill $sd/goal.md, get user approval, then --continue"
    exit 0 ;;
  check)
    gate; exit $? ;;
  continue)
    [ -f "$sd/goal.md" ] || { echo "GOAL_LOOP: ERROR no-contract (run --init first)" >&2; exit 4; }
    acquire_lock
    i=0
    while [ "$i" -lt "$max_iterations" ]; do
      i=$((i+1))
      if [ "$dry" -eq 1 ]; then
        echo "GOAL_LOOP: DRY-RUN iter=$i plan: $claude_bin -p /goal-loop --continue --output-format json (wallclock=${wallclock}s)"
      else
        mkdir -p "$sd/logs"
        echo "==== iter $i $(date '+%F %T') ====" >> "$sd/logs/loop.log"
        run_claude >> "$sd/logs/loop.log" 2>&1
        rotate
      fi
      gate; rc=$?
      case "$rc" in
        0) echo "GOAL_LOOP: DELIVERED iter=$i"; exit 0 ;;
        3) echo "GOAL_LOOP: BLOCKED iter=$i (breaker/false-complete)"; exit 3 ;;
        4) echo "GOAL_LOOP: ERROR state (iter=$i)" >&2; exit 4 ;;
        *) echo "GOAL_LOOP: no-go iter=$i (reason above); next round" ;;
      esac
      [ "$dry" -eq 1 ] || sleep "$rate"
    done
    echo "GOAL_LOOP: BLOCKED iterations-exhausted after $max_iterations" >&2
    exit 3 ;;
  *)
    sed -n '4,8p' "$0" >&2; exit 4 ;;
esac
