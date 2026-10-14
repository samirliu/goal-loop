# Goal contract - ship a correct tool

Status: DRAFT

## Objective

Ship tool.sh that parses fixtures and exits 0.

## Exit policy

exit: threshold

## Acceptance criteria

- AC-1 | tool exits 0 on good fixture | check: `bash verify/run.sh fixtures/good.csv` | expected: exit=0
- AC-2 | tool refuses known-bad input | check: `bash verify/run.sh fixtures/bad.csv` | expected: exit=2

## Out of scope

UI polish.

## Budget knobs

max_iterations=8 check_timeout=30

## Approval

Approval mode: auto
approved: <first 8 hex of sha1 over the Acceptance-criteria section body> <YYYY-MM-DD>
