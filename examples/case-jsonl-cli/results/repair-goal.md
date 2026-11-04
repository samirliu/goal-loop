# Goal contract - JSONL logtool repair
Status: DRAFT

## Objective
Implement the standard-library JSONL CLI described in TASK.md, including atomic validation, stats, filtering, and documented module interfaces.

## Exit policy
exit: threshold

## Acceptance criteria
- AC-1 | Public task requirements pass black-box CLI tests for validation, atomic output, filtering, quantiles, empty data and files | check: `python3 -m unittest discover -s tests -v` | expected: exit=0

## Out of scope
- Dependencies, TASK.md and verify/ changes; evaluator inspection.

## Budget knobs
max_iterations=4 no_progress_limit=2 max_replans=2
per_check_fail_cap=3 panel_max=1 dry_limit=3 check_timeout=30
wallclock=240

## Approval
Approval mode: auto
approved: 21f9f30a 2026-11-04 auto
