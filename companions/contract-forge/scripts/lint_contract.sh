#!/usr/bin/env bash
# lint_contract.sh - advisory pre-stamp linter for goal-loop contracts (DRAFT).
# READ-ONLY. Never writes .goal/, never stamps, never runs gates.
# Grammar mirrored from goal-loop references/gate.md (not sourced).
#
#   bash lint_contract.sh <goal.md> [--project DIR] [--strict]
#
# Exit: 0 clean (warnings ok unless --strict) · 1 errors · 2 usage/missing file
set -u
export LC_ALL=C.UTF-8

usage(){ sed -n '2,9p' "$0"; }

file="" project="" strict=0
while [ $# -gt 0 ]; do
  case "$1" in
    --project) [ $# -ge 2 ] || { echo "LINT: usage --project DIR" >&2; exit 2; }; project="$2"; shift ;;
    --strict) strict=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "LINT: usage unknown flag $1" >&2; exit 2 ;;
    *) [ -n "$file" ] && { echo "LINT: usage single file" >&2; exit 2; }; file="$1" ;;
  esac
  shift
done
[ -n "$file" ] || { usage; exit 2; }
[ -f "$file" ] || { echo "LINT: missing file $file" >&2; exit 2; }

r(){ tr -d '\r'; }
errors=0 warns=0

err(){ echo "LINT: error $1" >&2; errors=$((errors+1)); }
warn(){ echo "LINT: warn $1" >&2; warns=$((warns+1)); }

body=$(r < "$file")

# --- helpers ---------------------------------------------------------------
# Extract `key: \`cmd\`` inner command (first match).
get_bt(){
  # $1=key
  printf '%s\n' "$body" | sed -n "s/.*${1}: \`\\([^\`]*\\)\`.*/\\1/p" | head -1
}
# Extract bare field value on an AC line context: key: value (to eol or next |)
get_field(){
  # $1=line $2=key -> value
  printf '%s\n' "$1" | sed -n "s/.*${2}: \\([^|]*\\).*/\\1/p" | head -1 | sed 's/[[:space:]]*$//'
}

# Split AC line into fields outside backticks: replace \`...\` with <BT>
mask_bts(){
  # collapse `...` spans to <BT> so | is safe
  awk '{
    s=$0; out="";
    while (match(s, /`[^`]*`/)) {
      out = out substr(s,1,RSTART-1) "<BT>"
      s = substr(s, RSTART+RLENGTH)
    }
    out = out s
    print out
  }'
}

has_hex_approved=0
approved_count=0
obj_ac="" obj_dir=""
exit_line=""
horizon_line=""
is_forge=0
declare -A seen_ids
declare -A ac_expected
declare -A ac_has_check
declare -A ac_has_calib
declare -A ac_calib_good
declare -A ac_calib_bad
declare -A ac_has_probe
declare -A ac_has_metric
declare -A ac_has_baseline
declare -A ac_has_external
declare -A ac_has_window
declare -A ac_spec
declare -A ac_line

# scan lines
while IFS= read -r line; do
  # contract-level
  case "$line" in
    approved:*)
      approved_count=$((approved_count+1))
      rest=${line#approved:}
      rest=$(printf '%s' "$rest" | sed 's/^[[:space:]]*//')
      if printf '%s' "$rest" | grep -qE '^[0-9a-f]{8}([[:space:]]|$)'; then
        has_hex_approved=1
      fi
      ;;
  esac
  case "$line" in
    exit:*)
      exit_line=$(printf '%s' "$line" | sed 's/^exit:[[:space:]]*//' | sed 's/[[:space:]]*$//')
      case "$exit_line" in forge) is_forge=1 ;; esac
      ;;
    objective:*)
      # objective: maximize AC-N  |  objective: minimize AC-N
      obj_dir=$(printf '%s' "$line" | sed -n 's/.*objective:[[:space:]]*\(maximize\|minimize\).*/\1/p' | head -1)
      obj_ac=$(printf '%s' "$line" | sed -n 's/.*objective:[[:space:]]*\(maximize\|minimize\)[[:space:]]\{1,\}\(AC-[0-9A-Za-z][0-9A-Za-z-]*\).*/\2/p' | head -1)
      ;;
    horizon-waived:*)
      horizon_line=$(printf '%s' "$line" | sed 's/^horizon-waived:[[:space:]]*//' | sed 's/[[:space:]]*$//')
      ;;
  esac

  # AC lines
  case "$line" in
    '- AC-'*|'-AC-'*)
      masked=$(printf '%s\n' "$line" | mask_bts)
      id=$(printf '%s\n' "$masked" | sed -n 's/^-[[:space:]]*\(AC-[0-9A-Za-z][0-9A-Za-z-]*\).*/\1/p')
      [ -n "$id" ] || continue
      if [ -n "${seen_ids[$id]:-}" ]; then
        err "ac-id-unique $id: duplicate AC id"
      fi
      seen_ids[$id]=1
      ac_line[$id]=$line

      # expected: take from original, after expected: to end (spec cannot contain |)
      exp=$(printf '%s\n' "$line" | sed -n 's/.*expected:[[:space:]]*//p' | head -1 | sed 's/[[:space:]]*$//')
      if [ -z "$exp" ]; then
        err "missing-expected $id: no expected: field"
      else
        ac_spec[$id]=$exp
        ac_expected[$id]=$exp
        if printf '%s' "$exp" | grep -q '|'; then
          err "spec-pipe $id: expected: spec must not contain |"
        fi
        # form check
        ok=0
        case "$exp" in
          exit=0|exit=[0-9]*|maximize|minimize|judged) ok=1 ;;
        esac
        if [ "$ok" -eq 0 ]; then
          if printf '%s' "$exp" | grep -qE '^(>=|<=|>|<|==|!=)[0-9]+([.][0-9]+)?$'; then
            ok=1
          fi
        fi
        if [ "$ok" -eq 0 ]; then
          err "spec-form $id: unexpected expected: '$exp'"
        fi
      fi

      # check:
      if printf '%s\n' "$line" | grep -q 'check:[[:space:]]*`'; then
        ac_has_check[$id]=1
        cmd=$(printf '%s\n' "$line" | sed -n 's/.*check:[[:space:]]*`\([^`]*\)`.*/\1/p' | head -1)
        if [ -z "$cmd" ] || printf '%s' "$cmd" | grep -qE '^(<exact command>|TODO|todo|<command>)$'; then
          err "empty-check $id: empty or placeholder check"
        fi
      else
        # check without backticks?
        if printf '%s\n' "$masked" | grep -q 'check:'; then
          ac_has_check[$id]=1
          warn "ac-grammar $id: check: not in backticks"
        else
          err "missing-check $id: no check: field"
        fi
      fi

      # probe / metric / sd / var / external in backticks on this line
      if printf '%s\n' "$line" | grep -q 'probe:[[:space:]]*`'; then ac_has_probe[$id]=1; fi
      if printf '%s\n' "$line" | grep -q 'metric:[[:space:]]*`'; then
        ac_has_metric[$id]=1
        mre=$(printf '%s\n' "$line" | sed -n 's/.*metric:[[:space:]]*`\([^`]*\)`.*/\1/p' | head -1)
        if ! printf '%s' "$mre" | grep -q '('; then
          warn "metric-capture $id: metric: regex should contain one capture group"
        fi
      fi
      if printf '%s\n' "$line" | grep -q 'external:[[:space:]]*`'; then ac_has_external[$id]=1; fi
      if printf '%s\n' "$line" | grep -qE 'window:[[:space:]]*[0-9]+'; then ac_has_window[$id]=1; fi

      # baseline
      if printf '%s\n' "$line" | grep -qE 'baseline:[[:space:]]*(delta|abs)'; then
        ac_has_baseline[$id]=1
      fi

      # calib
      if printf '%s\n' "$line" | grep -q 'calib:'; then
        ac_has_calib[$id]=1
        good=$(printf '%s\n' "$line" | sed -n 's/.*calib:[[:space:]]*.*good=\([^ |]*\).*/\1/p' | head -1)
        bad=$(printf '%s\n' "$line" | sed -n 's/.*calib:[[:space:]]*.*bad=\([^ |]*\).*/\1/p' | head -1)
        ac_calib_good[$id]=$good
        ac_calib_bad[$id]=$bad
        if [ -z "$good" ] || [ -z "$bad" ]; then
          err "calib-both $id: calib: needs both good= and bad="
        elif [ "$good" = "$bad" ]; then
          err "calib-both $id: calib: good= and bad= must differ"
        fi
        # calib only on judged
        if [ -n "${ac_expected[$id]:-}" ] && [ "${ac_expected[$id]}" != "judged" ]; then
          err "calib-judged-only $id: calib: only on expected: judged (got ${ac_expected[$id]})"
        fi
      fi

      # window without external
      if [ -n "${ac_has_window[$id]:-}" ] && [ -z "${ac_has_external[$id]:-}" ]; then
        err "window-external $id: window: requires external:"
      fi
      ;;
  esac
done <<EOF
$body
EOF

# --- contract-level relations ---------------------------------------------
if [ -n "$obj_ac" ] && [ -n "$obj_dir" ]; then
  if [ -z "${seen_ids[$obj_ac]:-}" ]; then
    err "objective-target $obj_ac: objective names missing AC"
  else
    exp=${ac_expected[$obj_ac]:-}
    if [ "$exp" != "$obj_dir" ]; then
      err "objective-target $obj_ac: expected: '$exp' != objective direction '$obj_dir'"
    fi
  fi

  # horizon: >=1 judged+calib OR non-empty horizon-waived
  ok_horizon=0
  if [ -n "$horizon_line" ]; then
    ok_horizon=1
  else
    for id in "${!ac_expected[@]}"; do
      if [ "${ac_expected[$id]}" = "judged" ] && [ -n "${ac_has_calib[$id]:-}" ]; then
        ok_horizon=1
        break
      fi
    done
  fi
  if [ "$ok_horizon" -eq 0 ]; then
    err "horizon: objective without judged+calib or horizon-waived: (stamp would refuse)"
  fi
fi

if [ "$has_hex_approved" -eq 1 ]; then
  warn "already-stamped: approved: looks like a hash; do not edit (R3) - proposals only"
fi
if [ "$approved_count" -eq 0 ]; then
  err "approved-placeholder: missing approved: placeholder line"
fi

# forge baseline
if [ "$is_forge" -eq 1 ]; then
  if ! printf '%s' "$body" | grep -qE 'dry_limit='; then
    warn "forge-dry-limit: exit: forge without dry_limit= in budget knobs"
  fi
  for id in "${!ac_expected[@]}"; do
    exp=${ac_expected[$id]}
    need_base=0
    case "$exp" in
      maximize|minimize) need_base=1 ;;
    esac
    if [ -n "${ac_has_metric[$id]:-}" ] && [ "$need_base" -eq 0 ]; then
      # metric with comparison is also delta-risk for forge
      if printf '%s' "$exp" | grep -qE '^(>=|<=|>|<|==|!=)'; then
        need_base=1
      fi
    fi
    if [ "$need_base" -eq 1 ]; then
      if [ -z "${ac_has_baseline[$id]:-}" ]; then
        err "forge-baseline $id: forge score/metric AC needs baseline: delta|abs"
      else
        bl="$project/.goal/baseline.md"
        if [ -n "$project" ] && [ ! -f "$bl" ]; then
          warn "forge-baseline $id: .goal/baseline.md missing (measure before stamp; rows required for delta)"
        elif [ -n "$project" ] && [ -f "$bl" ]; then
          if ! r < "$bl" | grep -qE "^${id}[[:space:]]*\|"; then
            warn "forge-baseline $id: no baseline.md row for $id"
          fi
        fi
      fi
    fi
  done
fi

# probe spirit
for id in "${!ac_expected[@]}"; do
  exp=${ac_expected[$id]}
  case "$exp" in
    maximize|minimize)
      if [ -z "${ac_has_probe[$id]:-}" ]; then
        warn "probe-spirit $id: maximize/minimize without probe: (R9)"
      fi
      ;;
  esac
  if [ -n "${ac_has_metric[$id]:-}" ] && [ -z "${ac_has_probe[$id]:-}" ]; then
    warn "probe-spirit $id: metric: without probe:"
  fi
done

# calib files if --project
if [ -n "$project" ]; then
  for id in "${!ac_has_calib[@]}"; do
    for kind in good bad; do
      f=""
      case $kind in
        good) f=${ac_calib_good[$id]:-} ;;
        bad) f=${ac_calib_bad[$id]:-} ;;
      esac
      if [ -n "$f" ] && [ ! -e "$project/$f" ] && [ ! -e "$f" ]; then
        err "calib-files $id: fixture $kind=$f not found under project"
      fi
    done
  done
fi

# summary
echo "LINT: summary errors=$errors warnings=$warns file=$file"
if [ "$errors" -gt 0 ]; then
  exit 1
fi
if [ "$strict" -eq 1 ] && [ "$warns" -gt 0 ]; then
  exit 1
fi
exit 0
