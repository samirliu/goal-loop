# Pack: gradient (GRADIENT)

**Open when:** contract has `objective:` · `exit: forge` · horizon / `horizon-waived:` · CLI uses `--strategy` · you are reading EFFICIENCY output.

**Invariant: GRADIENT** — optimization never delivers below the water mark; blind spots are declared; waves are labeled for attribution.
**Also touches FENCE** — `progress=no` must carry `strategy_delta=` (honest next direction).

Legacy aliases: `R10 R11 R13 R17b R19` → GRADIENT / FENCE.

---

## 1 Water mark (`objective:` + `best_score`)

- Contract line: `objective: maximize AC-N` or `objective: minimize AC-N` (primary score AC).
- `best_score` is the water mark: high-water for maximize, low-water for minimize.
- Claim refuses a score worse than the water mark in that direction (`score-regressed`). A number is not a recoverable artifact: before a risky candidate, retain a scoped patch/artifact of the incumbent and its digest under evidence; restore only owned files if it loses.
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

## 6 EFFICIENCY / STRATEGY-PICK / eval-gap / promote

Printed by `ctl status` when optimizing or stalled. **Advisory to the gate** — never changes gate rc or hint. **STRATEGY-PICK is what the next wave uses** (brief + replan/delta NEXT text).

- **EFFICIENCY** — one kernel (`scripts/goal_strategy.awk`) computes both display and pick. Score at t is AFTER wave t: `delta(t) = score(t) - score(t-1)` belongs to label(t), including its entry wave. First recorded score is an anchor, not credited gain. Missing/non-numeric scores or ledger gaps break the chain; only the latest contiguous measured suffix counts.
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

`CLOSED → HALF_OPEN (progress=no) → OPEN → BLOCKED`. Progress=yes resets. Every HALF_OPEN landing owes a `strategy_delta`. Two gate-caught false claims → BLOCKED (see GATE / ratchet in `gate.md`).
