#!/usr/bin/env bash
# goal_gate.sh - the EXTERNAL arbiter of goal-loop. Read-only: it decides,
# it never writes. The controller performs every state update it is told to.
# Usage:
#   bash goal_gate.sh --check  [--project DIR]   # 0 GO / 2 NO-GO / 3 BLOCKED / 4 state error
#   bash goal_gate.sh --digest [--project DIR]   # print 12-hex tree digest
set -u
export LC_ALL=C.UTF-8

usage(){ sed -n '2,5p' "$0"; }

project="." mode=""
while [ $# -gt 0 ]; do
  case "$1" in
    --check)  mode=check ;;
    --digest) mode=digest ;;
    --project) [ $# -ge 2 ] || { echo "GATE: NO-GO reason=missing-project-arg" >&2; exit 4; }; project="$2"; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "GATE: NO-GO reason=unknown-flag:$1" >&2; exit 4 ;;
  esac
  shift
done

[ -n "$mode" ] || { echo "GATE: NO-GO reason=no-mode (use --check or --digest)" >&2; exit 4; }

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

ac_body_hash(){                                        # first 8 hex over AC section body
  r < "$sd/goal.md" |
  awk '/^## Acceptance criteria[ ]*$/{f=1;next} f&&/^## /{f=0} f' | hash_std | cut -c1-8
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

digest=$(tree_digest) || state_err "unreadable-project"
if [ "$mode" = digest ]; then echo "$digest"; exit 0; fi

# -0. state present and complete -----------------------------------------
[ -d "$sd" ] || state_err "no-goal-dir"
[ -f "$sd/goal.md" ] || state_err "no-goal-md"
required="iteration breaker false_completes replans no_progress_streak max_iterations no_progress_limit"
for k in $required; do
  [ -n "$(state_get "$k")" ] || state_err "missing-key:$k"
done
iter=$(state_get iteration); breaker=$(state_get breaker)
fc=$(state_get false_completes); streak=$(state_get no_progress_streak)
maxit=$(state_get max_iterations); npl=$(state_get no_progress_limit)
case "$iter$breaker$fc$streak$maxit$npl" in *[!0-9A-Z_a-z_]*) state_err "unparseable-state" ;; esac

# -1. contract frozen by a matching stamp (R3) ----------------------------
stamp=$(r < "$sd/goal.md" | grep -E '^approved: [0-9a-f]{6,}' | tail -1 | awk '{print $2}')
[ -n "$stamp" ] || fail "no-approval"
body=$(ac_body_hash)
if [ "${stamp#"$body"}" = "$stamp" ] && [ "$body" != "${stamp:0:${#body}}" ]; then
  fail "contract-tampered:stam=$stamp recomputed=$body"
fi
[ "${stamp:0:8}" = "$body" ] || fail "contract-tampered:stam=$stamp recomputed=$body"

# -2..-4b. breaker, budget, stagnation, grind -----------------------------
[ "$breaker" = OPEN ] && blocked "breaker-open"
[ "${fc:-0}" -ge 2 ] && blocked "false-completes>=2"
[ "${iter:-0}" -le "${maxit:-12}" ] || fail "budget-exhausted:iter=$iter max=$maxit"
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

ac_ids=$(r < "$sd/goal.md" | grep -oE '^- AC-[0-9]+' | sort -u | sed 's/^- //')
[ -n "$ac_ids" ] || fail "contract-empty:no AC ids"
lv=$(latest_verdicts)
total=0; passn=0; unv=0
for id in $ac_ids; do
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

echo "GATE: GO digest=$digest iter=$iter ac=$total pass=$passn unverified=$unv"
exit 0
