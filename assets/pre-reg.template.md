# pre-reg.md — generated at stamp (goal-agnostic defaults)

T0 = <ISO stamp time>
budget: max_iterations=<> wallclock=<seconds or off>

## Hypotheses (fill or delete; do not wait for a perfect story)

1. After >=2 `close-iteration` rows, `ctl status` shows `STRATEGY-PICK` (prefer=…); if a label goes flat it appears under `avoid=`.
2. A claim only passes with the two-pass + sensor teeth: `adversarial.rec` clear@ (iter,digest), non-empty `evidence/raw/<iter>.txt`, check/probe scripts unfrozen.

## Strategy labels (objective contracts)

Derive 2–4 short ASCII attack labels from THIS objective (not from the agent's mood).
One primary label per wave via `close-iteration --strategy`.
Changing label without `--strategy-delta` when `progress=no` is a fail line.

- label_a: <what it attacks>
- label_b: <what it attacks>

## Kill lines (any hit → stop and report; do not raise budget to "try again")

- `iteration=0` after real work product exists, or after >=50% wallclock — loop never turned; stop dispatching.
- Repeat an `avoid=` label without `strategy_delta`.
- Claim without adversarial clear / raw dump / untouched check scripts.
- Self-declared complete, or gate rc disagrees with the claim.
- Change metric/check definitions mid-run to raise a score (Goodhart).

## Success digits (report these; do not invent a rubric)

1. loop-log rows with `strategy=` + STRATEGY-PICK lines
2. score trajectory per label (optimize = better score / same work, not more words or more files)
3. gate line + the three teeth paths

## Degrade line

If wallclock or max_iterations is spent: deliver **what already passes** + a short continuation note (interfaces/open items). Never pad volume to look done.
