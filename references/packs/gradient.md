# Pack: gradient (GRADIENT)

**Open when:** contract has `objective:` · `exit: forge` · horizon / `horizon-waived:` · CLI uses `--strategy` · comparing policy costs or autonomous promotion · you are reading EFFICIENCY output.

**Invariant: GRADIENT** — optimization never delivers below the water mark; blind spots are declared; waves are labeled for attribution.
**Also touches FENCE** — `progress=no` must carry `strategy_delta=` (honest next direction).

Legacy aliases: `R10 R11 R13 R17b R19` → GRADIENT / FENCE.

---

## 1 Water mark (`objective:` + `best_score`)

- Contract line: `objective: maximize AC-N` or `objective: minimize AC-N` (primary score AC).
- `best_score` is the water mark: high-water for maximize, low-water for minimize.
- Claim refuses a score worse than the water mark in that direction (`score-regressed`). Before changing a qualified artifact, save its owned files with `goal_store.py incumbent save`. Use `--intermediate` during exploration after floors and horizon pass. Capture the trial's exact output before rollback. The [checkpoint procedure](../../docs/transaction-state.md#accepted-artifact-checkpoints) explains how to recover and recheck the restored artifact.
- `tolerance:` (and data-driven `sd:`/`var:` bands from `packs/instrument.md`) widen the compare so noise is “holds”, not “regressed”.
- Band math uses `|best|*tol` so negative water marks do not flip direction.

## 2 Horizon (blind-spot guard)

- An objective is a **gradient**: what the number cannot see gets optimized away.
- Stamp requires either:
  - ≥1 judged AC (with `calib:` preferred) watching the qualities the metric can chase, **or**
  - `horizon-waived: <why the blind spot is immaterial>` (frozen by the stamp).
- Neither present → stamp refuses. Silent absence is the failure mode.

## 3 Attribution (label the wave)

- On objective contracts, every `close-iteration` must carry `--strategy <label>` (writer tooth). Unlabeled waves are refused (`rc=4`).
- Objective labels are single ASCII tokens (`[A-Za-z0-9][A-Za-z0-9._-]*`), so `STRATEGY-PICK` can round-trip them without truncation or delimiter ambiguity. Legacy threshold-only labels retain their existing folding behavior.
- `scores.rec` 4th column is the strategy label; `ctl status` derives local evidence from measured adjacent rounds. A joint crew wave is one treatment, not independent evidence for each worker.
- `strategy_delta=` remains mandatory when `progress=no` (what changes next). Grinding without revising is make-work.

## 4 Divergence (score vs judge)

- When `scores.rec` holds two comparable points (`iter|score|judge` both numeric) and their **directions oppose**, the objective is optimizing away from perceived quality → claim refused (`DIVERGENCE:score-vs-judge`).
- Flat movement is unverified, not divergence. Fewer than two points = skip.

## 5 Forge exit (`exit: forge`)

GO requires **all** of:
1. Floor ACs pass (every non-objective AC),
2. `dry_streak >= dry_limit` (default 3) of deterministic-clean rounds with no new evidence-backed finding,
3. Completeness critic answers empty.

- `max_iterations` is a pure fuse (`budget-fuse` / rc=3).
- Metric ACs default `baseline: delta`; stamp requires `.goal/baseline.md` (pre-stamp smoke run **is** the baseline measurement, repeats≥2).
- Threshold exit (default) is the other policy: deliver when every AC floor passes. Exit policy is a **contract field**, not a mode matrix.

Before stamping a forge contract, declare `.goal/forge-plan.json`. Each case
names a dimension, a frozen input file, and a command that reads that input
from stdin. List the probe instruments and the remaining blind spots.

```json
{
  "version": 1,
  "instruments": ["probe.py"],
  "cases": [
    {"id": "signed", "dimension": "integer-sign", "input": "cases/signed.json",
     "command": ["python3", "-B", "probe.py"]}
  ],
  "blind_spots": ["Inputs outside the declared cases"]
}
```

Give goal-critic the next iteration, current artifact digest, approved probe
scope digest, and recent raw results. Its existing
`critic-iter-<N>.md` file now carries `ITERATION`, `ARTIFACT`, and `PLAN`
bindings before FINDING/CLEAR. On `--dry yes`, the controller archives the
critic and runs the declared probes under the remaining budget. A missing
critic, a finding, a failed floor, or an incomplete probe batch earns no dry
credit. Repeated successful inputs count as stability checks. New coverage is
reported separately. Final GO includes `coverage=declared`.

Stamp archives the plan and input/instrument bytes in
`evidence/raw/0.txt`. Each dry attempt keeps its actual inputs' identities,
outputs, elapsed time, failures, remaining cases and blind spots in its
canonical raw record. Use `status` for the latest bounded result.
For an older forge run, author the plan and run `goal_ctl.sh migrate`.
Migration preserves history and starts fresh dry evidence. The same entry
point can add probes while retaining all earlier cases and materials.

## 6 EFFICIENCY / STRATEGY-PICK / eval-gap / promote

Printed by `ctl status` when optimizing or stalled. **Advisory to the gate** — never changes gate rc or hint. **STRATEGY-PICK is what the next wave uses** (brief + replan/delta NEXT text).

- **EFFICIENCY** — one kernel (`scripts/goal_strategy.awk`) computes both display and pick. For a newly observed artifact, score at t is the AFTER measurement: `delta(t) = score(t) - score(t-1)` belongs to label(t), including its entry wave. First recorded score is an anchor, not credited gain. Missing/non-numeric scores, missing artifact identities, unchanged/restored artifacts or ledger gaps break attribution; only the latest eligible measured suffix counts.
- **EVENTS** — status separates observed artifact versions, acceptance claims, unchanged-artifact rounds, restorations and new score readings. Unchanged/restored artifacts do not earn fresh artifact-strategy gain or role-promotion credit. Artifact stagnation is derived from content identities, not reset by a self-reported `progress=yes`. A changed reading on unchanged bytes is information, not evidence of a successful artifact edit. Legacy digests are marked unverified; these counts cannot observe failed worker attempts that left no new artifact or replace missing duration/cost telemetry.
- **RUNTIME** — actual supervised command spans under `.goal/evidence/runtime/`, with input artifact, contract/checker identities, parent span, elapsed time and result. Timeout/cancelled spans remain in the data; interrupted/incomplete traces and unavailable costs stay unknown. Executor/measurement durations include nested work and are not summed as wall time. Runtime observations do not count as artifact gains, and transitive/external inputs may still be unknown. Missing telemetry is not zero cost; crew decisions must wait for usable comparable samples.
- **STRATEGY-PICK** — latest window for each label supersedes its history. Prefer the greatest direction-adjusted gain per measured wave beyond `tolerance:`; avoid regressions or ≥3 flat deltas (whole observed range inside band). Unmeasured/oscillating is `prefer=none`, not invented confidence. Ties use first appearance. A label cannot be both prefer and avoid. Historical EFFICIENCY lines describe history; use the pick for current routing.
- Paste the pick into every wave brief. `avoid` means change the hypothesis before a deliberate retry; record the counterevidence in `strategy_delta`, rather than rename the same tactic. After retry, new evidence supersedes the old window.
- **eval-gap** — latest three adjacent measured rounds flat while stalled: inspect raw failures first, then ask goal-critic for candidate AC proposals in `.goal/proposals/`. Plateau alone does not prove the metric is wrong. Contract changes require approval.
- **promote** — repeated task id while stalled suggests inspecting a role card; repetition is not evidence of effectiveness.
- **attribution-unused** — an objective contract has no strategy labels.

These are **local observational deltas**, not causal estimates or statistical significance. A tolerance is a decision deadband, not a confidence interval. If `sd:`/`var:` is declared, scores.rec lacks the dispersion needed for comparison: show `noise-unverified`, suppress exploit/prune and gather repeated raw measurements; the gate keeps its own dispersion check. Per-wave slope measures iteration economy; it does not measure tokens, elapsed time, or money. Compare parallel widths under the same total budget, counting joins, verification, retries and failures.

### Learning without moving the goalposts

Before dispatch, pre-register one falsifiable change: hypothesis → expected metric movement → failure condition → next action. Read the smallest decisive raw trace on failure; fix execution, instrument, or hypothesis according to evidence. A green candidate becomes the incumbent only after floors and horizon checks hold at its digest; a label alone cannot establish quality.

For a reusable strategy/skill change, use the existing `.goal/proposals/` channel: include triggering trace and reproducer, old/new policy diff, scope of applicability and rollback condition. Freeze graders, budgets and held-out tasks before comparing; keep hidden tests/answers out of worker briefs (fresh context alone is not a data holdout). Compare incumbent vs candidate on paired fresh task states, multiple trials, with all failures counted. Report acceptance rate, all-trial total cost / accepted deliveries, and median/p90 time-to-accepted-delivery; zero accepted means cost per delivery is undefined. Failed trials are budget-censored, not dropped from timing reports; missing telemetry is unknown. Promote only with held-out benefit and no floor regression; otherwise retain the incumbent. A local winner can guide the current task while transfer remains unproven. Do not let the optimizing worker edit its grader, contract or installed skill during the trial.

## 7 Breaker (direction honesty)

Before trials, compare the proposed action with the current baseline at the
same condition. A rule that repeats the baseline has no incremental action;
retain the baseline instead of counting repeated advice as learning benefit.
Controlled telemetry tests qualification and consumption, never real utility.

`CLOSED → HALF_OPEN (progress=no) → OPEN → BLOCKED`. Progress=yes resets. Every HALF_OPEN landing owes a `strategy_delta`. Two gate-caught false claims → BLOCKED (see GATE / ratchet in `gate.md`).

## 8 Executable local policy experiments

Use the [paired protocol](../../examples/evolution-dedupe/README.md) when a
worker proposes a reusable Python policy with a frozen independent evaluator.
Run `goal_evolve.py protocol.json --state .goal/proposals/evolution`. Version 1
takes standalone programs. Version 2 also takes `--project` and a matched
incumbent/candidate checkpoint pair, so it can compare multiple owned files,
including additions and removals. Keep shared dependencies inside the recorded
scope and use a separate state directory per policy scope.

Every new comparison must declare `calibration.good` and `calibration.bad` fixture
lists (`output`/`expected` file paths). The actual grader must accept the good
outputs and reject the bad outputs before either policy is dispatched. These
frozen known answers use the existing trial/run deadline; an invalid grader
preserves the incumbent and does not consume held-out testing budget. Missing
fixtures fail before state creation. An expired run executes neither grader nor
policy; it is recorded as budget exhaustion rather than a broken instrument.

New selections bind the exact qualification report SHA-256. `run-enabled` and
production dispatch validate that report, frozen inputs/instruments, calibration
outputs, and paired eligibility before consuming the archive. Historical records
and transactions remain readable and recoverable; an old selection without this
binding requires a new calibrated comparison with fresh holdout in the same
state directory. Successful requalification refreshes the receipt even for
unchanged program bytes, so earlier plans must be regenerated. Testing/exposure
history is retained. A verified baseline remains the fallback after regression.

For routing policies, measure the complete downstream tool/worker workflow,
including preparation, coordination, checks, close and original acceptance.
Faster recommendation printing does not establish dispatch benefit. A qualified
`choice:crew` can change an unknown-cost serial recommendation only within the
existing graph's independent domains and capacity, when observed trial cost plus
policy overhead fits the remaining allowance. Explicit inline remains inline.
Outside the validated context, return baseline. See the [repository-regression
experiment](../../examples/learning-regression/README.md) for actual local jobs;
it is not an agent-model or native `/goal` comparison.

The runner gives both variants the same input in fresh workspaces and measures
setup, worker, and grading under a single trial allowance. Promotion requires
complete paired development and fresh holdout evidence above the preset floor
and horizon. An underpowered holdout is skipped before dispatch. A verified
regression can withdraw the active candidate. An instrument failure or an
inconclusive timeout preserves the active selection. Route later tasks in this
scope through `goal_evolve.py run-enabled --state … --seconds …`. To restore
owned files in the live project, use the [checkpoint restore procedure](../../docs/transaction-state.md#accepted-artifact-checkpoints)
and run a fresh gate. Candidate generation and cross-task transfer still
require an agent and independent task evidence.

For an actual proposal, retain the raw failure/cost trigger and a scoped
hypothesis, then have the agent write candidate source without changing the
grader or success definition. Freeze the comparison and inspect the returned
enabled/retained/withdrawn decision; exercise run-enabled on a later task.
Monitor the exact archived active bytes. After a counterexample, preserve the
withdrawal and generate a repair against new development/holdout inputs in
the same statistical-budget state. The [recorded agent proposal](../../docs/evals/agent-evolution/README.md)
demonstrates this sequence with independently reconstructed raw outcomes;
its local execution gains do not measure total agent cost or generalization.

The experiment result includes bounded `feedback`: raw failure paths and
stderr, the current selection and the next sequential alpha/minimum fresh
pair count. Read it again with `goal_evolve.py feedback --state … --run …`.
An old report never silently stands in for the current enabled selection.
