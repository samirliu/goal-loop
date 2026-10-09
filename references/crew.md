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
Rules: never touch .goal/ (R6); no subagents; no scope drift.
Interface contract: <relevant excerpt of interfaces.md>
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
for a multi-role team. **Portable by default**: `scripts/goal_team.sh`
implements the cc-haha file protocol (roster + inboxes + TeammateMessage)
so this works on ANY harness — no TeamCreate required. If the harness
does have native TeamCreate/SendMessage, upgrade to it for true persistent
teammates and the panel; same dual-layer rules either way. Contract, loop,
gate, and every rule stay identical - only the execution surface changes.
Prefer the default; `--teams` is for long unattended multi-role runs.
Protocol details: references/teams.md.

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
2. Team up:
   - Portable (always available): `goal_team.sh init` + `roster --add` per
     role (≤3). Summary line already declared `派工: teams`.
   - Native (if TeamCreate exists): TeamCreate + TeamPlan submit — user
     reviews the roster in the panel. Approval starts the run.
   **No `isolation: worktree`** - teammates edit the shared workspace.
   A worktree would hide their diffs from the digest and poison R7
   verdict binding. This is a hard ban, not a preference.
3. Waves: keep `work-plan.md` as plan of record; dispatch role-card
   workers -> they implement (notes home via `MSG: to=...` the controller
   `send`s) -> controller join (§4) -> `gate --check` exactly as usual.
4. Delivery/fuse: `goal_team.sh delete` (or TeamDelete). Resume: team dir
   still there -> continue; gone -> rebuild roster or fall back to the
   default backend and log it.

### 7.3 Coordination

- Interfaces stay frozen in `.goal/interfaces.md`.
- Workers MAY negotiate mid-wave: native SendMessage, or portable
  `MSG: to=<name> text=...` return lines the controller posts via
  `goal_team.sh send`.
- A negotiated interface change is binding only after it lands as a file
  write to interfaces.md (R3 spirit). Talk is cheap; the file is the
  contract.
- Briefs unchanged (paths, scope, pass condition, evidence, no `.goal/`,
  no spawn).
- The judged cold seat is NEVER a team member - dispatch one fresh
  independent Agent. Production context voids a judge.

## 8 Degradation

No Agent tool on the surface -> work inline, self-verify cold from the
claims list and artifact alone (not from production memory), label the
report `WEAKER VERIFICATION: cold self-check`.

Teams backend requested but TeamCreate/TeamPlan unavailable or refused ->
fall back to the default backend, close the wave with
`task=T2[crew:3]` and a task-suffix note `(fallback:teams-unavailable)`,
continue. Do not invent new loop-log keys (schema is exact). The gate
does not care which backend produced the artifacts.
