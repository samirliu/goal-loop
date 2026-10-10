# Crew - parallel dispatch, join, final review

## 1 When crew applies

Decompose the objective; crew applies when the split yields ≥2 task domains
with DISJOINT file scopes and stateable interfaces. Interfaces you cannot
state -> serial single-task (log the reason). Crew composition is
controller-elected (no flag). Backend selection does take a flag: default
one-shot subagents; `--teams` opts into the Teams backend (§7).

## 2 Interface first

Before dispatching, write `.goal/interfaces.md`: module boundaries, shared
types, naming conventions, who owns which files. Frozen at crew start;
changes are proposals (R3 spirit).

Coordination channel by backend:
- Default: workers coordinate ONLY through files + your briefs - a plain
  text reply from a worker is invisible to the others.
- Teams: workers MAY SendMessage to negotiate mid-wave. Negotiation is
  never binding on its own - an interface change counts only after it
  lands as a file write to interfaces.md (R3 spirit).

## 3 The brief (per worker)

```
Task: <bounded deliverable>
Output paths: <exact>
Scope: touch ONLY these files/dirs: <list>
Pass condition: <named check or observable>
Evidence: return the command you ran and its decisive output.
Rules: never write .goal/; read only your own inbox (if the brief says so);
no subagents; no scope drift. (R6)
Interface contract: <excerpt INLINED here by the controller - workers must
not open .goal/interfaces.md themselves>
```

Dispatch up to 3 workers in ONE message (they run concurrently). Their
execution craft is theirs - do not put goal-loop rules in the brief.
Teams backend: each roster member's TeamPlan prompt carries the same
brief fields below; the shared task item description repeats Task /
Output paths / Scope / Pass condition so the backlog is self-describing.

## 4 Join

Wave finished (default: all workers returned; Teams: all wave items
closed or you call the wave) -> merge review: run the pass conditions,
read the seams (interfaces between their outputs), fix trivial mismatches
yourself. Interface conflict needing a redesign -> one serial repair
round; two failed repairs -> fall back to serial execution (log it).
Join is bookkeeping. It is not GO - only the gate decides that.

## 5 FAIL attribution

Deterministic FAIL after join: fix within the owning worker's scope, then
`goal_gate.sh --verify [AC-ID]`. A FAIL that cannot be attributed -> rerun
the batch serially (bundle unbundle rule). Loop-log the wave as
`task=T2[crew:3]` with each worker's file list (`task=T2[teams:3]` when the
Teams backend below is in use).

## 6 Final review (judged ACs - once, before claiming exit)

Dispatch ONE fresh reviewer seat. Brief carries: verbatim AC text, evidence
paths ONLY, rubric anchors. Never the producer's reasoning. Verdicts
ternary with quoted observation; findings must bind evidence.

Judging quality claims (what "逼真/好用/清晰" become) - in order:
- Rubric decomposition: observable dimensions, written 1-5 anchors, threshold.
- Pairwise A/B at a FIXED observation point (same camera/input/viewport)
  vs the previous iteration or a named reference artifact.
- Reference anchoring: delta against a known-good example, not absolute vibes.

Perspective note for reviewers: a far wing-tip or tail plane may PROJECT
above the fuselage silhouette from a quarter view - normal geometry, not a
floating defect; call detached only with a 3D gap across views.

## 7 Teams backend (opt-in)

Default = the one-shot subagents above. `--teams` swaps Step 2's dispatch
for a multi-role team, selected by **native first** detection: if the
controller's own tool list contains native TeamCreate/TeamPlan/SendMessage
this run, use NATIVE (session-resumed teammates + panel). Only when native
is absent fall back to the portable layer (`scripts/goal_team.sh`, cc-haha
file protocol - roster + inboxes + TeammateMessage), which runs on ANY
harness. The flag `--teams` never selects the layer; detection does, and
the run declares `teams native` / `teams portable` in the summary. Same
dual-layer rules either way; contract, loop, gate, and every rule stay
identical - only the execution surface changes. Prefer the default;
`--teams` is for long unattended multi-role runs. Protocol details:
references/teams.md.

Native process lifetime (truth): process-backed teammates are NOT
independent persistent OS processes. They stop when the lead turn ends /
pauses / compacts; the persistent object is the teammate sessionId /
transcript. Resume via SendMessage per roster member. `stopped` /
`terminated` is recoverable, not backend death. Never silent-fallback;
never TeamDelete mid-run to "clean up". Full protocol: teams.md §5.

### 7.1 Dual layer (non-negotiable)

`.goal/` already owns a work queue (`work-plan.md`, what `goal_ctl.sh
status` reads). The Team task list is a **projection** of that queue for
the panel and self-claim - it is not a second source of truth.

| | Work tracking | Court |
|---|---|---|
| where | `.goal/work-plan.md` + Team task list (mirror) | contract + gate + verdicts |
| says a work item is done | controller ticks work-plan; TaskUpdate=completed | — |
| says the GOAL is done | — | `goal_gate.sh` rc=0 only |

**`TaskUpdate = completed` (and a ticked work-plan item) is NEVER a GO signal.**
The gate is the only completion authority. Teammates still never touch
`.goal/` (R6). If work-plan and the Team task list disagree, work-plan wins
and the team queue is repaired to match.

### 7.2 Lifecycle

1. Contract stamped (unchanged).
2. Team up (native first - probe the tool list, do not ask the user):
   - Native (TeamCreate/TeamPlan in the tool list): TeamCreate + TeamPlan
     submit returns `review_pending` + `reviewRequired:true` — then END
     THE PLANNING TURN. Tell the user to approve the roster in the panel.
     Approval starts the run; nothing dispatches before it. Pre-approval
     `stopped` workers are NORMAL (review gate not yet opened) — not a
     failure. This is the PRIMARY path whenever native exists; do not
     quietly use the portable layer just because it is available.
   - Portable (native absent/unusable): `goal_team.sh init` + `roster
     --add` per role (≤3).
   Summary line declares `派工: teams native` or `teams portable`.
   **No `isolation: worktree`** - teammates edit the shared workspace.
   A worktree would hide their diffs from the digest and poison R7
   verdict binding. This is a hard ban, not a preference.
3. Waves: keep `work-plan.md` as plan of record; dispatch role-card
   workers -> they implement (native: teammates SendMessage each other
   directly; portable: notes home via `MSG: to=...` the controller
   `send`s) -> controller join (§4) -> `gate --check` exactly as usual.
   Native process workers stop when the lead turn ends / pauses /
   compacts — that is lifetime, not failure. On resume or a dead roster:
   SendMessage each member to continue its task (session resume);
   work-plan.md stays the queue of record.
4. Delivery/fuse: native -> TeamDelete the roster ONLY here, after the
   run; portable -> `goal_team.sh delete`. NEVER TeamDelete mid-run to
   clean up a dying team — it destroys sessionId evidence and hides the
   bug. Resume: roster present -> SendMessage revive (teams.md §5.2);
   revive fails 2x or roster/TeamCreate truly gone -> fall back to
   portable or default backend and name the mode in the ledger, e.g.
   `(fallback:teams-process-reaped)` or `(fallback:teams-unavailable)`.
   No silent fallback.

### 7.3 Coordination

- Interfaces stay frozen in `.goal/interfaces.md`.
- Workers MAY negotiate mid-wave: native SendMessage, or portable
  `MSG: to=<name> text=...` return lines the controller posts via
  `goal_team.sh send`.
- A negotiated interface change is binding only after it lands as a file
  write to interfaces.md (R3 spirit). Talk is cheap; the file is the
  contract.
- Briefs unchanged (paths, scope, pass condition, evidence, no `.goal/`
  writes, no spawn). The interface excerpt is INLINED in the brief; a
  worker reading `.goal/interfaces.md` itself is a scope violation (R6).
- The judged cold seat is NEVER a team member - dispatch one fresh
  independent Agent. Production context voids a judge.

## 8 Degradation

No Agent tool on the surface -> work inline, self-verify cold from the
claims list and artifact alone (not from production memory), label the
report `WEAKER VERIFICATION: cold self-check`.

Teams backend: never silent-fallback. Process workers stopping when the
lead turn ends / pauses / compacts is NORMAL lifetime (§7) — revive via
SendMessage, not fallback. Fall back only when revive fails twice or the
roster / TeamCreate is truly gone.

- revive failed 2x / process reaped and unresumable -> portable (or
  default if portable also dead); close the wave with `task=T2[crew:3]`
  and suffix `(fallback:teams-process-reaped)`.
- native AND portable both unavailable or refused -> default backend,
  close the wave with `task=T2[crew:3]` and suffix
  `(fallback:teams-unavailable)`.
- Ledger and report MUST carry the suffix.
  Do not invent new loop-log keys (schema is exact); only task= suffixes.
  The gate does not care which backend produced the artifacts.
