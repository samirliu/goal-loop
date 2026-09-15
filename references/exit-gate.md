# Exit gate - schemas, rules, scenarios

Contents: [1 file formats] [2 tree digest] [3 gate checks in order] [4 circuit
breaker] [5 anti-gaming rules R1-R7] [6 scenarios] [7 non-goals].
Read this before every gate decision. The gate is read-only: it decides, it
never writes; the controller performs every state update it is told to.

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
```

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
digest=6a1b2c3d4e5f        # tree digest at block-close
```

`.goal/verdicts.rec` - append-only, pipe-separated, LATEST record per id wins,
iter+digest bind the verdict to a revision of the tree. Six fields:
`id|verdict|iter|digest|command|evidence` (evidence is field 6):
```
AC-1|PASS|3|6a1b2c3d4e5f|bash primes.sh|"2 3 5 7 11 13 17 19 23 29 31 37 41 43 47"
AC-2|FAIL|2|6a1b2c3d4e5f|wc -l < primes.sh|"31"
AC-3|UNVERIFIABLE|3|6a1b2c3d4e5f|-|PROBE=offline doc lookup REASON=vendor API unreachable
```
The 6th field: PASS/FAIL -> quoted output line; UNVERIFIABLE -> the literal
`PROBE=<attempted> REASON=<why inapplicable>`. An empty 6th field voids PASS.

`.goal/goal.md` - stamp line matches `^approved: [0-9a-f]{8} [0-9]{4}-` and the
stamp value is the first 8 hex of sha1 over the lines of the `## Acceptance
criteria` section body (between its header and the next `^## ` or EOF).

## 2 Tree digest (12 hex; `goal_gate.sh --digest` prints it; never compute by hand)

- inside a git work tree: sha1 over `git rev-parse HEAD` newline `git status --porcelain | sort`
- outside git: sha1 over the sorted `path cksum` list of all files, excluding
  `.goal/` and `.git/`
- `.goal/evidence/` is where checker commands write GENERATED files
  (screenshots, dumps): under `.goal/` it stays digest-excluded, so re-running
  a check never moves the binding. In-tree evidence outputs are a
  contract-design fault (they churn the digest on every re-run).
Deterministic; a file edited then restored to identical content may still move
the digest (porcelain records) - that is admissible, it over-flags, never
under-flags.

## 3 Gate checks, in order; the FIRST failure decides the exit code

```
0. .goal/ readable, state.rec has all required keys      else exit 4 (state error)
1. stamp present AND recomputed AC-body hash matches     else exit 2 (no-approval / contract-tampered)  [R3]
2. breaker=OPEN or false_completes>=2                    else exit 3 (blocked)
3. iteration <= max_iterations                            else exit 2 (budget-exhausted)
4. no_progress_streak <= no_progress_limit                else exit 3 (stagnation)
4b. last two loop blocks share the same non-none
    error_signature (grind on one wall)                   else exit 3 (repeated-error)
5. last loop block: exit_signal=yes                       else exit 2 (not-claimed)
6. last loop block digest == recomputed tree digest       else exit 2 (verdicts-stale)      [R7]
7. every AC id in goal.md has its LATEST verdict with
   iter==iteration and digest==recomputed, and none FAIL  else exit 2 (not-covered / open-FAIL)  [R1]
8. every PASS record has non-empty quoted evidence        else exit 2 (evidence-missing)   [R5]
9. unverifiable*3 <= total                                 else exit 2 (unverifiable-excessive) [R4]
   PASS -> print "GATE: GO digest=<d> iter=<n> ac=<total> pass=<p> unverified=<u>"
```
When check 6 (digest mismatch) fails while exit_signal=yes was claimed, the
gate prints `GATE: NOTE false-complete suspected; controller: append
false_complete=yes and increment false_completes in state.rec`. Other check
5-9 failures on a claimed exit print no NOTE; the controller still logs
false_complete=yes per SKILL.md Phase 3 (the two-strikes BLOCKED rule is
enforced through state, not through the NOTE).

The gate also prints `GATE: NOTE loop-log-missing-keys:<keys>` (stderr, no
exit-code change) when the last loop block omits any of the canonical schema
keys declared as `loop_keys` in goal_gate.sh (task, files_modified,
checks_pass, checks_fail, checks_unverifiable, error_signature, progress,
exit_signal, false_complete, digest). This is advisory; only exit_signal and
digest are hard-checked.

## 4 Circuit breaker (controller bookkeeps, gate enforces)

CLOSED (streak below limit) -> HALF_OPEN (streak == limit: change strategy,
replans++, a third replan -> ask the user) -> OPEN (streak > limit, or
false_completes >= 2: stop, report BLOCKED, hand back). Any progress=yes block
resets streak to 0 and the breaker to CLOSED.

## 5 The seven anti-gaming rules (normative)

- R1 false-complete: a claimed exit is honored only with (all-AC latest
  verdicts PASS/justified-UNVERIFIABLE) AND (exit_signal=yes in the last block)
  AND (digest match). Two gate-flagged false claims -> BLOCKED, human decides.
- R2 duplicate checks: re-running a check is illegal while the digest of its
  covered files is unmoved since its last FAIL; illegal re-runs count as
  stagnation, never as work.
- R3 criteria inflation: the AC section is frozen by the stamp; agent edits
  -> contract-tampered -> NO-GO; new criteria go to the user as proposals.
- R4 unverifiable dumping: each UNVERIFIABLE must name PROBE and REASON; for
  artifact types in domain-patterns.md with an applicable pattern, a claimed
  UNVERIFIABLE is coerced to FAIL; above one third -> adversarial recheck.
- R5 checker contamination: briefs carry verbatim AC text + paths only;
  verdicts must quote command+output; verdicts without observation are void.
- R6 interference: worker diffs that touch `.goal/` -> violation; two ->
  BLOCKED; only the controller writes state files.
- R7 stale verdicts: verdicts bind to (iter, digest); anything after a digest
  move is stale and must be re-judged.

## 6 Scenarios (Given/When/Then)

1. In-progress: checks_fail>0, exit_signal=no -> gate not consulted; continue.
2. Clean completion: all AC PASS this iter/digest, exit_signal=yes -> GO(0),
   deliver.
3. False-complete attempt: exit_signal=yes but AC-3 latest verdict is FAIL
   from an older digest -> NO-GO(2) + false-complete note; controller logs
   false_complete=yes, false_completes=1; next such claim -> 1+1>=2 -> BLOCKED.
4. Stagnation: progress=no two blocks running -> streak=2=limit -> HALF_OPEN
   (strategy change); third -> OPEN -> exit 3.
5. Unverifiable dumping: 2 of 3 AC UNVERIFIABLE -> exit 2
   (unverifiable-excessive); fix the probe or ask the user.

## 7 Non-goals

The gate never: writes files, runs the project's build/tests itself, reads
chat, trusts the GOAL_STATUS block (it reads only the persisted loop-log
mirror), or bypasses the stamp. Exit codes: 0 GO / 2 NO-GO / 3 BLOCKED /
4 state error.
