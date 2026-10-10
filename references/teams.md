# Teams — Agent-Teams backend (native first, portable fallback)

`--teams` must work on ANY Claude Code harness. Selection is by
**detection, not by flag**: if the controller's tool list this run has
native TeamCreate/TeamPlan/SendMessage, use native (persistent
teammates + panel) — that is the PRIMARY path, never a quiet downgrade
to the file layer. Only when native is absent does the portable layer
run: it implements the cc-haha file protocol over bash + files
(`scripts/goal_team.sh`) so multi-role crews work everywhere. The flag
asks for a team; the tool list decides which kind.

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
  do not "prefer portable for safety", that silently loses persistence
  and the panel. The user-facing flag is always `--teams`.
- TeamCreate + TeamPlan submit (roster ≤3 role cards, tasks carry the
  brief fields); the user's panel approval starts the run.
- Teammates negotiate via SendMessage directly; an interface change is
  binding only after a file write to interfaces.md (R3 spirit).
- Keep `work-plan.md` as queue of record; the team task list mirrors it.
  Still ban `isolation: worktree` (digest must see teammate edits).
- Teammate idle notifications are normal, not failure.
- Close: TeamDelete. If the native path dies mid-run (team unavailable /
  roster lost), fall back to portable or default backend and log it.

## 5 CLI cheat sheet

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
