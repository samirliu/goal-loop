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

<!-- objective: maximize AC-N  |  objective: minimize AC-N
     Declares the PRIMARY score AC. Every iteration records its observed
     value (ctl --score); best_score is the water mark (high-water for
     maximize, low-water for minimize). The gate refuses a claim that is
     worse than best_score in the objective's direction (R11). Floors stay
     as ordinary ACs. Use with exit: forge. Examples:
       objective: maximize AC-2
       objective: minimize AC-1
     The objective is a GRADIENT: what the number cannot see gets optimized
     away. Gate it with the horizon layer - >=1 judged AC carrying calib:
     fixtures (R15) on the qualities the metric can chase - or declare the
     blind spot acceptable with a line (frozen by the stamp, R19):
       horizon-waived: <why this objective's blind spot is immaterial>
     Objective contracts refuse the stamp with neither. Every wave of an
     objective loop must carry --strategy <attack direction> at close-
     iteration (R17 attribution: slope is attributed per label).
     Optional measurement tokens on the score AC:
     - `sd:` / `var:` regexes naming the measurement's spread from its own
       output ("stddev: 1.4") - the R11 noise band then comes from data
       (z=2) instead of guessed tolerance.
     - `external:` / `window:` (R18): settle the AC against an out-of-tree
       source; window caches the verdict for <window> seconds. rc=75 from
       the command = "not ready", AC settles DEFERRED. window: without
       external: refuses the stamp. -->

## Acceptance criteria

<!-- verbatim, frozen by the stamp. Grammar per line:
     - AC-N | <yes/no statement> | check: `<command>` | [probe: `<cmd>`] | [baseline: delta|abs] | expected: <spec>
     spec: exit=0 (default) | exit=N (expect this exact failure code) |
           metric comparison (>=60, <=1.8, ...) | maximize | minimize | judged
     - a metric command aggregates internally (N repeats / percentile) and
       prints ONE number; set thresholds beyond the measured noise floor
       (patterns.md section 4)
     - probe (R9): MUST pass before the number is trusted - asserts the
       instrument (fixture loaded, seed fixed, tool alive), not the artifact.
       Every metric/maximize/minimize AC should carry one.
     - `metric:` (optional): one capture group; the gate takes the number from
       it (ANSI-stripped first) instead of guessing the last line - use it
       when output carries other numbers. `tolerance:` (optional): relative
       noise band for the water-mark comparison of an objective score.
     - baseline: delta (default for metric ACs) requires a .goal/baseline.md
       row `AC-N | observed=<v> | repeats=<N>=2 | cmd=<check verbatim>` -
       the pre-stamp smoke run IS the measurement; abs = new capability,
       no baseline owed. Controller infers delta/abs, never asks the user.
     - `maximize`/`minimize`: objective score (see above), numeric, not a floor
     - `judged` needs a written rubric anchor or a pairwise A/B protocol
       (crew.md section 6); its check must be a REAL command that produces
       the evidence the seats read (rendering/screenshots/extraction) -
       an empty or placeholder check voids the whole contract (fail-closed).
       A judged PASS must cite `artifact: <path>` + `digest: <sha256>` in its
       evidence; the gate recomputes the hash, so an unbound or stale
       verdict fails `verdict-unbound` (the seat must say what it judged).
     - `calib: good=<file> bad=<file>` (optional, judged only; R15) names the
       two calibration fixtures - one known-good, one known-bad artifact of
       this AC's subject. The gate refuses the claim until the seat's grades
       `AC-N#good = PASS` and `AC-N#bad = FAIL` are bound at the current
       iteration (see gate.md section 1). A seat that cannot reject the known-
       bad case is not trustworthy on the real subject. Stamp checks: judged
       expected, both fixtures named, both files present.
     - the command runs at project root and must not modify the tree;
       generated evidence goes to .goal/evidence/
     - the spec value must not contain "|"
     pick check shapes from references/patterns.md -->

- AC-1 | <yes/no decision statement> | check: `<exact command>` | expected: exit=0
- AC-2 | <...metric...> | check: `<command printing one number>` | probe: `<instrument check>` | baseline: delta | expected: >=<value>
- AC-3 | <...quality claim...> | check: `<command producing the reviewed artifact>` | expected: judged

## Out of scope

- <what will NOT be delivered - agreed, so late additions go to proposals>

## Patterns (optional)

patterns: <relative path to this project's check-recipes file>
<!-- authoring-time input only; its commands are written INTO the AC lines
     above and smoke-run like any other; the gate never reads it -->

## Budget knobs (override before approval if needed; BIND AT STAMP)

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
