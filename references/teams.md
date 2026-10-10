# Teams — Agent-Teams backend (native first, portable fallback)

`--teams` must work on ANY Claude Code harness. Selection is by
**detection, not by flag**: if the controller's tool list this run has
native TeamCreate/TeamPlan/SendMessage, use native (session-resumed
teammates + panel) — that is the PRIMARY path, never a quiet downgrade
to the file layer. Only when native is absent does the portable layer
run: it implements the cc-haha file protocol over bash + files
(`scripts/goal_team.sh`) so multi-role crews work everywhere. The flag
asks for a team; the tool list decides which kind.

Native "persistence" is the teammate sessionId/transcript, not an
independent OS process. Process workers stop with the lead turn; SendMessage
resumes the saved conversation. See §5.

## 1 What we took from cc-haha

| cc-haha piece | portable form |
|---|---|
| `~/.claude/teams/{name}/config.json` roster | `.goal/team/config.json` + `roster.jsonl` |
| `inboxes/{agent}.json` message queue | `inboxes/{agent}.jsonl` (JSONL; same field shape) |
| `TeammateMessage` | `{from, text, timestamp, read, summary?}` |
| `SendMessageTool` to / broadcast `*` | `goal_team.sh send --to N\|'*'` |
| `spawnTeammate` persistent process | **not portable** — Agent-tool wave workers + role cards |
| inbox poller 1s | **not portable** — controller relays on join / next brief |
| desktop team panel | **not portable** — `goal_team.sh status` + loop-log |
| TeamPlan roster approval | contract summary glance (already one-word) |

Field shape is intentionally compatible: a reader that understands
cc-haha `TeammateMessage` understands every inbox line. Layout is
project-local under `.goal/` so one ledger owns the whole run (R6 still
says workers never touch `.goal/` — the controller is the only writer).

## 2 Non-negotiable dual layer

Unchanged from crew.md §7:

- `.goal/work-plan.md` = queue of record; team roster/inbox are execution
  surface. **TaskUpdate=completed / a ticked work-plan item is NEVER a GO signal.**
- GO only when `goal_gate.sh` returns rc=0.
- No worktree isolation (digest must see every teammate edit).
- Interface changes bind only as file writes to `interfaces.md`.
- R6 in portable mode: a worker READS its own inbox file (only that one
  under `.goal/`) and never writes anything there. The interface excerpt
  is inlined in the brief - workers do not open `.goal/interfaces.md`.

## 3 Portable wave protocol (fallback layer)

1. `goal_team.sh init --team goal` once per run (after contract stamp).
2. `roster --add --name w1 --role backend --prompt '...' --scope 'src/api'`
   for each role (≤3 concurrent). Role card = persistent identity across
   waves; the process does not persist.
3. Per wave: for each open work-plan item, dispatch an Agent-tool worker
   with the role card + "unread inbox" + interface excerpt + brief fields.
   Workers write their deliverables; they may leave a note for another
   role via a return message the controller will `send`.
4. Controller `send`s negotiated notes (or board.md is the relay), then
   join + `goal_gate.sh --check` as usual. loop-log: `task=T2[teams:3]`.
5. Delivery/fuse: `goal_team.sh delete`.

Negotiation without SendMessage: worker returns
`MSG: to=<name> text=...` in its final message; controller posts it with
`goal_team.sh send`. Binding still requires an `interfaces.md` write.

## 4 Native wave protocol (primary layer)

When TeamCreate + TeamPlan + SendMessage are in the tool list, use them:

- Detection is trivial: if TeamCreate is in the tool list, native wins -
  do not "prefer portable for safety", that silently loses the session
  resume path and the panel. The user-facing flag is always `--teams`.
- TeamCreate + TeamPlan submit (roster ≤3 role cards, tasks carry the
  brief fields). Then STOP — see §5.1. The user's panel approval starts
  the run; nothing runs before it.
- Teammates negotiate via SendMessage directly; an interface change is
  binding only after a file write to interfaces.md (R3 spirit).
- Keep `work-plan.md` as queue of record; the team task list mirrors it.
  Still ban `isolation: worktree` (digest must see teammate edits).
- Teammate idle notifications are normal, not failure. `stopped` /
  `terminated` after a lead turn ends is also normal — see §5.
- Close: TeamDelete only at delivery/fuse, after the run is done. Mid-run
  death is a revive case (§5.2), never a cleanup case.

## 5 Native process lifetime (lifecycle truth)

Harness process-backed teammates (`backendType:process`) are NOT
independent persistent OS processes. What persists is the teammate
`sessionId` / transcript. The worker process dies when the lead's turn
ends, is paused, or is compacted.

- Process workers stop when the lead turn ends / pauses / compacts.
  That is normal lifetime, not "teams unavailable".
- Resume is session resume: SendMessage each roster member to continue
  its task; the saved conversation continues where it left off.
- A roster showing `stopped` / `terminated` is recoverable. Do not treat
  it as backend death. Do not rebuild the team. Do not fall back.

### 5.1 After TeamPlan submit — panel approval is mandatory

TeamPlan submit returns `review_pending` + `reviewRequired:true`. The
controller MUST end the planning turn and tell the user to approve the
roster in the panel. Pre-approval "stopped" workers are NORMAL — the
approval gate has not opened the run yet.

Do not dispatch work, claim tasks, TaskUpdate=completed, or bypass
review before the user approves. Approval starts the roster.

### 5.1b After approval lands — wake-with-brief is action #1

The "Approved … is running" notice is NOT a worker heartbeat. Process
workers are reaped at every lead turn boundary; the gap between panel
approval and the first SendMessage is a zero-output death window
(live case 2026-10-10: both members reaped before touching a file).

On the approval turn, in this order and nothing before it:

1. Liveness check (config `isActive` / `terminated`).
2. SendMessage **each** member its full task brief (wake-with-brief) —
   even if the roster claims to be running.
3. Only then write the ledger (work-plan.md etc.).

A session resume / user Stop that stopped the team is the same playbook:
open with liveness + wake-with-brief for every member with open work.
Never respawn, never TeamDelete, never fall back before the §5.3 rule.

### 5.2 Revive protocol

On resume, or whenever the roster looks dead mid-run:

1. SendMessage each roster member to continue its assigned task.
2. Keep `work-plan.md` as the queue of record; if the Team task list
   disagrees, work-plan wins and the team queue is repaired to match.
3. NEVER TeamDelete to clean up a dying team during a run. TeamDelete
   destroys the sessionId evidence and hides the bug. TeamDelete is
   delivery/fuse only.

### 5.3 Honest fallback (never silent)

Fall back only after revive fails twice for the same member, or the
roster / TeamCreate is truly gone.

- Fallback target: portable layer; if portable is also unavailable,
  default backend.
- The ledger and report MUST name the failure mode in the existing
  task= suffix form, e.g. `(fallback:teams-process-reaped)` or
  `(fallback:teams-unavailable)`. No silent fallback.
- Do not invent new loop-log keys; only task= suffixes.

## 6 CLI cheat sheet

```bash
bash scripts/goal_team.sh init   --project . --team goal --description 'run'
bash scripts/goal_team.sh roster --project . --add --name w1 \
     --role backend --prompt 'implement X' --scope 'src/api'
bash scripts/goal_team.sh roster --project . --list
bash scripts/goal_team.sh send   --project . --from w1 --to w2 \
     --text 'interface field renamed' --summary 'rename notice'
bash scripts/goal_team.sh inbox  --project . --name w2 --unread --mark-read
bash scripts/goal_team.sh status --project .
bash scripts/goal_team.sh delete --project .
```

No jq, no python, no daemon. Same deps as the rest of the skill.
