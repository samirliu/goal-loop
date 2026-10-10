# case-svg-dash

## Objective

Build an SVG analytics dashboard from a provided CSV dataset (sales by
month/region): bars + trend + KPI row. Numbers must be right; the picture
must read as a real dashboard.

## Contract sketch

- exit: threshold
- AC-1 | every plotted value equals the CSV aggregate | check: `bash verify/data_check.sh` | expected: exit=0
- AC-2 | SVG well-formed and contains required chart elements | check: `bash verify/svg_check.sh` | expected: exit=0
- AC-3 | generation is deterministic (byte-identical across two runs) | check: `bash verify/determinism.sh` | expected: exit=0
- AC-4 | judged: dashboard reads as a real BI chart (axes, labels, non-default palette, no overlapping text)
- AC-5 | judged: KPI row values are legible and correctly attributed

## Surfaces stressed

- judged AC with calibration anchors (known-good / known-bad SVG)
- cold-seat final verification protocol
- mixed judged + deterministic floors (what happens when they disagree?)
- default crew vs teams backend (pick whichever is free)

## Findings log

- (pending run)
