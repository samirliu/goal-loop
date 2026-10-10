# case-tsp-minimize

## Objective

Fixed 48-city Euclidean TSP instance. Find a tour and keep improving it
(shorter is better). Deliver a solver + tour file + verifier.

## Contract sketch

- exit: forge
- objective: minimize AC-1
- AC-1 | tour length as short as possible | check: `bash verify/tour_score.sh` | probe: `bash verify/tour_probe.sh` | expected: minimize
- AC-2 | tour is a valid Hamiltonian cycle on the fixed instance | check: `bash verify/tour_valid.sh` | expected: exit=0
- AC-3 | solver reproduces the delivered tour from seed | check: `bash verify/repro.sh` | expected: exit=0
- AC-4 | judged: solver code is a real heuristic, not hardcoded tour

## Surfaces stressed

- `objective: minimize` / `expected: minimize` (do they exist?)
- best_score as low-water mark; score-regressed direction
- R9 probe on an algorithmic instrument (not a browser)
- forge dry_limit exhaust on a minimization objective

## Findings log

- 2026-10-10 F1 (found while writing the minimize contract, before any worker ran):
  `expected: minimize` was silently classified as `judged` (classify_expected
  fallthrough). The gate never measured the tour length; `objective: minimize`
  was unrecognized; best_score/R13 assumed higher-is-better. Worse than a
  missing feature - silent misrouting. Fixed in v2.4.3: minimize class,
  objective_dir, directional best_score + score-regressed + R13, docs, tests
  69-72. (Also: ctl re-measures --score via gate --verify - a self-reported
  score is only a hint. Test 71 initially failed for the right reason.)

- 2026-10-10 F2 (found when the contract's max_iterations=10 never took effect):
  Budget knobs in goal.md were DECORATIVE - goal_ctl.sh init wrote defaults
  (max_iterations=12, check_timeout=120) and never read the contract. Silent
  contract lie. Fixed in v2.4.3: stamp parses key=value tokens from goal.md
  into state.rec; wallclock= seeds time_budget unless --time-budget wins.
  Test 73.
