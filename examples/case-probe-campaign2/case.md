# Case E: complex-loop probe campaign 2 (2026-10-12, dsh-style round two)

**Goal**: not single-rule hostiles - drive gate/ctl/audit as a LOOP ENGINE
through multi-iteration state machines. Ten families, 63 expected-vs-observed
steps. Harness: `~/goal-loop-case-probe-campaign2/campaign.sh` +
`runs/LEDGER.md`. The skill is the target, the ten scenarios are scaffolding.

## Families (all CONFIRMED at run end)

S1 forge dry rounds (dry_streak arithmetic, premature claim counted) -
S2 breaker arc CLOSED->HALF_OPEN->OPEN + stagnation + repeated-error grind -
S3 wall-clock fuse (green claim GO+NOTE, failing claim escalates BLOCKED) -
S4 judged freshness across digest moves (stale->bind-seat hint, rebind GO,
lying artifact digest ->verdict-unbound) - S5 full false-complete ratchet arc
(catch1 NOTE, catch2 count, third claim frozen, fix does not unfreeze) -
S6 work-plan honesty + hint routing (bind-seat/restore-best/proposal-to-user,
status never points at finished work) - S7 R13 divergence both directions
+ flat-not-divergence + no-judge skip - S8 forge baseline discipline
(stamp-time exposure, drift caught, abs exemption) - S9 check-order
first-failure walk (tamper>FAIL, fc>budget, stale>rerun, malformed no-run) -
S10 audit lifecycle (A1/A2/A3/A4/A6/A8 including WARN-never-blocks).

## Defects found

| # | Probe | Symptom | Fix |
|---|-------|---------|-----|
| D10 | S10.8: judged AC present, scores.rec never created (early rounds) | A8's reader error leaked `No such file or directory` to stderr - noise that looks like a violation | guard the read: missing file = zero judge scores = plain WARN (t97) |

**Non-defects worth stating**: the ledger's 62 other steps confirmed documented
behavior - notably S9 (the gate's check-order really is first-failure-wins),
S4.3b/S4.4b (R1 counts stale/unbound claims as false completes exactly once),
S7.2 (flat score with moving judge is NOT divergence), S8.6 (`baseline: abs`
exempts from baseline.md). Three earlier SEE rows were harness bugs on our
side, not skill defects: a sed with the wrong delimiter, binding a verdict to
iteration N while the claim lands at N+1 (R7 freshness trips first - bind at
the claim's iteration), and expecting verdict-unbound where not-covered had
already fired.

## Regression lock

Tests 93 (breaker sequence arc), 94 (repeated-error grind), 95 (hint routing
beyond bind-seat), 96 (forge dry round sequence), 97 (D10 stderr hygiene) turn
the campaign's state machines into permanent single-command assertions.
236 assertions, 0 fail. Method lesson (round 2): **single rules were already
green; the seams between SEQUENCES (iteration numbering, arc transitions,
sidecar lifecycle) were where the remaining risk lived** - D10 is one of those.
