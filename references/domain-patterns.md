# Domain patterns - failable check SHAPES per claim family (R4 basis)

Contents: [1 how to read] [2 executable-correctness] [3 behavioral]
[4 quantitative] [5 perceptual/quality] [6 data] [7 documents]
[8 long-running] [9 metric robustness] [10 project patterns slot].
This file is deliberately DOMAIN-FREE: it names claim families and the
shape a failable check must have - never tools or industries. Concrete
recipes belong to each project (section 10).

## 1 How to read

At contract time, classify each AC's claim into a family, take the shape,
and write it into the NAMED CHECK field verbatim-ready. If a family
applies and a check follows its shape, a claimed UNVERIFIABLE for it is
not admissible - the gate coerces it to FAIL (R4); "hard" or "slow" is no
reason, only genuine inapplicability is.

## 2 Executable-correctness family

Claims that a thing runs, refuses bad input, or produces exact output.

| shape | settles |
|---|---|
| parse/lint command, expect exit=0 | structurally valid at all |
| run once with a good input, expect exit=0 | works on the happy path |
| run once with a KNOWN-BAD input, expect refusal + non-zero exit | refuses when it must |
| byte-exact diff against a stored expected file | prints exactly |
| bounded size (`wc -l` style) vs stated bound | size discipline |
| the one named test command, full output | regressions |

## 3 Behavioral family

Claims about interactions over time (flows, sessions, state machines).
Shape: a scripted, replayable interaction with OBSERVABLE assertions at
fixed steps; the transcript and any captured artifacts land in
`.goal/evidence/`; the named check re-runs the script and asserts the end
state. A flow that was only ever exercised manually is not checked.

## 4 Quantitative family

Claims of the form "metric M is at least / at most V" (speed, cost, size,
accuracy, throughput). Shape (NON-NEGOTIABLE parts in caps):

- ONE command that runs the measurement N times (N fixed in the AC),
  aggregates INTERNALLY (mean or percentile - name which), and prints the
  single resulting number as its LAST stdout line. The gate compares that
  line against `expected: <op><V>`.
- NOISE FLOOR FIRST: before choosing V, run the measurement command twice
  on the un-optimized artifact and set V comfortably beyond observed
  run-to-run variance - a threshold inside the noise manufactures PASS and
  FAIL alike.
- Report the aggregation, not a single lucky run: one-off spikes game a
  boolean check, single runs game a metric.
- Variance itself can be an AC: same-input-twice byte-identical, or
  spread <= bound.

## 5 Perceptual / quality family

Claims a program cannot settle directly ("realistic", "clean", "usable").
Shape: convert to judgment (checker-panel.md section 5) - rubric with
WRITTEN anchors per dimension and a threshold; or pairwise A/B at a FIXED
observation point (same camera / input / viewport) against the previous
iteration or a named reference artifact; captured observations (renders,
screenshots, transcripts) go to `.goal/evidence/`. Mark the AC
`expected: judged`. A judged AC with no written anchor cannot claim
UNVERIFIABLE later - the anchor was the contract's job.

## 6 Data family

Claims about datasets (rows, totals, quality, determinism).

| shape | settles |
|---|---|
| shape first: head + row/col count vs claim | as claimed |
| recompute one subtotal independently of the artifact | arithmetic |
| null/duplicate recount | quality |
| grand total recompute == stated | totals |
| same input, run twice, byte-identical output | determinism |
| invariant assertions (referential integrity, ranges) | structural truth |

## 7 Documents family

Claims about generated documents/reports. Shape: read back the RENDERED
file, not the generator; required sections present by name; every
figure/table cross-referenced by its number; word/length bounds via the
named counting command; a claim in the summary that the body does not
carry is an escalated hedge - FAIL.

## 8 Long-running work family

The work log IS the check: testable done criteria written up front; each
continuation re-reads the log before acting. Progress must be observable:
a continuation that moves no file and closes no check is stagnation by
definition.

## 9 Metric robustness (contract authoring)

- Prefer byte-exact diffs, counts, existence checks, and rerun-rc checks
  over textual metrics - they survive extractor differences.
- NEVER word-count natural language with `wc -w`-style metrics:
  tokenization varies by extractor (one real document measured 798, 804,
  848, 886 and 892 under five extractors, straddling an 800 threshold). If
  a textual metric is unavoidable, NAME the exact extraction command in
  the AC - that command's number IS the metric - and place the bound
  comfortably inside extractor noise, not at its edge.
- Smoke-run the named check before stamping: a subcommand that does not
  exist is a contract defect, not a panel problem.

## 10 Project patterns slot (authoring-time, advisory)

A project may keep its own recipes file (tools, thresholds, exact
commands) and reference it from the contract (`patterns: <path>`). Rules:

- it is AUTHORING-TIME input only: the checks it yields are written INTO
  the stamped AC lines; the gate never reads the patterns file at runtime;
- it lives in the project tree (digest-covered), not under `.goal/`;
- every command it contributes still passes the smoke rule - a recipe
  that cannot run is rewritten or dropped at contract time.

This keeps the skill generic and the specifics where they belong: in the
project that knows them.
