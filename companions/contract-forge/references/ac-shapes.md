# AC shapes by claim family

Domain-free. Classification comes from goal-loop `references/patterns.md`.
Authority for line grammar: goal-loop `references/gate.md`.

## Fixed line shape

```
- AC-N | <yes/no statement> | check: `<command>` | [probe: `<cmd>`] | [baseline: delta|abs] | [metric: `<regex one capture group>`] | [tolerance: <rel>] | [calib: good=<f> bad=<f>] | expected: <spec>
```

`expected:` spec (no `|` inside): `exit=0` (default) | `exit=N` | `<op><number>` (`>= <= > < == !=`) | `maximize` | `minimize` | `judged`.

## Three-layer sketch (complex / optimization default)

| Layer | Role | Typical expected |
|---|---|---|
| **Floors** | non-regression (correctness, safety, interface) | `exit=0` / `exit=N` / bounds |
| **Objective** | one primary score | `maximize` / `minimize` + `objective:` line |
| **Horizon** | what the score cannot see | `judged` + `calib: good= bad=` **or** `horizon-waived:` |

## Family → construction

### Executable-correctness
- lint/parse/lint: `exit=0`
- known-bad refusal: `exit=N` (or N!=0)
- exact output: command runs `diff` / hash compare → `exit=0`
- named regression suite as the one check command

### Behavioral
- scripted replay + end-state assert in `check:`
- evidence under `.goal/evidence/` (gate path; here only name the command)

### Quantitative (noise floor first)
- ONE command, N repeats, aggregate internally, **LAST stdout line = number**
- `expected: >=V` / `<=V` / `maximize` / `minimize`
- Add `probe:` (instrument alive), `metric:` if output has other numbers
- `tolerance:` or `sd:`/`var:` for noise band
- `baseline: delta` (forge default) needs `.goal/baseline.md` row

### Perceptual / quality
- Convert to `expected: judged`
- Written rubric anchors or pairwise A/B at fixed observation point
- `check:` must be a **real** command that produces evidence (render/extract)
- `calib: good=<f> bad=<f>` when used as horizon or hardened judge (R15)

### Data / documents / long-running
- Shape checks (head/counts/totals), recompute subtotals, size bounds
- Documents: parse + required sections as `exit=0` checks; quality → judged
- Long-running: timeout + end-state; `external:`/`window:` for out-of-tree settle

## Goodhart sentinel (every AC sketch)

1. Can this pass **without advancing the real goal**? → proxy: rewrite or delete.
2. What is the **gamable path**? If cheap, add a floor or judged horizon.
3. Is score **monotone** with progress? If not, split metric or change objective.

## Metric AC non-negotiables

- Aggregate inside the command (mean/p50 named); never single lucky run.
- Measure noise **before** choosing V (run twice on pre-work artifact).
- Variance itself may be an AC (same-input-twice, or spread bound).
- `maximize`/`minimize` is a score, not a floor; direction lives in `objective:`.

## Objective / forge extras

- `objective: maximize|minimize AC-N` must match that AC `expected:`.
- Horizon required at stamp (judged+calib or `horizon-waived: <reason>`).
- Budgets: prefer `dry_limit=` and `max_iterations=` fuse.
- Handoff: every wave `close-iteration --strategy <label>`.
