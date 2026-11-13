#!/usr/bin/env bash
# goal_loop.sh - developer-only external harness runner, explicitly opt-in.
# Never installed or invoked by the skill. Trusts ONLY goal_gate.sh exit codes.
# Usage:
#   bash goal_loop.sh --init [--project DIR]
#   bash goal_loop.sh --continue [--max-iterations=N] [--wallclock=SEC] [--dry-run]
#                     [--check-only] [--resume] [--project DIR]
set -u
export LC_ALL=C.UTF-8
started_at=${GOAL_RUNNER_STARTED_AT:-$(date +%s)}

here=$(cd "$(dirname "$0")/../scripts" && pwd)
self=$(cd "$(dirname "$0")" && pwd)/goal_loop.sh
claude_bin="${CLAUDE_BIN:-claude}"
template="$here/../assets/goal.contract.md"
project="." mode="" max_iterations=12 wallclock=1800 rate=5 dry=0
_goal_loop_args=("$@")
lock_owned=0

while [ $# -gt 0 ]; do
  case "$1" in
    --init) mode="init" ;;
    --continue) mode="continue" ;;
    --check-only) mode="check" ;;
    --max-iterations=*) max_iterations="${1#*=}" ;;
    --wallclock=*) wallclock="${1#*=}" ;;
    --dry-run) dry=1 ;;
    # Accepted for CLI parity: --continue already resumes the persisted budget.
    --resume) ;;
    --project) [ $# -ge 2 ] || { echo "GOAL_LOOP: ERROR missing-project-arg" >&2; exit 4; }; project="$2"; shift ;;
    --help|-h) sed -n '4,8p' "$0"; exit 0 ;;
    *) echo "GOAL_LOOP: ERROR unknown-flag:$1" >&2; exit 4 ;;
  esac
  shift
done

sd="$project/.goal"
gate(){ bash "$here/goal_gate.sh" --check --project "$project"; }

# A process group keeps the deadline enforceable on macOS without GNU timeout.
# Requires Python 3 on POSIX; fail closed when this capability is absent.
bounded(){
  local kind=$1 seconds=$2 status supervisor_rc child_rc; shift 2
  command -v python3 >/dev/null 2>&1 || { echo 'GOAL_LOOP: ERROR python3-required-for-budget' >&2; return 4; }
  status=$(mktemp "${TMPDIR:-/tmp}/goal-supervisor.XXXXXX") || return 4
  if [ "$kind" = settlement ]; then
    python3 -I "$here/goal_bounded.py" --receipt "$status" --seconds "$seconds" --owner "$$" --settlement --kind verification --label settlement -- "$@"; supervisor_rc=$?
  elif [ "$kind" = executor ]; then
    python3 -I "$here/goal_bounded.py" --receipt "$status" --seconds "$seconds" --owner "$$" --reserve --kind executor --label iteration -- "$@"; supervisor_rc=$?
  else
    python3 -I "$here/goal_bounded.py" --receipt "$status" --seconds "$seconds" --owner "$$" --kind command --label "$kind" -- "$@"; supervisor_rc=$?
  fi
  child_rc=$(cat "$status" 2>/dev/null); rm -f "$status"
  [ "$supervisor_rc" -eq 0 ] || { echo 'GOAL_LOOP: ERROR supervisor-failed' >&2; return 4; }
  case "$child_rc" in ''|*[!0-9]*) echo 'GOAL_LOOP: ERROR supervisor-receipt-missing' >&2; return 4 ;; esac
  [ "$child_rc" -le 255 ] || { echo 'GOAL_LOOP: ERROR supervisor-receipt-invalid' >&2; return 4; }
  # Child rc=4 is a legitimate executor result; gate rc=4 remains an error.
  if [ "$kind" = executor ] && [ "$child_rc" -eq 4 ]; then return 125; fi
  return "$child_rc"
}

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

release_lock(){
  # Check/init and a refused duplicate never owned this lock. An overridden
  # runner must also leave a newer owner's lock intact when it finally exits.
  [ "$lock_owned" -eq 1 ] || return 0
  [ "$(head -1 "$sd/lock" 2>/dev/null)" = "$$" ] || return 0
  rm -f "$sd/lock" 2>/dev/null || true
}
trap release_lock EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

# Budget observations publish one complete version under the ledger lock.
# The persistent epoch deadline is additionally capped by this process run's
# monotonic deadline; frozen/regressed wall clocks cannot reset round budgets.
observe_clock(){
  local action=${1:-observe} observation
  clock_now=$(date +%s) || { echo 'GOAL_LOOP: ERROR clock-unavailable' >&2; return 4; }
  observation=$(python3 -I "$here/goal_runner.py" budget "$sd" "$action" "$started_at" "$wallclock" "$clock_now") || return 4
  read -r _ clock_now remaining GOAL_RUNNER_MONOTONIC_END <<< "$observation"
  export GOAL_RUNNER_MONOTONIC_END
}

run_claude(){
  local cmd=("$claude_bin" -p "/goal-loop --continue" --output-format json)
  # --project binds execution as well as verification. Keep the caller's cwd
  # outside this subshell so relative ledger/log paths retain their meaning.
  (
    cd "$project" || exit 4
    # A fixed-prompt unattended client owns its input. CLI clients may append
    # piped stdin to the prompt or wait forever for an inherited open pipe.
    bounded executor "$remaining" "${cmd[@]}" < /dev/null
  )
}

case "$mode" in
  init)
    if [ -f "$sd/goal.md" ]; then
      echo "GOAL_LOOP: already initialized ($sd/goal.md) - editing the contract means re-approval (R3)" >&2; exit 2
    fi
    [ -f "$template" ] || { echo "GOAL_LOOP: ERROR template-missing $template" >&2; exit 4; }
    if [ ! -f "$sd/state.rec" ]; then
      bash "$here/goal_ctl.sh" init --project "$project" --max-iterations="$max_iterations" >/dev/null || exit 4
    else
      # ctl init may already have prepared the ledger. Never reset its history
      # merely to seed the still-missing contract template.
      bash "$here/goal_ctl.sh" status --project "$project" >/dev/null || exit 4
    fi
    cp "$template" "$sd/goal.md"
    echo "GOAL_LOOP: INIT ok - fill $sd/goal.md, get user approval, then --continue"
    exit 0 ;;
  check)
    gate; exit $? ;;
  continue)
    [ -f "$sd/goal.md" ] || { echo "GOAL_LOOP: ERROR no-contract (run --init first)" >&2; exit 4; }
    GOAL_TRACE_PROJECT=$(cd "$project" && pwd) || exit 4
    export GOAL_TRACE_PROJECT
    case "$wallclock" in ''|*[!0-9]*) echo 'GOAL_LOOP: ERROR invalid-wallclock' >&2; exit 4 ;; esac
    # Bash arithmetic treats a leading zero as octal (08 would abort).
    wallclock=$(printf '%s' "$wallclock" | sed 's/^0*//')
    [ -n "$wallclock" ] && [ "${#wallclock}" -le 10 ] && [ "$wallclock" -le 2147483647 ] \
      || { echo 'GOAL_LOOP: ERROR invalid-wallclock' >&2; exit 4; }
    case "$max_iterations" in ''|*[!0-9]*) echo 'GOAL_LOOP: ERROR invalid-max-iterations' >&2; exit 4 ;; esac
    max_iterations=$(printf '%s' "$max_iterations" | sed 's/^0*//')
    [ -n "$max_iterations" ] && [ "${#max_iterations}" -le 7 ] || { echo 'GOAL_LOOP: ERROR invalid-max-iterations' >&2; exit 4; }
    if [ "${GOAL_RUNNER_EXEC_PID:-}" != "$$" ]; then
      exec python3 -I "$here/goal_runner.py" own "$sd" "$started_at" "$self" "${_goal_loop_args[@]}"
    fi
    lock_owned=1
    observe_clock begin || exit 4
    i=0
    while [ "$i" -lt "$max_iterations" ]; do
      observe_clock || exit 4
      if [ "$remaining" -le 0 ]; then
        # A bounded final settlement can still report an already-valid GO.
        bounded settlement 3 bash "$here/goal_gate.sh" --check --project "$project"; rc=$?
        [ "$rc" -ne 4 ] || { echo 'GOAL_LOOP: ERROR settlement-unavailable'; exit 4; }
        [ "$rc" -ne 0 ] || { observe_clock delivered || exit 4; echo 'GOAL_LOOP: DELIVERED after-deadline'; exit 0; }
        observe_clock incomplete || exit 4
        echo 'GOAL_LOOP: BLOCKED time-budget-exhausted'; exit 3
      fi
      i=$((i+1))
      if [ "$dry" -eq 1 ]; then
        echo "GOAL_LOOP: DRY-RUN iter=$i plan: $claude_bin -p /goal-loop --continue --output-format json (wallclock=${wallclock}s)"
      else
        mkdir -p "$sd/logs"
        echo "==== iter $i $(date '+%F %T') ====" >> "$sd/logs/loop.log"
        run_claude >> "$sd/logs/loop.log" 2>&1; run_rc=$?
        rotate
        [ "$run_rc" -ne 4 ] || { echo 'GOAL_LOOP: ERROR executor-unavailable'; exit 4; }
      fi
      observe_clock || exit 4
      if [ "$remaining" -gt 0 ]; then bounded gate "$remaining" bash "$here/goal_gate.sh" --check --project "$project"; rc=$?
      else bounded settlement 3 bash "$here/goal_gate.sh" --check --project "$project"; rc=$?; fi
      case "$rc" in
        0) observe_clock delivered || exit 4; echo "GOAL_LOOP: DELIVERED iter=$i"; exit 0 ;;
        3) observe_clock incomplete || exit 4; echo "GOAL_LOOP: BLOCKED iter=$i (breaker/false-complete)"; exit 3 ;;
        4) echo "GOAL_LOOP: ERROR state (iter=$i)" >&2; exit 4 ;;
        *) echo "GOAL_LOOP: no-go iter=$i (reason above); next round" ;;
      esac
      observe_clock || exit 4
      if [ "$remaining" -le 0 ]; then observe_clock incomplete || exit 4; echo 'GOAL_LOOP: BLOCKED time-budget-exhausted'; exit 3; fi
      if [ "$dry" -ne 1 ] && [ "$i" -lt "$max_iterations" ]; then
        bounded pause "$remaining" sleep "$rate" || true
      fi
    done
    observe_clock incomplete || exit 4
    echo "GOAL_LOOP: BLOCKED iterations-exhausted after $max_iterations" >&2
    exit 3 ;;
  *)
    sed -n '4,8p' "$0" >&2; exit 4 ;;
esac
