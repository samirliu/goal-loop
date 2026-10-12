#!/usr/bin/env bash
# goal_gate.sh - the EXTERNAL arbiter of goal-loop. It decides; it never
# writes state. Since v1.2 it also RERUNS the contract's DETERMINISTIC named
# checks itself (inline at --check, standalone via --verify). Those commands
# come from the stamped, smoke-run contract; a tree digest taken before and
# after the rerun fails check-mutated-tree if any check modified the tree.
# Verdicts for judged ACs still come from the checker seats (stored records,
# digest-bound). The gate remains the only authority on "done".
# Usage:
#   bash goal_gate.sh --check  [--project DIR]              # 0 GO / 2 NO-GO / 3 BLOCKED / 4 state error
#   bash goal_gate.sh --digest [--project DIR]              # print 12-hex tree digest
#   bash goal_gate.sh --verify [--project DIR] [AC-ID ...]  # rerun deterministic checks; 0 all-pass / 2 FAIL-or-broken / 4 state error
#   bash goal_gate.sh --baseline-check [--project DIR]      # forge contracts: baseline.md covers every delta metric AC; 0 ok / 2 problem
set -u
export LC_ALL=C.UTF-8

usage(){ sed -n '2,13p' "$0"; }

project="." mode="" positional=""
while [ $# -gt 0 ]; do
  case "$1" in
    --check)  mode=check ;;
    --digest) mode=digest ;;
    --verify) mode=verify ;;
    --baseline-check) mode=baseline ;;
    --project) [ $# -ge 2 ] || { echo "GATE: NO-GO reason=missing-project-arg" >&2; exit 4; }; project="$2"; shift ;;
    --help|-h) usage; exit 0 ;;
    -*) echo "GATE: NO-GO reason=unknown-flag:$1" >&2; exit 4 ;;
    *) positional="$positional $1" ;;                  # AC-IDs for --verify
  esac
  shift
done

[ -n "$mode" ] || { echo "GATE: NO-GO reason=no-mode (use --check, --digest, --verify or --baseline-check)" >&2; exit 4; }
[ -z "${positional# }" ] || [ "$mode" = verify ] || { echo "GATE: NO-GO reason=unknown-arg:$positional" >&2; exit 4; }

sd="$project/.goal"
r(){ tr -d '\r'; }                                    # CR scrubber for every read
hash_std(){                                            # one stable content hash
  if command -v sha1sum >/dev/null 2>&1; then sha1sum | cut -c1-40
  else cksum | awk '{print $1}'; fi
}

# Heavy third-party dirs skipped by the non-git tree walk (v2.6). Their bytes
# are not what an AC measures; including them made the digest O(whole-repo)
# per gate call. Override with GOAL_PRUNE="name name ...". .goalignore at the
# project root adds more prune names (one basename/dir per line). Semantics:
# skipped trees are invisible to the digest - that is the explicit trade, same
# spirit as .gitignore for a git digest.
prune_names(){ printf '%s\n' node_modules venv .venv __pycache__ dist build target out vendor .mypy_cache .pytest_cache; }
tree_digest(){                                         # 12 hex, deterministic
  ( cd "$project" 2>/dev/null || exit 4
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      { git rev-parse HEAD 2>/dev/null || echo none; git status --porcelain 2>/dev/null | r | sort; } | hash_std | cut -c1-12
    else
      prune=${GOAL_PRUNE:-}
      [ -z "$prune" ] && prune=$(prune_names | tr '\n' ' ')
      [ -f .goalignore ] && prune="$prune $(r < .goalignore | grep -vE '^[[:space:]]*(#|$)' | tr '\n' ' ')"
      args=(); i=0
      for p in $prune; do
        [ "$i" -gt 0 ] && args+=( -o )
        args+=( -name "$p" ); i=$((i+1))
      done
      # one xargs-fed sha1sum replaces a per-file bash spawn (the real cost);
      # paths stay in the hash so any content/rename change moves the digest.
      [ "$i" -gt 0 ] && set -- \( "${args[@]}" \) -prune -o
      # sort -z then one xargs-fed sha1sum replaces the per-file bash spawn
      # that used to dominate the digest (O(files) subshells -> O(batches)).
      find . \( "$@" -type f ! -path './.goal*' ! -path './.git*' -print0 \) 2>/dev/null |
      sort -z |
      xargs -0 -r sha1sum 2>/dev/null |
      sed -E 's/^([0-9a-f]{40})  (.*)$/\2 \1/' | sort | hash_std | cut -c1-12
    fi )
}

ac_body_hash(){                                        # 8 hex over AC body + ^exit: + ^objective: lines
  { r < "$sd/goal.md" |
    awk '/^## Acceptance criteria[ ]*$/{f=1;next} f&&/^## /{f=0} f'
    r < "$sd/goal.md" | grep -E '^(exit|objective):' || true
  } | hash_std | cut -c1-8
}

state_get(){                                           # $1 key -> value or empty
  [ -f "$sd/state.rec" ] || { echo ""; return; }
  grep -E "^$1=" "$sd/state.rec" | r | tail -1 | cut -d= -f2-
}

ledger_digest(){                                       # 8 hex over the LEDGER state files
  # Checks may write evidence (.goal/evidence/) but nothing else under
  # .goal/ (R6). The tree digest is blind to .goal, so the ledger gets its
  # own before/after guard - a check editing goal.md/state/verdicts mid-run
  # would otherwise measure one state and report another.
  { for f in goal.md state.rec loop-log.md verdicts.rec scores.rec work-plan.md baseline.md interfaces.md; do
      [ -f "$sd/$f" ] && { printf '%s\n' "$f"; r < "$sd/$f"; }
    done
  } | hash_std | cut -c1-8
}

last_block(){                                          # last loop-log block as key=value lines
  [ -f "$sd/loop-log.md" ] || return 1
  gawk '
    /^## iteration/{ split($0,a," "); cur=a[3]; order[++c]=cur; next }
    cur!="" { line=$0; sub(/\r$/,"",line)
      if (line ~ /=/) { p=index(line,"="); k=substr(line,1,p-1); v=substr(line,p+1); last[cur,k]=v } }
    END{ if (c==0) exit 5
      id=order[c]; printf "block_iteration=%s\n", id
      for (idx in last) { n=split(idx,parts,SUBSEP); if (n==2 && parts[1]==id) printf "%s=%s\n", parts[2], last[idx] }
    }' "$sd/loop-log.md"
}

latest_verdicts(){                                     # id|verdict|iter|digest|evidence, latest per id
  [ -f "$sd/verdicts.rec" ] || return 0
  gawk -F'|' '
    { id=$1; v=$2; it=$3+0; d=$4; e=$6; sub(/\r$/,"",e)
      if (!(id in best) || it >= best[id]) { best[id]=it; ver[id]=v; dig[id]=d; ev[id]=e } }
    END{ for (id in best) printf "%s|%s|%s|%s|%s\n", id, ver[id], best[id], dig[id], ev[id] }' "$sd/verdicts.rec"
}

fail(){
  # reason=$1 ; optional hint token routes the controller's next batch
  # (open-FAIL -> fix that AC's domain; not-covered -> dispatch the seat).
  # The hint is mechanical routing, not case knowledge.
  if [ "${deadline_expired:-0}" = 1 ]; then
    blocked "time-budget-exhausted (claim did not pass - stop burning time; extend = user-approved rewrite of deadline= in state.rec)"
  fi
  reason="$1"
  case "$reason" in
    open-FAIL:*)             hint=fix-AC ;;
    not-covered:*)           hint=bind-seat ;;
    check-broken:*)          hint=fix-instrument ;;
    probe-failed:*)          hint=fix-instrument ;;
    score-regressed:*)       hint=restore-best ;;
    not-dry:*)               hint=continue-forge ;;
    missing-strategy-delta*) hint=write-strategy-delta ;;
    verdicts-stale:*)        hint=rebind-judged ;;
    score-missing:*)         hint=objective-not-metric ;;
    not-claimed:*)           hint=set-exit-signal ;;
    not-claimed)             hint=set-exit-signal ;;   # bare reason, no AC suffix
    empty-loop-log)          hint=write-ledger-block ;;
    DIVERGENCE:*)            hint=redesign-AC ;;
    contract-tampered:*)     hint=proposal-to-user ;;
    calibration-missing:*)   hint=bind-calib-grades ;;
    calibration-*)           hint=fix-calib-fixture ;;
    time-budget-exhausted*)  hint=graceful-deliver ;;
    stagnation*|repeated-error*) hint=replan-or-stop ;;
    *)                       hint=see-reason ;;
  esac
  echo "GATE: NO-GO reason=$reason hint=$hint" >&2
  exit 2
}
blocked(){ echo "GATE: BLOCKED reason=$1" >&2; exit 3; }
# time-budget fuse: a wall-clock overrun must not confiscate completed work.
# 1) green claim still delivers (GO + NOTE); 2) any failure after the fuse
# escalates to BLOCKED so the loop stops instead of grinding another wave.
deadline_expired=0
state_err(){ echo "GATE: ERROR reason=$1" >&2; exit 4; }

# ---- contract parsing (v1.2) ----------------------------------------------
# AC line grammar:  - AC-N | statement | check: `<command>` | expected: <spec>
# expected spec: exit=0 (default) | <op><number> | judged      (no "|" inside)
# AC lines are NOT parsed by "|" splitting (commands contain pipes); the
# command is the backtick-quoted span, the expectation is the line tail.
contract_mode(){ r < "$sd/goal.md" | grep -qE '^exit: *forge' && echo forge || echo threshold; }
all_ac_ids(){ r < "$sd/goal.md" | grep -oE '^- AC-[0-9]+' | sort -u | sed 's/^- //'; }
ac_line_for(){ r < "$sd/goal.md" | awk -v id="$1" '$0 ~ "^- "id"[ |]"'; }
ac_check_cmd(){ ac_line_for "$1" | sed -nE 's/^.*check: *`([^`]*)`.*/\1/p' | tail -1; }
ac_expected(){ ac_line_for "$1" | sed -nE 's/^.*expected: *([^|]*)[[:space:]]*$/\1/p' | tail -1; }
ac_baseline_marker(){ ac_line_for "$1" | sed -nE 's/^.*baseline: *(delta|abs).*/\1/p' | tail -1; }
# Verifier-of-the-verifier (R9): any metric/maximize/minimize AC may carry a probe:
# check that must PASS before its number is trusted. The probe asserts the
# measurement itself (instrument alive, fixture loaded, seed fixed).
ac_probe_cmd(){ ac_line_for "$1" | sed -nE 's/^.*probe: *`([^`]*)`.*/\1/p' | tail -1; }
# Optional measurement tokens (v2.5): `metric: ` <ERE with exactly one capture
# group> pins WHERE the number comes from (immune to log noise / multi-number
# output); tolerance: <rel> absorbs measurement noise in water-mark compares.
ac_metric_re(){ ac_line_for "$1" | sed -nE 's/^.*metric: *`([^`]*)`.*/\1/p' | tail -1; }
ac_tolerance(){ ac_line_for "$1" | sed -nE 's/^.*tolerance: *([0-9.]+).*/\1/p' | tail -1; }
# Calibration fixtures (v2.6, judged ACs): `calib: good=<f1> bad=<f2>` names a
# known-good and a known-bad artifact of the AC's subject. A seat may claim
# PASS only after grading both correctly (#good=PASS, #bad=FAIL, same
# iteration+digest). A too-lenient seat passes the good fixture but fails the
# bad one, and the claim is refused mechanically.
ac_calib_good(){ ac_line_for "$1" | sed -nE 's/^.*calib:[^|]*good *= *([^ |]+).*/\1/p' | tail -1; }
ac_calib_bad(){ ac_line_for "$1"  | sed -nE 's/^.*calib:[^|]*bad *= *([^ |]+).*/\1/p' | tail -1; }
ac_calib_declared(){ ac_line_for "$1" | grep -qE 'calib:[^|]*(good|bad) *=' && echo yes || echo no; }
sha256_std(){                                           # one file -> 64 hex
  if command -v sha256sum >/dev/null 2>&1; then sha256sum < "$1" | cut -c1-64
  elif command -v openssl >/dev/null 2>&1; then openssl dgst -sha256 "$1" | awk '{print $NF}'
  else echo ""; fi
}
strip_ansi(){                                           # colored CLIs must not cut the metric regex
  gawk '{ gsub(/\033\[[0-9;?]*[A-Za-z]/, "", $0); print }'
}
extract_metric(){                                       # $1 text $2 regex-or-empty -> number or empty
  # regex via ENVIRON: -v would eat backslashes in the user's ERE. The pipeline
  # needs an EXPORT (assignment on the first command covers only printf).
  [ -n "$2" ] || return 0
  export MRE="$2"
  printf '%s\n' "$1" | gawk '{
    if (match($0, ENVIRON["MRE"], m)) {
      for (i = 1; i <= length(m); i++) if (m[i] != "") { print m[i]; exit }
    }
  }' | sed -nE 's/^[^-0-9]*(-?[0-9]+(\.[0-9]+)?).*/\1/p' | head -1
  # the leading-chars class must keep '-', or a captured "-10" is rewritten to 10
}
# Optional contract-level objective: maximize|minimize AC-N  (score-regressed guard).
# objective_dir: "maximize" (higher is better) or "minimize" (lower is better).
objective_ac(){ r < "$sd/goal.md" | sed -nE 's/^objective: *(maximize|minimize) +(AC-[0-9]+).*/\2/p' | tail -1; }
objective_dir(){ r < "$sd/goal.md" | sed -nE 's/^objective: *(maximize|minimize) +(AC-[0-9]+).*/\1/p' | tail -1; }
# Baseline validation (forge only): every delta metric AC needs a
# .goal/baseline.md line `AC-N | ... | repeats=<N>=2 | cmd=<check verbatim>`.
# The cmd match is the "same yardstick" rule made mechanical; repeats>=2
# mechanizes the noise-floor discipline. Absent marker -> delta.
baseline_validate(){                                   # fail-fast via fail(); forge paths only
  need=0
  for id in $(all_ac_ids); do
    cls=$(classify_expected "$(ac_expected "$id")")
    case "$cls" in metric*) [ "$(ac_baseline_marker "$id")" = abs ] || need=1 ;; esac
  done
  [ "$need" = 1 ] || return 0                          # no delta metric AC -> no baseline owed
  bl="$sd/baseline.md"
  [ -f "$bl" ] || fail "missing-baseline (forge: run every metric check against the pre-work artifact - the smoke run IS the measurement - and write .goal/baseline.md: AC-id | observed=<v> | repeats=<N>=2 | cmd=<check verbatim>)"
  for id in $(all_ac_ids); do
    cls=$(classify_expected "$(ac_expected "$id")")
    case "$cls" in metric*) : ;; *) continue ;; esac
    [ "$(ac_baseline_marker "$id")" = abs ] && continue
    cmd=$(ac_check_cmd "$id")
    line=$(r < "$bl" | grep -E "^$id \|.*cmd=" | tail -1)
    [ -n "$line" ] || fail "missing-baseline:$id (no baseline row for a delta metric AC)"
    bcmd=$(printf '%s' "$line" | sed -nE 's/^.* cmd=(.*)[[:space:]]*$/\1/p')
    [ "$bcmd" = "$cmd" ] || fail "baseline-cmd-mismatch:$id (baseline must be measured by the AC's own check command, verbatim)"
    rep=$(printf '%s' "$line" | sed -nE 's/^.* repeats=([0-9]+).*$/\1/p')
    { [ -n "$rep" ] && [ "$rep" -ge 2 ]; } || fail "baseline-weak:$id (repeats>=2 required - single runs game the metric)"
  done
}
classify_expected(){                                   # $1 raw -> exit0 | judged | maximize | minimize | "metric <op> <num>"
  v=$(printf '%s' "$1" | tr -d '[:space:]')
  case "$v" in
    ''|exit=0) echo "exit0" ;;
    judged)    echo "judged" ;;
    maximize)  echo "maximize" ;;
    minimize)  echo "minimize" ;;
    exit=[0-9]*) echo "rc ${v#exit=}" ;;
    *)
      op=$(printf '%s' "$v" | sed -nE 's/^([<>=!]+)[0-9].*/\1/p')
      num=$(printf '%s' "$v" | sed -nE 's/^[<>=!]+([0-9][0-9.]*)$/\1/p')
      if [ -n "$op" ] && [ -n "$num" ]; then
        case "$op" in
          '>='|'<='|'>'|'<'|'=='|'!=') echo "metric $op $num"; return ;;
        esac
      fi
      echo "judged" ;;                                 # prose (incl. v1.1) -> judged
  esac
}

run_one_check(){                                       # $1 id $2 class $3 op $4 num -> "id|VERDICT|detail"
  id="$1"; cls="$2"; m_op="${3:-}"; m_num="${4:-}"
  cmd=$(ac_check_cmd "$id")
  if [ -z "$cmd" ]; then printf '%s|BROKEN|no check command in AC line\n' "$id"; return; fi
  # R9 verifier-of-the-verifier: metric/maximize numbers are untrustworthy
  # unless their probe (instrument alive) passes first.
  case "$cls" in metric*|maximize|minimize)
    pcmd=$(ac_probe_cmd "$id")
    if [ -n "$pcmd" ]; then
      perr=$(mktemp "${TMPDIR:-/tmp}/goal-probe-err.XXXXXX" 2>/dev/null) || perr=/tmp/probe-err.$$
      if command -v timeout >/dev/null 2>&1; then
        ( cd "$project" 2>/dev/null && timeout "$tmo" bash -c "$pcmd" >/dev/null 2>"$perr" )
      else
        ( cd "$project" 2>/dev/null && bash -c "$pcmd" >/dev/null 2>"$perr" )
      fi
      prc=$?
      perr_tail=$(r < "$perr" | tail -2 | tr '\n' ' ' | sed 's/[[:space:]]*$//' | cut -c1-120)
      rm -f "$perr"
      if [ "$prc" -ne 0 ]; then
        printf '%s|BROKEN|probe-failed:rc=%s (measurement untrusted - fix the instrument before the number) %s\n' "$id" "$prc" "$perr_tail"
        return
      fi
    fi ;;
  esac
  # stdout stays the MEASUREMENT channel; stderr is captured to a side file so
  # a failure is never diagnosed by guessing (an eval system that says "failed"
  # with no reason violates fail-loud). Streams stay separated on purpose.
  gate_err=$(mktemp "${TMPDIR:-/tmp}/goal-gate-err.XXXXXX" 2>/dev/null) || gate_err=/tmp/gate-err.$$
  if command -v timeout >/dev/null 2>&1; then
    out=$(cd "$project" 2>/dev/null && timeout "$tmo" bash -c "$cmd" 2>"$gate_err"); rc=$?
  else
    out=$(cd "$project" 2>/dev/null && bash -c "$cmd" 2>"$gate_err"); rc=$?   # without coreutils timeout a hang hangs; documented
  fi
  err_tail=$(r < "$gate_err" | tail -3 | tr '\n' ' ' | sed 's/[[:space:]]*$//' | cut -c1-160)
  rm -f "$gate_err"
  [ -n "$err_tail" ] || err_tail=""
  out=$(printf '%s\n' "$out" | r)                    # CR scrub: Windows-native checks print CRLF
  metric=$(ac_metric_re "$id")
  if [ -n "$metric" ]; then
    clean=$(printf '%s\n' "$out" | strip_ansi)
    mval=$(extract_metric "$clean" "$metric")
  else
    mval=""
  fi
  case "$cls" in
    exit0)
      if [ "$rc" -eq 0 ]; then printf '%s|PASS|exit=0\n' "$id"
      elif [ "$rc" -eq 127 ] || [ "$rc" -eq 124 ]; then printf '%s|BROKEN|check not executable (rc=%d) %s\n' "$id" "$rc" "$err_tail"
      elif [ "$rc" -gt 128 ]; then printf '%s|BROKEN|check killed (rc=%d, signal) %s\n' "$id" "$rc" "$err_tail"
      else printf '%s|FAIL|exit=%d %s\n' "$id" "$rc" "$err_tail"; fi ;;
    rc\ *)                                            # negative assertion: rc==N passes
      want=${cls#rc }
      if [ "$rc" -eq "$want" ]; then printf '%s|PASS|exit=%d\n' "$id" "$rc"
      elif [ "$rc" -eq 124 ] && [ "$want" != 124 ]; then printf '%s|BROKEN|timed out (rc=124) %s\n' "$id" "$err_tail"
      elif [ "$rc" -eq 127 ] && [ "$want" != 127 ]; then printf '%s|BROKEN|check not executable (rc=127) %s\n' "$id" "$err_tail"
      else printf '%s|FAIL|exit=%d expect=exit=%s %s\n' "$id" "$rc" "$want" "$err_tail"; fi ;;
    metric\ *)
      last="$mval"
      if [ -z "$last" ] && [ -n "$metric" ]; then
        printf '%s|BROKEN|metric regex matched nothing: %s %s\n' "$id" "$metric" "$err_tail"; return
      fi
      if [ -z "$last" ]; then
        last=$(printf '%s\n' "$out" | strip_ansi | grep -vE '^[[:space:]]*$' | tail -1)
      fi
      case "$last" in
        ''|*[!0-9.\-]*)
          printf '%s|BROKEN|no number in output (metric or last line): %s\n' "$id" "${last:-<empty>}"; return ;;
      esac
      v=$(awk -v a="$last" -v b="$m_num" -v o="$m_op" \
          'BEGIN{ok=(o==">=")?(a>=b):(o=="<=")?(a<=b):(o==">")?(a>b):(o=="<")?(a<b):(o=="==")?(a==b):(a!=b); print ok?"PASS":"FAIL"}')
      printf '%s|%s|observed=%s expect=%s%s\n' "$id" "$v" "$last" "$m_op" "$m_num" ;;
    maximize)
      last="$mval"
      if [ -z "$last" ] && [ -n "$metric" ]; then
        printf '%s|BROKEN|metric regex matched nothing: %s %s\n' "$id" "$metric" "$err_tail"; return
      fi
      if [ -z "$last" ]; then
        last=$(printf '%s\n' "$out" | strip_ansi | grep -vE '^[[:space:]]*$' | tail -1)
      fi
      case "$last" in
        ''|*[!0-9.\-]*)
          printf '%s|BROKEN|no number in output: %s %s\n' "$id" "${last:-<empty>}" "$err_tail"; return ;;
      esac
      # maximize is the objective, not a floor: numeric = PASS. The score
      # itself is compared to best_score by the caller (score-regressed).
      printf '%s|PASS|observed=%s expect=maximize\n' "$id" "$last" ;;
    minimize)
      last="$mval"
      if [ -z "$last" ] && [ -n "$metric" ]; then
        printf '%s|BROKEN|metric regex matched nothing: %s %s\n' "$id" "$metric" "$err_tail"; return
      fi
      if [ -z "$last" ]; then
        last=$(printf '%s\n' "$out" | strip_ansi | grep -vE '^[[:space:]]*$' | tail -1)
      fi
      case "$last" in
        ''|*[!0-9.\-]*)
          printf '%s|BROKEN|no number in output: %s %s\n' "$id" "${last:-<empty>}" "$err_tail"; return ;;
      esac
      # minimize: the objective is to push the number DOWN. Numeric = PASS;
      # the low-water mark is enforced by the caller (score-regressed).
      printf '%s|PASS|observed=%s expect=minimize\n' "$id" "$last" ;;
    *)
      printf '%s|BROKEN|unroutable expectation class\n' "$id" ;;
  esac
}

digest=$(tree_digest) || state_err "unreadable-project"
# ledger state before the rerun batch (the tree guard is blind to .goal/)
[ -d "$sd" ] && ld_check0=$(ledger_digest) || ld_check0=none
if [ "$mode" = digest ]; then echo "$digest"; exit 0; fi

# -0. state present and complete -----------------------------------------
[ -d "$sd" ] || state_err "no-goal-dir"
[ -f "$sd/goal.md" ] || state_err "no-goal-md"
tmo=$(state_get check_timeout); [ -n "$tmo" ] || tmo=120
case "$tmo" in ''|*[!0-9]*) state_err "bad-check-timeout:$tmo" ;; esac

if [ "$mode" = verify ]; then
  # an AC id that is not in the contract is a usage error, not a verdict -
  # silently "skipping" a typo'd id would let --verify AC-9 report all-clear
  # while the real ACs were never measured.
  for rid in $positional; do
    printf '%s\n' "$(all_ac_ids)" | grep -qx "$rid" \
      || { echo "GATE: NO-GO reason=unknown-ac-id:$rid (no such AC in the contract)" >&2; exit 4; }
  done
  want="$positional "
  d0="$digest"; ld0=$(ledger_digest); nfail=0; nbroken=0; nchecked=0
  for id in $(all_ac_ids); do
    if [ -n "${want// /}" ]; then case "$want" in *" $id "*) ;; *) continue ;; esac; fi
    cls=$(classify_expected "$(ac_expected "$id")")
    if [ "$cls" = judged ]; then echo "GATE: VERIFY $id|SKIP|judged"; continue; fi
    line=$(run_one_check "$id" "$cls" ${cls#metric})
    echo "GATE: VERIFY $line"
    nchecked=$((nchecked+1))
    case "$line" in
      *'|FAIL|'*)   nfail=$((nfail+1)) ;;
      *'|BROKEN|'*) nbroken=$((nbroken+1)) ;;
    esac
  done
  d1=$(tree_digest)
  [ "$d0" = "$d1" ] || { echo "GATE: NO-GO reason=check-mutated-tree:before=$d0 after=$d1" >&2; exit 2; }
  # the ledger is digest-excluded from the tree, so a check editing goal.md /
  # state.rec / verdicts.rec mid-rerun is invisible to the tree guard: same
  # before/after rule, over the LEDGER state files (evidence/ stays free).
  ld1=$(ledger_digest)
  [ "$ld0" = "$ld1" ] || { echo "GATE: NO-GO reason=check-mutated-ledger:before=$ld0 after=$ld1 (a check wrote the ledger mid-run - only .goal/evidence/ is fair game)" >&2; exit 2; }
  [ "$nchecked" -gt 0 ] || { echo "GATE: VERIFY-OK nothing-deterministic"; exit 0; }
  if [ $((nfail+nbroken)) -eq 0 ]; then echo "GATE: VERIFY-OK checked=$nchecked"; exit 0; fi
  echo "GATE: NO-GO reason=verify-failures:fail=$nfail broken=$nbroken" >&2
  exit 2
fi

if [ "$mode" = baseline ]; then
  # stamp-time validation: contract + baseline.md only; no state needed
  contract_mode=$(contract_mode)
  if [ "$contract_mode" != forge ]; then echo "GATE: BASELINE-OK not-forge"; exit 0; fi
  baseline_validate
  echo "GATE: BASELINE-OK"
  exit 0
fi

required="iteration breaker false_completes replans no_progress_streak max_iterations no_progress_limit"
for k in $required; do
  [ -n "$(state_get "$k")" ] || state_err "missing-key:$k"
done
exit_mode=$(contract_mode)
if [ "$exit_mode" = forge ]; then
  for k in dry_streak dry_limit; do
    [ -n "$(state_get "$k")" ] || state_err "missing-key:$k (required for exit: forge)"
  done
fi
iter=$(state_get iteration); breaker=$(state_get breaker)
fc=$(state_get false_completes); streak=$(state_get no_progress_streak)
maxit=$(state_get max_iterations); npl=$(state_get no_progress_limit)
# the numeric counters must actually be numbers (a corrupted or hand-edited
# state.rec with iteration=banana must never reach an arithmetic comparison);
# breaker is the only word-valued key in this set.
for k in iteration false_completes no_progress_streak max_iterations no_progress_limit replans; do
  case "$(state_get "$k")" in
    ''|*[!0-9]*) state_err "unparseable-state:$k=$(state_get "$k") (numeric key not numeric)" ;;
  esac
done
case "$breaker" in CLOSED|HALF_OPEN|OPEN) : ;; *) state_err "unparseable-state:breaker=$breaker" ;; esac

# -1. contract frozen by a matching stamp (R3) ----------------------------
stamp=$(r < "$sd/goal.md" | grep -E '^approved: [0-9a-f]{6,}' | tail -1 | awk '{print $2}')
[ -n "$stamp" ] || fail "no-approval"
body=$(ac_body_hash)
[ "${stamp:0:8}" = "$body" ] || fail "contract-tampered:stam=$stamp recomputed=$body"

# -2..-4b. breaker, budget (forge: fuse), stagnation, grind ---------------
[ "$breaker" = OPEN ] && blocked "breaker-open"
[ "${fc:-0}" -ge 2 ] && blocked "false-completes>=2"
dl=$(state_get deadline)                               # optional wall-clock fuse (v1.3)
case "$dl" in
  ''|0) : ;;
  *[!0-9]*) state_err "bad-deadline:$dl" ;;
  *) now=$(date +%s)
     # Overrun is a CONTINUATION fuse, not a delivery veto: flag it here;
     # fail() escalates to BLOCKED, a green claim still GO (see fail/GO).
     [ "$now" -gt "$dl" ] && deadline_expired=1 ;;
esac
if [ "$exit_mode" = forge ]; then
  [ "${iter:-0}" -le "${maxit:-12}" ] || blocked "budget-fuse:iter=$iter max=$maxit (forge: budget is a fuse - extend it or deliver best-so-far)"
  baseline_validate                                   # belt+braces: baseline.md must still cover every delta metric AC
else
  [ "${iter:-0}" -le "${maxit:-12}" ] || fail "budget-exhausted:iter=$iter max=$maxit"
fi
[ "${streak:-0}" -le "${npl:-2}" ] || blocked "stagnation:streak=$streak limit=$npl"

# -4b. repeated-error grind (SKILL.md phase 2 step 8, mechanized): the last
# two loop blocks carrying the SAME non-none error_signature means the loop
# is grinding on one wall -> BLOCKED, hand back. none/empty never triggers.
sigs=$(awk '
  /^## iteration/ { if (cur != "") prev = cursig; cur = $3; cursig = ""; next }
  cur != "" { line = $0; sub(/\r$/, "", line)
              if (line ~ /^error_signature=/) { p = index(line, "="); cursig = substr(line, p + 1) } }
  END { print prev; print cursig }' "$sd/loop-log.md" 2>/dev/null)
sig_a=$(printf '%s\n' "$sigs" | sed -n '1p')
sig_b=$(printf '%s\n' "$sigs" | sed -n '2p')
if [ -n "$sig_a" ] && [ -n "$sig_b" ] && [ "$sig_a" = "$sig_b" ] && [ "$sig_b" != "none" ]; then
  blocked "repeated-error:sig=$sig_b"
fi

# -5..-9. dual condition on the last loop block + verdicts (R1,R5,R7) ----
lb=$(last_block) || fail "empty-loop-log"
# Canonical loop-log key set (schema doc: references/gate.md section 1).
# last_block() consumes key=value lines generically, so the set is declared
# here: it keeps parser and schema doc mutually named and advisory-checks
# presence (exit codes unchanged; exit_signal and digest stay hard-checked).
loop_keys="task files_modified checks_pass checks_fail checks_unverifiable error_signature progress exit_signal false_complete digest score strategy_delta"
missing_lk=""
for k in $loop_keys; do
  printf '%s\n' "$lb" | grep -qE "^$k=" || missing_lk="$missing_lk $k"
done
[ -z "$missing_lk" ] || echo "GATE: NOTE loop-log-missing-keys:${missing_lk# }" >&2
claim=$(printf '%s\n' "$lb" | grep -E '^exit_signal=' | tail -1 | cut -d= -f2-)
[ "$claim" = yes ] || fail "not-claimed"
lbdigest=$(printf '%s\n' "$lb" | grep -E '^digest=' | tail -1 | cut -d= -f2-)
# A stale claim IS a false complete; the ratchet (ctl close-iteration) counts
# it automatically - no manual bookkeeping asked of the controller anymore.
[ "$lbdigest" = "$digest" ] || { echo "GATE: NOTE false-complete suspected; already counted by the ratchet - fix the artifact and let the claim pass, do not re-claim unchanged" >&2; fail "verdicts-stale:block=$lbdigest current=$digest"; }

ac_ids=$(all_ac_ids)
[ -n "$ac_ids" ] || fail "contract-empty:no AC ids"
# a duplicated AC id is never silently resolved (the parser would pick one of
# the two lines by luck): same id twice = malformed contract.
dups=$(r < "$sd/goal.md" | grep -oE '^- AC-[0-9]+' | sort | uniq -d)
[ -z "$dups" ] || fail "contract-malformed:duplicate AC id(s): ${dups#- } (one line per AC id)"
# fail-closed contract sanity: an AC line whose expected:/check: tokens are
# missing (typo'd or half-written) must never silently default to exit=0 and
# get a free PASS - a silent hole in the eval surface is the worst defect class.
for id in $ac_ids; do
  [ -n "$(ac_expected "$id")" ] || fail "contract-malformed:$id (no expected: token - write expected: exit=0|<op><num>|maximize|minimize|judged)"
  [ -n "$(ac_check_cmd "$id")" ] || fail "contract-malformed:$id (no check: \`command\` - every AC needs a failable named check)"
done
lv=$(latest_verdicts)
total=0; passn=0; unv=0
observed_score=""
primary=$(objective_ac)
for id in $ac_ids; do
  cls=$(classify_expected "$(ac_expected "$id")")
  if [ "$cls" != judged ]; then
    # Deterministic AC: the gate reruns the check NOW. Stored verdicts for
    # these ids are mid-loop bookkeeping only; the rerun is the evidence.
    line=$(run_one_check "$id" "$cls" ${cls#metric})
    v=$(printf '%s' "$line" | cut -d'|' -f2)
    detail=$(printf '%s' "$line" | cut -d'|' -f3-)
    case "$v" in
      PASS)   total=$((total+1)); passn=$((passn+1))
              if [ "$id" = "$primary" ]; then
                observed_score=$(printf '%s' "$detail" | sed -nE 's/.*observed=([0-9.\-]+).*/\1/p' | tail -1)
              fi ;;
      FAIL)   fail "open-FAIL:$id (gate rerun: $detail)" ;;
      BROKEN) fail "check-broken:$id ($detail)" ;;
      *)      fail "check-unknown:$id ($line)" ;;
    esac
    continue
  fi
  # Judged AC: the stored seat verdict must be fresh (R7) and evidenced (R5).
  rec=$(printf '%s\n' "$lv" | gawk -F'|' -v want="$id" '$1==want{print}')
  v=$(printf '%s' "$rec" | cut -d'|' -f2)
  vi=$(printf '%s' "$rec" | cut -d'|' -f3)
  vd=$(printf '%s' "$rec" | cut -d'|' -f4)
  ev=$(printf '%s' "$rec" | cut -d'|' -f5-)
  [ -n "$v" ] || fail "not-covered:$id"
  [ "$vi" = "$iter" ] && [ "$vd" = "$digest" ] || fail "not-covered:$id (verdict bound to iter=$vi digest=$vd)"
  [ "$v" != FAIL ] || fail "open-FAIL:$id"
  total=$((total+1))
  if [ "$v" = PASS ]; then
    [ -n "$ev" ] || fail "evidence-missing:$id"
    # Mechanical binding (v2.5): the evidence must cite the exact artifact it
    # saw - `artifact: <path>` and `digest: <sha256-hex>`. The gate recomputes
    # and compares. A verdict that does not name what it examined, or names a
    # file whose bytes changed since, is worthless: verdict-unbound.
    # greedy match to the digest: token - artifact paths with spaces are
    # legal file names; stopping at whitespace silently loses the path.
    art=$(printf '%s' "$ev" | sed -nE 's/^.*artifact:[[:space:]]*(.*[^[:space:]])[[:space:]]+digest:.*/\1/p' | head -1)
    [ -n "$art" ] || art=$(printf '%s' "$ev" | grep -oE 'artifact:[[:space:]]*[^[:space:]]+' | head -1 | sed -E 's/^artifact:[[:space:]]*//')
    dig=$(printf '%s' "$ev" | grep -oE 'digest:[[:space:]]*(sha256:)?[a-f0-9]{8,64}' | head -1 | sed -E 's/^digest:[[:space:]]*(sha256:)?//')
    [ -n "$art" ] && [ -n "$dig" ] || fail "verdict-unbound:$id (PASS evidence must cite artifact: <path> and digest: <sha256> - the seat must say WHAT it judged)"
    if [ -f "$project/$art" ]; then
      now=$(sha256_std "$project/$art")
      case "$now" in "$dig"*) : ;; *) fail "verdict-unbound:$id (artifact $art changed since the verdict - digest mismatch)" ;; esac
    else
      fail "verdict-unbound:$id (artifact file $art not found)"
    fi
    # Calibration gate (v2.6, R9 applied to the judgment plane): if the AC
    # declared fixtures, the seat owed correct grades on both. A declared
    # fixture that never exists is a BROKEN instrument (fail-loud), never a
    # silent exemption - same fail-closed rule as metric probes.
    cg=$(ac_calib_good "$id"); cb=$(ac_calib_bad "$id")
    if [ -n "$cg" ] || [ -n "$cb" ]; then
      [ -n "$cg" ] && [ -n "$cb" ] || fail "calibration-malformed:$id (calib: needs BOTH good= and bad= fixtures)"
      [ -f "$project/$cg" ] || fail "calibration-broken:$id (good fixture $cg not found - instrument, not artifact)"
      [ -f "$project/$cb" ] || fail "calibration-broken:$id (bad fixture $cb not found - instrument, not artifact)"
      # fixtures are TREE state: their bytes must match the binding - reuse
      # the same verdict-unbound machinery per fixture via the ledger rule.
      g_rec=$(printf '%s\n' "$lv" | gawk -F'|' -v want="$id#good" '$1==want{print}')
      b_rec=$(printf '%s\n' "$lv" | gawk -F'|' -v want="$id#bad"  '$1==want{print}')
      gv=$(printf '%s' "$g_rec" | cut -d'|' -f2); gvi=$(printf '%s' "$g_rec" | cut -d'|' -f3); gvd=$(printf '%s' "$g_rec" | cut -d'|' -f4)
      bv=$(printf '%s' "$b_rec" | cut -d'|' -f2); bvi=$(printf '%s' "$b_rec" | cut -d'|' -f3); bvd=$(printf '%s' "$b_rec" | cut -d'|' -f4)
      # Evidence must name the fixture the grade was read from (R5 spirit):
      # an unbound grade is an invented grade, same as an unbound PASS.
      gve=$(printf '%s' "$g_rec" | cut -d'|' -f5-)
      bve=$(printf '%s' "$b_rec" | cut -d'|' -f5-)
      { [ "$gv" = PASS ] && [ "$gvi" = "$iter" ] && [ "$gvd" = "$digest" ] && printf '%s' "$gve" | grep -qF "$cg"; } \
        || fail "calibration-missing:$id/good (needs a fresh PASS verdict this iteration whose evidence quotes the good fixture $cg)"
      { [ "$bv" = FAIL ] && [ "$bvi" = "$iter" ] && [ "$bvd" = "$digest" ] && printf '%s' "$bve" | grep -qF "$cb"; } \
        || fail "calibration-missing:$id/bad (known-bad fixture $cb needs a fresh FAIL verdict in the current iteration - a seat that cannot reject the bad case cannot be trusted on the real one)"
    fi
    passn=$((passn+1))
  elif [ "$v" = UNVERIFIABLE ]; then
    case "$ev" in *PROBE=*REASON=*) ;; *) fail "evidence-missing:$id (PROBE/REASON required)" ;; esac
    unv=$((unv+1))
  else
    fail "bad-verdict:$id=$v"
  fi
done
[ $((unv*3)) -le "$total" ] || fail "unverifiable-excessive:unv=$unv total=$total"

# -10. guard against checks that mutated the tree mid-verification --------
digest2=$(tree_digest)
[ "$digest" = "$digest2" ] || fail "check-mutated-tree:before=$digest after=$digest2"
# .goal is digest-excluded from the tree, so the tree guard is blind there:
# a check editing goal.md/state.rec/verdicts.rec mid-run would measure one
# state and report another while leaving the tree pristine. The ledger gets
# its own before/after digest; evidence/ is the only directory checks may
# write (R6), so it stays out of the hash.
ld2=$(ledger_digest)
[ "$ld_check0" = "$ld2" ] || fail "check-mutated-ledger:before=$ld_check0 after=$ld2 (a check wrote the ledger mid-run - only .goal/evidence/ is fair game)"

# -11. forge: floors alone are not an exit; exhaustion is -----------------
if [ "$exit_mode" = forge ]; then
  dry=$(state_get dry_streak); dl=$(state_get dry_limit)
  [ "${dry:-0}" -ge "${dl:-3}" ] || fail "not-dry:dry_streak=${dry:-0} limit=$dl (forge exits on verification exhaustion, not on floors alone)"
fi

# -12. strategy-delta duty (R10): landing on HALF_OPEN without a recorded
# strategy change is make-work; refuse the claim until one is written.
if [ "$breaker" = HALF_OPEN ]; then
  sdelt=$(printf '%s\n' "$lb" | grep -E '^strategy_delta=' | tail -1 | cut -d= -f2-)
  case "$sdelt" in
    ''|none) fail "missing-strategy-delta (breaker=HALF_OPEN requires strategy_delta= <what you are changing>)" ;;
  esac
fi

# -13. optimize objective: never deliver a score worse than the best seen (R11).
# direction: maximize = high-water mark (current >= best);
#            minimize = low-water mark  (current <= best).
if [ -n "$primary" ]; then
  [ -n "$observed_score" ] || fail "score-missing:$primary (objective score needs a numeric observed score)"
  best=$(state_get best_score)
  pdir=$(objective_dir); [ -n "$pdir" ] || pdir=maximize
  # Relative tolerance absorbs benchmark noise (same code varies +-5% across
  # runs; an exact water-mark would false-alarm "regressed" every round and
  # teach the controller to distrust the metric). Inside the noise band the
  # score is treated as holding, not moving.
  tol=$(ac_tolerance "$primary"); case "$tol" in ''|*[!0-9.]*) tol=0 ;; esac
  if [ -n "$best" ] && [ "$best" != "none" ]; then
    # Noise band = b +/- |b|*t. Multiplying (1-t)*b flips the band on
    # NEGATIVE water marks (b=-10,t=.1 -> band -9, so -10 reads "regressed");
    # absolute value keeps the band on the correct side in every sign.
    if [ "$pdir" = minimize ]; then
      awk -v c="$observed_score" -v b="$best" -v t="$tol" 'BEGIN{a=(b<0)?-b:b; exit !(c+0 <= b+0 + a*t)}' \
        || fail "score-regressed:current=$observed_score best=$best dir=minimize tol=$tol (restore the best-scoring state or do not claim)"
    else
      awk -v c="$observed_score" -v b="$best" -v t="$tol" 'BEGIN{a=(b<0)?-b:b; exit !(c+0 >= b+0 - a*t)}' \
        || fail "score-regressed:current=$observed_score best=$best dir=maximize tol=$tol (restore the best-scoring state or do not claim)"
    fi
  fi
fi

# -14. score<->judge divergence (R13): the objective may improve while the
# cold seat falls - that is optimizing the wrong thing. Compare the last two
# comparable points in .goal/scores.rec (iter|score|judge, both numeric).
# Quality direction: maximize -> higher score is better; minimize -> lower
# score is better. Judge score is always higher-is-better. Opposite quality
# directions -> refuse the claim. Flat is "unverified movement", not
# divergence; <2 comparable points -> skip (no pair to compare).
if [ -f "$sd/scores.rec" ]; then
  rdir=$(objective_dir); [ -n "$rdir" ] || rdir=maximize
  pair=$(r < "$sd/scores.rec" | awk -F'|' '
    $2 ~ /^-?[0-9]+(\.[0-9]+)?$/ && $3 ~ /^-?[0-9]+(\.[0-9]+)?$/ {
      s1=s2; j1=j2; s2=$2+0; j2=$3+0; n++
    }
    END { if (n >= 2) printf "%s %s %s %s\n", s1, j1, s2, j2 }')
  if [ -n "$pair" ]; then
    set -- $pair
    awk -v s1="$1" -v j1="$2" -v s2="$3" -v j2="$4" -v d="$rdir" \
      'BEGIN{
        sd = (d=="minimize") ? (s1-s2) : (s2-s1);   # quality delta of score
        jd = j2-j1;                                  # quality delta of judge
        exit !(sd*jd < 0)
      }' \
      && fail "DIVERGENCE:score-vs-judge score:$1->$3 judge:$2->$4 dir=$rdir (objective and cold-seat moving apart - the metric is pulling away from perceived quality; redesign the AC or the direction)"
  fi
fi

if [ "${deadline_expired:-0}" = 1 ]; then
  echo "GATE: NOTE time-budget-exhausted (graceful delivery of passing work)"
fi
# Eval self-hardening notes (v2.5, advisory only - never block a GO).
# 1) Static tautology suspects: deterministic checks whose command cannot fail
#    (bare true/echo/cat) would pass every round and make the gate decorative.
#    judged ACs are exempt (their check generates evidence, the seats judge).
taut=""
for id in $ac_ids; do
  cls=$(classify_expected "$(ac_expected "$id")")
  [ "$cls" = judged ] && continue
  cmd=$(ac_check_cmd "$id")
  # cannot-fail shapes only: bare true/:/echo with no pipes, no test, no
  # redirects (cat/echo file can fail - missing artifact is a real outcome).
  if printf '%s' "$cmd" | grep -qE '^(true|:|:)[[:space:]]*$' ||
     printf '%s' "$cmd" | grep -qE '^echo [^|<>]*$'; then
    taut="$taut $id"
  fi
done
[ -z "$taut" ] || echo "GATE: NOTE tautology-suspect:${taut# } (check cannot fail across rounds - strengthen it or the gate is decorative)" >&2
# 2) Metric-flat: the objective score has sat at the water-mark for >=3
#    rounds - a ceiling metric with delta-style ambitions is unreachable and
#    the loop grinds. (Same code, same number: flat is not regressed.)
if [ -n "$primary" ] && [ -f "$sd/scores.rec" ] && [ -n "$observed_score" ]; then
  # count trailing rows pinned to the current score
  flat=$(r < "$sd/scores.rec" | awk -F'|' -v s="$observed_score" '
    { if ($2 ~ /^-?[0-9]+(\.[0-9]+)?$/ && $2+0 == s+0) c++; else if ($2 ~ /^-?[0-9]+(\.[0-9]+)?$/) c=0 }
    END { print c+0 }')
  [ "${flat:-0}" -ge 3 ] && echo "GATE: NOTE metric-flat ($primary pinned at $observed_score for $flat rounds - if the objective demands strict improvement, the metric may be saturated (ceiling); raise its headroom or accept floor+forge)" >&2
fi
if [ -n "$primary" ]; then
  echo "GATE: GO digest=$digest iter=$iter ac=$total pass=$passn unverified=$unv mode=$exit_mode score=$observed_score best=${best:-$observed_score}"
  exit 0
fi

echo "GATE: GO digest=$digest iter=$iter ac=$total pass=$passn unverified=$unv mode=$exit_mode"
exit 0
