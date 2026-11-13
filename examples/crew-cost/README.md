# Measured crew decisions

`scripts/goal_crew.py` records host-observed worker events and advises whether
delegation offers a delivery-time benefit. It uses the existing budget and
command supervisor, and leaves Agent dispatch, cancellation and the work queue
with the host controller.

Run the local reproducible experiment:

```bash
python3 -B examples/crew-cost/run.py --output docs/evals/crew-cost
```

Three independent jobs factor semiprimes. A separate checker validates the
small prime certificates by trial division and multiplication. Inline and crew
run the same algorithm and checks. The fixture injects only backend startup
delay (0.01 versus 8 seconds), alternates AB/BA order across three paired input
seeds, records all outcomes, and tests the decision on a new input seed. This
is a local subprocess experiment, not a native Agent API performance claim.
Failures and observation repairs remain archived. Every completed trial is
saved immediately; fresh input identities are not silently reused.

The example also kills T2 after READY, preserves T1/T3, records the existing
controller fault suffix, and retries only T2. Final GO is obtained from the
real gate, with the original contract and checker unchanged. The helper's
`quality` field refers to the declared wave checks, not whole-goal acceptance.

For an actual Agent host, author `.goal/proposals/crew.json` using existing
work-plan ids and the frozen interface. A minimal shape is:

```json
{
  "version": 1,
  "context": {"backend": "actual host/model/build", "controller": "actual adapter", "task_shape": "version and size"},
  "capacity": 2,
  "jobs": [
    {"id": "T1", "files": ["a.py"], "deps": [], "check": ["python3", "checks/a.py"]},
    {"id": "T2", "files": ["b.py"], "deps": ["T1"], "check": ["python3", "checks/b.py"]}
  ],
  "final_check": ["python3", "checks/join.py"],
  "instruments": ["../../checks/a.py", "../../checks/b.py", "../../checks/join.py"],
  "inputs": ["fixtures/case.json"]
}
```

Instrument paths resolve from the graph file. Commands run in the project;
`{project}` in an argument expands to its absolute path. Inputs are immutable
fixtures, disjoint from owned outputs. Capture every relevant checker source;
unknown transitive dependencies do not establish comparability. Do not reuse
costs across different hosts, backends, task maturity, or observer transports.
The helper also binds the contract, initial owned-file hashes and instrument
bytes. DAG/file coupling constrains concurrency regardless of file count.

```bash
python3 -I scripts/goal_crew.py begin --project PROJECT --graph GRAPH --mode crew --trial UNIQUE_ID
python3 -I scripts/goal_crew.py event --project PROJECT --wave ID --task T1 --event dispatch
# Now call the actual host Agent tool with its existing brief.
python3 -I scripts/goal_crew.py event --project PROJECT --wave ID --task T1 --event started
python3 -I scripts/goal_crew.py event --project PROJECT --wave ID --task T1 --event returned --result 0
python3 -I scripts/goal_crew.py validate --project PROJECT --wave ID --task T1
python3 -I scripts/goal_crew.py event --project PROJECT --wave ID --task T1 --event adopt
python3 -I scripts/goal_crew.py stage --project PROJECT --wave ID --stage join --phase begin
python3 -I scripts/goal_crew.py stage --project PROJECT --wave ID --stage join --phase end
python3 -I scripts/goal_crew.py finish --project PROJECT --wave ID
python3 -I scripts/goal_crew.py plan --project PROJECT --graph GRAPH
```

Record started only if exposed by the host. Record a dropped worker with
`event --event fault --note 'observed reason'`. An item never dispatched can be
closed with `--event cancel`; this does not cancel any live remote worker.
Explicit `stage --phase skip` means no operation was performed; unrecorded
stages are unknown. Final integration revalidation is measured automatically.
The finish command seals both successful and failed observations; rc=0 means
the observation was recorded. Inspect `quality` and run the normal gate for GO.

The adviser uses a fixed latest-three window per mode, conservative observed
ranges and a 10% / 0.05-second materiality margin. These are scheduling bounds,
not confidence intervals or causal proof. Duplicate trial identities do not
count as independent replication; recent failure or missing startup data keeps
serial advice. All records remain under `.goal/evidence/crew/`. Worker-seconds
include overlapping/failed worker spans and are not wall time, CPU usage or
money. Tokens and fees remain unknown until a real provider adapter supplies
them. Controlled fixture data is not authorization to assume those costs for
native agents.
