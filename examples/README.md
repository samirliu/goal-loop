# examples/ — runnable demonstrations and historical validation cases

The default installer includes the runnable demonstrations below for offline smoke checks.
These are protocol demonstrations and fixtures, not acceptance evidence for a
user's actual deliverable. Historical domain recipes remain in their case dirs.

| Runnable example | What it exercises |
| --- | --- |
| [quickstart-one-shot/run.sh](quickstart-one-shot/run.sh) | Real controller close and Gate GO without a model |
| [learning-edge](learning-edge/README.md) | Local repair/reuse and controlled policy transition/consumption |
| [evolution-dedupe](evolution-dedupe/README.md) | Paired local tool-policy experiments |
| [recursive-improvement](recursive-improvement/README.md) | Qualified generations, actual use, counterexample withdrawal and repair under one goal budget |
| [learning-regression](learning-regression/README.md) | Real test workflow with qualified routing and withdrawal |
| [crew-cost](crew-cost/README.md) | Frozen workload and measured serial/crew comparisons |

## Historical cases

Each subdirectory is a **stress case used to validate this skill**. The
goal of running a case is to find and fix skill defects, not to ship the
case deliverable. Cases may be abandoned mid-way once they have exposed
enough friction.

Historical `case-*` directories and the developer `agent-evals` harness ship
only with the optional history payload. See [history distribution](../docs/history.md).

Rules for this folder:

- Case-specific knowledge stays here. Generic skill files
  (SKILL.md, references/, scripts/, tests/, assets/) must not mention
  any case name, domain recipe, or case-specific path. The packaging inventory
  may name example paths as data; it does not teach a domain recipe.
- `case.md` in each case dir: objective, contract sketch, which protocol
  surfaces it is meant to stress, and a findings log (defect → fix commit).
- Runnable project trees live OUTSIDE the skill repo (e.g.
  `~/goal-loop-case-<name>/`); this folder records the case and may include fixture generators, graders and replay patches.

| case | domain | exit | stresses |
|---|---|---|---|
| case-tsp-minimize | algorithmic optimization | forge + minimize | minimize objective, R11 direction, R9 probe, forge exhaust |
| case-logcli | multi-module CLI | threshold | NO-GO next-batch, interface freeze, multi-worker domains, R12 |
| case-svg-dash | 2D data viz | threshold + judged | calibration anchors, cold-seat, judged×deterministic mix |
| case-probe-campaign | hostile contracts ×10 | mixed | rule seams: duplicate ids, verify filters, state garbage, ledger self-mutation |
| case-probe-campaign2 | state-machine loops ×10 | mixed | sequences: breaker arcs, ratchet arcs, fuse escalation, check-order walk, audit lifecycle |
| case-independent-repro | domain-neutral CSV tool | threshold | external-validation scaffold: multi-AC, false-complete denial then GO, zero author domain |
| case-jsonl-cli | JSONL CLI | threshold | timed paired trial, crew startup overhead, independent outcome grading, runtime cwd/lock regressions |
