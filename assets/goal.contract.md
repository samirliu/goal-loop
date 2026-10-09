# Goal contract - <objective, one line>

Status: DRAFT            <!-- flip to APPROVED only by the stamp below -->

## Objective

<the user's objective, in the user's own words>

## Exit policy

exit: threshold
<!-- NOTE: every `exit:` line is covered by the approval stamp - changing
     the policy after stamping is contract-tampered.
     threshold (default): deliver when every AC floor passes.
     forge: maximization objectives ("as good as possible") - deliver on
     verification exhaustion: dry_limit consecutive dry rounds (no new
     evidence-backed finding, fix-now discoveries closed) + an empty
     completeness-critic answer; max_iterations becomes a pure fuse.
     Smoke-run every named check before stamping (SKILL.md Step 1). -->

## Objective (optional, for optimization)

<!-- objective: maximize AC-N
     Declares the PRIMARY score AC. Every iteration records its observed
     value (ctl --score); best_score is the high-water mark. The gate
     refuses a claim below best_score (R11). Floors stay as ordinary ACs.
     Use with exit: forge. Example:
       objective: maximize AC-2 -->

## Acceptance criteria

<!-- verbatim, frozen by the stamp. Grammar per line:
     - AC-N | <yes/no statement> | check: `<command>` | [probe: `<cmd>`] | [baseline: delta|abs] | expected: <spec>
     spec: exit=0 (default) | metric comparison (>=60, <=1.8, ...) | maximize | judged
     - a metric command aggregates internally (N repeats / percentile) and
       prints ONE number on its last stdout line; set thresholds beyond the
       measured noise floor (patterns.md section 4)
     - probe (R9): MUST pass before the number is trusted - asserts the
       instrument (fixture loaded, seed fixed, tool alive), not the artifact.
       Every metric/maximize AC should carry one.
     - baseline: delta (default for metric ACs) requires a .goal/baseline.md
       row `AC-N | observed=<v> | repeats=<N>=2 | cmd=<check verbatim>` -
       the pre-stamp smoke run IS the measurement; abs = new capability,
       no baseline owed. Controller infers delta/abs, never asks the user.
     - `maximize`: objective score (see above), numeric last line, not a floor
     - `judged` needs a written rubric anchor or a pairwise A/B protocol
       (crew.md section 6)
     - the command runs at project root and must not modify the tree;
       generated evidence goes to .goal/evidence/
     - the spec value must not contain "|"
     pick check shapes from references/patterns.md -->

- AC-1 | <yes/no decision statement> | check: `<exact command>` | expected: exit=0
- AC-2 | <...metric...> | check: `<command printing one number>` | probe: `<instrument check>` | baseline: delta | expected: >=<value>
- AC-3 | <...quality claim...> | check: - | expected: judged

## Out of scope

- <what will NOT be delivered - agreed, so late additions go to proposals>

## Patterns (optional)

patterns: <relative path to this project's check-recipes file>
<!-- authoring-time input only; its commands are written INTO the AC lines
     above and smoke-run like any other; the gate never reads it -->

## Budget knobs (override before approval if needed)

max_iterations=12  no_progress_limit=2  max_replans=2
per_check_fail_cap=3  panel_max=4  dry_limit=3  check_timeout=120
wallclock=1800
<!-- in-session wall-clock fuse: invoke with --time-budget=N (seconds);
     the deadline is seeded into state.rec at stamping, enforced by the
     gate as rc=3 time-budget-exhausted (graceful best-so-far end) -->

## Approval

Approval mode: gate | auto   <!-- gate (default): stamp only on explicit user
sign-off. auto: show the contract, stamp immediately with the marker "auto",
log approval=auto in loop-log and delivery; irreversible-side-effect
objectives are refused in both modes. Smoke-run every named check first. -->

approved: <first 8 hex of sha1 over the Acceptance-criteria section body> <YYYY-MM-DD>

<!-- Write the stamp ONLY after the user explicitly approves. The gate
     recomputes it; a mismatch is contract-tampered (R3). After stamping:
     propose amendments, never apply them in place. -->
