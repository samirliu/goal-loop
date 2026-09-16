# Checker panel - assemble, brief, judge, recheck

Contents: [1 extraction] [2 panel routing] [3 brief template] [4 ternary
verdicts] [5 judging quality claims] [6 seam check] [7 fix and recheck]
[8 discoveries] [9 degradation].
Read this when assembling the panel for a finished artifact.

## 1 Extraction: claims and requirements, from the artifact, not from memory

- Claims C1, C2, ... : every falsifiable assertion the deliverable makes -
  numbers, paths, byte-exact outputs, "it works", "all rows present". Each
  restated so a specific observation could refute it; if none could, drop it
  from established status.
- Requirements R1, R2, ... : the ACs THIS artifact realizes, each already
  yes/no.
- Route each item: if a program can settle it, make it a deterministic
  named check (exit=0 or a metric spec) - the GATE will re-run it; never
  spend a seat on it. If it needs judgment, it stays with a seat and
  `expected: judged`.
- An item no check can reach -> declare UNVERIFIABLE up front with PROBE
  and REASON; do not smuggle it through as PASS.

## 2 Panel routing (budget: checkers <= panel_max = 4)

| lane | items | agent | model | seats |
|---|---|---|---|---|
| deterministic | anything a command settles (exit codes, counts, diffs, metric comparisons) | NONE - `goal_gate.sh --verify` / inline at --check | - | 0 |
| requirements | AC coverage by the artifact itself, internal consistency, claim NOMINATION (falsifiable claims the controller missed -> propose them as new named checks) | goal-checker-req | sonnet | 1 |
| judgment | quality claims marked `expected: judged` (see section 5) | goal-checker-req (or a judged-role seat) | sonnet | 0-1 |
| forge critic | "which dimension is still missing?" cold answer; zero-answer = clear | goal-critic | opus | 0-1 (forge, candidate-dry rounds ONLY - see below) |
| adjudication | only ids where seats split, or a disputed refutation / make-work claim | goal-adjudicator | opus | 0-1 |

The v1.1 mechanical seats (goal-checker-mech) are GONE: "run a command and
quote its output" is now the gate's job - cheaper and honest (no model in
the trust chain). What a seat adds over the gate is judgment and fresh-eyes
nomination, so that is all seats do.

GATE-ONLY ROUNDS: an iteration whose artifact is all deterministic surface
and introduces no new judged claims (the recurring polish/bundle round in
optimization loops) spawns ZERO seats - the gate is the whole panel and
costs a few bash invocations. Seats follow judgment, not ritual.

CRITIC-ON-DEMAND (forge): the completeness critic runs only when the
adversarial seat came back clean - a candidate-dry round. A round with a
FAIL is not dry, so the critic has nothing to arbitrate there; its cost is
paid only where it can change the outcome, and the dry guarantee is
unchanged (every round counting toward the streak still needs the empty
critic answer, archived per round).

## 3 The brief (verbatim template; fill, do not embellish)

```
READ-ONLY: judge the artifact; do not redo the task; do not modify anything
except writing your evidence under .goal/evidence/.
Locus: <absolute artifact paths>
Spec (verbatim, copied - never paraphrased):
<AC-7 text exactly as stamped>
Items (id | what would refute it):
<R2 | the summary claims 0 NULLs; count them>
Rules:
- Refute freely: a refutation found is a success, not a failure.
- Report PASS only for what you observed yourself; the evidence must quote the
  command and the exact output line.
- Cannot check -> UNVERIFIABLE with PROBE=<what you attempted> REASON=<why
  inapplicable>. Do not guess; do not fill gaps with plausibility.
- Findings must bind evidence (R8): name the check that produced or would
  produce the FAIL, or the missing dimension with a concrete probe. An
  evidence-free finding is void.
- Image budget: read each provided image at most twice (first view + one
  zoom batch); judge from the pre-cropped bands in .goal/evidence/ when
  present. Re-reading full images to re-confirm what you already described
  burns the session - it adds no evidence.
- Probe budget (adversarial seat): at most 6 invocations of the measured
  environment and ~10 minutes per round; rotate the attack surface per the
  coverage ledger (.goal/evidence/adv-coverage.md) - extend it, never repeat
  a covered surface.
- No subagents.
Output format, one line per item:
id|verdict|command|evidence
```

Never include in any brief: the controller's reasoning, its confidence,
hints of which items are suspect. A checker that reads the producer's
reasoning inherits the producer's blind spots and returns agreement, not
verification.

## 4 Ternary verdicts - forced, one per judged item

- PASS - with quoted command + exact output line. "Looks good" is no verdict.
- FAIL - with what is actually true instead, also quoted.
- UNVERIFIABLE - a first-class outcome, with PROBE/REASON; never a failure in
  disguise, never a dodge.
A panel over >=3 judged items that never says UNVERIFIABLE is guessing to
look thorough: pick one item and re-run it adversarially.

## 5 Judging quality claims (what "逼真/好用/清晰" become)

LLMs are unreliable at absolute scoring and reliable at comparison; convert
subjective claims accordingly, in this order of preference:

- Rubric decomposition: split the claim into observable dimensions, each
  scored 1-5 against a WRITTEN anchor ("5: X is true", "3: Y but not Z"),
  with a pass threshold. No anchor -> the claim is not judgable; rewrite it
  at contract time.
- Pairwise A/B: present the new artifact and the previous iteration side by
  side at a FIXED observation point (same camera, same input, same
  viewport) and ask one question: which is better, and name the dimension.
  Strictly-better chains across iterations are the forge ratchet.
- Reference anchoring: compare against a known-good example the user (or
  the contract) names; report the delta, not an absolute score.

Evidence discipline still applies: the judgment line quotes what was
compared and the deciding observation.

## 6 Synthesis seam check (the error that survives every other)

The handover document itself, not the intermediates: extract its claims too.
Two hunts:
- escalated hedges - a caveat in the work ("signal") became a firm assertion
  in the summary ("exposure") -> check the summary's word.
- proxy-metric traps - timestamp is not a version; file size is not disk
  usage; a search finding nothing is not evidence of absence. Verify the
  quantity itself.

## 7 Fix and recheck

- Deterministic FAIL: fix, then `goal_gate.sh --verify [AC-ID]` - exit code
  is the verdict; no seat, no R2 (measurement is always legal).
- Judged FAIL: fix, then re-run THAT seat only - never the whole panel.
  Legal re-run precondition: the digest of the covered files MOVED since
  the FAIL (R2). No move -> stagnation, not work.
- Per-check fail cap (state.rec per_check_fail_cap, default 3): at the cap,
  stop, mark the task blocked, ask the user. Grinding the same wall is
  prohibited.
- Delivery gate: zero open FAIL. Never deliver a FAIL with a footnote.

## 8 Discoveries (panel output beyond verdicts; forge's dry meter)

A seat may emit DISCOVERY lines alongside verdicts:
`DISCOVERY|<serves AC-id or 'quality'>|<one-line gap>|<evidence pointer>`.
- Evidence rule (R8): a discovery binds a check that produced or would
  produce a FAIL, or a critic-named dimension with a concrete probe.
  Evidence-free discoveries are void; the adjudicator arbitrates disputes.
- Triage (controller): fix-now -> append to work-plan as `[D]` task;
  deferred -> park, list at delivery; declined -> park with a one-line
  reason, list at delivery as proposals. Declined items still reach the
  user - triage sorts work, it does not hide findings.
- Forge metering: open fix-now discoveries block a `--dry yes` round;
  deferred/declined do not.

## 9 Degradation (no Agent tool on this surface)

Say so in one line, then cold self-check: work from the claims/requirements
lists and the artifact alone - deliberately not from the memory of
producing it; re-run every check yourself (or via the gate for
deterministic ones), same ternary discipline, same evidence rules. Label
the report `WEAKER VERIFICATION: cold self-check`. It is weaker: fresh
agents beat re-runs by the producer's own hand.
