# examples/ — validation cases (not part of the skill)

Each subdirectory is a **stress case used to validate this skill**. The
goal of running a case is to find and fix skill defects, not to ship the
case deliverable. Cases may be abandoned mid-way once they have exposed
enough friction.

Rules for this folder:

- Case-specific knowledge stays here. Generic skill files
  (SKILL.md, references/, scripts/, tests/, assets/) must not mention
  any case name, domain recipe, or case-specific path.
- `case.md` in each case dir: objective, contract sketch, which protocol
  surfaces it is meant to stress, and a findings log (defect → fix commit).
- Runnable project trees live OUTSIDE the skill repo (e.g.
  `~/goal-loop-case-<name>/`); this folder only records the case.

| case | domain | exit | stresses |
|---|---|---|---|
| case-tsp-minimize | algorithmic optimization | forge + minimize | minimize objective, R11 direction, R9 probe, forge exhaust |
| case-logcli | multi-module CLI | threshold | NO-GO next-batch, interface freeze, multi-worker domains, R12 |
| case-svg-dash | 2D data viz | threshold + judged | calibration anchors, cold-seat, judged×deterministic mix |
| case-probe-campaign | hostile contracts ×10 | mixed | rule seams: duplicate ids, verify filters, state garbage, ledger self-mutation |
| case-probe-campaign2 | state-machine loops ×10 | mixed | sequences: breaker arcs, ratchet arcs, fuse escalation, check-order walk, audit lifecycle |
| case-independent-repro | domain-neutral CSV tool | threshold | external-validation scaffold: multi-AC, false-complete denial then GO, zero author domain |
