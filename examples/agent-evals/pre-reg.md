# Real-agent matched evaluation

The cohort contains four task families, three fresh instances per family and
three arms, giving 36 attempts. Development pilots remain separate. Each arm
starts from identical source and public checks within its matched instance.
Hidden inputs use fixed distinct seeds. Arms run in a rotating
plain/skill/native order, one trial at a time. At most two agents, including
the trial controller, may work on an arm.

The first frozen release cohort used hidden seed base 229003. It was stopped
after two completed attempts when an independent invariant audit reproduced
an unqualified objective watermark blocking rollback. All two outcomes and
34 undispatched configurations remain archived. The repaired release cohort
uses seed base 329003; earlier outcomes are not relabelled or deleted.
If another production defect requires changing the frozen implementation,
stop further dispatch, retain every completed/inflight attempt, record the
reason, and start any repaired cohort with new hidden inputs and identity.

Plain uses the ordinary implement/test/fix workflow. Skill reads the frozen
goal-loop package and uses its normal entry points with existing automatic
authorization. Native creates a persisted goal using the host create_goal
tool, reads it back, and retains native thread and completion receipts.
The launch path is the Codex host Goal API. Host build and provider revision
remain unknown when the tools do not expose them. All agents inherit the
same parent model and settings, with no model override.

Each attempt has 600 seconds from dispatch through independent acceptance.
Workers should finish 35 seconds before cutoff and atomically publish a
DONE.json marker outside the work tree, in the trial directory. A separate
monitor observes public checks and this marker,
snapshots at completion or cutoff, and runs hidden checks on the snapshot.
Parent conversation latency does not postpone adjudication. Cancellation of
a host worker uses the actual host interrupt API. If that requires a later
controller turn, overrun compute is recorded as unknown and the deadline
snapshot remains authoritative.

The controller retains the actual host dispatch acknowledgement. Each worker
writes READY.json beside DONE.json on its first tool call, before reading the
task. Dispatch-to-ready includes queueing and the model's first-tool latency;
these components cannot be distinguished with the available host interface.
It is not reported as pure queueing time or omitted from delivery latency.

The primary result is independent correctness within budget. Protocol
compliance, acceptance claims and false acceptance are also recorded. Report
all attempts, including failed checks, timeouts, cancellations and environment
failures. Zero accepted deliveries makes cost per delivery undefined.
Independent grading time is included. Successful-only time summaries are
labelled conditional. This small cohort supports paired observations without
establishing general statistical superiority.

Workers may read their public task, checks and permitted source. Briefs
prohibit reading other workspaces and hidden evaluators. This is task-scope
isolation, without OS secrecy against a malicious process of the same user.
Evaluator/public hashes are checked after each attempt. Patches, raw evaluator
outputs, agent reports, marker times and native Goal receipts are retained.

Native Goal accounting is recorded where returned. Accounting coverage
differs across arms and cannot establish cross-arm token cost. Monetary cost
remains unknown. Crew and strategy-feedback ablations require separate
protocols and budgets.
