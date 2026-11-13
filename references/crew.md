# Crew - parallel dispatch, join, final review

深度协议见 `references/packs/README.md`（按契约能力键打开 instrument / gradient / external）。

## 1 When crew applies

Crew needs both a useful split (≥2 DISJOINT file scopes and stateable
interfaces) and enough remaining budget for startup, coordination, join and
verification. A split alone is not a reason to spawn. For a short-budget small
task with unknown worker startup cost, first deliver a serial end-to-end slice;
measure before widening. Multiple files do not require multiple workers. Start
the wall clock before reading/planning; reserve time to close the ledger. Crew
composition is controller-elected (no flag). The execution surface is one-shot subagents
(Agent tool): parallel workers, one shared workspace, one brief contract.

When choosing crew on cost evidence, use `scripts/goal_crew.py plan --project
<project> --graph .goal/proposals/crew.json`. The graph references existing
work-plan task ids, owned files and dependencies; it is an experiment input,
not another completion queue. The executable schema and lifecycle commands are
in [the cost example](../examples/crew-cost/README.md). Keep backend/model/host
identity, task shape, checker sources and read-only inputs explicit. Local
process-demo measurements do not establish native Agent-tool startup costs.

The adviser requires three recent inline and crew observations at comparable
conditions (including actual immutable input bytes), retains failures, and compares the DAG's conservative observed
cost range including startup, queue, coordination, join and validation. It
reports worker-seconds as well as delivery time; unknown tokens/money are not
free resources. No usable startup data means serial; coupled scopes acquire
precedence, and exhausted measured budgets stop further dispatch.

Record `begin`, then `event dispatch` **before** the real host call. Record
`started` only when the host exposes a readiness event; otherwise leave it
unknown. Record `returned` or the observed `fault`, then `validate` and `adopt`.
Validation runs the frozen named check; `first_valid` is the first observed
passing result, not the first text/token or an inferred artifact birth time.
Measure coordination/join/conflict/recovery with stage begin/end; skip is only
for an operation actually not performed. Missing stages stay unknown. Finish
reruns the integration check and preserves failed waves. Native cancellation
remains the host's job; only record an active worker fault after observing it.
The helper verifies/adopts file versions and reports cost; the existing gate
still decides GO, and the controller still ticks the original work-plan.

### Bound units and learned routing

Graph version 1 remains compatible. Version 2 has the same graph fields and
adds `inputs` to each job. List immutable files from graph `inputs` and actual
output files of direct `deps`; every declared dependency must provide a named
consumed artifact. Remove ordering with no data dependency. Overlapping v2
units must be fused; v1 retains its conservative ordered shared-write support.

Version 2 binds adopted output bytes/modes, transitive inputs, interfaces.md,
contract/check freeze, instruments, context and active routing version. A later
`begin` reuses an unchanged accepted unit and refuses its dispatch/prepare.
Only the failed or invalidated units need workers; the frozen integration check
and final gate still run. Reuse has no invented startup, first-valid or worker
time. Source wave and unit identity remain explicit. Changed input/interface/
checker/policy invalidates reuse. A changed adopted producer also blocks v1
successors before dispatch.

New wave observations also record `book_iteration`, read under the original
ledger lock at begin. The context map uses it to identify a finished wave that
still needs bookkeeping, including later waves. It grants no acceptance and
does not change Gate or the work-plan's authority. Plan/begin and native
lifecycle actions are available through context when their bound graph and
actual host inputs are known; missing receipts never produce a guessed command.

Failed dispatches accumulate by contract and owned file scope, independently of
task/strategy names. Three failures stop that unit. An unchanged retry requires
a different `--retry-note` describing the revised breakpoint brief; merely
changing a label cannot reset the count. The derived repair brief includes the
failed check output, fault, allowed files and attempts. It does not prove that
the supplied explanation is semantically correct.

`plan` and `begin` accept `--policy-state PROJECT/.goal/proposals/DIR`. They run
the existing qualified `goal_evolve.py` archive under the same deadline and
consume JSON `{"match":true,"choice":"serial","reason":"..."}`; unmatching
rules must return `match:false, choice:baseline`. These bounded decisions can
restrict concurrency, never widen permissions, skip checks or force a crew.
`begin` enforces serial as inline mode, and host prepare emits the consumed
version and focused input/check/repair map in worker_prefix. Invalid output,
pending transition or stale selection refuses dispatch. No configured policy
means the existing measured planner; an unqualified candidate has no effect.
The receipt records selection, actual input hash, decision and runtime. This is
context selection, not a filesystem read sandbox. See the [learning example](../examples/learning-edge/README.md)
for promotion/retention/withdrawal and its evidence limits.

For native host tools, [the host adapter](host.md) wraps these observations in
nonce-bound tickets, actual launch/status receipts and the shared deadline.
Use its ready/owned-tool commands; do not invent startup or cancellation times
from a worker's final prose. The explicit Work bridge does not install hooks.

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
direction with measured local gain; avoid is regressing/flat. `prefer=none`
means evidence is insufficient, so test a falsifiable hypothesis. A crew
wave yields one joint delta: disjoint writes do not isolate worker effects. Workers report
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
