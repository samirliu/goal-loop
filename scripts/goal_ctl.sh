#!/usr/bin/env bash
# goal_ctl.sh - in-session controller helper of goal-loop. One entry point per
# bookkeeping step. This script is the CONTROLLER's writing hand: it decides
# nothing; goal_gate.sh stays the only arbiter and is never written to.
# Usage:
#   bash goal_ctl.sh init  --project DIR [--max-iterations=N]
#   bash goal_ctl.sh stamp --project DIR [--auto]
#   bash goal_ctl.sh bind  --project DIR            # verdict lines on stdin
#   bash goal_ctl.sh close-iteration --project DIR --task ID --files LIST
#        --checks-pass N --checks-fail N --checks-unverifiable N
#        [--progress yes|no] [--exit-signal yes|no] [--error-signature none]
#        [--false-complete no] [--dry yes|no] [--no-gate]
#        (--dry is REQUIRED on exit: forge contracts: yes = this round's
#         panel+critic produced no new evidence-backed finding)
set -u
export LC_ALL=C.UTF-8

here=$(cd "$(dirname "$0")" && pwd)
cmd="" project="." auto=0 no_gate=0 max_iterations=12
task="" files="" cp="" cf="" cu="" progress=yes exit_signal=no errsig=none fcomplete=no dry=""

while [ $# -gt 0 ]; do
  case "$1" in
    init|stamp|bind|close-iteration) cmd="$1" ;;
    --project) [ $# -ge 2 ] || { echo "CTL: ERROR missing-project-arg" >&2; exit 4; }; project="$2"; shift ;;
    --auto) auto=1 ;;
    --no-gate) no_gate=1 ;;
    --max-iterations=*) max_iterations="${1#*=}" ;;
    --task) [ $# -ge 2 ] || { echo "CTL: ERROR missing-task" >&2; exit 4; }; task="$2"; shift ;;
    --files) [ $# -ge 2 ] || { echo "CTL: ERROR missing-files" >&2; exit 4; }; files="$2"; shift ;;
    --checks-pass) [ $# -ge 2 ] || { echo "CTL: ERROR missing-checks-pass" >&2; exit 4; }; cp="$2"; shift ;;
    --checks-fail) [ $# -ge 2 ] || { echo "CTL: ERROR missing-checks-fail" >&2; exit 4; }; cf="$2"; shift ;;
    --checks-unverifiable) [ $# -ge 2 ] || { echo "CTL: ERROR missing-checks-unverifiable" >&2; exit 4; }; cu="$2"; shift ;;
    --progress) [ $# -ge 2 ] || { echo "CTL: ERROR missing-progress" >&2; exit 4; }; progress="$2"; shift ;;
    --exit-signal) [ $# -ge 2 ] || { echo "CTL: ERROR missing-exit-signal" >&2; exit 4; }; exit_signal="$2"; shift ;;
    --error-signature) [ $# -ge 2 ] || { echo "CTL: ERROR missing-error-signature" >&2; exit 4; }; errsig="$2"; shift ;;
    --false-complete) [ $# -ge 2 ] || { echo "CTL: ERROR missing-false-complete" >&2; exit 4; }; fcomplete="$2"; shift ;;
    --dry) [ $# -ge 2 ] || { echo "CTL: ERROR missing-dry" >&2; exit 4; }; dry="$2"; shift ;;
    --help|-h) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "CTL: ERROR unknown-flag:$1" >&2; exit 4 ;;
  esac
  shift
done
[ -n "$cmd" ] || { echo "CTL: ERROR no-command (init|stamp|bind|close-iteration)" >&2; exit 4; }

sd="$project/.goal"
r(){ tr -d '\r'; }
state_get(){ [ -f "$sd/state.rec" ] && grep -E "^$1=" "$sd/state.rec" | r | tail -1 | cut -d= -f2-; echo; }

case "$cmd" in
  init)
    [ -d "$sd" ] || mkdir -p "$sd/logs"
    if [ -f "$sd/goal.md" ]; then echo "CTL: ERROR already-initialized ($sd/goal.md)" >&2; exit 2; fi
    printf 'iteration=0\nbreaker=CLOSED\nfalse_completes=0\nreplans=0\nno_progress_streak=0\nlast_progress_iteration=0\nmax_iterations=%s\nno_progress_limit=2\nmax_replans=2\nper_check_fail_cap=3\npanel_max=4\ndry_streak=0\ndry_limit=3\ncheck_timeout=120\n' "$max_iterations" > "$sd/state.rec"
    : > "$sd/loop-log.md"; : > "$sd/verdicts.rec"; : > "$sd/work-plan.md"; mkdir -p "$sd/evidence"
    echo "CTL: INIT ok - fill $sd/goal.md, then: goal_ctl.sh stamp --project $project" ;;

  stamp)
    [ -f "$sd/goal.md" ] || { echo "CTL: ERROR no-goal-md" >&2; exit 4; }
    if grep -qE '^approved: [0-9a-f]{6,}' "$sd/goal.md"; then
      echo "CTL: ERROR already-stamped (R3: one stamp; amendments go to the user)" >&2; exit 2
    fi
    h=$(r < "$sd/goal.md" | awk '/^## Acceptance criteria[ ]*$/{f=1;next} f&&/^## /{f=0} f' | sha1sum | cut -c1-8)
    marker=""; [ "$auto" -eq 1 ] && marker=" auto"
    sed -i "s/^approved: .*/approved: $h $(date +%F)$marker/" "$sd/goal.md"
    grep -E '^approved:' "$sd/goal.md" | head -1 ;;

  bind)
    [ -f "$sd/verdicts.rec" ] || { echo "CTL: ERROR no-verdicts-rec" >&2; exit 4; }
    n=0; bad=0
    while IFS= read -r line; do
      line=$(printf '%s' "$line" | r)
      [ -n "$line" ] || continue
      nf=$(printf '%s' "$line" | awk -F'|' '{print NF}')
      v=$(printf '%s' "$line" | cut -d'|' -f2)
      if [ "$nf" -ne 6 ] || ! printf '%s' "$v" | grep -qE '^(PASS|FAIL|UNVERIFIABLE)$'; then
        echo "CTL: WARN skipped-malformed: $line" >&2; bad=$((bad+1)); continue
      fi
      printf '%s\n' "$line" >> "$sd/verdicts.rec"; n=$((n+1))
    done
    echo "CTL: BIND ok appended=$n skipped=$bad" ;;

  close-iteration)
    for v in "$task" "$files" "$cp" "$cf" "$cu"; do
      [ -n "$v" ] || { echo "CTL: ERROR close-iteration needs --task --files --checks-pass --checks-fail --checks-unverifiable" >&2; exit 4; }
    done
    [ -f "$sd/loop-log.md" ] || { echo "CTL: ERROR no-loop-log" >&2; exit 4; }
    # forge bookkeeping: validate BEFORE anything is written - a rc=4 refusal
    # must never leave an orphan loop-log block (checker finding, v1.2)
    if grep -qE '^exit: *forge' "$sd/goal.md" 2>/dev/null; then
      [ -n "$dry" ] || { echo "CTL: ERROR forge-contract-needs-dry (close-iteration --dry yes|no)" >&2; exit 4; }
    fi
    if [ "$dry" = yes ] && [ "${cf:-0}" != 0 ]; then
      echo "CTL: ERROR inconsistent-dry (--dry yes with checks-fail=$cf)" >&2; exit 4
    fi
    digest=$(bash "$here/goal_gate.sh" --digest --project "$project") || { echo "CTL: ERROR digest-unavailable" >&2; exit 4; }
    it=$(state_get iteration); [ -n "$it" ] || it=0
    new=$((it+1))
    printf '%s\n' "## iteration $new" "task=$task" "files_modified=$files" \
      "checks_pass=$cp" "checks_fail=$cf" "checks_unverifiable=$cu" \
      "error_signature=$errsig" "progress=$progress" "exit_signal=$exit_signal" \
      "false_complete=$fcomplete" "digest=$digest" >> "$sd/loop-log.md"
    if [ "$progress" = yes ]; then
      streak=0; breaker=CLOSED; lpi=$new
    else
      streak=$(( $(state_get no_progress_streak) + 1 )); lpi=$(state_get last_progress_iteration)
      npl=$(state_get no_progress_limit); [ -n "$npl" ] || npl=2
      if [ "$streak" -gt "$npl" ]; then breaker=OPEN; else breaker=HALF_OPEN; fi
    fi
    # forge bookkeeping: --dry is mandatory there and must be consistent
    fc=$(state_get false_completes); [ -n "$fc" ] || fc=0
    [ "$fcomplete" = yes ] && fc=$((fc+1))
    mi=$(state_get max_iterations); [ -n "$mi" ] || mi=$max_iterations
    drys=$(state_get dry_streak); [ -n "$drys" ] || drys=0
    if [ "$dry" = yes ]; then drys=$((drys+1)); else drys=0; fi
    dlimit=$(state_get dry_limit); [ -n "$dlimit" ] || dlimit=3
    ctmo=$(state_get check_timeout); [ -n "$ctmo" ] || ctmo=120
    printf 'iteration=%s\nbreaker=%s\nfalse_completes=%s\nreplans=%s\nno_progress_streak=%s\nlast_progress_iteration=%s\nmax_iterations=%s\nno_progress_limit=%s\nmax_replans=2\nper_check_fail_cap=3\npanel_max=4\ndry_streak=%s\ndry_limit=%s\ncheck_timeout=%s\n' \
      "$new" "$breaker" "$fc" "$(state_get replans)" "$streak" "$lpi" "$mi" "$(state_get no_progress_limit)" "$drys" "$dlimit" "$ctmo" > "$sd/state.rec"
    echo "CTL: CLOSE ok iter=$new digest=$digest"
    [ "$no_gate" -eq 1 ] && exit 0
    bash "$here/goal_gate.sh" --check --project "$project"; exit $? ;;
esac
