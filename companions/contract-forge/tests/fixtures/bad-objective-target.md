# Goal contract - objective points at exit AC

Status: DRAFT

## Exit policy

exit: forge

## Objective (optional, for optimization)

objective: maximize AC-1

## Acceptance criteria

- AC-1 | runs | check: `bash verify/run.sh` | probe: `bash verify/probe.sh` | metric: `score=([0-9.]+)` | baseline: delta | expected: exit=0
- AC-2 | judged quality | check: `bash verify/extract.sh` | calib: good=fixtures/good.svg bad=fixtures/bad.svg | expected: judged

## Budget knobs

max_iterations=10 dry_limit=3

## Approval

Approval mode: auto
approved: <placeholder>
