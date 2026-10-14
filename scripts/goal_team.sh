#!/usr/bin/env bash
# goal_team.sh - portable Agent-Teams layer for goal-loop. Implements the
# cc-haha file protocol (team config + per-agent inbox + TeammateMessage)
# over bash + files, so --teams works on ANY Claude Code harness —
# including those with no TeamCreate/SendMessage tools at all.
# This script is the CONTROLLER's team hand: it decides nothing; the gate
# stays the only completion arbiter. Workers still never touch .goal/ (R6).
#
# Layout (project-local, under .goal/team/):
#   .goal/team/config.json          team meta (canonical roster = roster.jsonl)
#   .goal/team/inboxes/<name>.jsonl one TeammateMessage JSON per line
#   .goal/team/board.md             optional human-readable message mirror
#
# Usage:
#   bash goal_team.sh init   --project DIR --team NAME [--description TEXT]
#   bash goal_team.sh roster --project DIR --add --name N --role R \
#        --prompt P [--scope S]
#   bash goal_team.sh roster --project DIR --list
#   bash goal_team.sh send   --project DIR --from A --to B|'*' --text T \
#        [--summary S]
#   bash goal_team.sh inbox  --project DIR --name N [--unread] [--mark-read]
#   bash goal_team.sh status --project DIR
#   bash goal_team.sh health --project DIR
#   bash goal_team.sh delete --project DIR
#
# TeammateMessage fields (cc-haha shape): from, text, timestamp, read,
# optional summary, optional color. Inbox is JSONL (one object per line);
# each object is field-compatible with cc-haha's TeammateMessage.
#   text may be plain prose OR JSON-encoded control messages
#   (shutdown_request / plan_approval_response / ...). Portable mode treats
#   everything as text the controller relays — no background poller.
set -u
export LC_ALL=C.UTF-8

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=goal_parse.sh
. "$here/goal_parse.sh"   # gp_sed_inplace (BSD/GNU portability, v2.9)

cmd="" project="." team="" description="" add=0 list=0
name="" role="" prompt="" scope="" from="" to="" text="" summary=""
unread=0 mark_read=0

while [ $# -gt 0 ]; do
  case "$1" in
    init|roster|send|inbox|status|health|delete) cmd="$1" ;;
    --project) [ $# -ge 2 ] || { echo "TEAM: ERROR missing-project" >&2; exit 4; }; project="$2"; shift ;;
    --team) [ $# -ge 2 ] || { echo "TEAM: ERROR missing-team" >&2; exit 4; }; team="$2"; shift ;;
    --description) [ $# -ge 2 ] || { echo "TEAM: ERROR missing-description" >&2; exit 4; }; description="$2"; shift ;;
    --add) add=1 ;;
    --list) list=1 ;;
    --name) [ $# -ge 2 ] || { echo "TEAM: ERROR missing-name" >&2; exit 4; }; name="$2"; shift ;;
    --role) [ $# -ge 2 ] || { echo "TEAM: ERROR missing-role" >&2; exit 4; }; role="$2"; shift ;;
    --prompt) [ $# -ge 2 ] || { echo "TEAM: ERROR missing-prompt" >&2; exit 4; }; prompt="$2"; shift ;;
    --scope) [ $# -ge 2 ] || { echo "TEAM: ERROR missing-scope" >&2; exit 4; }; scope="$2"; shift ;;
    --from) [ $# -ge 2 ] || { echo "TEAM: ERROR missing-from" >&2; exit 4; }; from="$2"; shift ;;
    --to) [ $# -ge 2 ] || { echo "TEAM: ERROR missing-to" >&2; exit 4; }; to="$2"; shift ;;
    --text) [ $# -ge 2 ] || { echo "TEAM: ERROR missing-text" >&2; exit 4; }; text="$2"; shift ;;
    --summary) [ $# -ge 2 ] || { echo "TEAM: ERROR missing-summary" >&2; exit 4; }; summary="$2"; shift ;;
    --unread) unread=1 ;;
    --mark-read) mark_read=1 ;;
    --help|-h) sed -n '2,29p' "$0"; exit 0 ;;
    *) echo "TEAM: ERROR unknown-flag:$1" >&2; exit 4 ;;
  esac
  shift
done
[ -n "$cmd" ] || { echo "TEAM: ERROR no-command (init|roster|send|inbox|status|health|delete)" >&2; exit 4; }

td="$project/.goal/team"
cfg="$td/config.json"
inbox_dir="$td/inboxes"
board="$td/board.md"

jesc(){ # JSON string escape, no jq. Line-at-a-time awk: the old sed slurp
  # idiom (':a;N;$!ba') returns EMPTY for trailing-newline-less input on
  # BSD/macOS sed (GNU sed differs) - so every message escaped to nothing and
  # inbox reads came back blank. awk is portable across both.
  printf '%s\n' "$1" | awk '
    { gsub(/\\/,"\\\\"); gsub(/"/,"\\\""); gsub(/\t/,"\\t") }
    NR>1 { printf "\\n" }
    { printf "%s", $0 }
  '
}
now_iso(){ date -u +%Y-%m-%dT%H:%M:%SZ; }

need_team_dir(){
  [ -d "$td" ] || { echo "TEAM: ERROR not-initialized (run: goal_team.sh init)" >&2; exit 4; }
  [ -f "$cfg" ] || { echo "TEAM: ERROR missing-config" >&2; exit 4; }
}

# members are stored one per line inside a JSONL sidecar so we can append
# without jq; config.json itself keeps a members count + pointer for
# humans/cc-haha-shaped readers. Canonical roster = roster.jsonl.
roster_file(){ echo "$td/roster.jsonl"; }

touch_heartbeat(){
  mkdir -p "$td/heartbeat"
  now_iso > "$td/heartbeat/$1.ts"
}

# closed tool-error vocabulary (spec §5.3)
err_vocab_re='error:|exception:|traceback|panic:|exit status [1-9]|exit code [1-9]|rc=[1-9]|permission denied|command not found|no such file or directory|eacces|enoent|api error|rate limit'

# portable time helpers (GNU date -d, BSD date -j/-r, coreutils/BSD stat)
epoch_from_iso(){
  date -u -d "$1" +%s 2>/dev/null \
    || date -u -j -f %Y-%m-%dT%H:%M:%SZ "$1" +%s 2>/dev/null \
    || echo 0
}
iso_from_epoch(){
  date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
    || date -u -r "$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
    || date -u -j -f %s "$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
    || echo "1970-01-01T00:00:00Z"
}
file_mtime(){
  date -r "$1" +%s 2>/dev/null || stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0
}
max_tree_mtime(){
  # $1 = path (file or dir); prints max mtime epoch or 0
  [ -e "$1" ] || { echo 0; return 0; }
  if [ -f "$1" ]; then file_mtime "$1"; return 0; fi
  local m
  m=$(find "$1" -type f -printf '%T@\n' 2>/dev/null | sort -n | tail -1 | cut -d. -f1)
  [ -n "$m" ] || m=$(find "$1" -type f -exec stat -c %Y {} + 2>/dev/null | sort -n | tail -1)
  [ -n "$m" ] || m=$(find "$1" -type f -exec stat -f %m {} + 2>/dev/null | sort -n | tail -1)
  echo "${m:-0}"
}

case "$cmd" in
  init)
    [ -n "$team" ] || { echo "TEAM: ERROR init needs --team NAME" >&2; exit 4; }
    if [ -f "$cfg" ]; then echo "TEAM: ERROR already-initialized ($cfg)" >&2; exit 2; fi
    mkdir -p "$inbox_dir"
    : > "$board"
    : > "$(roster_file)"
    cat > "$cfg" <<EOF
{
  "name": "$(jesc "$team")",
  "description": "$(jesc "$description")",
  "createdAt": "$(now_iso)",
  "backend": "portable",
  "membersFile": "roster.jsonl",
  "inboxesDir": "inboxes",
  "note": "portable Agent-Teams layer; member records in roster.jsonl; TaskUpdate=completed is NEVER a GO signal"
}
EOF
    echo "TEAM: INIT ok team=$team dir=$td" ;;

  roster)
    need_team_dir
    if [ "$add" = 1 ]; then
      [ -n "$name" ] && [ -n "$role" ] && [ -n "$prompt" ] || {
        echo "TEAM: ERROR roster --add needs --name --role --prompt" >&2; exit 4; }
      # reject dup names
      if grep -q "\"name\":\"$(jesc "$name")\"" "$(roster_file)" 2>/dev/null; then
        echo "TEAM: ERROR duplicate-name:$name" >&2; exit 2
      fi
      printf '{"name":"%s","role":"%s","prompt":"%s","scope":"%s","joinedAt":"%s","active":true}\n' \
        "$(jesc "$name")" "$(jesc "$role")" "$(jesc "$prompt")" "$(jesc "$scope")" "$(now_iso)" \
        >> "$(roster_file)"
      : >> "$inbox_dir/$name.jsonl"
      echo "TEAM: ROSTER add name=$name role=$role"
    else
      echo "TEAM: ROSTER"
      if [ -s "$(roster_file)" ]; then
        sed 's/^/  /' "$(roster_file)"
      else
        echo "  (empty)"
      fi
    fi ;;

  send)
    need_team_dir
    [ -n "$from" ] && [ -n "$to" ] && [ -n "$text" ] || {
      echo "TEAM: ERROR send needs --from --to --text" >&2; exit 4; }
    ts=$(now_iso)
    msg=$(printf '{"from":"%s","text":"%s","timestamp":"%s","read":false%s%s}' \
      "$(jesc "$from")" "$(jesc "$text")" "$ts" \
      "$([ -n "$summary" ] && printf ',"summary":"%s"' "$(jesc "$summary")" || true)" \
      "")
    deliver(){ # $1 = recipient name
      printf '%s\n' "$msg" >> "$inbox_dir/$1.jsonl"
      printf -- '- %s  %s -> %s  %s\n' "$ts" "$from" "$1" "${summary:-$text}" >> "$board"
    }
    if [ "$to" = "*" ]; then
      # broadcast to every active member except sender
      n=0
      while IFS= read -r line; do
        [ -n "$line" ] || continue
        m=$(printf '%s' "$line" | sed -n 's/.*"name":"\([^"]*\)".*/\1/p')
        [ -n "$m" ] && [ "$m" != "$from" ] || continue
        [ -f "$inbox_dir/$m.jsonl" ] || : >> "$inbox_dir/$m.jsonl"
        deliver "$m"; touch_heartbeat "$m"; n=$((n+1))
      done < "$(roster_file)"
      echo "TEAM: SEND ok to=* delivered=$n"
    else
      [ -f "$inbox_dir/$to.jsonl" ] || : >> "$inbox_dir/$to.jsonl"
      deliver "$to"
      touch_heartbeat "$to"
      echo "TEAM: SEND ok to=$to"
    fi ;;

  inbox)
    need_team_dir
    [ -n "$name" ] || { echo "TEAM: ERROR inbox needs --name" >&2; exit 4; }
    f="$inbox_dir/$name.jsonl"
    [ -f "$f" ] || { echo "TEAM: INBOX empty name=$name"; exit 0; }
    echo "TEAM: INBOX name=$name"
    if [ "$unread" = 1 ]; then
      awk '/"read":false|"read": false/ {print "  " $0}' "$f"
    else
      sed 's/^/  /' "$f"
    fi
    if [ "$mark_read" = 1 ]; then
      gp_sed_inplace 's/"read":false/"read":true/g; s/"read": false/"read": true/g' "$f"
      echo "TEAM: INBOX marked-read name=$name"
    fi ;;

  status)
    if [ ! -f "$cfg" ]; then echo "TEAM: STATUS none"; exit 0; fi
    echo "TEAM: STATUS config=$cfg"
    sed 's/^/  /' "$cfg"
    echo "TEAM: ROSTER"
    sed 's/^/  /' "$(roster_file)" 2>/dev/null || echo "  (empty)"
    echo "TEAM: INBOXES"
    for f in "$inbox_dir"/*.jsonl; do
      [ -f "$f" ] || continue
      # grep -c prints 0 but exits 1 on zero matches — never `|| echo 0`
      # (that would append a second line and yield unread=0\n0).
      u=$(grep -c '"read":false\|"read": false' "$f" 2>/dev/null || true)
      t=$(grep -c . "$f" 2>/dev/null || true)
      u=${u:-0}; t=${t:-0}
      echo "  $(basename "$f"): total=$t unread=$u"
    done ;;

  health)
    # READ-ONLY probe (except send() may touch heartbeat). Row format EXACT:
    #   name|liveness|idle_s|last_touch|open_items|err_tag
    # liveness comes only from roster "active": true/false — never invented.
    # Stall: idle_s >= GOAL_STALL_SEC (default 300) AND open_items > 0.
    need_team_dir
    stall="${GOAL_STALL_SEC:-300}"
    case "$stall" in ''|*[!0-9]*) stall=300 ;; esac
    hbdir="$td/heartbeat"
    now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    now_s=$(date -u +%s)
    echo "TEAM: HEALTH stall_sec=$stall"
    while IFS= read -r line; do
      [ -n "$line" ] || continue
      nm=$(printf '%s' "$line" | sed -n 's/.*"name":"\([^"]*\)".*/\1/p')
      sc=$(printf '%s' "$line" | sed -n 's/.*"scope":"\([^"]*\)".*/\1/p')
      act=$(printf '%s' "$line" | sed -n 's/.*"active":\([a-z]*\).*/\1/p')
      [ -n "$nm" ] || continue
      # liveness from roster active flag only — never invent "active"
      live=unknown
      [ "$act" = "true" ] && live=active
      [ "$act" = "false" ] && live=stopped
      # last_touch = max(heartbeat, inbox mtime, scope mtime)
      # last_s is epoch seconds of the newest usable signal; "" = none yet.
      # Never leave it at 0 with last_iso=now — that pair made idle_s=now_s
      # (giant) and a false stall whenever a member simply had no signal.
      last_s=""
      last_iso=""
      hb="$hbdir/$nm.ts"
      if [ -f "$hb" ]; then
        hb_iso=$(tr -d '\r\n' < "$hb")
        # empty/garbage sidecar must not call `date -d ''` (GNU returns today);
        # a failed ISO parse is also NOT a signal (do not freeze last_s at 0).
        if [ -n "$hb_iso" ]; then
          hb_s=$(epoch_from_iso "$hb_iso")
          case "$hb_s" in ''|*[!0-9]*) hb_s="" ;; esac
          if [ -n "$hb_s" ] && [ "$hb_s" -gt 0 ]; then
            last_s=$hb_s
            last_iso=$hb_iso
          fi
        fi
      fi
      ib="$inbox_dir/$nm.jsonl"
      if [ -f "$ib" ]; then
        ims=$(file_mtime "$ib")
        case "$ims" in ''|*[!0-9]*) ims="" ;; esac
        if [ -n "$ims" ] && { [ -z "$last_s" ] || [ "$ims" -gt "$last_s" ]; }; then
          last_s=$ims
          last_iso=$(iso_from_epoch "$ims")
        fi
      fi
      if [ -n "$sc" ] && [ -e "$project/$sc" ]; then
        sms=$(max_tree_mtime "$project/$sc")
        case "$sms" in ''|*[!0-9]*) sms="" ;; esac
        if [ -n "$sms" ] && { [ -z "$last_s" ] || [ "$sms" -gt "$last_s" ]; }; then
          last_s=$sms
          last_iso=$(iso_from_epoch "$sms")
        fi
      fi
      # no usable signal → pretend touch at now (idle_s=0), not epoch 0
      if [ -z "$last_s" ]; then
        last_s=$now_s
        last_iso=$now
      fi
      [ -n "$last_iso" ] || last_iso="$now"
      idle_s=$(( now_s - last_s ))
      [ "$idle_s" -lt 0 ] && idle_s=0
      # open work-plan items assigned to this name — exact assignee field
      # (2nd `|` column of `- [ ] Tid | assignee | ...`). Substring grep
      # counted w12 rows against w1; field equality does not.
      open_n=0
      if [ -f "$project/.goal/work-plan.md" ]; then
        open_n=$(grep -E '^\- \[ \]' "$project/.goal/work-plan.md" 2>/dev/null \
          | awk -F'|' -v nm="$nm" '
              NF >= 2 {
                a = $2
                gsub(/^[ \t]+|[ \t]+$/, "", a)
                if (a == nm) n++
              }
              END { print n+0 }
            ')
        open_n=${open_n:-0}
      fi
      # err_tag hint from last inbox text + stall/death
      err=""
      if [ "$live" = "stopped" ] || [ "$live" = "terminated" ]; then
        err=death
      fi
      if [ -f "$ib" ]; then
        last_txt=$(tr -d '\r' < "$ib" | tail -5 | tr '\n' ' ')
        printf '%s' "$last_txt" | grep -qiE "$err_vocab_re" && err=tool-error
      fi
      if [ -z "$err" ] && [ "$idle_s" -ge "$stall" ] && [ "$open_n" -gt 0 ]; then
        err=stall
      fi
      printf '%s|%s|%s|%s|%s|%s\n' "$nm" "$live" "$idle_s" "$last_iso" "$open_n" "$err"
    done < "$(roster_file)" ;;

  delete)
    if [ ! -d "$td" ]; then echo "TEAM: DELETE none"; exit 0; fi
    rm -rf "$td"
    echo "TEAM: DELETE ok dir=$td" ;;

  *)
    echo "TEAM: ERROR unknown-command:$cmd" >&2; exit 4 ;;
esac
