# Goal contract - improve score

Status: DRAFT

## Objective

Maximize measured score without breaking floors.

## Exit policy

exit: forge

## Objective (optional, for optimization)

objective: maximize AC-1

## Acceptance criteria

- AC-1 | score improves | check: `bash verify/score.sh` | probe: `bash verify/probe.sh` | metric: `score=([0-9.]+)` | baseline: delta | expected: maximize
- AC-2 | tests stay green | check: `bash verify/tests.sh` | expected: exit=0
- AC-3 | judged quality holds | check: `bash verify/extract.sh` | calib: good=fixtures/good.svg bad=fixtures/bad.svg | expected: judged

## Out of scope

Rewriting the renderer.

## Budget knobs

max_iterations=20 dry_limit=3 check_timeout=60

## Approval

Approval mode: auto
approved: <first 8 hex of sha1 over the Acceptance-criteria section body> <YYYY-MM-DD>
