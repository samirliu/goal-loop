# Exit gate - schemas, rules, scenarios

Contents: [1 file formats] [2 tree digest + mutation guard] [3 gate checks
in order] [4 circuit breaker] [5 anti-gaming rules R1-R8] [6 scenarios]
[7 what the gate does and does not do].
Read this before every gate decision. The gate decides; the controller
performs every state update it is told to.

## 1 File formats (line-oriented, CR-tolerant - the gate strips CR itself)

`.goal/state.rec` - one `key=value` per line, required keys:
```
iteration=3
breaker=CLOSED            # CLOSED | HALF_OPEN | OPEN
false_completes=0         # gate-flagged false claims, counted by controller
replans=0
no_progress_streak=1      # consecutive loop blocks with progress=no
last_progress_iteration=2
max_iterations=12
no_progress_limit=2
max_replans=2
per_check_fail_cap=3
panel_max=4
dry_streak=0              # forge only: consecutive dry rounds
dry_limit=3               # forge only: rounds of exhaustion required to exit
check_timeout=120         # seconds per gate-rerun check (coreutils timeout)
time_budget=0             # seconds; 0 = no wall-clock fuse (v1.3)
deadline=0                # epoch set at stamping via --time-budget; 0 = off
```
`dry_streak`/`dry_limit` are REQUIRED only when goal.md declares
`exit: forge` (missing -> exit 4 missing-key).

`.goal/loop-log.md` - append-only, one block per iteration, exact keys:
```
## iteration 3
task=T2
files_modified=primes.sh
checks_pass=2
checks_fail=0
checks_unverifiable=0
error_signature=none      # short stable hash of the repeated error, or none
progress=yes              # yes if any AC advanced, any file changed, any check newly passed
exit_signal=no            # the controller's claim, mirrored from GOAL_STATUS
false_complete=no         # set by controller after a gate NO-GO on a claimed exit
digest=6a1b2c3d4e5f       # tree digest at block-close
```

`.goal/verdicts.rec` - append-only, pipe-separated, LATEST record per id wins,
iter+digest bind the verdict to a revision of the tree. Six fields:
`id|verdict|iter|digest|command|evidence` (evidence is field 6):
```
AC-1|PASS|3|6a1b2c3d4e5f|bash primes.sh|"2 3 5 7 11 13 17 19 23 29 31 37 41 43 47"
AC-2|FAIL|2|6a1b2c3d4e5f|wc -l < primes.sh|"31"
AC-3|UNVERIFIABLE|3|6a1b2c3d4e5f|-|PROBE=offline doc lookup REASON=vendor API unreachable
```
For DETERMINISTIC ACs (see contract grammar below) these records are mid-loop
bookkeeping only: at --check the gate ignores them and re-runs the check
itself; the rerun IS the evidence. The evidence rules below bind JUDGED
verdicts: PASS needs the quoted decisive output line; UNVERIFIABLE needs the
literal `PROBE=<attempted> REASON=<why inapplicable>`; an empty 6th field
voids a PASS.

`.goal/goal.md` - the AC grammar the gate parses:
```
- AC-1 | <yes/no statement> | check: `<command>` | expected: <spec>
```
- `expected: exit=0` (or omitted) -> deterministic, gate reruns, rc decides.
- `expected: <op><number>` (op in `>= <= > < == !=`) -> deterministic metric;
  the command's stdout LAST non-empty line must be the number; gate compares.
- `expected: judged` -> a seat verdict (stored record, digest-bound).
- anything else (prose, incl. v1.1 contracts) -> routed as `judged`
  (v1.1 semantics preserved: a human-worded expectation was always judged).
- the spec value must not contain `|` (it is parsed as the line tail);
  exact-text comparisons belong INSIDE the command (`test "$(cat x)" = y`).
- `exit: forge` line anywhere in goal.md switches the exit policy.

Stamp line matches `^approved: [0-9a-f]{8} [0-9]{4}-`; the stamp value is
the first 8 hex of sha1 over the `## Acceptance criteria` section body PLUS
every line matching `^exit:` (the exit policy is part of the frozen
contract - flipping `exit: forge` to `threshold` after approval is
contract-tampered). Budget-knob lines in goal.md are NOT covered: they are
decorative there, state.rec is authoritative. v1.1 contracts carry no
`^exit:` line, so their stamps verify unchanged.

## 2 Tree digest + mutation guard (12 hex; `goal_gate.sh --digest`)

- inside a git work tree: sha1 over `git rev-parse HEAD` newline
  `git status --porcelain | sort`; outside git: sorted `path cksum` list,
  excluding `.goal/` and `.git/`; `.goal/evidence/` is digest-excluded, so
  checker-produced files never move the binding.
- Since v1.2 the gate runs check commands. It takes a digest before and
  after every rerun batch (`--verify`) and after the inline rerun at
  `--check` (check 10): a moved digest -> `check-mutated-tree` NO-GO.
  Checks must be side-effect-free on the tree; generated evidence goes to
  `.goal/evidence/`.

## 3 Gate checks, in order; the FIRST failure decides the exit code

```
0.  .goal/ readable, state.rec has all required keys      else exit 4 (state error)
0b. exit: forge -> dry_streak/dry_limit present           else exit 4 (missing-key)
1.  stamp present AND recomputed AC-body hash matches     else exit 2 (no-approval / contract-tampered)  [R3]
2.  breaker=OPEN or false_completes>=2                    else exit 3 (blocked)
2c. now <= deadline (when time_budget>0; v1.3 wall-clock
    fuse; BEFORE the iteration budget so expiry always
    answers the graceful rc=3)                            else exit 3 (time-budget-exhausted: graceful
                                                          best-so-far delivery, extension = user-approved
                                                          rewrite of deadline= in state.rec)
3.  iteration <= max_iterations                           else exit 2 (budget-exhausted)
    ... on forge:                                         else exit 3 (budget-fuse: a fuse, ask the user)
4.  no_progress_streak <= no_progress_limit               else exit 3 (stagnation)
4b. last two loop blocks share the same non-none
    error_signature (grind on one wall)                   else exit 3 (repeated-error)
5.  last loop block: exit_signal=yes                      else exit 2 (not-claimed)
6.  last loop block digest == recomputed tree digest      else exit 2 (verdicts-stale)      [R7]
7.  per AC:
    deterministic -> gate re-runs the check NOW           FAIL -> exit 2 (open-FAIL, gate rerun)
                                                          not executable / non-numeric -> exit 2 (check-broken)
    judged        -> LATEST stored verdict with
    iter==iteration and digest==recomputed, none FAIL     else exit 2 (not-covered / open-FAIL)  [R1,R7]
    (iter==iteration is satisfied by a CARRY-FORWARD re-bind: appending the
    same PASS at the current iter while the digest is unchanged from the
    original verdict - same bytes, same truth, no re-seat)
8.  judged PASS records have non-empty quoted evidence    else exit 2 (evidence-missing)   [R5]
9.  unverifiable*3 <= total (judged UNVERIFIABLE only)    else exit 2 (unverifiable-excessive) [R4]
10. tree digest unchanged after the rerun batch           else exit 2 (check-mutated-tree)
11. forge: dry_streak >= dry_limit                        else exit 2 (not-dry)
    PASS -> print "GATE: GO digest=<d> iter=<n> ac=<total> pass=<p> unverified=<u> mode=<m>"
```
When check 6 fails while exit_signal=yes was claimed, the gate prints
`GATE: NOTE false-complete suspected; controller: append false_complete=yes
and increment false_completes in state.rec`. Other 5-9 failures on a claimed
exit print no NOTE; the controller still logs false_complete=yes (the
two-strikes rule is enforced through state).

The gate prints `GATE: NOTE loop-log-missing-keys:<keys>` (stderr, no
exit-code change) when the last loop block omits canonical keys; only
exit_signal and digest are hard-checked.

`--verify [AC-ID ...]` reruns deterministic checks standalone (0 all-pass /
2 fail-or-broken-or-mutated / 4 state error), skipping judged ids with a
SKIP line. It reads the contract WITHOUT consulting the stamp - measurement
is safe either way; only `--check` requires a frozen, approved contract.
Use it for fix-loop verification; the controller still binds
bookkeeping records if it wants the audit trail.

## 4 Circuit breaker (controller bookkeeps, gate enforces)

CLOSED (streak below limit) -> HALF_OPEN (streak == limit: change strategy,
replans++, a third replan -> ask the user) -> OPEN (streak > limit, or
false_completes >= 2: stop, report BLOCKED, hand back). Any progress=yes
block resets streak to 0 and the breaker to CLOSED.

## 5 The anti-gaming rules (normative)

- R1 false-complete: a claimed exit is honored only with (all-AC floors
  PASS/justified-UNVERIFIABLE - deterministic ACs via the gate's own
  rerun) AND (exit_signal=yes) AND (digest match). On forge also
  dry_streak >= dry_limit. Two gate-flagged false claims -> BLOCKED.
- R2 duplicate checks: re-running a SEAT judgment is illegal while the
  digest of its covered files is unmoved since its last FAIL; illegal
  re-runs count as stagnation, never as work. Gate re-runs of
  deterministic checks are measurement, not work - always legal.
- R3 criteria inflation: the AC section is frozen by the stamp; agent edits
  -> contract-tampered -> NO-GO; new criteria go to the user as proposals.
- R4 unverifiable dumping: each judged UNVERIFIABLE must name PROBE and
  REASON; a claim of UNVERIFIABLE for an artifact type with an applicable
  domain-pattern is coerced to FAIL; above one third -> adversarial recheck.
- R5 checker contamination (judged seats): briefs carry verbatim AC text +
  paths only; verdicts must quote command+output; verdicts without
  observation are void. Deterministic ACs are exempt: the gate's rerun is
  the evidence, no model in the loop.
- R6 interference: worker diffs that touch `.goal/` -> violation; two ->
  BLOCKED; only the controller writes state files (via goal_ctl.sh).
- R7 stale verdicts: judged verdicts bind to (iter, digest); anything after
  a digest move is stale and must be re-judged. Deterministic ACs are
  exempt (the gate recomputes at every exit). Carry-forward: a judged PASS
  may be re-bound to a later iteration while the digest is UNCHANGED
  (cite the original evidence; `carried=yes` in the evidence field). FAIL
  and UNVERIFIABLE are never carried. No covered-set sharding: a moved
  digest voids verdicts on untouched artifacts too - that hole is
  deliberate (scope-declaration risk outweighs the saved re-seats).
- R8 make-work (forge): a discovery item or adversarial finding is
  legitimate only if it binds evidence - a check that produced (or, run,
  would produce) a FAIL, or a critic-named dimension with a concrete probe.
  Evidence-free findings are void; the adjudicator arbitrates disputed
  make-work claims. Symmetric with R5: manufactured refutations are as
  forbidden as manufactured passes.

## 6 Scenarios (Given/When/Then)

1. In-progress: checks_fail>0, exit_signal=no -> gate not consulted; continue.
2. Clean threshold completion: all floors PASS at this iter/digest (deterministic via rerun), exit_signal=yes -> GO(0).
3. False-complete attempt: exit_signal=yes but a judged AC's latest verdict is FAIL from an older digest -> NO-GO(2) + note; two such claims -> BLOCKED.
4. Metric drift: AC-2 `expected: >=60`, rerun prints 58 -> NO-GO(2) open-FAIL with observed/expect in the reason; fix, `--verify AC-2` until rc 0.
5. Stagnation: progress=no two blocks running -> HALF_OPEN (strategy change); third -> OPEN -> exit 3.
6. Forge dry exit: floors PASS, dry_streak=3=limit, critic archive empty-answer -> GO(0) mode=forge.
7. Forge false-dry: exit claimed with dry_streak=3 but the rerun finds AC-2 failing -> open-FAIL(2); controller logs false_complete=yes; two -> BLOCKED.
8. Budget as fuse: forge, iteration 13 > max 12 -> BLOCKED(3) budget-fuse; user extends or best-so-far is delivered.
9. Mutating check: an AC's command appends to a tree file -> verify digest moves -> NO-GO(2) check-mutated-tree; rewrite the check.
10. Unverifiable dumping: 2 of 3 judged AC UNVERIFIABLE -> exit 2 (unverifiable-excessive).

## 7 What the gate does and does not do

The gate NEVER: writes any file, runs anything except the contract's
stamped, smoke-run check commands (each under `check_timeout` seconds, at
project root, with stderr discarded), reads chat, trusts the GOAL_STATUS
block (it reads only the persisted loop-log mirror), or bypasses the
stamp. It is not a sandbox: the commands it runs are the ones the user
approved and the controller already smoke-ran. Exit codes: 0 GO / 2 NO-GO
/ 3 BLOCKED / 4 state error. Self-test: `bash tests/run_tests.sh`.
