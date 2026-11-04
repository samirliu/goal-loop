# pre-reg.md — generated at stamp

T0 = <ISO stamp time>
budget: max_iterations=<> wallclock=<seconds or off>

## Hypothesis and counterevidence

Change <one mechanism> because <raw trace + failing reproducer>.
Predict <metric movement>; reject if <observable failure condition>.
First measured score anchors the trajectory; it does not prove a strategy.

## Strategy labels (objective contracts)

Derive 2–4 short labels from this objective; one primary label per wave.
For each: expected benefit / failure condition / scope of applicability.
`prefer=none` means gather evidence; do not guess a winning label.
Joint crew results belong to the wave, not to individual workers.

## Kill lines

- `iteration=0` with landed work or >=50% wallclock: close books before dispatch.
- Retry `avoid=` without a changed hypothesis and `strategy_delta`.
- Claim without adversarial clear, raw output, or untouched check scripts.
- Change the metric/check mid-run to raise the score.

## Success digits

Report accepted deliveries / all trials, score trajectory, and gate evidence.
For efficiency: total elapsed time and token/cost telemetry including evals,
joins, retries and failures; unavailable values are unknown, never zero.
Wave count alone cannot establish cost efficiency or parallel speedup.

## Reusable-policy promotion (only when changing the skill/strategy itself)

Freeze baseline/candidate, graders, task split and equal budgets before trials.
Keep held-out answers away from workers; use paired fresh states and repeats.
Report acceptance rate + all-trial cost / accepted deliveries + median/p90
time to delivery; failures are budget-censored, not excluded.
Retain incumbent on floor regression or no held-out benefit; keep failed trials.

## Degrade line

On budget expiry: report what passes + remaining evidence gaps and continuation
paths. Only gate GO is completion; partial delivery is not GO.
