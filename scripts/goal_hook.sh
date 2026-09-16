#!/usr/bin/env bash
# goal_hook.sh - opt-in Claude Code Stop hook of goal-loop (v1.4). Borrows
# the ONE good tooth of the harness built-in /goal (physical
# stop-prevention) while keeping the arbitration deterministic: it blocks
# stopping at exactly ONE moment - the last loop-log block claims
# exit_signal=yes AND goal_gate.sh --check answers rc=2 (the false-complete
# moment). Everything else passes untouched:
#   no .goal/ or claim -> allow (rc 0)      GO (rc 0)      -> allow, deliver
#   rc=3 BLOCKED/fuses -> allow (a user decision, not a grind)
#   rc=4 state error   -> allow (fail-open: a broken contract needs a human)
# The injected reason is sanitized the way the built-in /goal sanitizes its
# "Goal continuing" channel: strip <>&, collapse whitespace, cap 240 chars,
# GOAL_LOOP_GATE: prefix (grep-able). The user can always override with Esc.
# Install (settings.json -> hooks.Stop), see INTEGRATION.md section 5.7:
#   {"hooks":{"Stop":[{"hooks":[{"type":"command",
#     "command":"bash ~/.claude/skills/goal-loop/scripts/goal_hook.sh"}]}]}}
# The hook reads .goal/ relative to its cwd (Claude Code runs hooks in the
# project directory); run elsewhere it no-ops.
set -u
export LC_ALL=C.UTF-8

here=$(cd "$(dirname "$0")" && pwd)
sd=".goal"

[ -d "$sd" ] || exit 0
[ -f "$sd/loop-log.md" ] && [ -f "$sd/state.rec" ] && [ -f "$sd/goal.md" ] || exit 0

# claimed exit? (last loop-log block's exit_signal; absent -> no claim)
claim=$(gawk '
  BEGIN { last = "" }
  /^## iteration/ { last = ""; next }
  { line = $0; sub(/\r$/, "", line)
    if (line ~ /^exit_signal=/) { p = index(line, "="); last = substr(line, p + 1) } }
  END { print last }' "$sd/loop-log.md" 2>/dev/null)
[ "$claim" = "yes" ] || exit 0

if command -v timeout >/dev/null 2>&1; then
  out=$(timeout 60 bash "$here/goal_gate.sh" --check --project . 2>&1); rc=$?
else
  out=$(bash "$here/goal_gate.sh" --check --project . 2>&1); rc=$?
fi

case "$rc" in
  2) : ;;                                           # the false-complete moment
  *) exit 0 ;;                                      # 0 GO / 3 fuses / 4 broken / other
esac

reason=$(printf '%s\n' "$out" | tr -d '\r')
reason=$(printf '%s\n' "$reason" | grep -E '^GATE: NO-GO reason=' | tail -1 | cut -d= -f2-)
[ -n "$reason" ] || reason="gate denied the claimed exit"
reason=$(printf '%s' "$reason" | sed 's/[<>&]/ /g' | tr -s ' ' | cut -c1-240)
echo "GOAL_LOOP_GATE: claim denied by the gate: $reason" >&2
echo "GOAL_LOOP_GATE: controller: append false_complete=yes to the last loop-log block, increment false_completes in state.rec, then fix the reason above and claim again (two denied claims = BLOCKED)." >&2
exit 2
