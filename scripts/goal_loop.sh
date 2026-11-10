#!/usr/bin/env bash
# goal_loop.sh - OPTIONAL unattended outer loop of goal-loop (opt-in, never
# default). Trusts ONLY the exit code of goal_gate.sh, never any textual claim.
# Usage:
#   bash goal_loop.sh --init [--project DIR]
#   bash goal_loop.sh --continue [--max-iterations=N] [--wallclock=SEC] [--dry-run]
#                     [--check-only] [--resume] [--project DIR]
set -u
export LC_ALL=C.UTF-8
started_at=$(date +%s)

here=$(cd "$(dirname "$0")" && pwd)
claude_bin="${CLAUDE_BIN:-claude}"
template="$here/../assets/goal.contract.md"
project="." mode="" max_iterations=12 wallclock=1800 rate=5 dry=0
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
  python3 -I -c '
import os, signal, subprocess, sys, time
if os.name != "posix": sys.exit(4)
owner=int(sys.argv[3])
try: p=subprocess.Popen(sys.argv[4:], start_new_session=True)
except OSError as e:
 print("GOAL_LOOP: ERROR executor-start: " + str(e), file=sys.stderr); sys.exit(4)
def stop(*_):
 try: os.killpg(p.pid, signal.SIGTERM)
 except ProcessLookupError: pass
 try: p.wait(timeout=0.5)
 except subprocess.TimeoutExpired: pass
 try: os.killpg(p.pid, signal.SIGKILL)
 except ProcessLookupError: pass
 p.wait()
signal.signal(signal.SIGTERM, lambda *_: (stop(), sys.exit(143)))
signal.signal(signal.SIGINT, lambda *_: (stop(), sys.exit(130)))
try:
 end=time.monotonic()+max(0, float(sys.argv[2]))
 while True:
  try: os.kill(owner, 0)
  except ProcessLookupError:
   stop(); sys.exit(143)
  remaining=end-time.monotonic()
  if remaining<=0:
   stop(); rc=124; break
  try: rc=p.wait(timeout=min(remaining, 0.1)); break
  except subprocess.TimeoutExpired: pass
 try: os.killpg(p.pid, signal.SIGKILL)
 except ProcessLookupError: pass
 with open(sys.argv[1], "w", encoding="ascii") as receipt:
  receipt.write(str(rc if rc>=0 else 128-rc))
except BaseException:
 stop(); raise
' "$status" "$seconds" "$$" "$@"; supervisor_rc=$?
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

acquire_lock(){
  local lf="$sd/lock" pid age now
  if [ -f "$lf" ]; then
    pid=$(head -1 "$lf" | tr -d '\r'); now=$(date +%s)
    age=$(( now - $(sed -n '2p' "$lf" | tr -d '\r' | tr -d ' ') ))
    if kill -0 "$pid" 2>/dev/null; then
      echo "GOAL_LOOP: BLOCKED live-lock pid=$pid age=${age}s" >&2; exit 4
    fi
    echo "GOAL_LOOP: NOTE reclaiming stale/overridden lock pid=$pid age=${age}s" >&2
  fi
  mkdir -p "$sd/logs" || exit 4
  printf '%s\n%s\n' "$$" "$(date +%s)" > "$lf" || exit 4
  lock_owned=1
}
release_lock(){
  # Check/init and a refused duplicate never owned this lock. An overridden
  # runner must also leave a newer owner's lock intact when it finally exits.
  [ "$lock_owned" -eq 1 ] || return 0
  [ "$(head -1 "$sd/lock" 2>/dev/null)" = "$$" ] || return 0
  rm -f "$sd/lock" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

# Never reuse predictable temporary names: a pre-existing symlink or file in
# .goal/ must not be truncated by the runner's own state update.
atomic_runner_write(){
  local target="$sd/$1" value="$2" tmp
  [ ! -L "$target" ] && { [ ! -e "$target" ] || [ -f "$target" ]; } || {
    echo 'GOAL_LOOP: ERROR invalid-runner-state-path' >&2; return 4;
  }
  tmp=$(mktemp "$sd/.runner-write.XXXXXX") || return 4
  if ! printf '%s\n' "$value" > "$tmp"; then rm -f "$tmp"; return 4; fi
  if [ -L "$target" ] || ! mv -f "$tmp" "$target"; then
    rm -f "$tmp"; echo 'GOAL_LOOP: ERROR runner-state-write' >&2; return 4
  fi
}

# Wall-clock deadlines survive process restarts. Persist the greatest observed
# epoch so a clock rollback cannot silently grant another budget on resume.
# The runner lock serializes ordinary access; A3 still needs atomic ownership.
observe_clock(){
  clock_now=$(date +%s) || { echo 'GOAL_LOOP: ERROR clock-unavailable' >&2; return 4; }
  case "$clock_now" in ''|*[!0-9]*) echo 'GOAL_LOOP: ERROR invalid-clock' >&2; return 4 ;; esac
  if [ "$clock_now" -lt "$clock_high" ]; then
    echo 'GOAL_LOOP: ERROR clock-regressed' >&2; return 4
  fi
  clock_high=$clock_now
  atomic_runner_write runner.clock "$clock_high"
}

run_claude(){
  local cmd=("$claude_bin" -p "/goal-loop --continue" --output-format json)
  # --project binds execution as well as verification. Keep the caller's cwd
  # outside this subshell so relative ledger/log paths retain their meaning.
  (
    cd "$project" || exit 4
    bounded executor "$remaining" "${cmd[@]}"
  )
}

case "$mode" in
  init)
    if [ -f "$sd/goal.md" ]; then
      echo "GOAL_LOOP: already initialized ($sd/goal.md) - editing the contract means re-approval (R3)" >&2; exit 2
    fi
    [ -f "$template" ] || { echo "GOAL_LOOP: ERROR template-missing $template" >&2; exit 4; }
    bash "$here/goal_ctl.sh" init --project "$project" --max-iterations="$max_iterations" >/dev/null || exit 4
    cp "$template" "$sd/goal.md"
    echo "GOAL_LOOP: INIT ok - fill $sd/goal.md, get user approval, then --continue"
    exit 0 ;;
  check)
    gate; exit $? ;;
  continue)
    [ -f "$sd/goal.md" ] || { echo "GOAL_LOOP: ERROR no-contract (run --init first)" >&2; exit 4; }
    case "$wallclock" in ''|*[!0-9]*) echo 'GOAL_LOOP: ERROR invalid-wallclock' >&2; exit 4 ;; esac
    # Bash arithmetic treats a leading zero as octal (08 would abort).
    wallclock=$(printf '%s' "$wallclock" | sed 's/^0*//')
    [ -n "$wallclock" ] && [ "${#wallclock}" -le 10 ] && [ "$wallclock" -le 2147483647 ] \
      || { echo 'GOAL_LOOP: ERROR invalid-wallclock' >&2; exit 4; }
    acquire_lock
    case "$started_at" in ''|*[!0-9]*) echo 'GOAL_LOOP: ERROR invalid-clock' >&2; exit 4 ;; esac
    clock_high=$started_at
    if [ -f "$sd/runner.clock" ]; then
      old_clock=$(cat "$sd/runner.clock")
      case "$old_clock" in ''|*[!0-9]*) echo 'GOAL_LOOP: ERROR invalid-runner-clock' >&2; exit 4 ;; esac
      if [ "$started_at" -lt "$old_clock" ]; then echo 'GOAL_LOOP: ERROR clock-regressed' >&2; exit 4; fi
      clock_high=$old_clock
    fi
    observe_clock || exit 4
    deadline=$((started_at + wallclock))
    if [ -f "$sd/runner.deadline" ]; then
      old=$(cat "$sd/runner.deadline")
      case "$old" in ''|*[!0-9]*) echo 'GOAL_LOOP: ERROR invalid-runner-deadline' >&2; exit 4 ;; esac
      [ "$old" -ge "$deadline" ] || deadline=$old
    fi
    contract_deadline=$(sed -n 's/^deadline=//p' "$sd/state.rec" | tail -1)
    case "$contract_deadline" in ''|*[!0-9]*) echo 'GOAL_LOOP: ERROR invalid-contract-deadline' >&2; exit 4 ;; esac
    if [ "$contract_deadline" -gt 0 ] && [ "$contract_deadline" -lt "$deadline" ]; then deadline=$contract_deadline; fi
    atomic_runner_write runner.deadline "$deadline" || exit 4
    i=0
    while [ "$i" -lt "$max_iterations" ]; do
      observe_clock || exit 4
      remaining=$((deadline - clock_now))
      if [ "$remaining" -le 0 ]; then
        # A bounded final settlement can still report an already-valid GO.
        bounded gate 3 bash "$here/goal_gate.sh" --check --project "$project"; rc=$?
        [ "$rc" -ne 4 ] || { echo 'GOAL_LOOP: ERROR settlement-unavailable'; exit 4; }
        [ "$rc" -ne 0 ] || { echo 'GOAL_LOOP: DELIVERED after-deadline'; exit 0; }
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
      remaining=$((deadline - clock_now))
      if [ "$remaining" -gt 0 ]; then bounded gate "$remaining" bash "$here/goal_gate.sh" --check --project "$project"; rc=$?
      else bounded gate 3 bash "$here/goal_gate.sh" --check --project "$project"; rc=$?; fi
      case "$rc" in
        0) echo "GOAL_LOOP: DELIVERED iter=$i"; exit 0 ;;
        3) echo "GOAL_LOOP: BLOCKED iter=$i (breaker/false-complete)"; exit 3 ;;
        4) echo "GOAL_LOOP: ERROR state (iter=$i)" >&2; exit 4 ;;
        *) echo "GOAL_LOOP: no-go iter=$i (reason above); next round" ;;
      esac
      observe_clock || exit 4
      remaining=$((deadline - clock_now))
      if [ "$remaining" -le 0 ]; then echo 'GOAL_LOOP: BLOCKED time-budget-exhausted'; exit 3; fi
      if [ "$dry" -ne 1 ] && [ "$i" -lt "$max_iterations" ]; then
        [ "$remaining" -lt "$rate" ] && sleep "$remaining" || sleep "$rate"
      fi
    done
    echo "GOAL_LOOP: BLOCKED iterations-exhausted after $max_iterations" >&2
    exit 3 ;;
  *)
    sed -n '4,8p' "$0" >&2; exit 4 ;;
esac
