# Crew - parallel dispatch, join, final review

## 1 When crew applies

Decompose the objective; crew applies when the split yields ≥2 task domains
with DISJOINT file scopes and stateable interfaces. Interfaces you cannot
state -> serial single-task (log the reason). Crew is controller-elected;
there is no flag.

## 2 Interface first

Before dispatching, write `.goal/interfaces.md`: module boundaries, shared
types, naming conventions, who owns which files. Frozen at crew start;
changes are proposals (R3 spirit). Workers coordinate ONLY through files +
your briefs - a plain text reply from a worker is invisible to the others.

## 3 The brief (per worker)

```
Task: <bounded deliverable>
Output paths: <exact>
Scope: touch ONLY these files/dirs: <list>
Pass condition: <named check or observable>
Evidence: return the command you ran and its decisive output.
Rules: never touch .goal/ (R6); no subagents; no scope drift.
Interface contract: <relevant excerpt of interfaces.md>
```

Dispatch up to 3 workers in ONE message (they run concurrently). Their
execution craft is theirs - do not put goal-loop rules in the brief.

## 4 Join

All workers returned -> merge review: run the pass conditions, read the
seams (interfaces between their outputs), fix trivial mismatches yourself.
Interface conflict needing a redesign -> one serial repair round; two
failed repairs -> fall back to serial execution (log it).

## 5 FAIL attribution

Deterministic FAIL after join: fix within the owning worker's scope, then
`goal_gate.sh --verify [AC-ID]`. A FAIL that cannot be attributed -> rerun
the batch serially (bundle unbundle rule). Loop-log the wave as
`task=T2[crew:3]` with each worker's file list.

## 6 Final review (judged ACs - once, before claiming exit)

Dispatch ONE fresh reviewer seat. Brief carries: verbatim AC text, evidence
paths ONLY, rubric anchors. Never the producer's reasoning. Verdicts
ternary with quoted observation; findings must bind evidence.

Judging quality claims (what "逼真/好用/清晰" become) - in order:
- Rubric decomposition: observable dimensions, written 1-5 anchors, threshold.
- Pairwise A/B at a FIXED observation point (same camera/input/viewport)
  vs the previous iteration or a named reference artifact.
- Reference anchoring: delta against a known-good example, not absolute vibes.

Perspective note for reviewers: a far wing-tip or tail plane may PROJECT
above the fuselage silhouette from a quarter view - normal geometry, not a
floating defect; call detached only with a 3D gap across views.

## 7 Degradation

No Agent tool on the surface -> work inline, self-verify cold from the
claims list and artifact alone (not from production memory), label the
report `WEAKER VERIFICATION: cold self-check`.
