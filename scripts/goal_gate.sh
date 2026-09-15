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
set -u
export LC_ALL=C.UTF-8

usage(){ sed -n '2,12p' "$0"; }

project="." mode="" positional=""
while [ $# -gt 0 ]; do
  case "$1" in
    --check)  mode=check ;;
    --digest) mode=digest ;;
    --verify) mode=verify ;;
    --project) [ $# -ge 2 ] || { echo "GATE: NO-GO reason=missing-project-arg" >&2; exit 4; }; project="$2"; shift ;;
    --help|-h) usage; exit 0 ;;
    -*) echo "GATE: NO-GO reason=unknown-flag:$1" >&2; exit 4 ;;
    *) positional="$positional $1" ;;                  # AC-IDs for --verify
  esac
  shift
done

[ -n "$mode" ] || { echo "GATE: NO-GO reason=no-mode (use --check, --digest or --verify)" >&2; exit 4; }
[ -z "${positional# }" ] || [ "$mode" = verify ] || { echo "GATE: NO-GO reason=unknown-arg:$positional" >&2; exit 4; }

sd="$project/.goal"
r(){ tr -d '\r'; }                                    # CR scrubber for every read
hash_std(){                                            # one stable content hash
  if command -v sha1sum >/dev/null 2>&1; then sha1sum | cut -c1-40
  else cksum | awk '{print $1}'; fi
}

tree_digest(){                                         # 12 hex, deterministic
  ( cd "$project" 2>/dev/null || exit 4
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      { git rev-parse HEAD 2>/dev/null || echo none; git status --porcelain 2>/dev/null | r | sort; } | hash_std | cut -c1-12
    else
      find . -type f ! -path './.goal*' ! -path './.git*' | sort |
      while IFS= read -r f; do
        [ -f "$f" ] || continue
        h=$(hash_std < "$f")
        printf '%s %s\n' "$f" "$h"
      done | sort | hash_std | cut -c1-12
    fi )
}

ac_body_hash(){                                        # 8 hex over AC body + every ^exit: line
  { r < "$sd/goal.md" |
    awk '/^## Acceptance criteria[ ]*$/{f=1;next} f&&/^## /{f=0} f'
    r < "$sd/goal.md" | grep -E '^exit:' || true
  } | hash_std | cut -c1-8
}

state_get(){                                           # $1 key -> value or empty
  [ -f "$sd/state.rec" ] || { echo ""; return; }
  grep -E "^$1=" "$sd/state.rec" | r | tail -1 | cut -d= -f2-
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

fail(){ echo "GATE: NO-GO reason=$1" >&2; exit 2; }
blocked(){ echo "GATE: BLOCKED reason=$1" >&2; exit 3; }
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
classify_expected(){                                   # $1 raw -> exit0 | judged | "metric <op> <num>"
  v=$(printf '%s' "$1" | tr -d '[:space:]')
  case "$v" in
    ''|exit=0) echo "exit0" ;;
    judged)    echo "judged" ;;
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
  if command -v timeout >/dev/null 2>&1; then
    out=$(cd "$project" 2>/dev/null && timeout "$tmo" bash -c "$cmd" 2>/dev/null); rc=$?
  else
    out=$(cd "$project" 2>/dev/null && bash -c "$cmd" 2>/dev/null); rc=$?   # without coreutils timeout a hang hangs; documented
  fi
  out=$(printf '%s\n' "$out" | r)                    # CR scrub: Windows-native checks print CRLF
  case "$cls" in
    exit0)
      if [ "$rc" -eq 0 ]; then printf '%s|PASS|exit=0\n' "$id"
      elif [ "$rc" -eq 127 ] || [ "$rc" -eq 124 ]; then printf '%s|BROKEN|check not executable (rc=%d)\n' "$id" "$rc"
      else printf '%s|FAIL|exit=%d\n' "$id" "$rc"; fi ;;
    rc\ *)                                            # negative assertion: rc==N passes
      want=${cls#rc }
      if [ "$rc" -eq "$want" ]; then printf '%s|PASS|exit=%d\n' "$id" "$rc"
      elif [ "$rc" -eq 124 ] && [ "$want" != 124 ]; then printf '%s|BROKEN|timed out (rc=124)\n' "$id"
      elif [ "$rc" -eq 127 ] && [ "$want" != 127 ]; then printf '%s|BROKEN|check not executable (rc=127)\n' "$id"
      else printf '%s|FAIL|exit=%d expect=exit=%s\n' "$id" "$rc" "$want"; fi ;;
    metric\ *)
      last=$(printf '%s\n' "$out" | grep -vE '^[[:space:]]*$' | tail -1)
      case "$last" in
        ''|*[!0-9.\-]*)
          printf '%s|BROKEN|last stdout line is not a number: %s\n' "$id" "${last:-<empty>}"; return ;;
      esac
      v=$(awk -v a="$last" -v b="$m_num" -v o="$m_op" \
          'BEGIN{ok=(o==">=")?(a>=b):(o=="<=")?(a<=b):(o==">")?(a>b):(o=="<")?(a<b):(o=="==")?(a==b):(a!=b); print ok?"PASS":"FAIL"}')
      printf '%s|%s|observed=%s expect=%s%s\n' "$id" "$v" "$last" "$m_op" "$m_num" ;;
    *)
      printf '%s|BROKEN|unroutable expectation class\n' "$id" ;;
  esac
}

digest=$(tree_digest) || state_err "unreadable-project"
if [ "$mode" = digest ]; then echo "$digest"; exit 0; fi

# -0. state present and complete -----------------------------------------
[ -d "$sd" ] || state_err "no-goal-dir"
[ -f "$sd/goal.md" ] || state_err "no-goal-md"
tmo=$(state_get check_timeout); [ -n "$tmo" ] || tmo=120
case "$tmo" in ''|*[!0-9]*) state_err "bad-check-timeout:$tmo" ;; esac

if [ "$mode" = verify ]; then
  want="$positional "
  d0="$digest"; nfail=0; nbroken=0; nchecked=0
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
  [ "$nchecked" -gt 0 ] || { echo "GATE: VERIFY-OK nothing-deterministic"; exit 0; }
  if [ $((nfail+nbroken)) -eq 0 ]; then echo "GATE: VERIFY-OK checked=$nchecked"; exit 0; fi
  echo "GATE: NO-GO reason=verify-failures:fail=$nfail broken=$nbroken" >&2
  exit 2
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
case "$iter$breaker$fc$streak$maxit$npl" in *[!0-9A-Z_a-z_]*) state_err "unparseable-state" ;; esac

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
     [ "$now" -gt "$dl" ] && blocked "time-budget-exhausted:deadline=$dl now=$now (graceful: finish the current task, deliver best-so-far; extend = user-approved rewrite of deadline= in state.rec)" ;;
esac
if [ "$exit_mode" = forge ]; then
  [ "${iter:-0}" -le "${maxit:-12}" ] || blocked "budget-fuse:iter=$iter max=$maxit (forge: budget is a fuse - extend it or deliver best-so-far)"
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
# Canonical loop-log key set (schema doc: references/exit-gate.md section 1).
# last_block() consumes key=value lines generically, so the set is declared
# here: it keeps parser and schema doc mutually named and advisory-checks
# presence (exit codes unchanged; exit_signal and digest stay hard-checked).
loop_keys="task files_modified checks_pass checks_fail checks_unverifiable error_signature progress exit_signal false_complete digest"
missing_lk=""
for k in $loop_keys; do
  printf '%s\n' "$lb" | grep -qE "^$k=" || missing_lk="$missing_lk $k"
done
[ -z "$missing_lk" ] || echo "GATE: NOTE loop-log-missing-keys:${missing_lk# }" >&2
claim=$(printf '%s\n' "$lb" | grep -E '^exit_signal=' | tail -1 | cut -d= -f2-)
[ "$claim" = yes ] || fail "not-claimed"
lbdigest=$(printf '%s\n' "$lb" | grep -E '^digest=' | tail -1 | cut -d= -f2-)
[ "$lbdigest" = "$digest" ] || { echo "GATE: NOTE false-complete suspected; controller: append false_complete=yes and increment false_completes in state.rec" >&2; fail "verdicts-stale:block=$lbdigest current=$digest"; }

ac_ids=$(all_ac_ids)
[ -n "$ac_ids" ] || fail "contract-empty:no AC ids"
lv=$(latest_verdicts)
total=0; passn=0; unv=0
for id in $ac_ids; do
  cls=$(classify_expected "$(ac_expected "$id")")
  if [ "$cls" != judged ]; then
    # Deterministic AC: the gate reruns the check NOW. Stored verdicts for
    # these ids are mid-loop bookkeeping only; the rerun is the evidence.
    line=$(run_one_check "$id" "$cls" ${cls#metric})
    v=$(printf '%s' "$line" | cut -d'|' -f2)
    detail=$(printf '%s' "$line" | cut -d'|' -f3-)
    case "$v" in
      PASS)   total=$((total+1)); passn=$((passn+1)) ;;
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

# -11. forge: floors alone are not an exit; exhaustion is -----------------
if [ "$exit_mode" = forge ]; then
  dry=$(state_get dry_streak); dl=$(state_get dry_limit)
  [ "${dry:-0}" -ge "${dl:-3}" ] || fail "not-dry:dry_streak=${dry:-0} limit=$dl (forge exits on verification exhaustion, not on floors alone)"
fi

echo "GATE: GO digest=$digest iter=$iter ac=$total pass=$passn unverified=$unv mode=$exit_mode"
exit 0
