# Pack: bounded recursive policy improvement

Use when the user asks for recursive self-improvement, or actual repeated
failures/costs expose a reusable execution-method defect worth fixing within
the current goal. Keep the original deliverable first. Ordinary small tasks
need no experiment or improvement declaration.

## What recurses

The host agent reads an observed failure/cost, proposes a changed method,
compares it with the actual active parent, consumes the qualified version on
later work, and uses that feedback to propose the next generation. The
experiment engine supplies calibration, fresh holdout, bounded execution,
selection and withdrawal; it does not invent candidate code or launch models.
Use the existing [gradient protocol](gradient.md) for the evaluator schema.

Evolvable methods include local tools and workflow-routing policies. Existing
version 2 experiments also support multi-file checkpoint bundles, including
helpers or worker instructions whose actual downstream effect can be measured.
A proposal generator can itself be such a component, provided evaluation
includes the work it causes. Faster JSON printing, longer prompts, extra
reflections and controlled test telemetry do not establish improved reasoning
or net delivery benefit. Model weights and the active acceptance kernel are
outside this execution loop.

## Bind one campaign to the existing goal

Keep a real, immutable failure/profile file in the project. Declare an existing
calibrated `goal_evolve` protocol, then author `.goal/proposals/improvement.json`:

```json
{
  "version": 1,
  "scope": "the observed local tool workflow",
  "consumer": "tool",
  "state": ".goal/proposals/tool-policy",
  "protocol": ".goal/proposals/generation-1/protocol.json",
  "max_attempts": 3,
  "reserve_fraction": 0.25,
  "intent": "improve",
  "trigger": {
    "artifact": ".goal/evidence/profile.json",
    "sha256": "<actual SHA-256 of that evidence>",
    "observation": "The actual recurring failure or measured bottleneck."
  },
  "hypothesis": "The scoped method change and the observable result it should improve."
}
```

Scope and observation are actual task-specific statements. `consumer` is
`tool`, `routing` or `proposer`. Both state and protocol live under project proposals;
keep protocol inputs outside the policy state directory. The campaign needs
an existing host deadline. `reserve_fraction` reserves that fraction of the
remaining goal time at start for delivery; all generations share the resulting
fixed cutoff. Model/tool time already spent still counts against the original
goal. Attempt limits include rejected and interrupted recorded experiments.

Regenerate context and execute `actions.start-improvement.command`. It binds
the goal run, contract, check freeze, kernel bytes, scope, state, calibrated
grader, thresholds, attempt cap and cutoff. The allocation receipt is local
resource metadata; goal_evolve reports remain the trial/selection authority
and the original controller/Gate remain the only completion authority.
Repeated start does not extend time or reset attempts. Do not delete receipts,
rename the scope or fork a state directory to restart statistical testing.

## Improve, use, and improve again

1. Use the map's `improvement.parent_archive` as the exact baseline. For a
   multi-file policy, preserve the existing checkpoint qualification/ownership
   protocol. Have the host agent write only the candidate method; preserve
   the original task, interfaces, evaluator, calibration and success thresholds.
2. Supply fresh held-out inputs, following `improvement.feedback.next_holdout`.
   Producer-visible cases are development inputs, not future holdout. Existing
   content exposure and sequential alpha budgets stay in the same policy state.
   Hash inequality alone does not establish semantic independence.
3. Update protocol/trigger/hypothesis in the declaration, take a new map, and
   run `actions.evaluate-improvement.command`. It checks the parent and frozen
   boundaries inside the existing policy writer lock and after every pair.
   Do not hand-author an enabled pointer, PASS or generation history.
4. Consume a qualified tool using `improvement.consume_command`, with actual
   task bytes on stdin and stdout feeding the real workflow. It verifies and
   runs the archived bytes under the original goal deadline, recording an
   existing runtime span with policy, qualification, input/output hashes and
   observed execution cost. Run the independent business check too: process
   exit=0 is not a quality PASS.
5. For `consumer:routing`, context supplies the qualified state to the existing
   planner when execution.json has no explicit policy_state. Explicit null
   disables it; an explicit different state keeps its existing semantics.
   A finished, independently checked crew wave provides actual usage evidence.
   A plan/advice print alone does not. Capacity, dependencies, explicit inline,
   ownership and remaining-budget checks still apply.
6. Only after actual use can the selected method parent another generation.
   The map exposes attempts, parent identities, depth, actual usage, feedback
   and the source archive. Reading or accepting a report is not actual use.
   Book native worker waves through the ordinary controller before the next.

For improving the proposal operator itself, use `consumer:proposer`. After
qualification the map supplies `suggest-improvement`. The active proposer
receives its own archived `parent_program`, original goal and recorded
feedback, and returns `{"hypothesis":"…","files":{"candidate.py":"…"}}`.
It receives no fresh holdout gold. The host reviews these files in a new
experiment directory; nothing is automatically written or enabled. Then
the same fixed evaluator and new holdout must qualify the generated version.
Malformed proposals or `.goal`/`.git` file targets do not count as actual use.
The proposal operator's evaluator must judge the downstream changes it causes,
including generation and execution cost. Merely returning plausible source
or a different version number cannot establish improvement. This interface
allows the improved method to participate in producing its own successor;
actual intelligence gains still require task evidence.

Candidates are generated by the current host model and its existing permitted
tools/workers. No second harness, model client, unbounded background loop or
automatic publication is introduced. A worker must still have a scoped
ticket; no worker edits `.goal/` or grades its own judged acceptance.

## Counterexamples, recovery and stopping

An actual regression goes to `intent:monitor`, with the active archive as
candidate and its qualified parent as baseline. New development/holdout cases
must reproduce the observed issue. A verified failure withdraws the candidate;
an inconclusive timeout or invalid instrument preserves the safe prior choice.
After withdrawal, actually consume/check the fallback, then propose a repair
against it. Keep all generations and failures, without resetting exposure or
sequential alpha. A newer fast policy is not entitled to remain active.

Pending policy transitions expose `recover-improvement`; recovery completes
the recorded transition or quarantines an interrupted evaluation without
replaying trials. It remains available after goal expiry and when the next
proposal is incomplete. Repairs to an active grader or goal contract use the
existing authorized amendment workflow, not a quieter threshold in this loop.

When attempts, reserved time or the original deadline run out, stop new
experiments and finish/settle the original goal. A qualified archive remains
usable for delivery until the original deadline; an exhausted research
allowance does not confiscate a validated method. An incomplete next proposal
also does not replace or disable the existing qualified archive. At goal expiry
use the ordinary receipt/close/end actions; improvement never grants GO.

The [runnable example](../../examples/recursive-improvement/README.md) measures
two actual generations and an optional counterexample/withdrawal/repair,
ending with original Gate verification. Its candidates are fixtures, so it
tests this lifecycle and local tool cost, not autonomous model invention,
general self-improvement, cross-task transfer or weight-level RSI.
