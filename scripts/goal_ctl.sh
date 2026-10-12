#!/usr/bin/env bash
# goal_ctl.sh - in-session controller helper of goal-loop. One entry point per
# bookkeeping step. This script is the CONTROLLER's writing hand: it decides
# nothing; goal_gate.sh stays the only arbiter and is never written to.
# Usage:
#   bash goal_ctl.sh init  --project DIR [--max-iterations=N]
#   bash goal_ctl.sh stamp --project DIR [--auto] [--time-budget=N]
#   bash goal_ctl.sh bind  --project DIR            # verdict lines on stdin
#   bash goal_ctl.sh status --project DIR           # human progress summary
#   bash goal_ctl.sh close-iteration --project DIR --task ID --files LIST
#        --checks-pass N --checks-fail N --checks-unverifiable N
#        [--progress yes|no] [--exit-signal yes|no] [--error-signature none]
#        [--false-complete no] [--dry yes|no] [--no-gate]
#        [--score N] [--judge-score N] [--strategy-delta TEXT]
#        (--dry is REQUIRED on exit: forge contracts: yes = this round's
#         panel+critic produced no new evidence-backed finding)
#        (--score: objective:maximize|minimize value; --strategy-delta REQUIRED when
#         the new breaker is HALF_OPEN/OPEN — R10)
set -u
export LC_ALL=C.UTF-8

here=$(cd "$(dirname "$0")" && pwd)
cmd="" project="." auto=0 no_gate=0 max_iterations=12 time_budget=""
task="" files="" cp="" cf="" cu="" progress=yes exit_signal=no errsig=none fcomplete=no dry=""
score="" judge_score="" strategy_delta=""

while [ $# -gt 0 ]; do
  case "$1" in
    init|stamp|bind|close-iteration|status) cmd="$1" ;;
    --project) [ $# -ge 2 ] || { echo "CTL: ERROR missing-project-arg" >&2; exit 4; }; project="$2"; shift ;;
    --auto) auto=1 ;;
    --time-budget=*) time_budget="${1#*=}" ;;
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
    --score) [ $# -ge 2 ] || { echo "CTL: ERROR missing-score" >&2; exit 4; }; score="$2"; shift ;;
    --judge-score) [ $# -ge 2 ] || { echo "CTL: ERROR missing-judge-score" >&2; exit 4; }; judge_score="$2"; shift ;;
    --strategy-delta) [ $# -ge 2 ] || { echo "CTL: ERROR missing-strategy-delta" >&2; exit 4; }; strategy_delta="$2"; shift ;;
    --help|-h) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "CTL: ERROR unknown-flag:$1" >&2; exit 4 ;;
  esac
  shift
done
[ -n "$cmd" ] || { echo "CTL: ERROR no-command (init|stamp|bind|close-iteration|status)" >&2; exit 4; }

sd="$project/.goal"
r(){ tr -d '\r'; }
# MUST match goal_gate.sh hash_std - stamp and verify share one digest rule
hash_std(){ if command -v sha1sum >/dev/null 2>&1; then sha1sum | cut -c1-40; else cksum | awk '{print $1}'; fi }
state_get(){ [ -f "$sd/state.rec" ] && grep -E "^$1=" "$sd/state.rec" | r | tail -1 | cut -d= -f2-; echo; }

case "$cmd" in
  init)
    [ -d "$sd" ] || mkdir -p "$sd/logs"
    if [ -f "$sd/goal.md" ]; then echo "CTL: ERROR already-initialized ($sd/goal.md)" >&2; exit 2; fi
    printf 'iteration=0\nbreaker=CLOSED\nfalse_completes=0\nreplans=0\nno_progress_streak=0\nlast_progress_iteration=0\nmax_iterations=%s\nno_progress_limit=2\nmax_replans=2\nper_check_fail_cap=3\npanel_max=4\ndry_streak=0\ndry_limit=3\ncheck_timeout=120\ntime_budget=0\ndeadline=0\n' "$max_iterations" > "$sd/state.rec"
    : > "$sd/loop-log.md"; : > "$sd/verdicts.rec"; : > "$sd/work-plan.md"; mkdir -p "$sd/evidence"
    echo "CTL: INIT ok - fill $sd/goal.md, then: goal_ctl.sh stamp --project $project" ;;

  stamp)
    [ -f "$sd/goal.md" ] || { echo "CTL: ERROR no-goal-md" >&2; exit 4; }
    if grep -qE '^approved: [0-9a-f]{6,}' "$sd/goal.md"; then
      echo "CTL: ERROR already-stamped (R3: one stamp; amendments go to the user)" >&2; exit 2
    fi
    # forge contracts: baseline must cover every delta metric AC BEFORE the
    # stamp - t=0 exposure, never a mid-loop rc=4 surprise (v1.5)
    if grep -qE '^exit: *forge' "$sd/goal.md" 2>/dev/null; then
      if ! bl=$(bash "$here/goal_gate.sh" --baseline-check --project "$project" 2>&1); then
        printf '%s\n' "$bl" >&2
        echo "CTL: ERROR stamp-refused: baseline validation failed (forge contract) - run the metric checks against the pre-work artifact and write .goal/baseline.md" >&2
        exit 2
      fi
    fi
    # the objective must point at a score-producing AC (expected: maximize|
    # minimize); pointing it at a judged/exit AC can never yield a score and
    # only surfaces mid-loop as score-missing - catch the mismatch at t=0.
    oac=$(r < "$sd/goal.md" | sed -nE 's/^objective: *(maximize|minimize) +(AC-[0-9]+).*/\2/p' | tail -1)
    if [ -n "$oac" ]; then
      oexp=$(r < "$sd/goal.md" | awk -v id="$oac" '$0 ~ "^- "id"[ |]"' | sed -nE 's/^.*expected: *([^|]*)[[:space:]]*$/\1/p' | tail -1 | tr -d '[:space:]')
      case "$oexp" in
        maximize|minimize) : ;;
        *) echo "CTL: ERROR stamp-refused: objective points at $oac whose expected= is not maximize|minimize (it would never produce a score)" >&2; exit 2 ;;
      esac
    fi
    # Calibration fixtures (v2.6): calib: belongs to JUDGED ACs only, needs
    # both fixtures, and the fixture files must exist in the tree NOW - t=0
    # exposure so the loop never discovers mid-run that the yardstick is gone.
    while IFS= read -r ac_line; do
      # backtick spans are command text; strip before spotting calib: so a check
      # that greps the literal "calib:" cannot masquerade as a calibration claim
      ac_cline=$(printf '%s' "$ac_line" | sed -E 's/`[^`]*`//g')
      printf '%s' "$ac_cline" | grep -qE 'calib:' || continue
      ac_id=$(printf '%s' "$ac_line" | sed -nE 's/^- (AC-[0-9]+).*/\1/p')
      exp=$(printf '%s' "$ac_line" | sed -nE 's/^.*expected: *([^|]*)[[:space:]]*$/\1/p' | tail -1 | tr -d '[:space:]')
      [ "$exp" = judged ] || { echo "CTL: ERROR stamp-refused: $ac_id declares calib: but expected= is not judged (calibration measures a seat, not a command)" >&2; exit 2; }
      cg=$(printf '%s' "$ac_cline" | sed -nE 's/^.*calib:[^|]*good *= *([^ |]+).*/\1/p' | tail -1)
      cb=$(printf '%s' "$ac_cline" | sed -nE 's/^.*calib:[^|]*bad *= *([^ |]+).*/\1/p' | tail -1)
      { [ -n "$cg" ] && [ -n "$cb" ]; } || { echo "CTL: ERROR stamp-refused: $ac_id calib: needs BOTH good= and bad= fixtures" >&2; exit 2; }
      [ -f "$project/$cg" ] || { echo "CTL: ERROR stamp-refused: $ac_id good fixture $cg not found in the tree" >&2; exit 2; }
      [ -f "$project/$cb" ] || { echo "CTL: ERROR stamp-refused: $ac_id bad fixture $cb not found in the tree" >&2; exit 2; }
      # same file on both ends = one ruler claiming to measure both directions:
      # the pair's PASS+FAIL requirement is then a permanent block. Catch at t=0.
      [ "$cg" != "$cb" ] || { echo "CTL: ERROR stamp-refused: $ac_id calib: good= and bad= name the SAME file $cg (one ruler cannot calibrate both ways)" >&2; exit 2; }
    done < <(r < "$sd/goal.md" | grep -E '^- AC-[0-9]+' || true)
    h=$( { r < "$sd/goal.md" | awk '/^## Acceptance criteria[ ]*$/{f=1;next} f&&/^## /{f=0} f'
           r < "$sd/goal.md" | grep -E '^(exit|objective):' || true
         } | hash_std | cut -c1-8)
    # Budget knobs written in goal.md BIND at stamp. They used to be
    # decorative (contract said max_iterations=10, state.rec kept 12) -
    # that is a silent contract lie. Parse key=value tokens; CLI --time-budget
    # still wins over a wallclock= token.
    for key in max_iterations no_progress_limit max_replans per_check_fail_cap panel_max dry_limit check_timeout wallclock; do
      val=$(r < "$sd/goal.md" | sed -nE "s/.*(^|[[:space:]])${key}=([0-9]+).*/\2/p" | tail -1)
      [ -n "$val" ] || continue
      case "$key" in
        wallclock)
          [ -n "${time_budget:-}" ] || time_budget=$val
          ;;
        *)
          { grep -vE "^${key}=" "$sd/state.rec"; printf '%s=%s\n' "$key" "$val"; } > "$sd/state.rec.new" \
            && mv "$sd/state.rec.new" "$sd/state.rec"
          ;;
      esac
    done
    case "${time_budget:-}" in                            # optional wall-clock fuse, stamped at approval
      ''|0) : ;;
      *[!0-9]*) echo "CTL: ERROR bad-time-budget:$time_budget" >&2; exit 4 ;;
      *) { grep -vE '^(time_budget|deadline)=' "$sd/state.rec"
           printf 'time_budget=%s\ndeadline=%s\n' "$time_budget" "$(( $(date +%s) + time_budget ))"
         } > "$sd/state.rec.new" && mv "$sd/state.rec.new" "$sd/state.rec" ;;
    esac
    marker=""; [ "$auto" -eq 1 ] && marker=" auto"
    sed -i "s/^approved: .*/approved: $h $(date +%F)$marker/" "$sd/goal.md"
    # sed silently no-ops when the goal.md has no approved: placeholder line -
    # the whole stamp then pretends success while the contract stays
    # unstamped. Fail loud instead (the contract template always ships one).
    grep -E '^approved:' "$sd/goal.md" | head -1 | grep -qE '[0-9a-f]{6,}' \
      || { echo "CTL: ERROR stamp-refused: goal.md has no 'approved: <placeholder>' line to write the hash onto" >&2; exit 4; }
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
    # R10: any no-progress landing sets HALF_OPEN/OPEN and must carry a
    # strategy change - otherwise the loop is grinding without revising.
    if [ "$progress" != yes ]; then
      case "$strategy_delta" in
        ''|none) echo "CTL: ERROR missing-strategy-delta (progress=no needs --strategy-delta 'what you are changing')" >&2; exit 4 ;;
      esac
    fi
    # score bookkeeping (objective: maximize|minimize)
    if [ -n "$score" ]; then
      # one optional leading '-', digits, optional decimal - not "..." or "--"
      printf '%s' "$score" | grep -qE '^-?[0-9]+(\.[0-9]+)?$' \
        || { echo "CTL: ERROR bad-score:$score" >&2; exit 4; }
    fi
    if [ -n "$judge_score" ]; then
      printf '%s' "$judge_score" | grep -qE '^-?[0-9]+(\.[0-9]+)?$' \
        || { echo "CTL: ERROR bad-judge-score:$judge_score" >&2; exit 4; }
    fi
    # The score is MEASURED, never self-reported: ctl reruns the objective AC
    # (gate --verify, stateless) and records the observed value. A mismatch
    # from the controller is noted; an unmeasurable instrument records none
    # and the gate refuses any claim lacking a score.
    obj_ac=$(r < "$sd/goal.md" | sed -nE 's/^objective: *(maximize|minimize) +(AC-[0-9]+).*/\2/p' | tail -1)
    obj_dir=$(r < "$sd/goal.md" | sed -nE 's/^objective: *(maximize|minimize) +(AC-[0-9]+).*/\1/p' | tail -1)
    [ -n "$obj_dir" ] || obj_dir=maximize
    if [ -n "$obj_ac" ] && [ -n "$score" ]; then
      vline=$(bash "$here/goal_gate.sh" --verify "$obj_ac" --project "$project" 2>/dev/null \
              | grep -E "^GATE: VERIFY $obj_ac\|" | tail -1)
      mobs=$(printf '%s' "$vline" | sed -nE 's/.*observed=([0-9.\-]+).*/\1/p')
      if [ -n "$mobs" ]; then
        [ "$mobs" = "$score" ] || echo "CTL: NOTE score-measured-override (claimed=$score measured=$mobs)" >&2
        score="$mobs"
      else
        echo "CTL: WARN objective-unmeasurable:$obj_ac (recording score=none)" >&2
        score=""
      fi
    fi
    # R10 value must be single-line or it shreds the key=value block
    sdelta_show=$(printf '%s' "${strategy_delta:-none}" | tr '\n\r\t' '   ')
    case "$sdelta_show" in ''|*[![:print:]]*) sdelta_show=none ;; esac
    [ -n "$sdelta_show" ] || sdelta_show=none
    # R13 sidecar: iter|score|judge (either may be 'none'). Two comparable
    # points later let the gate refuse DIVERGENCE:score-vs-judge claims.
    printf '%s|%s|%s\n' "$new" "${score:-none}" "${judge_score:-none}" >> "$sd/scores.rec"
    # task= is ledger law (R12/A1): wave ids must carry their backend. A bare
    # T<n> means an ordinary one-shot subagent wave - normalize it (crew:1)
    # instead of letting the self-audit refuse the claim after the fact.
    case "$task" in
      '') echo "CTL: ERROR missing-task (ledger needs --task T<n> or T<n>[backend:N])" >&2; exit 4 ;;
      T[0-9]*) printf '%s' "$task" | grep -qE '^T[0-9]+$' && task="$task[crew:1]" ;;
    esac
    printf '%s' "$task" | grep -qE '^T[0-9]+\[(teams|crew):[0-9]+\]( *\(fallback:[a-z0-9-]+\))?$' \
      || { echo "CTL: ERROR bad-task:$task (schema: T<n>[crew:N] / T<n>[teams:N], bare T<n> normalizes to crew:1)" >&2; exit 4; }
    printf '%s\n' "## iteration $new" "task=$task" "files_modified=$files" \
      "checks_pass=$cp" "checks_fail=$cf" "checks_unverifiable=$cu" \
      "error_signature=$errsig" "progress=$progress" "exit_signal=$exit_signal" \
      "false_complete=$fcomplete" "digest=$digest" \
      "score=${score:-none}" "strategy_delta=$sdelta_show" >> "$sd/loop-log.md"
    if [ "$progress" = yes ]; then
      streak=0; breaker=CLOSED; lpi=$new
    else
      streak=$(( $(state_get no_progress_streak) + 1 )); lpi=$(state_get last_progress_iteration)
      npl=$(state_get no_progress_limit); [ -n "$npl" ] || npl=2
      if [ "$streak" -gt "$npl" ]; then breaker=OPEN; else breaker=HALF_OPEN; fi
    fi
    # forge bookkeeping: --dry is mandatory there and must be consistent
    fc=$(state_get false_completes); [ -n "$fc" ] || fc=0
    # The MECHANICAL ratchet below owns the false-complete count when the
    # gate runs. A manual --false-complete yes next to it used to DOUBLE-COUNT
    # (the first caught claim instantly BLOCKed the loop - defeating R1's
    # "two catches" rule). The flag only still means something with --no-gate,
    # where nothing else counts; with the gate running, note and defer.
    if [ "$fcomplete" = yes ]; then
      if [ "$no_gate" -eq 1 ]; then
        fc=$((fc+1))
      else
        echo "CTL: NOTE false-complete-flag-ignored (the gate ratchet counts catches mechanically)" >&2
      fi
    fi
    mi=$(state_get max_iterations); [ -n "$mi" ] || mi=$max_iterations
    drys=$(state_get dry_streak); [ -n "$drys" ] || drys=0
    # best_score: water mark for the objective (R11). maximize -> high-water
    # (keep the larger); minimize -> low-water (keep the smaller).
    best=$(state_get best_score); [ -n "$best" ] || best=none
    if [ -n "$score" ]; then
      if [ "$best" = none ]; then
        best=$score
      else
        if [ "$obj_dir" = minimize ]; then
          better=$(awk -v c="$score" -v b="$best" 'BEGIN{print (c+0<b+0)?1:0}')
        else
          better=$(awk -v c="$score" -v b="$best" 'BEGIN{print (c+0>b+0)?1:0}')
        fi
        [ "$better" = 1 ] && best=$score
      fi
    fi
    if [ "$dry" = yes ]; then drys=$((drys+1)); else drys=0; fi
    dlimit=$(state_get dry_limit); [ -n "$dlimit" ] || dlimit=3
    ctmo=$(state_get check_timeout); [ -n "$ctmo" ] || ctmo=120
    tb=$(state_get time_budget); [ -n "$tb" ] || tb=0
    dl=$(state_get deadline); [ -n "$dl" ] || dl=0
    printf 'iteration=%s\nbreaker=%s\nfalse_completes=%s\nreplans=%s\nno_progress_streak=%s\nlast_progress_iteration=%s\nmax_iterations=%s\nno_progress_limit=%s\nmax_replans=2\nper_check_fail_cap=3\npanel_max=4\ndry_streak=%s\ndry_limit=%s\ncheck_timeout=%s\ntime_budget=%s\ndeadline=%s\nbest_score=%s\n' \
      "$new" "$breaker" "$fc" "$(state_get replans)" "$streak" "$lpi" "$mi" "$(state_get no_progress_limit)" "$drys" "$dlimit" "$ctmo" "$tb" "$dl" "$best" > "$sd/state.rec"
    echo "CTL: CLOSE ok iter=$new digest=$digest"
    [ "$no_gate" -eq 1 ] && exit 0
    # False-complete ratchet, mechanized: a claim that the gate catches failing
    # IS a false complete - counting it used to depend on the controller
    # obeying the NOTE and appending false_complete=yes by hand. Two catches
    # now BLOCK the loop automatically (gate rule fc>=2). Only NO-GO (rc=2)
    # claims count; BLOCKED/rc=4 mean other failures.
    # Capture the gate's verdict: the reason/hint pair lands in state.rec so
    # `status` can print a mechanical NEXT= later. Streams are split-captured
    # and replayed (stdout->stdout, stderr->stderr) so the pass-through stays
    # byte-identical to the old direct call; the real gate rc survives.
    g_out=$(mktemp "${TMPDIR:-/tmp}/ctl-gate-out.XXXXXX") || g_out=/tmp/ctl-gate-out.$$
    g_err=$(mktemp "${TMPDIR:-/tmp}/ctl-gate-err.XXXXXX") || g_err=/tmp/ctl-gate-err.$$
    bash "$here/goal_gate.sh" --check --project "$project" >"$g_out" 2>"$g_err"; grc=$?
    cat "$g_out"; cat "$g_err" >&2
    gate_out=$(cat "$g_out" "$g_err")
    rm -f "$g_out" "$g_err"
    last_reason=$(printf '%s\n' "$gate_out" | grep -E '^GATE: (NO-GO|BLOCKED|ERROR)' | tail -1 | sed -nE 's/.*reason=([^ ]*).*/\1/p')
    last_hint=$(printf '%s\n' "$gate_out" | grep -E '^GATE: NO-GO' | tail -1 | sed -nE 's/.*hint=([^ ]*).*/\1/p')
    { grep -vE '^last_(reason|hint)=' "$sd/state.rec" 2>/dev/null
      printf 'last_reason=%s\nlast_hint=%s\n' "${last_reason:-ok}" "${last_hint:-}"; } > "$sd/state.rec.new" \
      && mv "$sd/state.rec.new" "$sd/state.rec"
    if [ "$grc" -eq 2 ] && [ "$exit_signal" = yes ]; then
      fc=$(( $(state_get false_completes) + 1 ))
      { grep -vE '^false_completes=' "$sd/state.rec"; printf 'false_completes=%s\n' "$fc"; } > "$sd/state.rec.new" \
        && mv "$sd/state.rec.new" "$sd/state.rec"
      echo "CTL: NOTE false-complete-counted=$fc (gate caught a failing claim; two catches BLOCK the loop - fix the artifact, do not re-claim)" >&2
    fi
    exit "$grc" ;;

  status)
    [ -f "$sd/state.rec" ] || { echo "CTL: STATUS no active goal-loop ledger ($sd/state.rec missing)" >&2; exit 4; }
    g(){ state_get "$1"; }
    left="off"
    d=$(g deadline); if [ -n "$d" ] && [ "$d" != 0 ]; then left=$(( d - $(date +%s) ))s; [ "$left" = "" ] && left=0s; fi
    printf 'CTL: STATUS iter=%s/%s breaker=%s dry_streak=%s/%s best_score=%s time_left=%s\n' \
      "$(g iteration)" "$(g max_iterations)" "$(g breaker)" "$(g dry_streak)" "$(g dry_limit)" "$(g best_score)" "$left"
    lb=$(awk '
      /^## iteration/ { delete l; next }
      { line=$0; sub(/\r$/,"",line)
        if (line ~ /=/) { p=index(line,"="); l[substr(line,1,p-1)]=substr(line,p+1) } }
    END { printf "task=%s checks=%s pass / %s fail / %s unverifiable progress=%s digest=%s",
      l["task"], l["checks_pass"], l["checks_fail"], l["checks_unverifiable"], l["progress"], l["digest"] }
    ' "$sd/loop-log.md" 2>/dev/null)
    echo "CTL: LAST $lb"
    # All open queue items (controller must tick [x] on join). A single
    # "NEXT" line hid the rest and after a NO-GO kept pointing at finished work.
    open=$(grep -E '^- \[ \]' "$sd/work-plan.md" 2>/dev/null | sed 's/^- \[ \] //' | cut -c1-120)
    if [ -n "$open" ]; then
      echo "CTL: OPEN ($(printf '%s\n' "$open" | wc -l | tr -d ' ') items)"
      printf '%s\n' "$open" | sed 's/^/CTL:   - /'
    else
      echo "CTL: OPEN none (all tasks closed)"
    fi
    # NEXT= is the mechanical routing the controller must otherwise remember
    # from the gate's hint token: state.rec carries the pair recorded by the
    # last close-iteration, and this maps it to one sentence. No judgment:
    # the mapping lives in one place and matches references/gate.md section 3.
    lr=$(g last_reason); lh=$(g last_hint)
    if [ -z "$lr" ] || [ "$lr" = ok ]; then
      echo "CTL: NEXT (nothing pending at last gate check - claim when ready)"
    else
      case "$lh" in
        fix-AC)              next="dispatch a fixer scoped to the open-FAIL AC's files" ;;
        bind-seat)           next="dispatch a cold judging seat - do NOT send a coder" ;;
        fix-instrument)      next="repair the probe/verify instrument; the number is untrusted" ;;
        bind-calib-grades)   next="grade the calib fixtures and bind AC-N#good=PASS / AC-N#bad=FAIL this iteration" ;;
        fix-calib-fixture)   next="restore the named calibration fixture (or restamp with valid paths)" ;;
        restore-best)        next="return the tree to best_score state before claiming" ;;
        continue-forge)      next="keep forging: dry_streak < dry_limit, run another exhaustion round" ;;
        write-strategy-delta) next="record what genuinely changes next, then close-iteration" ;;
        rebind-judged)       next="re-run the judging seat at the current digest and bind fresh" ;;
        set-exit-signal)     next="the block never claimed exit - close-iteration --exit-signal yes" ;;
        redesign-AC)         next="the metric and the cold seat disagree: rewrite the AC or its direction" ;;
        proposal-to-user)    next="the contract changed: propose an amendment, do not apply it" ;;
        graceful-deliver)    next="time fuse expired: deliver the passing work as best-so-far and stop" ;;
        replan-or-stop)      next="same error signature twice: change strategy (HALF_OPEN) or stop and report" ;;
        *)                   next="read reason=$lr (hint=$lh) and route literally" ;;
      esac
      echo "CTL: NEXT reason=$lr hint=${lh:-none}"
      echo "CTL:   -> $next"
    fi
    exit 0 ;;
esac
