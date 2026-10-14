#!/usr/bin/env bash
# goal_parse.sh - shared parsing layer of goal-loop. SOURCED, never executed.
# Every ledger/contract grammar rule lives exactly once so gate / ctl / audit
# cannot drift apart. Before v2.7 the same grammar was re-implemented in two
# or three scripts (two state_get, two objective parsers, two hash_std, three
# score validators) - each probe-campaign defect in this family was a bug in
# one copy that the other copy did not have.
#
# Conventions:
#   - project directory is the FIRST argument of every function
#   - pure functions: no globals read (callers keep their own $sd if they like)
#   - hostile-input contracts this layer must survive (the classes that
#     generated the probe campaigns): CRLF files, spaces in artifact paths,
#     negative numbers, backtick spans that look like contract tokens,
#     prose or empty expectations.
#   - unit tests: tests/test_parse.sh; end-to-end: tests/run_tests.sh

gp_r(){ tr -d '\r'; }

gp_hash_std(){                                           # one stable content hash
  if command -v sha1sum >/dev/null 2>&1; then sha1sum | cut -c1-40
  else cksum | awk '{print $1}'; fi
}

gp_sha256_std(){                                         # one file -> 64 hex
  if command -v sha256sum >/dev/null 2>&1; then sha256sum < "$1" | cut -c1-64
  elif command -v openssl >/dev/null 2>&1; then openssl dgst -sha256 "$1" | awk '{print $NF}'
  else echo ""; fi
}

# BSD/GNU portability (v2.9): `sed -i` with no extension is GNU-only; on
# macOS/BSD sed swallows the expression as a backup suffix and corrupts or
# silently skips the edit. CI runs GNU only, so the bug hid until a macOS
# user. One in-place edit = transform to a sibling tmp + atomic mv.
gp_sed_inplace(){                                        # $1 expression $2 file
  local f="$2"
  sed "$1" "$f" > "$f.gptmp" || { rm -f "$f.gptmp"; return 1; }
  mv -f "$f.gptmp" "$f"
}

# ---- number validators ----------------------------------------------------
# A score is: optional '-', digits, optional single decimal part.
# "1.2.3", "1e3", "--5", "-.5" FAIL; "-10", "0", "7.5" pass.
gp_is_score(){ printf '%s' "$1" | grep -qE '^-?[0-9]+(\.[0-9]+)?$'; }
# Counters in state.rec are unsigned integers. Empty string FAILS.
gp_is_natural(){ printf '%s' "$1" | grep -qE '^[0-9]+$'; }

# ---- state.rec -------------------------------------------------------------
gp_state_get(){                                          # $1 project $2 key -> value or ""
  local f="$1/.goal/state.rec"
  [ -f "$f" ] || { echo ""; return; }
  grep -E "^$2=" "$f" | gp_r | tail -1 | cut -d= -f2-
}

# ---- goal.md contract grammar (references/gate.md section 1) --------------
gp_contract_mode(){ gp_r < "$1/.goal/goal.md" 2>/dev/null | grep -qE '^exit: *forge' && echo forge || echo threshold; }
gp_all_ac_ids(){ gp_r < "$1/.goal/goal.md" | grep -oE '^- AC-[0-9]+' | sort -u | sed 's/^- //'; }
gp_ac_line_for(){ gp_r < "$1/.goal/goal.md" | awk -v id="$2" '$0 ~ "^- "id"[ |]"'; }
# Commands stay in backticks; AC lines are never split on '|' (commands
# contain pipes). The expectation is the line tail after "expected:".
gp_ac_check_cmd(){  gp_ac_line_for "$1" "$2" | sed -nE 's/^.*check: *`([^`]*)`.*/\1/p' | tail -1; }
gp_ac_expected(){   gp_ac_line_for "$1" "$2" | sed -nE 's/^.*expected: *([^|]*)[[:space:]]*$/\1/p' | tail -1; }
gp_ac_baseline_marker(){ gp_ac_line_for "$1" "$2" | sed -nE 's/^.*baseline: *(delta|abs).*/\1/p' | tail -1; }
gp_ac_probe_cmd(){  gp_ac_line_for "$1" "$2" | sed -nE 's/^.*probe: *`([^`]*)`.*/\1/p' | tail -1; }
gp_ac_metric_re(){  gp_ac_line_for "$1" "$2" | sed -nE 's/^.*metric: *`([^`]*)`.*/\1/p' | tail -1; }
gp_ac_tolerance(){  gp_ac_line_for "$1" "$2" | sed -nE 's/^.*tolerance: *([0-9.]+).*/\1/p' | tail -1; }
# Calib fixtures belong to judged ACs. Backtick spans are command text, not
# calib declarations: strip them first, or an AC whose check greps the literal
# "calib:" is mistaken for a calibrated seat (v2.6 fix, kept here as law).
gp_ac_calib_line(){  gp_ac_line_for "$1" "$2" | sed -E 's/`[^`]*`//g'; }
gp_ac_calib_good(){  gp_ac_calib_line "$1" "$2" | sed -nE 's/^.*calib:[^|]*good *= *([^ |]+).*/\1/p' | tail -1; }
gp_ac_calib_bad(){   gp_ac_calib_line "$1" "$2" | sed -nE 's/^.*calib:[^|]*bad *= *([^ |]+).*/\1/p' | tail -1; }
gp_ac_calib_declared(){ gp_ac_calib_line "$1" "$2" | grep -qE 'calib:[^|]*(good|bad) *=' && echo yes || echo no; }
# External/deferred check surface (v2.9): an `external:` command settles an AC
# against an OUT-OF-TREE source (CRM, prod metrics, an async peer review) that
# no in-tree file captures; `window:` = validity of the cached result in whole
# seconds - inside it, the recorded measurement in deferred.rec IS the check
# (re-querying a slow system every gate exit is not measurement, it is
# spinning). Backtick decoys stripped first: the calib law, kept.
# external: its command lives INSIDE backticks, so the calib line-strip would
# delete the very declaration it is looking for (v2.9 self-inflicted bug caught
# by t117). Greedy .* means the LAST external: span wins: a decoy inside the
# check: command sits earlier in the line than the real trailing declaration.
gp_ac_external_cmd(){ gp_ac_line_for "$1" "$2" | sed -nE 's/^.*external: *`([^`]*)`.*/\1/p' | tail -1; }
gp_ac_window(){       gp_ac_calib_line "$1" "$2" | sed -nE 's/^.*window: *([0-9]+).*/\1/p' | tail -1; }
# Horizon layer (v2.9): a contract may declare `horizon-waived: <reason>` to
# accept an objective whose blind spot is unguarded. The parser only finds it;
# the refuse-at-stamp tooth lives in goal_ctl.sh.
gp_horizon_waived(){ gp_r < "$1/.goal/goal.md" 2>/dev/null | grep -iE '^horizon-waived:[[:space:]]*[^[:space:]]' | tail -1 | sed -E 's/^[^:]*:[[:space:]]*//' | cut -c1-200; }
# var: (v2.9) a second capture-group regex pinning WHERE the measurement's
# dispersion comes from, so the significance band is computed from data
# instead of the AC author's memory of typical noise.
gp_ac_var_re(){ gp_ac_line_for "$1" "$2" | sed -nE 's/^.*var: *`([^`]*)`.*/\1/p' | tail -1; }
# sd: (v2.9) stddev regex for significance bands on an objective metric -
# one capture group; extracts the measurement's spread (what benchmark
# harnesses actually print: "stddev: 1.4"), sqrt'd into the z-band.
gp_ac_sd_re(){ gp_ac_line_for "$1" "$2" | sed -nE 's/^.*sd: *`([^`]*)`.*/\1/p' | tail -1; }
# ---- deferred.rec grammar (v2.9 external checks) ---------------------------
# Lives under .goal/evidence/ (digest-excluded, R6-fair) because the GATE
# writes it during a rerun batch - it is a measurement cache, not ledger state.
# 4 fields: id|verdict|tstamp|detail. Append-only; reader takes the LAST row
# per id (ties by file order - latest wins, the verdicts.rec law).
gp_defer_path(){ echo "$1/.goal/evidence/deferred.rec"; }
gp_defer_latest(){
  [ -f "$(gp_defer_path "$1")" ] || return 0
  gp_r < "$(gp_defer_path "$1")" | gawk -F'|' '{ id=$1; v=$2; t=$3+0; d=$4; sub(/\r$/,"",d); l=NR
    if (!(id in bt) || t > bt[id] || (t == bt[id] && l > bn[id])) {
      bt[id]=t; bn[id]=l; bv[id]=v; bd[id]=d } }
  END { for (id in bt) printf "%s|%s|%s|%s\n", id, bv[id], bt[id], bd[id] }'
}
gp_objective_ac(){  gp_r < "$1/.goal/goal.md" | sed -nE 's/^objective: *(maximize|minimize) +(AC-[0-9]+).*/\2/p' | tail -1; }
gp_objective_dir(){ gp_r < "$1/.goal/goal.md" | sed -nE 's/^objective: *(maximize|minimize) +(AC-[0-9]+).*/\1/p' | tail -1; }
# R3 frozen surface: AC section body + exit: + objective: lines. ctl stamp and
# gate check MUST hash the same thing or every legitimate run trips
# contract-tampered. This is that one definition.
gp_ac_body_hash(){
  { gp_r < "$1/.goal/goal.md" | awk '/^## Acceptance criteria[ ]*$/{f=1;next} f&&/^## /{f=0} f'
    gp_r < "$1/.goal/goal.md" | grep -E '^(exit|objective|horizon-waived):' || true
  } | gp_hash_std | cut -c1-8
}

# expected token -> a routing class the gate understands
gp_classify_expected(){
  local v; v=$(printf '%s' "$1" | tr -d '[:space:]')
  case "$v" in
    ''|exit=0) echo "exit0" ;;
    judged)    echo "judged" ;;
    maximize)  echo "maximize" ;;
    minimize)  echo "minimize" ;;
    exit=[0-9]*) echo "rc ${v#exit=}" ;;
    *)
      local op num
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

# ---- measurement -----------------------------------------------------------
gp_strip_ansi(){                                         # colored CLIs must not cut the metric regex
  gawk '{ gsub(/\033\[[0-9;?]*[A-Za-z]/, "", $0); print }'
}
gp_extract_metric(){                                     # $1 text $2 regex-or-empty -> number or ""
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

# ---- verdict evidence extraction --------------------------------------------
# `artifact: <path> digest: <sha256>` in the evidence string. Greedy to the
# digest: token - artifact paths with spaces are legal file names; stopping at
# whitespace silently loses the path (probe-campaign D4).
gp_ev_artifact(){
  local ev="$1" a=""
  a=$(printf '%s' "$ev" | sed -nE 's/^.*artifact:[[:space:]]*(.*[^[:space:]])[[:space:]]+digest:.*/\1/p' | head -1)
  [ -n "$a" ] || a=$(printf '%s' "$ev" | grep -oE 'artifact:[[:space:]]*[^[:space:]]+' | head -1 | sed -E 's/^artifact:[[:space:]]*//')
  printf '%s' "$a"
}
gp_ev_digest(){
  printf '%s' "$1" | grep -oE 'digest:[[:space:]]*(sha256:)?[a-f0-9]{8,64}' | head -1 | sed -E 's/^digest:[[:space:]]*(sha256:)?//'
}

# ---- verdicts.rec grammar ---------------------------------------------------
# 6 fields: id|verdict|iter|digest|command|evidence. Binding rows use derived
# ids (AC-N#good / AC-N#bad) - ordinary rows to the schema.
gp_verdict_ok(){ printf '%s' "$1" | awk -F'|' '{exit NF!=6}'; }
gp_verdict_verdict(){ printf '%s' "$1" | cut -d'|' -f2; }
# Latest row per id: max (iteration, then file order). An earlier version used
# `it >= best[id]` with unordered gawk iteration - two rows for one id in the
# same iteration left the winner to hash order, so a rebind result was
# effectively random. File order is ledger order: later binding wins.
gp_latest_verdicts(){
  [ -f "$1/.goal/verdicts.rec" ] || return 0
  gawk -F'|' '{
    id=$1; v=$2; it=$3+0; d=$4; e=$6; sub(/\r$/,"",e); l=NR
    if (!(id in best_it) || it > best_it[id] || (it == best_it[id] && l > best_l[id])) {
      best_it[id]=it; best_l[id]=l; ver[id]=v; dig[id]=d; ev[id]=e
    }
  } END{ for (id in best_it) printf "%s|%s|%s|%s|%s\n", id, ver[id], best_it[id], dig[id], ev[id] }' "$1/.goal/verdicts.rec"
}
# Contradiction scan: rows for one id bound to the SAME (iter, digest) that
# DISAGREE (distinct verdict values). Two concurrent verdicts on one bound
# state = the judge plane contradicts itself on unchanged tree state (R2 makes
# re-judging illegal while files are unchanged) - mechanically a conflict.
# Deliberately scoped to MAIN ids: calib derived rows (AC-N#good/#bad) may be
# re-graded within an iteration by design (100c), latest-wins resolves them.
gp_verdict_conflict(){                                 # $1 project $2 id $3 iter $4 digest -> yes|no
  local p="$1" id="$2" it="$3" d="$4"
  [ -f "$p/.goal/verdicts.rec" ] || { echo no; return; }
  gp_r < "$p/.goal/verdicts.rec" | gawk -F'|' -v id="$id" -v it="$it" -v d="$d" '
    { sub(/\r$/,"",$2)
      if ($1==id && $3+0==it+0 && $4==d) seen[$2]=1 }
    END { n=0; for (v in seen) n++; print (n>1) ? "yes" : "no" }'
}

# ---- task= id grammar (R12/A1: ledger law, enforced by the writer) ----------
gp_task_ok(){ printf '%s' "$1" | grep -qE '^T[0-9]+\[(teams|crew):[0-9]+\]( *\(fallback:[a-z0-9-]+\))?$'; }
gp_task_fallback(){ printf '%s' "$1" | sed -nE 's/.*\(fallback:([a-z0-9-]+)\).*/\1/p'; }
gp_task_backend(){ printf '%s' "$1" | sed -nE 's/.*\[(teams|crew):[0-9]+\].*/\1/p'; }
