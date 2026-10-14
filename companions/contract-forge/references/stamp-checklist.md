# Stamp-risk checklist

Map every `goal_ctl.sh stamp` refusal (goal-loop) to interview answers.
Authority: goal-loop `scripts/goal_ctl.sh` stamp path. contract-forge predicts;
the user still runs stamp.

| # | Refusal (stamp) | Interview answer that prevents it | Lint id |
|---|---|---|---|
| 1 | `no-goal-md` | Emit `.goal/goal.md` after `init` | — |
| 2 | `already-stamped` (R3) | Keep DRAFT; never write hex into `approved:` | `approved-placeholder` / warn `already-stamped` |
| 3 | forge + missing baseline for delta metric AC | R3 noise measure + write `.goal/baseline.md` rows before stamp | `forge-baseline` |
| 4 | `objective:` target AC not maximize/minimize | R2: objective line must match that AC `expected:` | `objective-target` |
| 5 | `calib:` on non-judged AC | R1/R4: calib only on `expected: judged` | `calib-judged-only` |
| 6 | `calib:` missing good= or bad= | R4: always both | `calib-both` |
| 7 | calib fixture file missing | R4: create/locate fixtures in tree first | `calib-files` |
| 8 | good == bad fixture | R4: distinct known-good / known-bad | `calib-both` |
| 9 | `window:` without `external:` | Pair both or neither | `window-external` |
| 10 | objective without horizon layer | R4: judged+calib **or** `horizon-waived: <reason>` | `horizon` |
| 11 | no `approved:` placeholder line | Keep the placeholder line in the draft | `approved-placeholder` |

## Handoff notes (not stamp fields)

- Objective loop: every `close-iteration` needs `--strategy <label>` (writer tooth).
- Smoke every named check before stamp; smoke of a metric AC **is** the baseline measurement (repeats >= 2).
- Post-stamp: never edit AC body / `exit:` / `objective:` / `horizon-waived:` (contract-tampered). Amendments only under `.goal/proposals/` for the user to approve.

## Goodhart / noise (pre-stamp quality, not mechanical refusals)

| Risk | Guard |
|---|---|
| Proxy metric (satisfied without advancing goal) | Goodhart sentinel: rewrite or delete |
| Threshold inside noise | Measure twice on unoptimized artifact; set V beyond variance |
| Blind-spot optimization | horizon judged+calib or explicit waiver |
| Lucky single run | Aggregate N repeats inside one command (mean/percentile) |
