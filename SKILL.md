---
name: goal-loop
description: |-
  Goal-driven loop with an EXTERNALLY-ARBITRATED exit gate and an adversarial
  checker panel: decompose an objective into an approved acceptance-criteria
  contract, run one task per iteration delegating to named sub-agents, and stop
  only when scripts/goal_gate.sh certifies every AC as PASS or justified
  UNVERIFIABLE - the model can never self-declare completion. Trigger when the
  user states a goal and wants it driven to fully-verified completion:
  "/goal-loop [objective]", "loop until 100% satisfied", "verify every angle",
  "self-verify this and keep iterating". Not for trivial one-pass tasks,
  pure Q&A, or actions needing immediate irreversible side effects.
---

# Goal Loop (v1)

Contract-first, loop-per-iteration, gate-decides. Authority is split: you (the
controller) execute and delegate; independent checkers judge; the gate (a shell
script, not you) certifies completion. Fuses ralph-claude-code's dual-condition
exit gate with fable-mode's checker-panel discipline; design reimplementation,
no verbatim source text.

## When NOT to run

One obvious approach, fits in a single pass -> do it directly, no ceremony.
Refuse the loop when the deliverable's failure mode is an irreversible side
effect outside the workspace (money moved, messages sent, systems deleted).

## State layout (project root `.goal/`) — CONTROLLED, never hand-edit mid-run

| file | role | written by |
|---|---|---|
| goal.md | the contract: objective, AC-N lines, out-of-scope, budget knobs, approval stamp | bootstrap only; frozen after approval |
| work-plan.md | prioritized tasks derived from ACs, checkbox list | controller |
| state.rec | flat `key=value` counters: iteration, breaker, false_completes, replans | controller |
| loop-log.md | one block per iteration, `key=value` lines, append-only | controller |
| verdicts.rec | `id|verdict|iter|digest|command|evidence` records, append-only | controller (from checkers) |
| logs/ | unattended outer-loop output, rotated | goal_loop.sh |

`grep` is the query language; all five files are line-oriented on purpose.
Workers must never touch `.goal/` (R6). See references/exit-gate.md for schemas.

## Phase 1 - Contract (bootstrap; run once)

1. If `.goal/` exists with a valid approval stamp, skip to Phase 2.
2. Copy `assets/goal.contract.md` -> `.goal/goal.md`. Decompose the user's
   objective into `AC-1..AC-N` lines. Per AC write: (a) a yes/no decision
   statement in the user's words, (b) the NAMED CHECK - the exact command,
   file comparison, or observable that settles it. Pick check patterns from
   references/domain-patterns.md for the artifact type; a check must be able
   to FAIL; "looks right" is not a check.
3. Derive work-plan.md (tasks -> the ACs they realize) and init state.rec
   (iteration=0, breaker=CLOSED, false_completes=0, replans=0, fail caps from
   budget).
4. Present the contract to the user. ONLY on explicit approval, stamp
   `approved: <sha1-8-of-AC-body> <date>` in goal.md. No stamp -> the gate
   answers NO-GO; never iterate. The user may amend freely until stamping;
   after stamping, you propose amendments, you do not apply them (R3).

## Phase 2 - Iteration (one task per loop, one pass per turn)

At each iteration:

1. Re-read `.goal/state.rec` + last 3 blocks of loop-log.md. If
   breaker=OPEN or false_completes>=2 -> stop, report BLOCKED to the user.
2. Take the highest-priority unchecked task of work-plan.md (one per loop).
3. Delegate artifact production via the Agent tool:
   reasoning-heavy -> `goal-worker`, bulk mechanical -> `goal-mech-worker`.
   Brief each with: bounded task, exact output path, needed context, pass
   condition, and "return evidence (command + output) with your report".
   Workers do not spawn workers. No Agent tool -> work inline and log
   `WEAKER VERIFICATION: cold self-check, no sub-agents`.
4. Skeptical self-review of the artifact: name a real weakness or state
   plainly it is clean; never manufacture findings, never rubber-stamp.
5. Before closing the task, assemble the checker panel
   (references/checker-panel.md): extract claims/requirements FROM THE
   FINISHED ARTIFACT, give each its exact check, then spawn in parallel
   `goal-checker-mech` x2-3 (mechanical bundles) + `goal-checker-req` x1.
   Checkers receive the AC text VERBATIM + artifact paths ONLY - never your
   reasoning, never hunches about which items are suspect. On checker
   disagreement escalate one `goal-adjudicator` (it adjudicates, it does not
   re-check everything).
6. Append verdicts to verdicts.rec: `id|verdict|iter|digest|command|evidence`;
   verdict in PASS/FAIL/UNVERIFIABLE; a PASS without a quoted output line is
   void. Bind each record to the iteration number and the current tree digest
   (`bash scripts/goal_gate.sh --digest`).
7. FIX any FAIL, then RE-RUN ONLY the failed check (per-check fail cap 3 ->
   at cap, mark task blocked and ask the user). A re-run is illegal if the
   covered files did not change since the FAIL (recompute the digest first,
   R2); no-change retries count as stagnation, not as work.
8. Append the loop-log block (iteration, task, files_modified, checks
   PASS/FAIL/UNVERIFIABLE counts, digest, progress=yes/no) and update
   state.rec counters. Progress accounting: `no_progress_limit` consecutive
   no-progress iterations -> change strategy, not the goal (replans<=2; a
   third replan -> ask the user); two identical error blocks -> BLOCKED.

## Phase 3 - Exit gate (the only arbiter)

End EVERY iteration with the status block (exact keys, parseable):

```
---GOAL_STATUS---
ITERATION: <n>
STATUS: IN_PROGRESS | COMPLETE | BLOCKED
TASK: <id>  TASKS_DONE: <n>  FILES_MODIFIED: <n>
TESTS: PASSING | FAILING | NOT_RUN
CHECKS: PASS <n> / FAIL <n> / UNVERIFIABLE <n>
TREE_DIGEST: <12-hex from goal_gate.sh --digest>
EXIT_SIGNAL: false | true
RECOMMENDATION: <one line>
---END_GOAL_STATUS---
```

`EXIT_SIGNAL: true` is permitted ONLY when: every AC's latest verdict is
PASS or a justified UNVERIFIABLE; zero open FAIL; the panel judged THIS
digest; budget not exhausted; you touched nothing under `.goal/` beyond the
state files. Claiming it is not holding it: the authority is external -

```
bash scripts/goal_gate.sh --check    # 0=GO 2=NO-GO 3=BLOCKED/breaker 4=state error
```

Exit 0 -> deliver. Exit 2 -> continue iterating (or stop at budget). Exit 3
-> stop, report BLOCKED with reasons. If you claimed EXIT_SIGNAL true and the
gate answered NO-GO, log `false_complete=yes`; the gate counts them; two ->
halt BLOCKED, hand back to the user. Never deliver with an open FAIL.

## Delivery format

Hand over: what was built; the verification summary - every item the panel
REFUTED and then fixed, listed concretely (a clean pass stated plainly beats a
manufactured caveat); verdict counts + panel makeup (`2x mech, 1x req`);
each UNVERIFIABLE named with the probe that was inapplicable and why; final
gate line (`GATE: GO digest=<...> iter=<n>`). Attach nothing outside the
contract; late findings go to the user as proposals.

## Budget knobs (contract may override; sane defaults)

max_iterations=12  no_progress_limit=2  max_replans=2  per_check_fail_cap=3
panel_max=4  wallclock=1800s (unattended)

## Unattended outer loop (opt-in, never default)

`bash scripts/goal_loop.sh --continue [--max-iterations=N] [--dry-run]
[--check-only] [--resume] [--help]` - needs the `claude` CLI on PATH. The
shell loop trusts ONLY the gate's exit code, never the status block's claims.
Honors HTTP(S)_PROXY. On Windows/git-bash: no jq, CR-stripping and
`LC_ALL=C.UTF-8` are already handled in the scripts.

References: read exit-gate.md before every gate decision; checker-panel.md
when assembling the panel; domain-patterns.md when writing the contract.
