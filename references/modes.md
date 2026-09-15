# Modes, arguments, and the in-session helper

Contents: [1 invocation grammar] [2 the three budget modes] [3 forge exit]
[4 auto approval] [5 pre-stamp smoke rule] [6 evidence directory]
[7 check-expectation grammar] [8 mechanical bundling] [9 goal_ctl.sh]
[10 time budget].

## 1 Invocation grammar

```
/goal-loop [flags] <objective>
  --mode=quick|standard|deep   default: standard (budget only)
  --max-iterations=N           overrides the mode's budget
  --min-acs=N                  floor for the contract's AC count
  --auto                       no-approval mode (section 4)
  --forge                      sugar: contract gets `exit: forge` + deep budget
  --time-budget=N              whole-loop wall-clock fuse in seconds (section 10)
```
Unknown flags are an error: report them, never silently ignore. Budget and
exit policy are ORTHOGONAL axes - any budget mode may combine with either
exit policy.

## 2 The three budget modes

| mode | max_iterations | AC count | panel | extra duty |
|---|---|---|---|---|
| quick | 3 | 2-4 | req x1 | - |
| standard | 6 | 4-6 | req x1 | - |
| deep | 12 | 6-10 | req x1 + adversarial seat | below |

Deep mode's adversarial duty: every iteration, one seat receives ONE check
plus the assignment to make it FAIL legitimately - a real input, edge, or
environment that breaks it. A caught FAIL is a success: it routes through
fix-and-recheck and exercises the loop's repair path. A deep run whose every
iteration passes everything on the first sweep has NOT earned its exit.
Under forge this duty is what feeds the dry streak.

## 3 Forge exit (`exit: forge`) - maximization objectives

For "as good as possible / until it stops improving" goals. The contract
declares `exit: forge`; GO requires floors AND exhaustion:

- dry streak: `dry_limit` (default 3) consecutive rounds in which the panel,
  the adversarial seat and the completeness critic produced no new
  evidence-backed finding, and all fix-now discovery items are closed
  (R8 governs what counts as evidence-backed; checker-panel.md section 8).
- the critic's cold answer ("which dimension is still missing?") is empty;
  archived per round under `.goal/evidence/critic-iter-N.md`.
- max_iterations is a FUSE: exhausted without dry -> gate rc=3 budget-fuse
  -> ask the user to extend or deliver best-so-far. It never certifies
  completion.
- Optimization objectives SHOULD measure a baseline before stamping (store
  under `.goal/`), express ACs as metric deltas against it, and report
  deltas at delivery. Stagnation in metrics with findings still flowing is
  NOT dry - keep iterating or triage.
- Dry rounds usually leave the tree untouched (nothing to fix). Then the
  seats' DISCOVERY duty still runs - dryness is earned by finding nothing
  new, not by skipping the panel - but already-judged artifacts do NOT
  need re-seating: re-bind their PASSes at the current iteration under
  carry-forward (exit-gate.md R7). This is the main token saving of a
  long forge run.
- Honesty note: the dry streak is controller-bookkept and can only be
  discipline-audited, not mechanically proven; the gate's mechanical teeth
  are the deterministic rerun on claimed exits (a FAIL found there counts
  as a false-complete) and R8. Say this plainly in the delivery.

## 4 Auto approval (--auto)

The contract is still written and still shown in full in the conversation -
but the controller stamps it immediately (`approved: <hash> <date> auto`)
and starts iterating without waiting for sign-off. Guardrails that do NOT
bend:

- the stamp still freezes the AC section (R3) - no mid-run criteria edits;
- false-complete counting, evidence rules and the gate are unchanged;
- the loop-log block and the delivery both carry `approval=auto` so a human
  can audit after the fact;
- irreversible-side-effect objectives are refused in auto mode exactly as
  in gate mode (When-NOT-to-run is not waivable by a flag).

Default remains gate mode: present the contract, wait for explicit approval.

## 5 Pre-stamp smoke rule (contract authoring)

Before stamping, smoke-run EVERY named check command once, against a probe
or the in-progress artifact. A check that cannot execute as written (wrong
tool name, missing subcommand, unavailable binary) is rewritten at contract
time - never stamped and later excused by the panel. This rule exists
because it failed once: a contract named a CLI subcommand that did not
exist. The gate's `check-broken` reason is what catches survivors.

## 6 Evidence directory (.goal/evidence/)

Checks that GENERATE files (screenshots, dumps, renders) write them under
`.goal/evidence/`. It lives under `.goal/`, which the tree digest excludes -
so re-running a check never moves the binding. In-tree evidence outputs are
a contract-design fault. The critic archive and seat evidence live here too.

## 7 Check-expectation grammar (what the gate parses)

AC line: `- AC-N | <yes/no statement> | check: \`<command>\` | expected: <spec>`

| spec | class | gate behavior |
|---|---|---|
| `exit=0` or omitted | deterministic | rerun command; rc 0 = PASS; rc != 0 = FAIL; rc 124/127 = check-broken |
| `exit=N` (N>0) | deterministic negative | rc == N = PASS; asserts a failure mode is ABSENT (`repro.sh` expected `exit=1` = the crash no longer reproduces); other rc = FAIL; rc 124/127 (unless N) = check-broken |
| `>=N` `<=N` `>N` `<N` `==N` `!=N` | deterministic metric | rerun; LAST non-empty stdout line must be the number; compare |
| `judged` | judgment | seat verdict from verdicts.rec, digest-bound |
| anything else (prose) | judgment | routed as judged (v1.1 contracts keep working) |

Hard rules:
- the spec value must not contain `|` (it is parsed as the AC line tail);
  exact-text comparisons go INSIDE the command: `test "$(cat out.txt)" = expected`.
- the command runs at PROJECT ROOT via bash; stderr is discarded; it must
  not modify the tree (the gate fingerprints before/after: check-mutated-tree).
- metric commands should aggregate internally (N repeats, percentile) and
  print ONE number on the last line; see domain-patterns.md.
- prefer promoting judgments to deterministic checks over time: every
  check the gate owns is one a model can no longer hallucinate.

## 8 Mechanical bundling

"Every iteration one task" stays the default; polish phases produce all-green
empty rounds otherwise. Purely mechanical, mutually independent actions
(rename, format, complete, annotate) may bundle into one work-plan entry:

- mark the entry `[bundle]`; cap 5 actions; actions must touch disjoint
  files or be provably non-interacting;
- on ANY FAIL in the bundle's checks, unbundle for the fix round (attribution);
- forge/deep duties are unchanged: the adversarial seat and the gate still
  run every round;
- reasoning-heavy work never bundles.

## 9 goal_ctl.sh (in-session controller helper)

One entry point per bookkeeping step; the script is the controller's writing
hand and decides nothing (the gate stays the only arbiter):

```
bash scripts/goal_ctl.sh init  --project DIR [--max-iterations=N]   # seed .goal/
bash scripts/goal_ctl.sh stamp --project DIR [--auto]               # hash + stamp, refuses re-stamp
bash scripts/goal_ctl.sh bind  --project DIR < verdict-lines        # id|verdict|iter|digest|command|evidence
bash scripts/goal_ctl.sh close-iteration --project DIR --task ID \
     --files LIST --checks-pass N --checks-fail N --checks-unverifiable N \
     [--progress yes|no] [--exit-signal yes|no] [--error-signature none] \
     [--false-complete no] [--dry yes|no] [--no-gate]
```

`--dry` is REQUIRED on `exit: forge` contracts (yes = no new evidence-backed
finding this round and fix-now discoveries closed); the helper refuses
`--dry yes` alongside checks-fail > 0 and refuses to close a forge round
without it. `close-iteration` recomputes the tree digest, appends the
loop-log block, updates state (streak/breaker/dry_streak) and relays
`goal_gate.sh --check` unless `--no-gate`.

## 10 Time budget (`--time-budget=N`, v1.3)

A whole-loop wall-clock fuse in SECONDS. The deadline is seeded at approval:
`bash scripts/goal_ctl.sh stamp --project . --time-budget=1800` writes
`time_budget=1800` and `deadline=<epoch>` into state.rec (stamping is the
loop's official start, so the clock starts there). The GATE enforces it -
check 3b: `now > deadline` -> rc=3 `time-budget-exhausted`, the same
graceful-fuse class as forge's `budget-fuse`:

- graceful end, not a hard abort: finish the task in flight, close the
  iteration, run the gate, then deliver best-so-far with the open-items
  list (per SKILL.md Phase 2 step 1 the controller does not START a new
  task once the deadline has passed);
- passing floors before expiry still GOs normally - the fuse only fires
  when the loop would otherwise keep iterating;
- extension = explicit user approval, then rewrite `deadline=<new-epoch>`
  in state.rec (state.rec is controller bookkeeping; goal.md stays
  untouched, so R3 is not involved);
- `time_budget=0` / absent = no fuse (the default);
- NOT the same knob as unattended `goal_loop.sh --wallclock=SEC`, which
  caps ONE claude invocation, not the whole loop.

Example: `/goal-loop --time-budget=3600 "审计这个仓库的依赖并升级补丁版本"`
- 1 hour from approval, then whatever passed the gate ships.
