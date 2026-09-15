# Checker panel - assemble, brief, judge, recheck

Contents: [1 extraction] [2 panel routing] [3 brief template] [4 ternary
verdicts] [5 seam check] [6 fix and recheck] [7 report] [8 degradation].
Read this when assembling the panel for a finished artifact.

## 1 Extraction: claims and requirements, from the artifact, not from memory

- Claims C1, C2, ... : every falsifiable assertion the deliverable makes -
  numbers, paths, byte-exact outputs, "it works", "all rows present". Each
  restated so a specific observation could refute it; if none could, drop it
  from established status.
- Requirements R1, R2, ... : the contract's AC text, each already yes/no.
- Per item name THE check: the exact command, comparison, or observation that
  settles it. An item no check can reach -> declare UNVERIFIABLE up front with
  PROBE and REASON; do not smuggle it through as PASS.

## 2 Panel routing (budget: checkers <= panel_max = 4)

| lane | items | agent | model | seats |
|---|---|---|---|---|
| mechanical | recompute, recount, rerun commands, file exists/shape, byte-exact diff | goal-checker-mech | haiku | 2-3 (one bundle each) |
| requirements | coverage of every AC by the artifact itself, internal consistency | goal-checker-req | sonnet | 1 |
| adjudication | only the ids where the panel split, or a disputed refutation | goal-adjudicator | opus | 0-1 |

Escalate to adjudication sparingly: one adjudicator, disputed ids only, it
does not re-check the rest.

## 3 The brief (verbatim template; fill, do not embellish)

```
READ-ONLY: judge the artifact; do not redo the task; do not modify anything.
Locus: <absolute artifact paths>
Spec (verbatim, copied - never paraphrased):
<AC-7 text exactly as stamped>
Items (id | named check):
<C3 | diff <(bash out.sh) expected.txt -> must be empty>
Rules:
- Refute freely: a refutation found is a success, not a failure.
- Report PASS only for what you observed yourself; the evidence must quote the
  command and the exact output line.
- Cannot check -> UNVERIFIABLE with PROBE=<what you attempted> REASON=<why
  inapplicable>. Do not guess; do not fill gaps with plausibility.
- No subagents.
Output format, one line per item:
id|verdict|command|evidence
```

Never include in any brief: the controller's reasoning, its confidence, hints
of which items are suspect. A checker that reads the producer's reasoning
inherits the producer's blind spots and returns agreement, not verification.

## 4 Ternary verdicts - forced, one per item

- PASS - with quoted command + exact output line. "Looks good" is no verdict.
- FAIL - with what is actually true instead, also quoted.
- UNVERIFIABLE - a first-class outcome, with PROBE/REASON; never a failure in
  disguise, never a dodge.
A panel over >=3 items that never says UNVERIFIABLE is guessing to look
thorough: pick one item and re-run it adversarially.

## 5 Synthesis seam check (the error that survives every other)

The handover document itself, not the intermediates: extract its claims too.
Two hunts:
- escalated hedges - a caveat in the work ("signal") became a firm assertion
  in the summary ("exposure") -> check the summary's word.
- proxy-metric traps - timestamp is not a version; file size is not disk
  usage; a search finding nothing is not evidence of absence. Verify the
  quantity itself.

## 6 Fix and recheck

- A FAIL: fix, then re-run THAT check only - never the whole panel (cost,
  and a second full run produces a second version plus a comparison problem).
- Legal re-run precondition: the digest of the covered files MOVED since the
  FAIL (R2). No move -> stagnation, not work.
- Per-check fail cap (state.rec per_check_fail_cap, default 3): at the cap,
  stop, mark the task blocked, ask the user. Grinding the same wall is
  prohibited.
- Delivery gate: zero open FAIL. Never deliver a FAIL with a footnote.

## 7 Report (controller assembles, then delivers)

```
Verification: <p> PASS, <f> FAIL (fixed: <list each concretely, one line>),
<u> UNVERIFIABLE (<each named: probe/reason>).
Panel: <mech>x mechanical, <req>x requirements[, 1x adjudicator].
Clean pass stated plainly if clean; no manufactured findings.
```
A summary that confirms everything is either a clean run or a rubber stamp;
only concrete named refutations tell them apart - name the ones you have.

## 8 Degradation (no Agent tool on this surface)

Say so in one line, then cold self-check: work from the claims/requirements
lists and the artifact alone - deliberately not from the memory of producing
it; rerun every check yourself, same ternary discipline, same evidence rules.
Label the report `WEAKER VERIFICATION: cold self-check`. It is weaker: fresh
agents beat re-runs by the producer's own hand.
