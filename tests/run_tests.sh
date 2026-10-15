#!/usr/bin/env bash
# tests/run_tests.sh - scenario suite runner for goal_gate.sh / goal_ctl.sh.
# Parallel by default. Cases live in tests/cases.inc.sh; helpers in tests/lib.sh.
#
#   bash tests/run_tests.sh                 # --jobs=8 (default)
#   bash tests/run_tests.sh --jobs=1        # sequential, same 395 semantics
#   bash tests/run_tests.sh --only 78       # one block + its shared-project mates
#   bash tests/run_tests.sh --only 78-90    # inclusive id range
#   bash tests/run_tests.sh --only 53,74    # list
#   bash tests/run_tests.sh --list          # show blocks / clusters / shards
#
# Exit 0 = all green. Parallel shards share no mutable state (each gets its
# own mktemp root). Dependency clusters (tests that share a $T/tNN project)
# always ride in the same shard — never split across workers.
set -u
export LC_ALL=C.UTF-8

here=$(cd "$(dirname "$0")/.." && pwd)
LIB="$here/tests/lib.sh"
BODY="$here/tests/cases.inc.sh"
jobs=8
only=""
list_only=0

while [ $# -gt 0 ]; do
  case "$1" in
    --jobs=*) jobs="${1#*=}" ;;
    --jobs) [ $# -ge 2 ] || { echo "run_tests: --jobs needs N" >&2; exit 4; }; jobs="$2"; shift ;;
    --only=*) only="${1#*=}" ;;
    --only) [ $# -ge 2 ] || { echo "run_tests: --only needs SPEC" >&2; exit 4; }; only="$2"; shift ;;
    --list) list_only=1 ;;
    --help|-h)
      sed -n '2,16p' "$0"; exit 0 ;;
    *)
      echo "run_tests: unknown arg $1" >&2; exit 4 ;;
  esac
  shift
done

[ -f "$LIB" ] || { echo "run_tests: missing $LIB" >&2; exit 4; }
[ -f "$BODY" ] || { echo "run_tests: missing $BODY" >&2; exit 4; }
case "$jobs" in
  ''|*[!0-9]*|0) echo "run_tests: --jobs must be a positive integer" >&2; exit 4 ;;
esac

# ---------------------------------------------------------------------------
# Block map: every "^# NN..." header in cases.inc.sh starts a block that runs
# through the line before the next header (or EOF).
# Emits: start_line \t end_line \t id \t label
# ---------------------------------------------------------------------------
block_map() {
  awk '
    /^# [0-9]/ {
      if (start) print start "\t" NR-1 "\t" id "\t" label
      label = $0
      sub(/^# /, "", label)
      id = label
      sub(/[^0-9a-z].*/, "", id)
      start = NR
      next
    }
    { next }
    END { if (start) print start "\t" NR "\t" id "\t" label }
  ' "$BODY"
}

# projects touched by lines s..e → one per line "projkey"
# Matches $T/<name>, mkproj/close_iter/contract <name>, and --project $T/<name>.
projs_in() {
  local s=$1 e=$2
  sed -n "${s},${e}p" "$BODY" | awk '
    {
      line=$0
      while (match(line, /\$T\/[A-Za-z0-9_]+/)) {
        print substr(line, RSTART+3, RLENGTH-3)
        line = substr(line, RSTART+RLENGTH)
      }
    }
    /mkproj[[:space:]]+[A-Za-z0-9_]+/ {
      if (match($0, /mkproj[[:space:]]+[A-Za-z0-9_]+/)) {
        tok = substr($0, RSTART, RLENGTH)
        sub(/^mkproj[[:space:]]+/, "", tok)
        print tok
      }
    }
    /close_iter[[:space:]]+[A-Za-z0-9_]+/ {
      if (match($0, /close_iter[[:space:]]+[A-Za-z0-9_]+/)) {
        tok = substr($0, RSTART, RLENGTH)
        sub(/^close_iter[[:space:]]+/, "", tok)
        print tok
      }
    }
  ' | sort -u
}

# --- build cluster assignment (union-find over shared $T/tNN) ---
MAP=$(block_map)
NB=$(printf '%s\n' "$MAP" | grep -c .)
[ "$NB" -gt 0 ] || { echo "run_tests: no blocks found in cases.inc.sh" >&2; exit 4; }

# parent[i]=i initially (1-based block index)
parents=""
for i in $(seq 1 "$NB"); do parents="$parents $i"; done
parent_of() { eval "printf '%s' \"\$p$1\""; }
set_parent() { eval "p$1=\$2"; }

i=0
printf '%s\n' "$MAP" | while IFS= read -r _; do i=$((i+1)); done
# init parents in a single pass without subshell (use a flat array string)
declare -a P START END BID BLAB
idx=0
while IFS=$'\t' read -r s e id lab; do
  idx=$((idx+1))
  START[$idx]=$s; END[$idx]=$e; BID[$idx]=$id; BLAB[$idx]=$lab
  P[$idx]=$idx
done <<< "$MAP"

# union by shared project number
union() {
  local a=$1 b=$2 ra rb
  ra=$a; rb=$b
  while [ "${P[$ra]}" != "$ra" ]; do ra=${P[$ra]}; done
  while [ "${P[$rb]}" != "$rb" ]; do rb=${P[$rb]}; done
  [ "$ra" = "$rb" ] && return 0
  P[$rb]=$ra
}
findr() {
  local r=$1
  while [ "${P[$r]}" != "$r" ]; do r=${P[$r]}; done
  printf '%s' "$r"
}

# bash 3.2: no declare -A. Project keys are [A-Za-z0-9_]+ (safe as var suffix);
# numeric maps use indexed arrays, which bash 3.2 has always supported.
spo_get(){ eval "printf '%s' \"\${spo_$1:-}\""; }
spo_set(){ eval "spo_$1=\$2"; }
for i in $(seq 1 "$NB"); do
  while read -r proj; do
    [ -n "$proj" ] || continue
    if [ -n "$(spo_get "$proj")" ]; then
      union "$i" "$(spo_get "$proj")"
    else
      spo_set "$proj" "$i"
    fi
  done < <(projs_in "${START[$i]}" "${END[$i]}")
done

# cluster id per block = findr(i); order clusters by min start line
declare -a cluster_of
for i in $(seq 1 "$NB"); do
  cluster_of[$i]=$(findr "$i")
done

# --only filter: select blocks whose id matches, then expand to full cluster
want_idx() {
  local id=$1
  [ -z "$only" ] && return 0
  # SPEC: N | N-M | a,b,c | N and friends via cluster expansion outside
  case "$only" in
    *,*)
      local o
      for o in ${only//,/ }; do
        [ "$id" = "$o" ] && return 0
        case "$id" in
          "$o"|"${o}"[a-z]|${o}[a-z]) return 0 ;;
        esac
        # prefix: only=78 matches 78, 78b; only=100 matches 100a..
        case "$id" in
          "${o}"*) return 0 ;;
        esac
      done
      return 1 ;;
    *-*)
      local a b na nb nid
      a=${only%%-*}; b=${only#*-}
      # numeric compare on leading digits
      na=${id%%[!0-9]*}; nb=${b%%[!0-9]*}
      a=${a%%[!0-9]*}
      [ -n "$na" ] && [ -n "$a" ] && [ -n "$nb" ] || return 1
      [ "$na" -ge "$a" ] && [ "$na" -le "$nb" ] && return 0
      return 1 ;;
    *)
      case "$id" in
        "$only"|"$only"[a-z]|${only}[a-z]|${only}*) return 0 ;;
      esac
      return 1 ;;
  esac
}

# Select block indices
declare -a SEL
nsel=0
if [ -n "$only" ]; then
  # first pass: matching blocks → their clusters
  declare -a want_cluster
  for i in $(seq 1 "$NB"); do
    if want_idx "${BID[$i]}"; then
      want_cluster[${cluster_of[$i]}]=1
    fi
  done
  for i in $(seq 1 "$NB"); do
    if [ -n "${want_cluster[${cluster_of[$i]}]:-}" ]; then
      nsel=$((nsel+1)); SEL[$nsel]=$i
    fi
  done
else
  for i in $(seq 1 "$NB"); do
    nsel=$((nsel+1)); SEL[$nsel]=$i
  done
fi

if [ "$list_only" -eq 1 ]; then
  echo "blocks=$NB jobs=$jobs only=${only:-*}"
  for i in $(seq 1 "$nsel"); do
    b=${SEL[$i]}
    echo "  ${BID[$b]}  L${START[$b]}-${END[$b]}  cluster=${cluster_of[$b]}  ${BLAB[$b]}"
  done
  exit 0
fi

if [ "$nsel" -eq 0 ]; then
  echo "run_tests: --only $only matched nothing" >&2
  exit 4
fi

# ---- pack selected clusters into $jobs shards (greedy by line count) ----
# unique clusters in order of first appearance
declare -a CLUSTERS
declare -a cl_lines cl_members
ncl=0
for i in $(seq 1 "$nsel"); do
  b=${SEL[$i]}
  c=${cluster_of[$b]}
  if [ -z "${cl_members[$c]:-}" ]; then
    ncl=$((ncl+1)); CLUSTERS[$ncl]=$c
  fi
  cl_members[$c]="${cl_members[$c]:-} $b"
  cl_lines[$c]=$(( ${cl_lines[$c]:-0} + END[$b] - START[$b] + 1 ))
done

# greedy pack clusters into min(jobs, ncl) buckets by line weight
nj=$jobs
[ "$nj" -gt "$ncl" ] && nj=$ncl
[ "$nj" -lt 1 ] && nj=1

declare -a bucket_w
for j in $(seq 1 "$nj"); do bucket_w[$j]=0; done
declare -a cluster_bucket
for k in $(seq 1 "$ncl"); do
  c=${CLUSTERS[$k]}
  best=1; bestw=${bucket_w[1]}
  for j in $(seq 1 "$nj"); do
    if [ "${bucket_w[$j]}" -lt "$bestw" ]; then best=$j; bestw=${bucket_w[$j]}; fi
  done
  cluster_bucket[$c]=$best
  bucket_w[$best]=$(( bucket_w[$best] + cl_lines[$c] ))
done

# ---- emit & run shard scripts ----
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

emit_shard() {
  local out=$1
  shift
  local blocks="$*"   # block indices
  {
    echo '#!/usr/bin/env bash'
    echo 'set -u'
    echo 'export LC_ALL=C.UTF-8'
    echo "here=$(printf '%q' "$here")"
    echo 'GATE="$here/scripts/goal_gate.sh"'
    echo 'CTL="$here/scripts/goal_ctl.sh"'
    echo 'TEAM="$here/scripts/goal_team.sh"'
    echo 'T=$(mktemp -d)'
    echo 'trap '\''rm -rf "$T"'\'' EXIT'
    echo 'pass=0; failn=0'
    # helpers: lib already defines ok/no/assert_*/sed_in/mkproj/contract/bind_v/close_iter
    # but those reference $T/$CTL/$GATE — fine once exported above.
    # Strip lib's own T/here/setup if any; we inject ours first.
    grep -v '^set -u' "$LIB" | grep -v '^export LC_ALL'
    echo "cd $(printf '%q' "$here")"
    for b in $blocks; do
      sed -n "${START[$b]},${END[$b]}p" "$BODY"
    done
    echo 'echo "== results: pass=$pass fail=$failn =="'
    echo '[ "$failn" -eq 0 ] && exit 0 || exit 1'
  } > "$out"
}

# collect per-bucket block lists
declare -a bucket_blocks
for k in $(seq 1 "$ncl"); do
  c=${CLUSTERS[$k]}
  j=${cluster_bucket[$c]}
  bucket_blocks[$j]="${bucket_blocks[$j]:-} ${cl_members[$c]:-}"
done

pids=""
outfiles=""
for j in $(seq 1 "$nj"); do
  s="$work/shard-$j.sh"
  o="$work/shard-$j.out"
  emit_shard "$s" ${bucket_blocks[$j]:-}
  outfiles="$outfiles $o"
  if [ "$nj" -eq 1 ]; then
    bash "$s" > "$o" 2>&1
  else
    bash "$s" > "$o" 2>&1 &
    pids="$pids $!"
  fi
done

fail_launch=0
for p in $pids; do
  wait "$p" || fail_launch=1
done

# merge outputs (shard order) + sum results
total_pass=0
total_fail=0
for o in $outfiles; do
  cat "$o"
  # last results line
  line=$(grep -E '^== results: pass=' "$o" | tail -1)
  if [ -n "$line" ]; then
    pf=${line#== results: pass=}; pf=${pf%% fail=*}
    ff=${line#* fail=}; ff=${ff%% *}
    total_pass=$((total_pass + pf))
    total_fail=$((total_fail + ff))
  else
    total_fail=$((total_fail + 1))
    echo "  FAIL - shard produced no results line: $o"
  fi
done

echo "== total: pass=$total_pass fail=$total_fail shards=$nj =="
[ "$total_fail" -eq 0 ] && exit 0 || exit 1
