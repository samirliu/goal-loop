# Gate - schemas, check order, rules (the only completion authority)

Read before every gate decision. The gate decides; the controller
bookkeeps via goal_ctl.sh. Scripts: `scripts/goal_gate.sh` (`--check`,
`--digest`, `--verify [AC-ID]`, `--baseline-check`).

For a retryable close, choose and record `--operation-id ID` before the first
call. Reuse the ID and original arguments on retry; IDs are project-local
ASCII tokens, 1–128 characters, starting with a letter/digit and containing
letters/digits/`._-`. Omitting it generates a new ID for each call. A repeated
committed ID returns its historical result without rerunning checks or
consuming another iteration; changed arguments are refused. `CTL: REPLAY`
does not establish current GO: run the gate again before delivery. Argument
order and explicit defaults count as request changes (project and ID are
excluded from the request hash).

The context map can compile this exact call from authored JSON inputs. New
close journals (version 6; existing mutation/checkpoint versions unchanged)
and close commit metadata (version 2) retain the original argv and verify it
against the same operation/intent hash. Legacy journals remain readable; they
cannot invent missing original arguments. Recovery and REPLAY keep their
existing semantics and never replace a fresh Gate decision.

If `recovery-required` appears, run `goal_ctl.sh recover --project DIR` first.
It rolls back a close interrupted before its atomic commit pointer, or restores
the committed snapshot after that point, without replaying tools. A journal
whose baseline/operation conflicts with the current commit is refused. Keep
the journal for diagnosis; never clear it merely to make a gate run.

Readers now verify managed text views against the immutable commit snapshot.
`ledger-view-mismatch` also requires controller recovery, even without pending.
For an older unversioned ledger, use `goal_ctl.sh migrate --project DIR` after
`ledger-migration-required`; migration refuses contradictory history. Do not
use migration to bless edits to an already versioned ledger. Author the goal
and work-plan through the existing workflow; state/log/scores, verdicts, frozen
checker records and managed raw receipts are controller projections.

## 1 Schemas

`.goal/state.rec` keys: iteration breaker(CLOSED|HALF_OPEN|OPEN)
false_completes replans no_progress_streak last_progress_iteration
max_iterations no_progress_limit max_replans per_check_fail_cap panel_max
dry_streak dry_limit check_timeout time_budget deadline best_score.
Objective records also carry best_score_basis, last_quality_score and
last_quality_judge. Raw failed attempts remain in scores.rec.
`dry_streak/dry_limit` required only for `exit: forge`.
Budget knobs written in goal.md (max_iterations, dry_limit, check_timeout,
wallclock, ...) BIND at stamp - goal_ctl.sh stamp copies them into state.rec.
`best_score` is the water mark for `objective: maximize|minimize AC-N` (R11) -
high-water for maximize, low-water for minimize.

`.goal/scores.rec` 4 fields: `iter|score|judge|strategy` (v2.9; rows written
before v2.9 carry 3 fields and every reader is field-indexed, so both shapes
parse). The strategy column is what per-strategy attribution (SKILL.md
Step 4) reads; objective contracts must label every wave (writer tooth, R17).
`.goal/evidence/deferred.rec` 4 fields: `id|verdict|tstamp|detail` - the
external-check cache (R18): append-only, latest-per-id wins by (tstamp,
file order). Evidence lives under `.goal/evidence/`: exempt from BOTH
digests, which is what lets a gate rerun batch write measurement cache
without tripping check-mutated-ledger (R6-fair).
`.goal/loop-log.md` append-only blocks, exact keys:
`## iteration N` + task files_modified checks_pass checks_fail
checks_unverifiable error_signature progress exit_signal false_complete
digest score strategy_delta. `task=T2[crew:N]` marks a one-shot crew wave
(N = actual concurrent workers in that wave). The task id may carry ONE
trailing suffix from the closed vocabulary in crew.md §3.5
(`(fallback:provider-fatal)`, `(stall-recovered)`, `(tool-error-fixed)`,
`(re-run:stall|tool-error|death)`); the suffix is DERIVED by ctl from a
declared worker fault (`--fault CLASS --fault-outcome OUTCOME`) and is never
self-declared: a suffix with no fault row is refused at write time and
flagged by audit A11, and a fault row with no block is flagged too.
`.goal/evidence/faults.rec` holds the fault rows — `task|class|suffix|note|ts`
— and is exempt from both digests (evidence sidecar).
Bare `T<n>` normalizes to `T<n>[crew:1]` at write; free-form task ids are
refused by ctl (R12/A1 is enforced by the writer, not only by the audit).
`score=` holds the objective value or `none`; `strategy_delta=`
is mandatory whenever `progress=no` (R10). Optional v2.8 key `strategy=<label>`
(the wave's attack direction, one word; folded single-line exactly like
`strategy_delta`, default `none` when `close-iteration --strategy` was not
given). It is deliberately NOT in the gate's advisory key list - legacy
ledgers must read silent. `status` uses it for per-strategy score attribution
(efficiency windows over `scores.rec`; see SKILL.md Step 4).

`.goal/verdicts.rec` 6 fields: `id|verdict|iter|digest|command|evidence`.
Deterministic ACs: records are bookkeeping; the gate's rerun is the
evidence. Judged ACs: PASS needs the quoted decisive output PLUS an
`artifact: <path> digest: <sha256>` binding - the gate recomputes the
sha256 of that path and voids the verdict on mismatch (`verdict-unbound`);
UNVERIFIABLE needs `PROBE=.. REASON=..`; empty evidence voids a PASS.
Two rows for one id at the SAME (iter,digest) that DISAGREE are a mechanical
contradiction - the claim is refused `verdict-conflict` (R2 makes re-judging
illegal while the files are unchanged, so a disagreeing pair means the judge
plane contradicts itself on one bound state). A same-verdict rebind is legal:
the later row wins by ledger order (v2.7; pre-v2.7 the winner was gawk hash
order and therefore nondeterministic).
Calibration rows share the same 6-field schema under derived ids: `AC-1#good`
and `AC-1#bad` - the seat's grades on the declared fixtures (see `calib:`
below). Derived ids count as ordinary rows for bind/stale rules: a digest
move or iteration bump voids them exactly like the parent verdict.
Orphan rows (ids absent from the contract) are ignored by `--check` and
caught by `--verify` as `unknown-ac-id` (by design: the gate measures the
contract, not the ledger).

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
- `external: \`<command>\`` (v2.9, R18) settles the AC against an OUT-OF-TREE
  source (a CRM, prod metrics, an async reviewer). It is ADDITIVE: the in-tree
  `check:` floor still runs and a floor FAIL/BROKEN is decisive - "something is
  still pending" never masks a failure. rc=75 means "not ready yet" -> the AC
  settles DEFERRED (wait, not deliver). `window: <seconds>` (default 3600) is
  the cache validity: inside it the recorded verdict in `deferred.rec` IS the
  measurement, so a day-to-settle fact costs one query per window, not one per
  gate exit. `window:` without `external:` is refused at stamp (window caches
  an out-of-tree check - declare both or neither).
- `sd: \`regex one capture group\`` / `var: \`regex\`` (v2.9, R17) extract the
  measurement's spread (stddev / variance, sqrt'd) from the check output. With
  a spread the R11 water-mark band is `max(2*spread/|best|, tolerance)` - the
  noise floor comes from data, not from the author's memory. Declared-but-
  non-matching = BROKEN (fail-loud), never a silently band-less compare.
- stderr is captured to the verdict detail (stdout stays the measurement
  channel); a FAIL/BROKEN that says only "failed" is the eval system
  violating fail-loud.
- Optional contract line `objective: maximize|minimize AC-N` (R11): the gate tracks
  that AC's observed value against `best_score` and refuses a claim that
  regresses. Stamp still covers only the AC body + `exit:`/`objective:`/
  `horizon-waived:` lines.
- Optional contract line `horizon-waived: <reason>` (v2.9, R19): declares that
  the objective's blind spot is accepted. An objective contract needs either
  >=1 judged AC with `calib:` (the horizon layer) or this waiver - otherwise
  stamp refuses (a gradient without a guard-rail is a Goodhart machine).
- Stamp `^approved: [0-9a-f]{8} [0-9]{4}-` = sha1-8 over the AC section body
  PLUS every `^exit:`, `^objective:` and `^horizon-waived:` line (exit policy,
  maximize target and horizon waiver are frozen too - R11/R19 are unpatchable
  after stamping). Direction comes from the objective line; changing it is
  contract-tampered.

## 2 Digest + mutation guard

Worktrees use a `v2-` SHA-256 digest over NUL-delimited path, type, mode and
content records. Existing verdicts bound to the old identity become stale and
must be rechecked. Git includes tracked and non-ignored untracked files; ignored
untracked files are excluded. Non-Git projects retain `.goalignore` and
`GOAL_PRUNE` directory pruning. To bind an excluded deliverable, put
``| watch: `build/output file` `` before `expected:` on its AC line. Multiple
watch fields are allowed. A watched directory is recursive, including empty
directories; a missing path is bound as missing. Paths are project-relative,
cannot escape or pass through symlink parents, and cannot name `.goal`/`.git`.
Symlinks bind the link itself, not the target contents. Explicit scopes are
part of the frozen AC; the author must identify all excluded deliverables.
Both modes exclude `.goal/` and `.git/`.
On supported POSIX systems Python 3 provides an optional single-process digest
accelerator; otherwise the shell implementation is used. The two backends use
the same records and identity. A runtime hashing failure is never retried as a
successful fallback. `tests/benchmark_tree_digest.py` compares both paths; it
is a local diagnostic, not a task-level efficiency benchmark.
Legacy digest migration reports `digest-version-mismatch` and routes to fresh
bookkeeping/evidence; the controller does not count this version change as a
false completion. The approved AC itself is not re-stamped.
Evidence dir `.goal/evidence/` is digest-excluded. The gate
fingerprints before/after every rerun batch: a moved digest = a check
mutated the tree -> NO-GO.
The tree digest is blind to `.goal/`, so the ledger gets its own before/after
digest (`ledger_digest`, over goal.md/state.rec/loop-log.md/verdicts.rec/
scores.rec/work-plan.md/baseline.md/interfaces.md/runner.deadline/runner.clock/runner.json) - a check that rewrites
the contract or a state file mid-rerun trips `check-mutated-ledger`; only
`.goal/evidence/` is fair game for checks (R6). Peer-notes (v2.8 protocol,
see crew.md §4) live under `.goal/evidence/peer-notes/` - invisible to both
digests by construction.

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
1b check/probe script bodies match stamp freeze else 2 check-script-tampered
5  last block exit_signal=yes                 else 2 not-claimed
5c adversarial.rec clear@ (iter,digest)      else 2 adversarial-missing /
                                            adversarial-finding
5d evidence/raw/<iter>.txt non-empty         else 2 raw-evidence-missing
5b claiming block task= is a valid ledger id  else 2 bad-task [R12 tooth at
   (bare T<n] = v1.x read-compat, NOTE only)      the arbiter; ctl still
                                                  enforces it at write time]
5b2 work-plan has no unticked item at claim     else 2 open-items (a dropped
   (owed work cannot be claimed away)             worker leaves its item open)
6  block digest == current digest             else 2 verdicts-stale [R7]
   (ctl counts the false complete automatically - the ratchet is mechanical)
6b every AC line has expected: and check:     else 4 contract-malformed
7  per AC: external settle (R18) + probe (R9)  FAIL 2 open-FAIL / BROKEN 2
     then deterministic; judged -> stored      DEFERRED 2 deferred-pending
     verdict fresh+non-FAIL                   else 2 not-covered/open-FAIL [R7]
7b same-(iter,digest) verdict pair disagrees  else 2 verdict-conflict [R16]
   (latest wins only when identical; disagreement = R2 was violated)
8  judged PASS evidence cited AND artifact    else 2 evidence-missing /
   digest recomputes same                     verdict-unbound [R5]
8b calib: fixtures graded both ways fresh     else 2 calibration-missing /
   + EXCLUSIVE fixture citation per grade     calibration-broken [R15]
8c judged PASS claims judge=N when the ledger  else 2 judge-score-missing
   already records judge scores                 (NOTE once when it never
                                                used the judge plane)
9  judged UNVERIFIABLE *3 <= total            else 2 unverifiable-excessive [R4]
10 digest unchanged after rerun batch         else 2 check-mutated-tree
11 forge: dry_streak >= dry_limit             else 2 not-dry
   + last K canonical raw records contain complete executed scope and bound
     empty critic conclusions                 else 2 forge-coverage-unverified
12 breaker=HALF_OPEN: strategy_delta set      else 2 missing-strategy-delta [R10]
13 objective score vs best_score by direction else 2 score-regressed [R11]
   (band = sd/var spread z2 or tolerance, wider wins; noise inside = holds)
14 score<->judge direction on last 2 points  else 2 DIVERGENCE:score-vs-judge [R13]
   advisory NOTEs on GO: tautology-suspect / metric-flat (never block)
GO -> "GATE: GO ... mode=<m> [score=<s> best=<b>]"
```

`--checkpoint` qualifies the latest booked artifact for a reversible trial.
It requires all ACs verified within the active budget and retains the frozen
contract, calibration, adversarial evidence, and water-mark checks. Remaining
work items, dry rounds, and a final claim are delivery conditions. The
checkpoint receipt says `CHECKPOINT-OK`. See the [restore procedure](../docs/transaction-state.md#accepted-artifact-checkpoints).

## 4 Invariants + legacy index

The always-on law is **five invariants**. Depth lives in `references/packs/README.md` (instrument / gradient / external).
Check order (§3) is the mechanical statute; this section is the map.

### 4.1 Invariant map

| Invariant | One sentence | Enforced by (check order / surface) | Depth |
|---|---|---|---|
| **GATE** | Completion is declared only by the gate re-run; the model never self-declares. | whole check order; false-complete ratchet (§4.2 R1) | SKILL.md |
| **BIND** | Every claim binds (stamped-contract × iteration × digest × evidence-hash); unbound claims are void. | 1, 3, 5b, 6, 7b, 8, 14 | packs/instrument.md |
| **PROVE** | An instrument must prove itself before its number or verdict is trusted. | 7 (probe), 8 (calib), 14 (measurement) | packs/instrument.md |
| **GRADIENT** | Optimization never delivers below the water mark; blind spots are declared; waves are labeled. | 12–14; stamp `objective:` / `horizon-waived:` | packs/gradient.md |
| **FENCE** | Ledger write-fence, honest progress, controller self-audit; out-of-tree facts settle via cache. | 5b, 5b2, 11–12; `external:` / DEFERRED | packs/external.md + goal_audit.sh |

### 4.2 Legacy index (R1–R19)

Stable IDs for docs/tests anchors. Each line is an **instance** of an invariant, not a separate law.

- **R1** false-complete ratchet → **GATE**. Claimed exit honored only with floors verified ∧ `exit_signal=yes` ∧ digest match (forge: also dry). Two gate-caught false claims → BLOCKED. Counting is mechanical (`false-complete-counted=N`). Exemption: `deferred-pending:*` is not counted (patience ≠ lie; NOTE `deferred-wait-not-counted`).
- **R2** seat re-judgment illegal while covered files unchanged; gate re-runs are measurement, always legal → **BIND**.
- **R3** stamped contract frozen (AC body + `exit:` / `objective:` / `horizon-waived:` lines); amendments are proposals to the user → **BIND**.
- **R4** judged UNVERIFIABLE ≤ 1/3, always PROBE/REASON → **FENCE** (process confidence ceiling).
- **R5** judged briefs carry verbatim AC text + evidence paths only; no producer reasoning; verdicts without observation are void → **BIND** / **PROVE**.
- **R6** workers never WRITE `.goal/`; only `goal_ctl.sh` writes state. Reads limited to own inbox + brief-named files. Exception: APPEND ≤1 line/iteration to `.goal/evidence/peer-notes/<task>.md` (evidence dir is digest-exempt) → **FENCE**.
- **R7** judged verdicts bind (iter, digest); digest move voids all judged verdicts, no sharding. Deterministic exempt (gate recomputes) → **BIND**.
- **R8** findings bind evidence — manufactured discoveries as forbidden as manufactured passes → **BIND**.
- **R9** verify the verifier: metric/maximize/minimize numbers require a passing `probe:` → **PROVE**.
- **R10** no-progress must be paired with `strategy_delta=` (what changes next) → **FENCE** / **GRADIENT**.
- **R11** objective score never delivers worse than `best_score` (direction-aware; tolerance band; band = `|best|*tol` so it survives NEGATIVE water marks) → **GRADIENT**.
- **R12** controller self-audit (`goal_audit.sh`) before claim; gate judges artifacts, audit judges the controller → **FENCE**.
- **R13** score↔judge direction oppose on last two comparable points → `DIVERGENCE:score-vs-judge`; flat is unverified → **GRADIENT**.
- **R14** measurement honesty: metric regex pins the number, ANSI stripped, stderr in verdicts, judged PASS binds artifact hash, tautology-suspect advisory → **PROVE** / **BIND**.
- **R15** judge calibration (`calib: good= bad=`): seat must PASS #good ∧ FAIL #bad this iteration; missing = `calibration-missing` / `calibration-broken` → **PROVE**.
- **R16** verdict-conflict: two rows one id at same (iter,digest) with different verdicts = refuse claim; same-verdict rebind legal (latest wins) → **BIND**.
- **R17** significance + attribution: (a) water-mark band from `sd:`/`var:` data (z=2) wider-of with tolerance, declared-but-silent = BROKEN; (b) objective contracts require `--strategy` at close (writer tooth) → **PROVE** (a) / **GRADIENT** (b).
- **R18** external/deferred settle: `external:` additive to in-tree floor; rc=75 → DEFERRED; `window:` cache in `deferred.rec`; never deliver on pending → **FENCE** / **BIND**. Detail: `references/packs/external.md`.
- **R19** horizon hard constraint: objective contracts declare judged+calib layer or `horizon-waived: <reason>` (stamp-frozen) → **GRADIENT**.

Depth documents: `references/packs/instrument.md` · `gradient.md` · `external.md`. Crew protocol: `references/crew.md`. Check shapes: `references/patterns.md`.
## 5 Breaker

CLOSED -> HALF_OPEN (any progress=no: change strategy) -> OPEN (beyond, or
false_completes>=2) -> BLOCKED. progress=yes resets. Every HALF_OPEN
landing owes a `strategy_delta` (R10).
