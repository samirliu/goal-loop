# Gate - schemas, check order, rules (the only completion authority)

Read before every gate decision. The gate decides; the controller
bookkeeps via goal_ctl.sh. Scripts: `scripts/goal_gate.sh` (`--check`,
`--digest`, `--verify [AC-ID]`, `--baseline-check`).

## 1 Schemas

`.goal/state.rec` keys: iteration breaker(CLOSED|HALF_OPEN|OPEN)
false_completes replans no_progress_streak last_progress_iteration
max_iterations no_progress_limit max_replans per_check_fail_cap panel_max
dry_streak dry_limit check_timeout time_budget deadline best_score.
`dry_streak/dry_limit` required only for `exit: forge`.
Budget knobs written in goal.md (max_iterations, dry_limit, check_timeout,
wallclock, ...) BIND at stamp - goal_ctl.sh stamp copies them into state.rec.
`best_score` is the water mark for `objective: maximize|minimize AC-N` (R11) -
high-water for maximize, low-water for minimize.

`.goal/loop-log.md` append-only blocks, exact keys:
`## iteration N` + task files_modified checks_pass checks_fail
checks_unverifiable error_signature progress exit_signal false_complete
digest score strategy_delta. `task=T2[crew:3]` marks a one-shot crew wave,
`task=T2[teams:3]` a Teams-backend wave (same gate authority either way).
Bare `T<n>` normalizes to `T<n>[crew:1]` at write; free-form task ids are
refused by ctl (R12/A1 is enforced by the writer, not only by the audit).
`score=` holds the objective value or `none`; `strategy_delta=`
is mandatory whenever `progress=no` (R10).

`.goal/verdicts.rec` 6 fields: `id|verdict|iter|digest|command|evidence`.
Deterministic ACs: records are bookkeeping; the gate's rerun is the
evidence. Judged ACs: PASS needs the quoted decisive output PLUS an
`artifact: <path> digest: <sha256>` binding - the gate recomputes the
sha256 of that path and voids the verdict on mismatch (`verdict-unbound`);
UNVERIFIABLE needs `PROBE=.. REASON=..`; empty evidence voids a PASS.
Calibration rows share the same 6-field schema under derived ids: `AC-1#good`
and `AC-1#bad` - the seat's grades on the declared fixtures (see `calib:`
below). Derived ids count as ordinary rows for bind/stale rules: a digest
move or iteration bump voids them exactly like the parent verdict.

`.goal/goal.md` AC grammar:
`- AC-N | <statement> | check: \`<command>\` | [probe: \`<cmd>\`] | [baseline: delta|abs] | [metric: \`regex one capture group\`] | [tolerance: <rel>] | [calib: good=<f> bad=<f>] | expected: <spec>`
- `exit=0`/omitted -> deterministic rc check; `exit=N` -> must end with that
  exact code (error paths as first-class ACs); `<op><number>` (>= <= > < == !=)
  -> metric, number from `metric:` regex or LAST non-empty stdout line;
  `maximize`/`minimize` -> objective score (numeric, not a floor; direction
  taken from the objective line); `judged` -> seat
  verdict digest-bound; prose (v1.1) -> judged. Spec value must not contain
  `|`; exact-text compare goes INSIDE the command.
- AC lines missing `expected:` or `check:` make the gate refuse the contract
  (`contract-malformed`, fail-closed) - no silent AC loss, no free PASS.
- `metric:` pins WHERE the number comes from (one capture group; ANSI codes
  stripped before matching) - use when output carries other numbers.
  `tolerance:` gives the objective water-mark a relative noise band: within
  it the score holds (no false regression); below/above it R11 fires.
- `probe: \`cmd\`` (R9) must PASS before a metric/maximize/minimize number is
  trusted - it asserts the measurement instrument, not the artifact.
- `calib: good=<f> bad=<f>` (R15, judged ACs only) names a known-good and a
  known-bad fixture of the AC's subject. The claim is refused until
  `AC-N#good` = PASS and `AC-N#bad` = FAIL are bound at the current
  iteration+digest (derived-id rows in verdicts.rec), and the row's evidence
  must QUOTE the fixture file it read (an unbound grade is an invented grade).
  R9 extended from the numeric plane to the judgment plane: a seat that cannot
  reject the known-bad case cannot be trusted on the real one. Fixtures exist
  in the tree (stamp validates), fixture decay mid-loop = `calibration-broken`
  (fail-closed, never a silent exemption).
- stderr is captured to the verdict detail (stdout stays the measurement
  channel); a FAIL/BROKEN that says only "failed" is the eval system
  violating fail-loud.
- Optional contract line `objective: maximize|minimize AC-N` (R11): the gate tracks
  that AC's observed value against `best_score` and refuses a claim that
  regresses. Stamp still covers only the AC body + `exit:` lines.
- Stamp `^approved: [0-9a-f]{8} [0-9]{4}-` = sha1-8 over the AC section body
  PLUS every `^exit:` and `^objective:` line (exit policy and maximize
  target are frozen too - R11 is unpatchable after stamping).
  Direction comes from the objective line; changing it is contract-tampered.

## 2 Digest + mutation guard

12-hex over git HEAD+porcelain (or cksum list outside git), excluding
`.goal/ .git/`. Evidence dir `.goal/evidence/` is digest-excluded. The gate
fingerprints before/after every rerun batch: a moved digest = a check
mutated the tree -> NO-GO.
The tree digest is blind to `.goal/`, so the ledger gets its own before/after
digest (`ledger_digest`, over goal.md/state.rec/loop-log.md/verdicts.rec/
scores.rec/work-plan.md/baseline.md/interfaces.md) - a check that rewrites
the contract or a state file mid-rerun trips `check-mutated-ledger`; only
`.goal/evidence/` is fair game for checks (R6).

## 3 Check order (first failure decides)

```
0  state.rec keys complete                    else 4
0b forge: dry_streak/dry_limit present        else 4
1  stamp matches recomputed hash              else 2 contract-tampered [R3]
2  breaker OPEN / false_completes>=2          else 3
2c deadline passed (time_budget>0)            flag only: green claim still GO
                                               (NOTE); any fail() -> 3 fuse
3  iteration <= max_iterations                else 2 (forge: 3 budget-fuse)
4  no_progress_streak <= limit                else 3 stagnation
4b last two blocks same error_signature       else 3 repeated-error
5  last block exit_signal=yes                 else 2 not-claimed
6  block digest == current digest             else 2 verdicts-stale [R7]
   (ctl counts the false complete automatically - the ratchet is mechanical)
6b every AC line has expected: and check:     else 4 contract-malformed
7  per AC: probe (R9) then deterministic      FAIL 2 open-FAIL / BROKEN 2
     judged -> stored verdict fresh+non-FAIL  else 2 not-covered/open-FAIL [R7]
8  judged PASS evidence cited AND artifact    else 2 evidence-missing /
   digest recomputes same                     verdict-unbound [R5]
8b calib: fixtures graded both ways fresh     else 2 calibration-missing /
                                               calibration-broken [R15]
9  judged UNVERIFIABLE *3 <= total            else 2 unverifiable-excessive [R4]
10 digest unchanged after rerun batch         else 2 check-mutated-tree
11 forge: dry_streak >= dry_limit             else 2 not-dry
12 breaker=HALF_OPEN: strategy_delta set      else 2 missing-strategy-delta [R10]
13 objective score vs best_score by direction else 2 score-regressed [R11]
   (tolerance: absorbs noise inside the band)
14 score<->judge direction on last 2 points  else 2 DIVERGENCE:score-vs-judge [R13]
   advisory NOTEs on GO: tautology-suspect / metric-flat (never block)
GO -> "GATE: GO ... mode=<m> [score=<s> best=<b>]"
```

## 4 Rules

- **R1** false-complete: claimed exit honored only with all floors verified
  AND exit_signal=yes AND digest match (forge: also dry). Two gate-caught
  false claims -> BLOCKED. The counting is MECHANICAL: close-iteration with
  exit-signal=yes that the gate answers rc=2 auto-increments
  false_completes (NOTE `false-complete-counted=N`) - the controller no
  longer has to append the count by hand.
- **R2** seat re-judgment illegal while covered files unchanged; gate
  re-runs are measurement, always legal.
- **R3** stamped contract frozen (AC body + `exit:` lines); amendments are
  proposals to the user.
- **R4** judged UNVERIFIABLE <= 1/3, always PROBE/REASON.
- **R5** judged briefs carry verbatim AC text + evidence paths only; no
  producer reasoning; verdicts without observation are void.
- **R6** workers never WRITE `.goal/`; only goal_ctl.sh writes state. Reads
  are limited to the worker's own inbox file and files its brief explicitly
  names - nothing else under `.goal/` (ledger, verdicts, other inboxes).
- **R7** judged verdicts bind (iter, digest); digest move voids all judged
  verdicts, no sharding. Deterministic exempt (gate recomputes).
- **R8** findings bind evidence - manufactured discoveries as forbidden as
  manufactured passes.
- **R9** verify the verifier: metric/maximize/minimize numbers require a passing
  `probe:` (instrument alive). An unprobed metric is a Goodhart magnet.
- **R10** no-progress must be paired with `strategy_delta=` (what changes
  next). Grinding without revising is make-work.
- **R11** objective score never delivers worse than `best_score`
  (maximize: current >= best; minimize: current <= best) - restore
  the best-scoring state or do not claim. `tolerance:` widens the comparison
  by a relative band so benchmark noise is "holds", not "regressed". The band
  is computed from `|best|*tol` so it survives NEGATIVE water marks (a
  multiply-by-(1-tol) flips the band when best<0).
- **R14** measurement honesty (v2.5): metric regex pins the number, ANSI is
  stripped before matching, stderr rides along in verdicts (fail-loud),
  judged PASS must bind its artifact hash, and deterministic checks that
  cannot fail across rounds get flagged `tautology-suspect` (advisory).
- **R15** judge calibration (v2.6, `calib:` fixtures on judged ACs): the
  verifier-of-the-verifier rule (R9) extended to the judgment plane. A judged
  AC that names `good=`/`bad=` fixtures owes correct grades on both in the
  current iteration - mechanically checked from derived-id rows in
  `verdicts.rec`. A too-lenient seat passes `#good` and FAILS `#bad`, and the
  claim is refused `calibration-missing:*/*`; declared-but-missing fixtures
  are `calibration-broken` (fail-closed). Stamp refuses calib on non-judged
  ACs, one-sided declarations, and missing fixture files (t=0 exposure).
- **R13** score/judge divergence: when .goal/scores.rec holds two comparable
  points (iter|score|judge both numeric) and their directions oppose, the
  objective is optimizing away from perceived quality - refuse the claim.
  Flat movement is unverified, not divergence. Fewer than two points = skip.
- **R12** controller self-audit: before claiming exit run
  `scripts/goal_audit.sh` (task= schema, fallback suffixes, no silent
  downgrade, strategy_delta honesty). rc!=0 blocks the claim. The gate
  judges the artifact; the audit judges the controller.

## 5 Breaker

CLOSED -> HALF_OPEN (any progress=no: change strategy) -> OPEN (beyond, or
false_completes>=2) -> BLOCKED. progress=yes resets. Every HALF_OPEN
landing owes a `strategy_delta` (R10).
