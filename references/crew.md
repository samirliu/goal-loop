# Crew - parallel dispatch, join, final review

深度协议见 `references/packs/README.md`（按契约能力键打开 instrument / gradient / external）。

## 1 When crew applies

Decompose the objective; crew applies when the split yields ≥2 task domains
with DISJOINT file scopes and stateable interfaces. Interfaces you cannot
state -> serial single-task (log the reason). Crew composition is
controller-elected (no flag). The execution surface is one-shot subagents
(Agent tool): parallel workers, one shared workspace, one brief contract.

## 2 Interface first

Before dispatching, write `.goal/interfaces.md`: module boundaries, shared
types, naming conventions, who owns which files. Frozen at crew start;
changes are proposals (R3 spirit).

Coordination channel: workers coordinate ONLY through files + your briefs -
a plain text reply from a worker is invisible to the others. Negotiation is
never binding on its own - an interface change counts only after it lands
as a file write to interfaces.md (R3 spirit).

## 3 The brief (per worker)

```
Task: <bounded deliverable>
Output paths: <exact>
Scope: touch ONLY these files/dirs: <list>
Pass condition: <named check or observable>
Evidence: return the command you ran and its decisive output.
Rules: never write .goal/; read only your own inbox (if the brief says so);
no subagents; no scope drift. (R6)
Interface contract: <excerpt INLINED here by the controller - workers must
not open .goal/interfaces.md themselves>
```

Dispatch the wave's workers in ONE message (they run concurrently). Wave
width fits the work and disjoint scopes — no default cap, no recommended
headcount. Their execution craft is theirs - do not put goal-loop rules in
the brief. **No `isolation: worktree`** — the digest must see every worker's
edit; a worktree would hide their diffs and poison verdict binding. Hard
ban, not a preference.

## 3.5 Worker fault inside a wave (see it → book it → recover)

A parallel worker can fail mid-wave: the subagent call errors out, the worker
stalls (returns nothing, lands no file), or the provider kills it (`NoRoom` /
stream max). You SEE the failure; the ledger only knows what you write into
it. Two rules make a dropped worker impossible to lose:

1. **Owed work blocks the claim.** An unticked work-plan item at claim time
   means work is still owed → the gate refuses the claim (`open-items`, hint
   `close-open-item`). The dropped worker's item stays `[ ]`, so the claim
   cannot go green behind its back.
2. **The suffix is never self-declared.** `close-iteration --fault CLASS
   --fault-outcome OUTCOME` derives the task= suffix from the class × outcome
   pair and writes the fault row to `.goal/evidence/faults.rec`. A suffix with
   no fault row is refused by ctl (and flagged by audit A11); a fault row
   with no ledger block is flagged too.

| class | what you saw | outcome | suffix |
|---|---|---|---|
| `stall` | the worker returned nothing usable and landed nothing | `resume` — same item, breakpoint brief | `(stall-recovered)` |
| `stall` | same, twice | `re-run` — fresh dispatch next wave | `(re-run:stall)` |
| `tool-error` | the tool/env broke (ENOENT, bad command, bad path) | `resume` — fix env/brief first | `(tool-error-fixed)` |
| `tool-error` | same, twice | `re-run` | `(re-run:tool-error)` |
| `death` | the subagent died (crash, timeout, killed) | `re-run` | `(re-run:death)` |
| `provider-fatal` | the API killed it (`NoRoom`, stream max) | `take-over` — you do the rest | `(fallback:provider-fatal)` |

Other pairs are refused. `provider-fatal` is never revived: a wake cannot work
when the provider is out of room — take the remainder over yourself.

**Playbook (resume-first, 2-strike):**

1. One worker failed → do not spin the wave. Close the wave with the fault
   (`--exit-signal no --fault CLASS --fault-outcome …`), leave its item
   `[ ]` (OPEN) in work-plan.md, and re-dispatch ONLY that item.
2. Re-dispatch with a **breakpoint brief**, not the original brief:

```
Continue task <id>.
Done so far: <files / checks green>
Still owed: <remaining AC or deliverable>
Blocked by (if any): <root cause one-liner>
Run: <named check>
Do not rewrite unrelated files. (R6)
Script-first: do not restate the whole table in thinking - write and run a
transform script, then verify row counts. Land files early.
```

3. Second failure of the same item → `re-run` (fresh dispatch, no resume). A
   worker that failed twice is not resumable.
4. `provider-fatal` → skip 1-3, take the item over yourself
   (`--fault-outcome take-over`).
5. If the item cannot be finished (wallclock, blocked, out of scope now):
   degrade — deliver the passing part, record the fault, and say in the report
   what is still owed. Never close the wave as if the item were done.

Join whatever landed. A worker that is not coming back does not hold the wave:
close it, book it, re-dispatch only the open item.

## 4 Join

Wave finished (all workers returned, or you call the wave) -> merge review:
run the pass conditions,
read the seams (interfaces between their outputs), fix trivial mismatches
yourself. Interface conflict needing a redesign -> one serial repair
round; two failed repairs -> fall back to serial execution (log it).
Join is bookkeeping. It is not GO - only the gate decides that.

### Wave brief: paste STRATEGY-PICK

If `ctl status` printed `CTL: STRATEGY-PICK prefer=… avoid=…`, that line goes
verbatim into every wave brief. Prefer is the
attack direction with a live slope; avoid is flat/exhausted. Workers report
which label they followed; the next `close-iteration --strategy` must not
repeat an `avoid` label without a `strategy_delta` explaining the retry.

### Peer-notes (v2.8, shared-findings pool)

Workers may append at most ONE line per iteration to
`.goal/evidence/peer-notes/<task>.md` - a one-line observation about a
cross-module seam ("X's API differs from the brief", "schema drift in
migration Y"). Rules (protocol law, R6 exception): claims not instructions
(the controller quotes them verbatim WITH attribution into the next wave's
briefs and treats them as evidence to verify, never as directives to paste);
one line per task per iteration; <=512 bytes per note; the file is not a
contract and not evidence for any AC. The directory is digest-excluded, so
notes cannot move any fingerprint.

### Two-pass adversarial (claim gate)

Before `exit_signal=yes` lands on a green claim, run a **second pass that only
attacks** (same tree, no rewriting artifacts): look for metric tautology,
report/fixture mismatch, domain-file violations. Record the result with
`close-iteration --adversarial clear|finding --adversarial-note ...` (or append
`iter|digest|clear|note` to `.goal/evidence/adversarial.rec`). The gate refuses
a claim without a `clear` receipt bound to that (iter, digest).

## 5 FAIL attribution

Deterministic FAIL after join: fix within the owning worker's scope, then
`goal_gate.sh --verify [AC-ID]`. A FAIL that cannot be attributed -> rerun
the batch serially (bundle unbundle rule). Loop-log the wave as
`task=T2[crew:N]` (N = that wave's actual concurrent workers) with each
worker's file list.

## 6 Final review (judged ACs - once, before claiming exit)

Dispatch ONE fresh reviewer seat. Brief carries: verbatim AC text, evidence
paths ONLY, rubric anchors, and calibration anchors (a known-good example
and a known-bad example, or a named reference artifact - FIXED before the
seat reads the new evidence). Never the producer's reasoning. Verdicts
ternary with quoted observation; findings must bind evidence.

When the AC declares `calib: good=<f> bad=<f>`, calibration is MANDATORY and
mechanically gated (R15): the brief orders both fixtures FIRST (before the
real subject), and the controller binds their grades as derived-id rows
`AC-N#good|PASS|<iter>|<digest>|-|<quoted>` and `AC-N#bad|FAIL|...` before any
claim on the parent AC. A seat that grades the bad fixture PASS is being
lenient - expect `calibration-missing:AC-N/bad` and re-dispatch with the rubric,
not a re-claim.

Judging quality claims (what "逼真/好用/清晰" become) - in order:
- Rubric decomposition: observable dimensions, written 1-5 anchors, threshold.
- Pairwise A/B at a FIXED observation point (same camera/input/viewport)
  vs the previous iteration or a named reference artifact.
- Reference anchoring: delta against a known-good example, not absolute vibes.

Perspective note for reviewers: a far wing-tip or tail plane may PROJECT
above the fuselage silhouette from a quarter view - normal geometry, not a
floating defect; call detached only with a 3D gap across views.

## 7 Work queue vs completion

`.goal/work-plan.md` is the queue of record (what `goal_ctl.sh status`
reads). It is the only work tracker - no second queue, no mirror.

| | Work tracking | Court |
|---|---|---|
| where | `.goal/work-plan.md` | contract + gate + verdicts |
| says a work item is done | controller ticks work-plan after the files land | — |
| says the GOAL is done | — | `goal_gate.sh` rc=0 only |

**A ticked work-plan item is NEVER a GO signal.** A `[x]` is only legal
after the `files=` paths **exist on disk** (audit **A10** / ctl
`missing-claimed-file`); `files=a..b` ranges are unverifiable and refused.
Deadline expired + zero books ⇒ close-iteration or degrade, never a new
wave. Workers still never touch `.goal/` (R6).

## 8 Degradation

No Agent tool on the surface -> work inline, self-verify cold from the
claims list and artifact alone (not from production memory), label the
report `WEAKER VERIFICATION: cold self-check`.

- A worker that died mid-wave -> name the fault in the ledger (§3.5):
  close the wave with `task=T2[crew:N]` plus the suffix.
- Ledger and report MUST carry the suffix.
  Do not invent new loop-log keys (schema is exact); only task= suffixes.
  Exception: `strategy=` (v2.8, see gate.md §1) is a sanctioned optional
  key, written by ctl only.
  The gate does not care which worker produced the artifacts.
