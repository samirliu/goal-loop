# Interview tree (evaluation design)

Adapted from grilling: **design tree** of evaluation decisions; **frontier** = questions whose prerequisites are settled; ask the **whole frontier** per round; facts via subagents (never ask the user to look up); decisions wait on the user.

## Question format

```
❓ QN - <title>: <body / options>

➡️ <recommended answer>
```

Recompute the frontier after answers. Dependent questions go to a later round, never the same round.

## Decision tree

```
A. Goal shape
   A1 done enumerability? (yes / no / conditional)
   A2 claim family per done-item (patterns.md families)
   A3 three-layer sketch: floors / objective / horizon?
B. Objective (only if optimizing)
   B1 one primary number? maximize|minimize
   B2 Goodhart red-team (proxy? gamable path? monotone?)
   B3 probe + metric regex + tolerance/sd?
   B4 noise floor plan (N repeats, V beyond variance)
C. Horizon
   C1 what does the number not see?
   C2 calib fixtures good/bad OR horizon-waived reason
D. Floors
   D1 correctness / safety / interface non-regressions
   D2 family shapes for floors
E. Exit + budget
   E1 threshold vs forge
   E2 forge: baseline plan, dry_limit, max_iterations fuse
   E3 budget knobs / wallclock
   E4 out of scope (late ideas → proposals)
F. Confirm shared understanding → emit DRAFT
```

## Rounds

| Round | Frontier (ask together) | Facts first (subagent / read) |
|---|---|---|
| **R0 Scope** | A1; need goal-loop loop vs contract-only? | project layout, existing tests/scripts, `.goal/` stamped? |
| **R1 Classify** | A2 per candidate done-item; A3 three-layer? | patterns families; smoke-runnable check candidates |
| **R2 Objective** | B1–B3 (only if objective) | how the metric prints; existing benchmark harness |
| **R3 Noise** | B4 V vs noise; N; sd/var | **run candidate measure twice** on pre-work artifact |
| **R4 Horizon** | C1 blind spots; C2 calib vs waiver | fixture candidates; good≠bad |
| **R5 Floors + exit** | D1; E1–E3 | forge baseline row shape |
| **R6 Confirm** | Shared summary; **wait for user confirm** | — |

## Rules

- One round = whole current frontier.
- Facts are the agent's job; decisions are the user's.
- Every AC sketch: Goodhart sentinel (see `ac-shapes.md`).
- Metric AC: noise floor **before** V.
- Objective contracts: note `--strategy` at close (handoff, not a contract field).
- Done interviewing = frontier empty **and** user confirms shared understanding.
- **Only then** write `.goal/goal.md` DRAFT (Status: DRAFT). Never write stamp hash.

## Default path (complex + Teams + quantitative optimization)

Prefer:

- `exit: forge`
- `objective: maximize|minimize AC-N` with `probe:` + `baseline: delta` + `tolerance:` (and `sd:`/`var:` if harness prints spread)
- floors: executable-correctness + interface checks
- horizon: >=1 `judged` + `calib: good= bad=` on qualities the metric can chase
- budgets: `dry_limit=` + `max_iterations=` fuse
- explicit **Out of scope**
- handoff: `--strategy` every close; Teams is execution only (not in the contract)

## R0 negative exits (do not force goal-loop)

If done is non-enumerable (pure aesthetics) or one named check is already obvious:

- aesthetic → say goal-loop is the wrong instrument (or split into sub-goals)
- trivial one-check → goal-loop quick lane / skip this interview
