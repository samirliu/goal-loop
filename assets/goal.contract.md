# Goal contract - <objective, one line>

Status: DRAFT            <!-- flip to APPROVED only by the stamp below -->

## Objective

<the user's objective, in the user's own words>

## Acceptance criteria

<!-- verbatim, frozen by the stamp; each ends in its named check;
     pick check patterns from references/domain-patterns.md -->

- AC-1 | <yes/no decision statement> | check: `<exact command or comparison>` | expected: <observable>
- AC-2 | <...> | check: `<...>` | expected: <...>

## Out of scope

- <what will NOT be delivered - agreed, so late additions go to proposals>

## Budget knobs (override before approval if needed)

max_iterations=12  no_progress_limit=2  max_replans=2
per_check_fail_cap=3  panel_max=4  wallclock=1800

## Approval

approved: <first 8 hex of sha1 over the Acceptance-criteria section body> <YYYY-MM-DD>

<!-- Write the stamp ONLY after the user explicitly approves. The gate
     recomputes it; a mismatch is contract-tampered (R3). After stamping:
     propose amendments, never apply them in place. -->
