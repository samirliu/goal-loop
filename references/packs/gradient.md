# Pack: gradient (GRADIENT)

**Open when:** contract has `objective:` · `exit: forge` · horizon / `horizon-waived:` · CLI uses `--strategy` · you are reading EFFICIENCY output.

**Invariant: GRADIENT** — optimization never delivers below the water mark; blind spots are declared; waves are labeled for attribution.
**Also touches FENCE** — `progress=no` must carry `strategy_delta=` (honest next direction).

Legacy aliases: `R10 R11 R13 R17b R19` → GRADIENT / FENCE.

---

## 1 Water mark (`objective:` + `best_score`)

- Contract line: `objective: maximize AC-N` or `objective: minimize AC-N` (primary score AC).
- `best_score` is the water mark: high-water for maximize, low-water for minimize.
- Claim refuses a score worse than the water mark in that direction (`score-regressed`).
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
- `scores.rec` 4th column is the strategy label; per-strategy slope lives in `ctl status` EFFICIENCY.
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

## 6 EFFICIENCY / eval-gap / promote (advisory only)

Printed by `ctl status` when optimizing or stalled. **Never** changes gate rc, hint, or NEXT routing.

- **EFFICIENCY** — window = same-`strategy=` runs; slope vs band; `-> exploit` / `-> prune` / `unmeasured`.
- **eval-gap** — objective scores flat while stalled: dispatch goal-critic to draft candidate ACs into `.goal/proposals/` (user-approved; do not self-edit the contract).
- **promote** — same bare task id ≥3 waves + stalled: consider role-card promotion (suggestion only).
- **attribution-unused** — objective contract that never recorded a strategy.

## 7 Breaker (direction honesty)

`CLOSED → HALF_OPEN (progress=no) → OPEN → BLOCKED`. Progress=yes resets. Every HALF_OPEN landing owes a `strategy_delta`. Two gate-caught false claims → BLOCKED (see GATE / ratchet in `gate.md`).
