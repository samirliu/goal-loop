# Rule Compaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the R1–R19 legal surface into five invariants + on-demand protocol packs, with zero behavioral change to gate/ctl/parse/audit.

**Architecture:** Invariant algebra (GATE/BIND/PROVE/GRADIENT/FENCE) as the only always-on law; lazy packs for instrument/gradient/external depth; check-order in `references/gate.md` remains the mechanical statute; R# survive only as a legacy index for docs/tests anchors.

**Tech Stack:** Markdown docs, bash test suites (`tests/run_tests.sh`, `tests/docs_consistency.sh`), no application code changes.

**Spec:** `docs/superpowers/specs/2026-10-14-rule-compaction-design.md`

## Global Constraints

- **Zero behavioral change** to `scripts/goal_gate.sh`, `scripts/goal_ctl.sh`, `scripts/goal_parse.sh`, `scripts/goal_audit.sh`, `scripts/goal_team.sh`, `scripts/goal_hook.sh`, `scripts/goal_loop.sh`, `assets/goal.contract.md` stamp format, ledger schema, CLI flags.
- `tests/run_tests.sh` must remain fully green (target `pass=395 fail=0`).
- `tests/docs_consistency.sh` must print `CONSISTENT`.
- SKILL.md target size ≤ 6,000 bytes; always-on pair (SKILL.md + gate.md) ≤ 20,000 bytes.
- SKILL.md contains **zero** matches of `R[0-9]+`.
- R1–R19 one-line aliases live only in `references/gate.md` §Legacy index.
- Version becomes `3.0.0` in `VERSION` and SKILL title; behavior-compatible with 2.9 ledgers.
- Do not invent new protocol semantics while extracting prose — move and compress only.
- Case names (tsp-minimize, logcli, svg-dash, probe-campaign) must not appear in generic skill surfaces (C6).
- Working directory for all steps: `C:/Users/samir/goal-loop` (repo `~/goal-loop`).
- After the last task, sync install copy to `~/.claude/skills/goal-loop/` and re-run both suites there.

---

### Task 1: Create protocol packs (extract, do not invent)

**Files:**
- Create: `references/packs/instrument.md`
- Create: `references/packs/gradient.md`
- Create: `references/packs/external.md`
- Create: `references/packs/README.md`

**Interfaces:**
- Consumes: current prose in `SKILL.md`, `references/gate.md`, `references/crew.md`, `references/patterns.md`
- Produces: three pack files that later tasks link to from SKILL.md and gate.md

- [ ] **Step 1: Create `references/packs/README.md`**

```markdown
# Protocol packs

Load a pack only when the contract (or CLI) activates its capability keys.
SKILL.md stays the only always-on narrative; these files are depth.

| Pack | Activate when you see |
|---|---|
| `instrument.md` | `judged` · `calib:` · `probe:` · `metric:` · `sd:` · `var:` · cold-seat brief |
| `gradient.md` | `objective:` · `exit: forge` · horizon · `--strategy` · EFFICIENCY/eval-gap/promote |
| `external.md` | `external:` · `window:` · deferred settle |

Invariant map (see references/gate.md):
instrument → PROVE · gradient → GRADIENT · external → FENCE (out-of-tree settle) / BIND (deferred ledger)
```

- [ ] **Step 2: Create `references/packs/instrument.md` (PROVE)**

Extract and compress **without new rules** from:
- `SKILL.md` Step 1 bullets: Goodhart sentinel, R9 probe, R15 calib, metric/tolerance/sd/var
- `references/gate.md` §1 schema notes on `probe:`, `calib:`, `metric:`, `sd:`/`var:`
- `references/crew.md` §6 cold-seat / judged brief / calibration anchors
- `references/patterns.md` sections on metric shapes (pointer + short shape table only)

Required sections in this file:
1. **When to open** — capability key list
2. **PROVE** — instrument must prove itself before a number or verdict is trusted
3. **Numeric instruments** — `probe:`, `metric:`, `tolerance:`, `sd:`/`var:` (R9/R14/R17a aliases)
4. **Judgment instruments** — `judged`, `calib: good= bad=`, cold-seat terminal review, artifact+digest binding (R15/R5/R14 aliases)
5. **Goodhart sentinel** — one short paragraph (keep the “can you satisfy this without advancing the goal?” test)
6. **Legacy aliases** — one line: `R5 R9 R14 R15 R17a → PROVE/BIND`

- [ ] **Step 3: Create `references/packs/gradient.md` (GRADIENT)**

Extract from `SKILL.md` Step 1 (objective/R11/R13/R19), Step 4 (R10/R17b, EFFICIENCY/eval-gap/promote), forge exit rules, and `references/gate.md` R11/R13/R17b/R19 + breaker notes.

Required sections:
1. **When to open** — `objective:`, `exit: forge`, horizon, `--strategy`
2. **Water mark** — `best_score`, maximize/minimize, tolerance band, negative-band rule (R11)
3. **Horizon** — judged+calib layer or `horizon-waived:` (R19)
4. **Attribution** — mandatory `--strategy` on objective contracts; scores.rec column (R17b)
5. **Divergence** — score↔judge opposite directions refuse claim (R13)
6. **Forge exit** — floors + dry_limit + empty completeness critic; budget fuse
7. **EFFICIENCY / eval-gap / promote** — advisory only; never routes (move the long v2.8 explanation here)
8. **Legacy aliases** — `R10 R11 R13 R17b R19 → GRADIENT`

- [ ] **Step 4: Create `references/packs/external.md` (FENCE · out-of-tree settle)**

Extract from `SKILL.md` R18 block and `references/gate.md` R18 + deferred.rec schema.

Required sections:
1. **When to open** — `external:`, `window:`
2. **Additive rule** — in-tree `check:` floor still runs; floor FAIL is decisive
3. **rc=75 = DEFERRED** — wait, never deliver; hint `wait-for-source` / `deferred-pending`
4. **window cache** — deferred.rec, default 3600s, latest-per-id wins
5. **Ratchet exemption** — deferred NO-GO does not count toward false_completes
6. **Stamp rules** — `window:` without `external:` refused
7. **Legacy aliases** — `R18 → FENCE (settle) / BIND (deferred.rec)`

- [ ] **Step 5: Sanity-check pack sizes and C6**

Run: `bash tests/docs_consistency.sh`
Expected: `CONSISTENT` (new files may be unreferenced yet; C1 only checks cited paths — do not cite packs from SKILL until Task 3 if that would break mid-task; prefer creating packs first then wiring).

Also verify no case names: `grep -nE 'tsp-minimize|logcli|svg-dash|probe-campaign' references/packs/*.md` must be empty.

- [ ] **Step 6: Commit**

```bash
git add references/packs
git commit -m "docs: add instrument/gradient/external protocol packs (extracted depth)"
```

---

### Task 2: Rewrite `references/gate.md` legal core

**Files:**
- Modify: `references/gate.md`

**Interfaces:**
- Consumes: packs from Task 1 (paths only)
- Produces: §Invariant map + §Legacy index that SKILL.md and docs_consistency rely on

- [ ] **Step 1: Keep §1–§3 (Schemas, Digest, Check order) byte-stable unless a path pointer changes**

Do **not** renumber check-order items 1–14. If a comment says “see SKILL.md R15”, repoint to `references/packs/instrument.md` or the Legacy index line.

- [ ] **Step 2: Replace §4 Rules with two subsections**

**§4.1 Invariant map** (new table — the only always-on “law list”):

| Invariant | One sentence | Enforced by (check order) | Depth |
|---|---|---|---|
| GATE | Completion only via gate re-run; never self-declare | 1–14 overall; false-complete ratchet | SKILL.md |
| BIND | Claim binds contract-stamp × iter × digest × evidence hash | 1, 3, 5b, 6, 7b, 8, 14 | packs/instrument.md (evidence) |
| PROVE | Instrument proves itself before number/verdict trust | 7 (probe), 8 (calib), 14 (measurement) | packs/instrument.md |
| GRADIENT | Never deliver below water mark; declare blind spots; label waves | 12–14, stamp objective/horizon | packs/gradient.md |
| FENCE | Write-fence, honest progress, self-audit; out-of-tree settle | 5b, 11–12, external/DEFERRED | packs/external.md + audit |

**§4.2 Legacy index** (R1–R19, one-to-two lines each, stable IDs for tests):

For every former rule keep a bullet with exact ID `**R1**`…`**R19**` and the invariant tag, e.g.:

```markdown
- **R1** false-complete ratchet → GATE. Two gate-caught false claims → BLOCKED.
  DEFERRED (`deferred-pending`) is not counted (patience ≠ lie).
- **R3** stamped contract frozen → BIND.
...
```

Full one-line text must retain the *load-bearing literals* that C5/docs currently pin (e.g. `verdict-unbound`, `contract-malformed`, `work-plan`, `never WRITE`, `strategy_delta`, `horizon-waived`, `deferred-pending`, `calibration-missing`).

- [ ] **Step 3: Point narrative depth at packs**

Replace long R15/R18/R17/R19 paragraphs in old §4 with the one-liner + `see references/packs/….md`.

- [ ] **Step 4: Run docs consistency**

Run: `bash tests/docs_consistency.sh`
Expected: `CONSISTENT`. If C5 needles live only in the long R paragraphs, move those literal strings into the Legacy one-liners or pack body first.

- [ ] **Step 5: Commit**

```bash
git add references/gate.md
git commit -m "docs(gate): compile rules into invariant map + legacy index"
```

---

### Task 3: Rewrite SKILL.md to invariant surface

**Files:**
- Modify: `SKILL.md`

**Interfaces:**
- Consumes: gate.md §4 (Task 2), packs (Task 1)
- Produces: always-on controller brief ≤6KB, zero `R[0-9]+`

- [ ] **Step 1: Replace SKILL body with the target outline**

Keep frontmatter `name: goal-loop` and a description that does **not** grow. Title line: `# Goal Loop (v3.0.0)`.

Target outline (write this literally; compress existing wording, do not add features):

1. **身份** — one table /goal vs /team vs goal-loop (keep existing 4-row table)
2. **五条不变量** — GATE / BIND / PROVE / GRADIENT / FENCE, each **one Chinese sentence + English code**, pointer `细节与检查序号 → references/gate.md`
3. **四步循环** — 契约→派工→Join+gate→分岔 (keep, strip R# and deep DSL)
4. **停车规则** — four categories only; “R3” replaced by “盖戳后只能提案”
5. **Step 1 契约要点** — Level 0 AC shape only (`AC-N | 陈述 | check: \`cmd\` | expected: exit=0|exit=N|judged|maximize|minimize|<op>N`); one line Goodhart sentinel; pack activation table:

```markdown
| 契约出现 | 必读 pack |
|---|---|
| judged / calib / probe / metric / sd / var | references/packs/instrument.md |
| objective / exit: forge / horizon / --strategy | references/packs/gradient.md |
| external / window | references/packs/external.md |
| --teams | references/teams.md |
```

6. **小任务快车道** — keep the four commands (no R#)
7. **Step 2/3/4** — dispatch/join/branch skeletons; claim 前 `goal_audit.sh`; hint 路由一句话; “冷席终验”一句 + pack pointer
8. **账本** — file list one paragraph (no R#)
9. **脚本与自检** — script list; run_tests + docs_consistency + quickstart; **growth freeze** paragraph:

```markdown
## 规则冻结
任何新行为必须能写成「某不变量在新场景的实例」。写不成 → 要么是新原语
（先删并等价物或并入现有不变量），要么不做。**编号只减不增（禁止新增 R20+）。**
```

10. **卸载** — keep one line

- [ ] **Step 2: Enforce zero R# and size**

Run:
```bash
grep -nE 'R[0-9]+' SKILL.md && echo 'FAIL r-refs' || echo 'OK no R#'
wc -c SKILL.md
```
Expected: `OK no R#` and size ≤ 6000.

- [ ] **Step 3: Version string for C2**

Ensure SKILL title contains `(v3.0.0)` and `VERSION` file is already `3.0.0` (Task 5 may bump; if VERSION not yet bumped, bump here in the same commit to keep C2 green: `echo 3.0.0 > VERSION`).

- [ ] **Step 4: Run suites**

```bash
bash tests/docs_consistency.sh
bash tests/run_tests.sh 2>/dev/null | grep -E '^== results'
```
Expected: `CONSISTENT` and `pass=395 fail=0` (or equivalent all-green). If a run_tests case greps SKILL.md for an R literal, point that assertion at `references/gate.md` legacy index instead — **edit the assertion string only**, never the gate behavior.

- [ ] **Step 5: Commit**

```bash
git add SKILL.md VERSION tests/run_tests.sh tests/docs_consistency.sh
git commit -m "docs(skill): five-invariant always-on surface (v3.0.0 legal compaction)"
```

---

### Task 4: Contract template + crew/patterns pointers

**Files:**
- Modify: `assets/goal.contract.md` (comments only — grammar lines that stamp parses stay intact)
- Modify: `references/crew.md` (strip always-on incident history if any; add pack pointers)
- Modify: `references/patterns.md` (header pointer to packs; keep shape library)

**Interfaces:**
- Consumes: pack paths
- Produces: author-side navigation without changing stamp-parsed tokens

- [ ] **Step 1: `goal.contract.md` comment block**

Add at top of Acceptance criteria comment (do not alter machine-parsed example AC lines):

```markdown
<!-- Level 0 (default): statement | check: `<cmd>` | expected: exit=0|exit=N|<op>N
     Capability keys open packs before you finish authoring:
     probe/metric/sd/var/calib/judged → references/packs/instrument.md
     objective / exit: forge / horizon-waived → references/packs/gradient.md
     external/window → references/packs/external.md -->
```

Keep existing token explanations; if they duplicate a pack, leave a single sentence + pointer rather than dual full texts.

- [ ] **Step 2: `crew.md` / `patterns.md`**

- Add one line near top: `深度协议见 references/packs/（按契约能力键打开）。`
- Remove or relocate any multi-paragraph incident retellings that duplicate `examples/case.md` (C6 still applies).
- Do **not** delete cold-seat brief template content that instrument pack only *references* — either move the template into `packs/instrument.md` and leave a one-line pointer, or leave it in crew.md and have the pack point to it. Choose **single source**: if the template is long, keep it in `crew.md` and link from the pack.

- [ ] **Step 3: Run suites**

```bash
bash tests/docs_consistency.sh
bash tests/run_tests.sh 2>/dev/null | grep -E '^== results'
```
Expected: CONSISTENT + all green.

- [ ] **Step 4: Commit**

```bash
git add assets/goal.contract.md references/crew.md references/patterns.md references/packs
git commit -m "docs: capability-key navigation for contract/crew/patterns"
```

---

### Task 5: docs_consistency pins for invariants + packs

**Files:**
- Modify: `tests/docs_consistency.sh`

**Interfaces:**
- Consumes: SKILL.md invariant codes, pack activation keys, gate.md legacy IDs
- Produces: C7 (new) failing when the legal surface drifts

- [ ] **Step 1: Add C7 block after C6**

```bash
# C7 rule compaction: five invariants stay on the always-on surface; packs
# remain the only depth; SKILL.md must not reintroduce R-numbers.
for needle in GATE BIND PROVE GRADIENT FENCE; do
  grep -q "$needle" SKILL.md && ok "C7 SKILL has invariant $needle" || bad "C7 SKILL missing $needle"
done
if grep -qE 'R[0-9]+' SKILL.md; then
  bad "C7 SKILL.md reintroduced R-numbers (legacy index lives in references/gate.md)"
else
  ok "C7 SKILL.md free of R-numbers"
fi
for p in instrument gradient external; do
  [ -f "references/packs/$p.md" ] && ok "C7 pack exists: $p.md" || bad "C7 pack missing: $p.md"
done
for needle in GATE BIND PROVE GRADIENT FENCE; do
  grep -q "$needle" references/gate.md && ok "C7 gate.md maps $needle" || bad "C7 gate.md missing $needle"
done
for r in R1 R2 R3 R4 R5 R6 R7 R8 R9 R10 R11 R12 R13 R14 R15 R16 R17 R18 R19; do
  grep -q "\*\*$r\*\*" references/gate.md && ok "C7 legacy $r retained" || bad "C7 legacy $r missing from gate.md"
done
for needle in instrument.md gradient.md external.md; do
  grep -q "$needle" SKILL.md && ok "C7 SKILL activates pack $needle" || bad "C7 SKILL missing pack $needle"
done
```

- [ ] **Step 2: Run docs_consistency**

Run: `bash tests/docs_consistency.sh`
Expected: `CONSISTENT`. Fix needles until green.

- [ ] **Step 3: Commit**

```bash
git add tests/docs_consistency.sh
git commit -m "test(docs): C7 pins five invariants, packs, legacy index"
```

---

### Task 6: README note + VERSION + full freeze gate

**Files:**
- Modify: `README.md` (short “v3.0.0 legal compaction” note; install steps unchanged)
- Modify: `VERSION` (ensure `3.0.0`)

**Interfaces:**
- Consumes: all prior tasks
- Produces: releasable tree

- [ ] **Step 1: README**

In the EN/中文 intro, add 2–3 sentences max:

```markdown
**v3.0.0** — legal-surface compaction only. The always-on law is five invariants
(GATE / BIND / PROVE / GRADIENT / FENCE); depth lives in `references/packs/`.
Mechanical gate checks are unchanged from 2.9.0.
```

Remove any README paragraph that teaches all R-numbers if it duplicates gate.md (keep a pointer).

- [ ] **Step 2: Full freeze gate**

```bash
echo 3.0.0 > VERSION
bash tests/docs_consistency.sh
bash tests/run_tests.sh 2>/dev/null | grep -E '^== results'
grep -nE 'R[0-9]+' SKILL.md || echo 'OK no R# in SKILL'
wc -c SKILL.md references/gate.md
```
Expected: CONSISTENT · `pass=395 fail=0` · OK · SKILL.md ≤6000, gate.md+SKILL ≤20000.

- [ ] **Step 3: Install copy sync + smoke**

```bash
cp -f SKILL.md VERSION \
  ~/.claude/skills/goal-loop/
cp -rf assets references scripts tests \
  ~/.claude/skills/goal-loop/
cp -f agents/*.md ~/.claude/agents/
bash ~/.claude/skills/goal-loop/tests/run_tests.sh 2>/dev/null | grep -E '^== results'
bash ~/.claude/skills/goal-loop/tests/docs_consistency.sh
bash ~/.claude/skills/goal-loop/examples/quickstart-one-shot/run.sh
```
Expected: same green results on the install copy; quickstart `GATE: GO` / rc=0.

- [ ] **Step 4: Commit (and push only if user asks)**

```bash
git add README.md VERSION
git commit -m "release: v3.0.0 rule compaction (five invariants + packs, teeth unchanged)"
```

Do **not** `git push` unless the user explicitly requests it.

---

## Self-review checklist (plan author)

1. **Spec coverage:** packs (4.2) → T1; gate invariant map + legacy (4.5) → T2; SKILL shape (4.4) + growth freeze (4.6) → T3; contract/capability keys (4.3) → T4; tests (4.7) → T5; version/success criteria (7) → T6.  
2. **Placeholders:** no TBD; pack bodies specify sections + source files to extract.  
3. **Type consistency:** pack filenames `instrument.md|gradient.md|external.md`; invariant codes `GATE BIND PROVE GRADIENT FENCE`; C7 needles match.  
4. **Behavior freeze:** no script implementation tasks exist.
