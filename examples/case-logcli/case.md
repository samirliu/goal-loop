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

- (pending run)
