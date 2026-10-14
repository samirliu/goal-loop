# Rule Compaction Design — goal-loop

**Date:** 2026-10-14  
**Scope:** Documentation / legal-surface restructuring only (no behavioral change to gate/ctl/parse/audit/CLI/ledger schema)  
**Trigger:** Objective review found R1–R19 rule accretion has passed the elegance line; controller legal load is the failure mode (“做歪”), not missing teeth.

---

## 1. Problem

| Layer | Today | Symptom |
|---|---|---|
| Controller legal surface | SKILL.md 15KB + R-refs 18× + gate.md 265 lines narrative | High “do it wrong” rate; every run loads a legal code |
| Contract authoring surface | 14 optional AC tokens | Non-trivial contracts feel like a DSL |
| Mechanical teeth | gate check 1–14, ~395 assertions | **Healthy — do not thin this round** |

R1–R19 grew as post-incident patches. Many are re-skins of the same few primitives. The number of *invariants* did not grow at the same rate as the number of *rules*.

---

## 2. Goals / Non-goals

### Goals
1. Compress always-on controller load to **five invariants** + mechanical check-order.
2. Progressive disclosure: instrument/gradient/external detail loads only when the contract activates those surfaces.
3. Freeze rule growth (“R20 and beyond: numbers only shrink”).
4. Keep all mechanical teeth and the full assertion suite green.

### Non-goals (this round)
- Merging, deleting, or weakening `goal_gate.sh` checks.
- Changing ledger schema, CLI flags, or stamp format.
- Rewriting incident case studies beyond moving references out of the always-on path.
- Improving /goal vs goal-loop efficiency claims (separate work).

---

## 3. Approaches considered

| | A. Invariant algebra | B. Lazy protocol packs | C. Code-as-law |
|---|---|---|---|
| Idea | R1–R19 → 5 invariants; R# become aliases | Split judged/gradient/external into on-demand packs | Delete prose; gate errors are the law |
| Controller load | Main path ↓↓ | Simple contracts ↓↓ | ↓ but loses judgment |
| Teeth | Preserve | Preserve | Preserve (gate grows) |
| Verdict | **Primary** | **Bundled with A** | Rejected — gate.sh is already 820 lines |

**Chosen: A + B hybrid.** Law is compiled into five invariants; depth is packed; check-order remains the mechanical statute.

---

## 4. Design

### 4.1 The five invariants

| Code | One sentence | Absorbs (legacy) |
|---|---|---|
| **GATE** | Completion is declared only by the external gate re-run; the model never self-declares. | R1 (ratchet = compound interest on false bindings) |
| **BIND** | Every claim binds to (stamped-contract × iteration × digest × evidence-hash); unbound claims are void. | R2 R3 R5 R7 R8 R14 (artifact-hash half) R16 |
| **PROVE** | An instrument must prove itself before its number or verdict is trusted. | R9 R15 R17a R14 (measurement half) |
| **GRADIENT** | Optimization never delivers below the water mark; blind spots are declared; waves are labeled for attribution. | R11 R13 R17b R19 |
| **FENCE** | Ledger write-fence, honest progress, controller self-audit; out-of-tree facts settle via cache, never by guessing. | R6 R10 R12 R4 R18 |

**R4 placement ruling:** UNVERIFIABLE cap lives under **FENCE** (process confidence ceiling), with a one-line note. Do not create a sixth invariant for it.

### 4.2 Load surfaces

```
ALWAYS (target ≤20KB combined):
  SKILL.md                 ≤6KB  loop + 5 invariants + parking + user interaction budget
  references/gate.md       invariant alias table + check-order + schemas (mechanical statute)

ON DEMAND (open when contract AC uses the capability key):
  references/packs/instrument.md   judged · probe · calib · sd/var · cold seat
  references/packs/gradient.md     objective · forge · horizon · strategy · EFFICIENCY
  references/packs/external.md     external · window · deferred
  references/teams.md              --teams (existing)
  references/crew.md               dispatch protocol (existing; strip incident history)
  references/patterns.md           check shapes (author-side; not always-on)

NEVER at runtime:
  Incident narratives (F1–F4, D1–D10) → examples/*/case.md or docs/incidents/
  Full R1–R19 prose → gate.md appendix “Legacy index” (docs_consistency anchors)
```

### 4.3 Capability keys → packs

Contract authoring is level-based. Level 0 is the entire fast path.

| Level / tokens present | Packs the controller must open |
|---|---|
| Level 0: `check:` + `expected: exit=0\|exit=N\|<op>N` only | *(none)* |
| `judged` / `calib:` / `probe:` / `metric:` / `sd:` / `var:` | `packs/instrument.md` |
| `objective:` / `exit: forge` / horizon / `--strategy` | `packs/gradient.md` |
| `external:` / `window:` | `packs/external.md` |
| `--teams` | `references/teams.md` |

Activation rule lives in SKILL.md Step 1 and in the contract template comments.  
`docs_consistency.sh` pins the activation words so packs cannot silently drift.

### 4.4 SKILL.md shape (target)

Keep:
- Identity one-liner + comparison table (drive/crew/gate)
- Four-step loop
- Parking rules (four categories only)
- Five invariants (one sentence each + pointer to gate.md)
- User interaction budget
- Pack activation table
- Script/self-check pointers + uninstall

Remove from always-on:
- R# inline teaching
- Full AC DSL grammar (move to contract template + packs)
- Incident lessons as narrative (leave one Goodhart one-liner if needed)
- EFFICIENCY/eval-gap/promote depth (→ `packs/gradient.md`)
- R15/R18/R19 depth (→ packs)

### 4.5 gate.md shape

1. Schemas (unchanged truth)  
2. Digest + mutation guard  
3. Check order (unchanged numbering 1–14)  
4. **Invariant → check map** (new short table)  
5. **Legacy index** R1–R19 one-liners with “implements BIND (see …)” (compat for tests/docs)

### 4.6 Growth freeze

Written into SKILL.md next to self-checks:

> Any new behavior must be expressible as *an existing invariant in a new situation*.  
> If it cannot: either it is a new primitive (then delete or merge an equivalent first), or it does not ship.  
> **From here, rule numbers only shrink (R20+ forbidden as additions).**

### 4.7 Mechanical teeth / tests

| Artifact | Change |
|---|---|
| `goal_gate.sh` / `goal_ctl.sh` / `goal_parse.sh` / `goal_audit.sh` / CLI / ledger | **Zero behavioral change** |
| `tests/run_tests.sh` (395) | Must stay green; only touch assertion *strings* if docs anchors rename |
| `tests/docs_consistency.sh` | Add pins for five invariant literals + pack activation keys; keep R# alias pins |
| CI | Unchanged |

---

## 5. Data flow (runtime after compaction)

```
/goal-loop objective
  → read SKILL.md (always)
  → draft contract; inspect capability keys
  → open only needed packs
  → user one-word approval → stamp
  → loop: dispatch / join / gate --check
       gate.md check-order is the only completion authority (GATE)
  → GO | NO-GO | BLOCKED
```

No new runtime files. Packs are pure documentation.

---

## 6. Error handling

| Risk | Mitigation |
|---|---|
| Rewrite drops a tooth | Migration checklist: every R1–R19 maps to an invariant + pack/gate anchor; tick off before merge |
| Pack not loaded | Step 1 hard rule + docs_consistency activation pins |
| Test/docs anchors break | Keep R# aliases; dual-ship invariant names and legacy ids |
| Install copy drifts | Same ritual as v2.9: `cp` to `~/.claude/skills/goal-loop` and re-run full suite |

---

## 7. Success criteria

1. A cold reader who only read SKILL.md can state all five invariants.  
2. SKILL.md ≤ 6,000 bytes; always-on total ≤ 20,000 bytes.  
3. `tests/run_tests.sh` and `tests/docs_consistency.sh` fully green.  
4. SKILL.md contains **zero** `R[0-9]+` tokens (legacy index lives only under `references/gate.md`).  
5. Full suite green after sync to the install copy.

---

## 8. Implementation plan (high level)

1. Write `references/packs/{instrument,gradient,external}.md` by extracting prose from SKILL.md + gate.md + crew/patterns (no logic invention).  
2. Rewrite `references/gate.md` §4 → invariant map + legacy index (R1–R19 one-liners preserved).  
3. Rewrite `SKILL.md` to the §4.4 shape.  
4. Light touch on `assets/goal.contract.md` comments: level-0 vs capability keys.  
5. Trim incident narrative from `crew.md` if present in always-on form.  
6. Extend `docs_consistency.sh` pins.  
7. Run full tests; fix only string anchors.  
8. Sync install copy; smoke `examples/quickstart-one-shot/run.sh`.  
9. Version bump → **3.0.0** (legal-surface major; behavior-compatible 2.9).  
10. Update README “what changed” one-paragraph note (install docs unchanged).

---

## 9. Open rulings (defaults chosen; override if needed)

| Question | Default |
|---|---|
| Invariant code language | English codes (GATE/BIND/PROVE/GRADIENT/FENCE) with Chinese one-liners in SKILL.md |
| R4 home | FENCE |
| Behavior change allowed if a tooth is redundant | **No** — not this round |
| Keep R# forever | Yes, as legacy index only |
