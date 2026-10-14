# case-independent-repro

## Objective

Deliver `csv_summarizer.sh` for a fixed CSV fixture (row count + score sum),
rejecting malformed input with exit 2. **Zero author-domain knowledge** —
no TSP, no multi-module CLI, no SVG/dashboard. Shape a stranger would invent.

## Why this case exists

Prior cases (tsp / logcli / svg-dash / probe campaigns) were authored by the
skill owner around defects already suspected. That inflates confidence.
This case is the **external-validation scaffold**: same mechanical loop,
unfamiliar domain, one command to re-run.

> Status: **agent-constructed scaffold**, not yet third-party human attested.
> A true external reproduction needs a non-author clone + run + findings note.

## Contract sketch

- exit: threshold
- AC-1 | summarizer accepts the good fixture and exits 0 | check: `bash verify/run_ok.sh` | expected: exit=0
- AC-2 | summary numbers match golden exactly | check: `bash verify/match_golden.sh` | expected: exit=0
- AC-3 | malformed csv is rejected with exit 2 | check: `bash verify/rejects_bad.sh` | expected: exit=0

Runnable tree: `~/goal-loop-case-independent-repro/` (fixtures + checks +
deliverable + `.goal/goal.md`). Runner: `run.sh` drives **NO-GO then GO** —
a broken deliverable must be refused, the fixed one must deliver.

## Surfaces stressed

- Multi-AC threshold path (not the one-AC quickstart)
- Checks that can genuinely FAIL (golden mismatch / accept bad input)
- False-complete ratchet on a lying claim (`--false-complete yes` + gate)
- Domain-neutral packaging (install README smoke can cite this path)

## Findings log

- 2026-10-14 scaffold created. Phase A initially never reached the gate —
  `progress=no` without `--strategy-delta` is refused at ctl (R10). Correct
  behavior, not a defect; runner now passes strategy_delta so the broken
  product actually attempts a false claim and the gate denies it.
- 2026-10-14 live run: **Phase A `GATE: NO-GO reason=open-FAIL:AC-2` +
  `false-complete-counted=1`**; Phase B `GATE: GO ac=3 pass=3`. Denial and
  delivery both real. `run.sh` is the third-party entry point.
  Known residual gap: **no non-author runner yet** — someone outside
  samirliu should execute `run.sh` and append a one-line result here.
