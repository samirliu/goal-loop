# Pack: instrument (PROVE)

**Open when:** AC or brief uses `judged` · `calib:` · `probe:` · `metric:` · `sd:` · `var:` · cold-seat terminal review.

**Invariant: PROVE** — an instrument must prove itself before its number or verdict is trusted.
**Also touches BIND** — a judged PASS is void without `artifact:` + `digest:` binding.

Legacy aliases: `R5 R9 R14 R15 R17a` → PROVE / BIND.

---

## 1 Numeric instruments

### `probe:` (verify the verifier)

- Required spirit for every `metric` / `maximize` / `minimize` AC: the probe asserts the **instrument** (fixture loaded, seed fixed, tool alive), not the artifact.
- Probe must PASS before the number is trusted. Unprobed metric is a Goodhart magnet.
- Probe failure → gate `BROKEN` / `probe-failed` — never a silent PASS.

### `metric:` (pin the number)

- One capture group; ANSI stripped before matching.
- Use when stdout carries other numbers; otherwise last non-empty line is the metric.
- stderr rides along in verdict detail (fail-loud). A FAIL that says only “failed” is the eval system violating fail-loud.
- Tautological checks (cannot fail across rounds) may be flagged `tautology-suspect` (advisory).

### `tolerance:` / `sd:` / `var:` (noise band)

- `tolerance:` relative band on the objective water-mark compare (see `gradient.md`).
- `sd:` / `var:` extract spread from the check’s own output (one capture group). Band becomes `max(2*spread/|best|, tolerance)`.
- Declared-but-non-matching instrument = BROKEN, never a silently band-less compare.

### Measurement shape rules (authoring)

- Prefer programmatic metrics over text extraction; never `wc -w` on natural language.
- Aggregating metrics must print ONE number (N repeats / percentile) and state the repeat count in the contract.

---

## 2 Judgment instruments

### `judged` ACs

- `check:` must be a **real** command that produces the evidence the seat reads (render / screenshot / extract). Placeholder check voids the contract (`contract-malformed`).
- Prose expectations (legacy v1.1) route to judged.

### Cold-seat terminal review (once, before claiming exit)

- Dispatch a **fresh** seat (visual/judgment), not a producer.
- Brief carries: verbatim AC text + evidence paths + rubric anchors + calibration anchors. **No controller/producer reasoning.**
- PASS → bind the verdict and deliver; FAIL → fix and come back.
- A verdict without observation is void.

### Binding (BIND)

- Judged PASS evidence must cite `artifact: <path>` + `digest: <sha256>`.
- Gate recomputes sha256; mismatch → `verdict-unbound`.
- Deterministic ACs: gate rerun is the evidence; ledger rows are bookkeeping.

### `calib: good=<f> bad=<f>` (judge calibration)

- Judged ACs that can name known-good / known-bad fixtures **should** declare `calib:`.
- Seat must grade `AC-N#good = PASS` ∧ `AC-N#bad = FAIL` in the current iteration+digest (derived-id rows in `verdicts.rec`).
- A seat that cannot reject the known-bad case is not trustworthy on the real one.
- Declared-but-missing fixtures → `calibration-broken` (fail-closed). Stamp refuses one-sided declarations or missing files.
- Grade evidence must QUOTE the fixture it read (unbound grade = invented grade).

### Goodhart sentinel (every AC)

Ask: *can this be satisfied without advancing the goal?* If yes, it is a proxy metric — rewrite or delete. Size/ratio ACs must cite a real spec source.

---

## 3 Brief checklist (judged)

- [ ] AC text verbatim
- [ ] Evidence paths only (no producer reasoning)
- [ ] Rubric anchors (how to grade)
- [ ] Calibration anchors or `calib:` fixtures (known good / known bad)
- [ ] Output form: PASS / FAIL / UNVERIFIABLE + PROBE= REASON= + artifact/digest when PASS

UNVERIFIABLE ≤ 1/3 of judged ACs; always PROBE/REASON (see gate.md / FENCE).
