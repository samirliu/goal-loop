# Goal contract - maximize without horizon

Status: DRAFT

## Objective

Maximize score only.

## Exit policy

exit: forge

## Objective (optional, for optimization)

objective: maximize AC-1

## Acceptance criteria

- AC-1 | score | check: `bash verify/score.sh` | probe: `bash verify/probe.sh` | metric: `score=([0-9.]+)` | baseline: delta | expected: maximize

## Budget knobs

max_iterations=10 dry_limit=3

## Approval

Approval mode: auto
approved: <first 8 hex of sha1 over the Acceptance-criteria section body> <YYYY-MM-DD>
