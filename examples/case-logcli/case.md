# case-logcli

## Objective

A small multi-module log-analysis CLI over a provided JSONL access-log
fixture: parse, aggregate, filter-query, and golden-test the output.
Modules must be split with a frozen interface (parser / aggregator /
query / CLI).

## Contract sketch

- exit: threshold
- AC-1 | `cli stats` matches golden stats | check: `bash verify/stats_golden.sh` | expected: exit=0
- AC-2 | `cli query --where ...` matches golden rows | check: `bash verify/query_golden.sh` | expected: exit=0
- AC-3 | parser rejects malformed lines with nonzero rc and stderr | check: `bash verify/bad_input.sh` | expected: exit=0
- AC-4 | `cli stats` on the big fixture prints latency p50/p95 within tolerance | check: `bash verify/latency.sh` | probe: `bash verify/latency_probe.sh` | expected: <=2.0
- AC-5 | judged: modules respect the frozen interface (no reach-through)

## Surfaces stressed

- multi-worker domain split + interfaces.md freeze
- NO-GO → next batch behavior (what does the controller actually do?)
- threshold (non-maximize) metric AC with probe
- --teams backend under a non-visual domain
- R12 audit on a long multi-wave run

## Findings log

- 2026-10-10 F3 (found when claiming without the judged seat): after
  `GATE: NO-GO reason=not-covered:AC-5`, `ctl status` still printed
  `NEXT T1 | w-mod | split src/cli.js...` - the FIRST unchecked work-plan
  line, which was already finished. Next-batch selection was a stub: no
  mapping from gate reason to action, no tick discipline, status hid the
  rest of the queue. Fixed in v2.4.5: gate NO-GO line carries `hint=`
  (bind-seat / fix-AC / fix-instrument / ...); status lists ALL open items;
  SKILL.md Step 4 has a mechanical routing table; Step 3 requires ticking
  work-plan rows on join. Tests 74-75.

- 2026-10-10 (instrument, not skill): golden compare must CR-scrub
  (`tr -d '\r'`) and number-format must match the CLI's stringification
  (JS `14` vs Python `14.0`) - regenerate goldens via the CLI itself.

- 2026-10-10 F4 (found when wallclock=1200 expired while we were fixing F1-F3):
  `GATE: BLOCKED reason=time-budget-exhausted` fired BEFORE AC checks, so a
  fully green, ready-to-deliver claim was vetoed. The message even said
  "graceful: deliver best-so-far" while rc=3 confiscated the work. Fuse should
  stop grinding, not confiscate passing delivery. Fixed in v2.4.6: deadline
  overrun flags only; green claim GO + NOTE; any fail() after the fuse
  escalates to BLOCKED. Tests 76-77.
