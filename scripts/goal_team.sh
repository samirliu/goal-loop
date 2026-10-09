#!/usr/bin/env bash
# goal_team.sh - portable Agent-Teams layer for goal-loop. Implements the
# cc-haha file protocol (team config + per-agent inbox + TeammateMessage)
# over bash + files, so --teams works on ANY Claude Code harness —
# including those with no TeamCreate/SendMessage tools at all.
# This script is the CONTROLLER's team hand: it decides nothing; the gate
# stays the only completion arbiter. Workers still never touch .goal/ (R6).
#
# Layout (project-local, under .goal/team/):
#   .goal/team/config.json          roster (cc-haha-shaped members[])
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

cmd="" project="." team="" description="" add=0 list=0
name="" role="" prompt="" scope="" from="" to="" text="" summary=""
unread=0 mark_read=0

while [ $# -gt 0 ]; do
  case "$1" in
    init|roster|send|inbox|status|delete) cmd="$1" ;;
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
    --help|-h) sed -n '2,28p' "$0"; exit 0 ;;
    *) echo "TEAM: ERROR unknown-flag:$1" >&2; exit 4 ;;
  esac
  shift
done
[ -n "$cmd" ] || { echo "TEAM: ERROR no-command (init|roster|send|inbox|status|delete)" >&2; exit 4; }

td="$project/.goal/team"
cfg="$td/config.json"
inbox_dir="$td/inboxes"
board="$td/board.md"

jesc(){ # JSON string escape, no jq
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | awk '{gsub(/\t/,"\\t"); printf "%s", $0}' | sed -e ':a' -e 'N' -e '$!ba' -e 's/\n/\\n/g'
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
        deliver "$m"; n=$((n+1))
      done < "$(roster_file)"
      echo "TEAM: SEND ok to=* delivered=$n"
    else
      [ -f "$inbox_dir/$to.jsonl" ] || : >> "$inbox_dir/$to.jsonl"
      deliver "$to"
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
      sed -i 's/"read":false/"read":true/g; s/"read": false/"read": true/g' "$f"
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
      u=$(grep -c '"read":false\|"read": false' "$f" 2>/dev/null || echo 0)
      t=$(grep -c . "$f" 2>/dev/null || echo 0)
      echo "  $(basename "$f"): total=$t unread=$u"
    done ;;

  delete)
    if [ ! -d "$td" ]; then echo "TEAM: DELETE none"; exit 0; fi
    rm -rf "$td"
    echo "TEAM: DELETE ok dir=$td" ;;

  *)
    echo "TEAM: ERROR unknown-command:$cmd" >&2; exit 4 ;;
esac
