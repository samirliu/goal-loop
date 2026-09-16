---
name: goal-loop
description: |-
  Goal-driven loop with an EXTERNALLY-ARBITRATED exit gate: decompose an
  objective into an approved acceptance-criteria contract, run one task per
  iteration delegating to named sub-agents, and stop only when
  scripts/goal_gate.sh certifies completion - the model can never
  self-declare it. Since v1.2 the gate itself re-runs every deterministic
  named check (zero model in the trust chain) and supports the forge exit:
  for open-ended "make it as good as possible" objectives, the loop ends on
  verification exhaustion (K consecutive dry adversarial rounds), not on
  floors alone. Trigger when the user states a goal and wants it driven to
  fully-verified completion: "/goal-loop [objective]", "loop until 100%
  satisfied", "verify every angle", "self-verify this and keep iterating",
  "keep optimizing until it stops improving". Not for trivial one-pass
  tasks, pure Q&A, or actions needing immediate irreversible side effects.
---

# Goal Loop (v1.2)

Contract-first, loop-per-iteration, gate-decides. Authority is split: you (the
controller) execute and delegate; independent checkers judge quality claims;
the gate (a shell script, not you) certifies completion AND re-runs every
deterministic check itself. Design reimplements ralph-claude-code's dual-
condition exit gate with fable-mode's checker-panel discipline.

Invocation: `/goal-loop [flags] <objective>` - flags `--mode=quick|standard|deep`,
`--max-iterations=N`, `--min-acs=N`, `--auto`, `--forge` (semantics:
references/modes.md); unknown flags are an error.

## When NOT to run

One obvious approach, fits in a single pass -> do it directly, no ceremony.
Refuse the loop when the deliverable's failure mode is an irreversible side
effect outside the workspace (money moved, messages sent, systems deleted).

## State layout (project root `.goal/`) — CONTROLLED, never hand-edit mid-run

| file | role | written by |
|---|---|---|
| goal.md | the contract: objective, AC-N lines, exit policy, out-of-scope, budget knobs, approval stamp | bootstrap only; frozen after approval |
| work-plan.md | prioritized tasks derived from ACs + discovery items, checkbox list | controller |
| state.rec | flat `key=value` counters: iteration, breaker, false_completes, replans, dry_streak | controller (via goal_ctl.sh) |
| loop-log.md | one block per iteration, `key=value` lines, append-only | controller |
| verdicts.rec | `id|verdict|iter|digest|command|evidence` records, append-only | controller (from seats; deterministic ids are bookkeeping only - the gate re-runs those itself) |
| logs/ | unattended outer-loop output, rotated | goal_loop.sh |
| evidence/ | seat-produced artifacts (screenshots, dumps, critic answers) | named checks / critic |

`grep` is the query language; all files are line-oriented on purpose.
Workers must never touch `.goal/` (R6). Schemas: references/exit-gate.md.

## Phase 1 - Contract (bootstrap; run once)

1. If `.goal/` exists with a valid approval stamp, skip to Phase 2.
2. Copy `assets/goal.contract.md` -> `.goal/goal.md`. Decompose the objective
   into `AC-1..AC-N`. Per AC write: (a) a yes/no decision statement in the
   user's words, (b) the NAMED CHECK in the contract grammar:
   `- AC-1 | <statement> | check: \`<command>\` | expected: <spec>`
   where spec is `exit=0` (default), a metric comparison (`>=60`, `<=1.8`,
   ...), or `judged` (a quality claim a program cannot settle - a seat
   judges it). Every check must be able to FAIL; "looks right" is not a
   check. Pick shapes from references/domain-patterns.md. Before stamping,
   smoke-run EVERY named check once; a check that cannot execute as written
   is rewritten here, never stamped (modes.md).
   Exit policy: `exit: threshold` (default - deliver when all floors pass)
   or `exit: forge` (maximization goals - deliver on verification
   exhaustion; see Phase 3). Optimization-type objectives SHOULD declare
   metric ACs against a measured baseline stored under `.goal/`.
3. Derive work-plan.md (tasks -> the ACs they realize) and init state.rec.
4. Approval: default (gate mode) - present the contract to the user; ONLY on
   explicit approval, stamp `approved: <sha1-8-of-AC-body> <date>` in
   goal.md. With `--auto`, still show the contract in full, then stamp
   immediately, appending `auto` (audit marker). No stamp -> the gate
   answers NO-GO; never iterate. The user may amend freely until stamping;
   after stamping, you propose amendments, you do not apply them (R3).
   Irreversible-side-effect refusals hold in both modes.

## Phase 2 - Iteration (one task per loop, one pass per turn)

1. Re-read `.goal/state.rec` + last 3 blocks of loop-log.md. If
   breaker=OPEN or false_completes>=2 -> stop, report BLOCKED.
2. Take the highest-priority unchecked task of work-plan.md. Purely
   mechanical, mutually independent actions (rename/format/补全类) MAY be
   bundled: cap 5 actions, disjoint files, mark the entry `[bundle]`; on
   any FAIL, unbundle for the fix round. Reasoning-heavy tasks stay
   one-task-per-loop.
3. Delegate artifact production via the Agent tool: reasoning-heavy ->
   `goal-worker`, bulk mechanical -> `goal-mech-worker`. Brief each with:
   bounded task, exact output path, needed context, pass condition, and
   "return evidence (command + output) with your report". Workers do not
   spawn workers. No Agent tool -> work inline and log `WEAKER
   VERIFICATION: cold self-check, no sub-agents`. Named goal-* types
   unregistered -> general-purpose with role text injected verbatim; log
   the substitution.
4. Skeptical self-review of the artifact: name a real weakness or state
   plainly it is clean; never manufacture findings, never rubber-stamp.
5. Before closing the task, assemble the panel
   (references/checker-panel.md) FOR THIS ARTIFACT's claims and the ACs it
   realizes - not the whole contract. Deterministic ACs need NO seat: the
   gate re-runs them. Spawn `goal-checker-req` x1 (requirements coverage +
   claim nomination + seam hunt); on forge, add `goal-checker-critic` x1;
   deep adds an adversarial seat; on split, escalate `goal-adjudicator`.
   Seats receive the AC text VERBATIM + artifact paths ONLY - never your
   reasoning, never hunches. On checker disagreement escalate one
   adjudicator (it adjudicates, it does not re-check everything).
6. Append verdicts to verdicts.rec:
   `id|verdict|iter|digest|command|evidence`; verdict PASS/FAIL/UNVERIFIABLE;
   a judged PASS without a quoted output line is void. Bind each record to
   the IN-FLIGHT iteration number (state.iteration + 1) and the current
   tree digest (`bash scripts/goal_gate.sh --digest`). For deterministic
   ACs the bind is bookkeeping; the gate's rerun is the evidence. Checks
   that generate files write them under `.goal/evidence/` (digest-excluded).
7. FIX any FAIL. Deterministic: re-run via the gate
   (`goal_gate.sh --verify [AC-ID]`) - its exit code is the verdict, no
   seat involved. Judged: re-run THAT seat only. A re-run is illegal if the
   covered files did not change since the FAIL (R2 - seats only; gate
   re-runs are measurement, always legal). Per-check fail cap 3 -> at cap,
   mark the task blocked and ask the user.
8. Append the loop-log block and update state.rec IN ONE Bash call:
   `bash scripts/goal_ctl.sh close-iteration --project . --task ID --files
   LIST --checks-pass N --checks-fail N --checks-unverifiable N
   [--dry yes|no]` (--dry REQUIRED on forge contracts: yes = this round's
   panel+critic produced no new evidence-backed finding and all fix-now
   discovery items are closed). Progress accounting: no_progress_limit
   consecutive no-progress iterations -> change strategy, not the goal
   (replans<=2); two identical error signatures -> BLOCKED.

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
PASS or a justified UNVERIFIABLE (deterministic ACs: the gate's own rerun
counts); zero open FAIL; the panel judged THIS digest; on forge,
dry_streak >= dry_limit; budget not exhausted; you touched nothing under
`.goal/` beyond the state files. Claiming it is not holding it:

```
bash scripts/goal_gate.sh --check    # 0=GO 2=NO-GO 3=BLOCKED 4=state error
```

Exit 0 -> deliver. Exit 2 -> continue iterating (or stop at budget).
Exit 3 -> stop, report BLOCKED with reasons; on forge, rc=3
`budget-fuse` means the budget ran out WITHOUT exhaustion - ask the user
to extend or deliver best-so-far. If you claimed EXIT_SIGNAL true and the
gate answered NO-GO, log `false_complete=yes`; two -> halt BLOCKED. Never
deliver with an open FAIL.

## Forge exit (`exit: forge`) - for "as good as possible" objectives

Threshold floors alone cannot certify "optimal". Forge adds two conjuncts:
(1) dry streak - `dry_limit` (default 3) consecutive iterations in which
the panel + adversarial seat + completeness critic produced NO new
evidence-backed finding and all fix-now discovery items are closed;
(2) the completeness critic's cold answer to "which dimension is still
missing" is empty, archived under `.goal/evidence/critic-iter-N.md`.
max_iterations degrades to a pure fuse (rc=3 budget-fuse, ask the user).
The dry streak is controller-bookkept and discipline-audited, not
mechanically provable - the gate's teeth against false dry claims are the
deterministic rerun (a FAIL it finds on a claimed exit counts as a
false-complete) and R8's evidence rule on findings. Symmetric
anti-gaming: manufactured findings are as forbidden as manufactured
passes (R8).

## Delivery format

Hand over: what was built; the verification summary - every item the panel
REFUTED and then fixed, listed concretely; verdict counts + panel makeup;
each UNVERIFIABLE named with probe and why; discovery triage list (fixed /
deferred / declined-with-reason); on forge, the dry evidence (K rounds,
critic archive) and the metric deltas vs baseline; final gate line
(`GATE: GO digest=<...> iter=<n> mode=<threshold|forge>`). Attach nothing
outside the contract; late findings go to the user as proposals.

## Budget knobs (contract may override; sane defaults)

max_iterations=12  no_progress_limit=2  max_replans=2  per_check_fail_cap=3
panel_max=4  dry_limit=3  check_timeout=120  wallclock=1800s (unattended)
Modes, `--auto`, DSL grammar: references/modes.md.

## Unattended outer loop (opt-in, never default)

`bash scripts/goal_loop.sh --continue [--max-iterations=N] [--dry-run]
[--check-only] [--resume] [--help]` - needs the `claude` CLI on PATH. The
shell loop trusts ONLY the gate's exit code, never the status block's
claims. Honors HTTP(S)_PROXY. On Windows/git-bash: no jq, CR-stripping and
`LC_ALL=C.UTF-8` are handled in the scripts; check commands run at project
root; without coreutils `timeout` a hung check hangs (documented).

Self-test: `bash tests/run_tests.sh` (scenario suite, no API needed).

References: exit-gate.md before every gate decision; checker-panel.md when
assembling the panel; domain-patterns.md when writing the contract;
modes.md for flags, approval modes, DSL grammar and the helper script;
INTEGRATION.md for install, flags-in-Chinese and troubleshooting.
