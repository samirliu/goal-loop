# Gate - schemas, check order, rules (the only completion authority)

Read before every gate decision. The gate decides; the controller
bookkeeps via goal_ctl.sh. Scripts: `scripts/goal_gate.sh` (`--check`,
`--digest`, `--verify [AC-ID]`, `--baseline-check`).

## 1 Schemas

`.goal/state.rec` keys: iteration breaker(CLOSED|HALF_OPEN|OPEN)
false_completes replans no_progress_streak last_progress_iteration
max_iterations no_progress_limit max_replans per_check_fail_cap panel_max
dry_streak dry_limit check_timeout time_budget deadline.
`dry_streak/dry_limit` required only for `exit: forge`.

`.goal/loop-log.md` append-only blocks, exact keys:
`## iteration N` + task files_modified checks_pass checks_fail
checks_unverifiable error_signature progress exit_signal false_complete
digest. `task=T2[crew:3]` marks a crew wave.

`.goal/verdicts.rec` 6 fields: `id|verdict|iter|digest|command|evidence`.
Deterministic ACs: records are bookkeeping; the gate's rerun is the
evidence. Judged ACs: PASS needs the quoted decisive output; UNVERIFIABLE
needs `PROBE=.. REASON=..`; empty evidence voids a PASS.

`.goal/goal.md` AC grammar:
`- AC-N | <statement> | check: \`<command>\` | [baseline: delta|abs] | expected: <spec>`
- `exit=0`/omitted -> deterministic rc check; `<op><number>` (>= <= > < == !=)
  -> metric, LAST non-empty stdout line must be the number; `judged` -> seat
  verdict digest-bound; prose (v1.1) -> judged. Spec value must not contain
  `|`; exact-text compare goes INSIDE the command.
- Stamp `^approved: [0-9a-f]{8} [0-9]{4}-` = sha1-8 over the AC section body
  PLUS every `^exit:` line (exit policy is frozen too).

## 2 Digest + mutation guard

12-hex over git HEAD+porcelain (or cksum list outside git), excluding
`.goal/ .git/`. Evidence dir `.goal/evidence/` is digest-excluded. The gate
fingerprints before/after every rerun batch: a moved digest = a check
mutated the tree -> NO-GO.

## 3 Check order (first failure decides)

```
0  state.rec keys complete                    else 4
0b forge: dry_streak/dry_limit present        else 4
1  stamp matches recomputed hash              else 2 contract-tampered [R3]
2  breaker OPEN / false_completes>=2          else 3
2c deadline passed (time_budget>0)            else 3 time-budget-exhausted
3  iteration <= max_iterations                else 2 (forge: 3 budget-fuse)
4  no_progress_streak <= limit                else 3 stagnation
4b last two blocks same error_signature       else 3 repeated-error
5  last block exit_signal=yes                 else 2 not-claimed
6  block digest == current digest             else 2 verdicts-stale [R7]
7  per AC: deterministic -> gate reruns NOW   FAIL 2 open-FAIL / BROKEN 2
     judged -> stored verdict fresh+non-FAIL  else 2 not-covered/open-FAIL [R7]
8  judged PASS has quoted evidence            else 2 evidence-missing [R5]
9  judged UNVERIFIABLE *3 <= total            else 2 unverifiable-excessive [R4]
10 digest unchanged after rerun batch         else 2 check-mutated-tree
11 forge: dry_streak >= dry_limit             else 2 not-dry
GO -> "GATE: GO digest=<d> iter=<n> ac=<t> pass=<p> unverified=<u> mode=<m>"
```

## 4 Rules

- **R1** false-complete: claimed exit honored only with all floors verified
  AND exit_signal=yes AND digest match (forge: also dry). Two gate-caught
  false claims -> BLOCKED.
- **R2** seat re-judgment illegal while covered files unchanged; gate
  re-runs are measurement, always legal.
- **R3** stamped contract frozen (AC body + `exit:` lines); amendments are
  proposals to the user.
- **R4** judged UNVERIFIABLE <= 1/3, always PROBE/REASON.
- **R5** judged briefs carry verbatim AC text + evidence paths only; no
  producer reasoning; verdicts without observation are void.
- **R6** workers never touch `.goal/`; only goal_ctl.sh writes state.
- **R7** judged verdicts bind (iter, digest); digest move voids all judged
  verdicts, no sharding. Deterministic exempt (gate recomputes).
- **R8** findings bind evidence - manufactured discoveries as forbidden as
  manufactured passes.

## 5 Breaker

CLOSED -> HALF_OPEN (streak==limit: change strategy) -> OPEN (beyond, or
false_completes>=2) -> BLOCKED. progress=yes resets.
