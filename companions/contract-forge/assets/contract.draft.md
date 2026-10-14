# Goal contract - <objective, one line>

Status: DRAFT            <!-- flip only via goal-loop stamp; this file never writes approved: hash -->

## Objective

<the user's objective, in the user's own words>

## Exit policy

exit: threshold
<!-- threshold (default): deliver when every AC floor passes.
     forge: maximization / "as good as possible" - dry streak + empty critic.
     Grammar authority: goal-loop references/gate.md and assets/goal.contract.md. -->

## Objective (optional, for optimization)

<!-- objective: maximize AC-N  |  objective: minimize AC-N
     Optional tokens on the score AC: probe / metric: / tolerance: / sd: / var:
     / baseline: delta|abs / external: + window:.
     Objective needs >=1 judged AC with calib: good= bad= OR:
       horizon-waived: <why the blind spot is immaterial>
     Every close-iteration of an objective loop needs --strategy <label>. -->

## Acceptance criteria

<!-- Level 0 line shape (fixed; no '|' inside expected: spec):
- AC-N | <yes/no statement> | check: `<command>` | [probe: `<cmd>`] | [baseline: delta|abs] | [metric: `<regex one capture group>`] | [tolerance: <rel>] | [calib: good=<f> bad=<f>] | expected: <spec>
     spec: exit=0 (default) | exit=N | >=N | <=N | >N | <N | ==N | !=N | maximize | minimize | judged
     Examples:
- AC-1 | tool exits 0 on fixture | check: `bash verify/run.sh` | expected: exit=0
- AC-2 | score improves | check: `bash verify/score.sh` | probe: `bash verify/probe.sh` | metric: `score=([0-9.]+)` | baseline: delta | expected: maximize
- AC-3 | judged quality holds | check: `bash verify/extract.sh` | calib: good=fixtures/good.svg bad=fixtures/bad.svg | expected: judged
-->

- AC-1 | <statement> | check: `<command>` | expected: exit=0

## Out of scope

<explicit non-goals>

## Patterns (optional)

<!-- patterns: <path to project check-shape notes> - authoring only -->

## Budget knobs

<!-- key=value tokens bound at stamp; forge should set dry_limit= -->
max_iterations=12 no_progress_limit=2 max_replans=2 dry_limit=3 check_timeout=120

## Approval

Approval mode: auto
<!-- USER runs goal-loop stamp. This skill never writes the stamp hash. -->
approved: <first 8 hex of sha1 over the Acceptance-criteria section body> <YYYY-MM-DD>
