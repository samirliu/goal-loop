# Case D: adversarial probe campaign (2026-10-12, dsh-style)

**Goal**: 10 hostile contracts that stress the seams BETWEEN documented
v2.5.0 behaviors - the goal is the skill, not the cases.
Harness: `~/goal-loop-case-probe-campaign/campaign.sh` + `campaign2.sh`
(throwaway ledgers, no network). Ledger: runs/LEDGER.md.

## Defects found (all fixed + regression-tested)

| # | Probe | Symptom | Fix |
|---|-------|---------|-----|
| D1 | duplicate AC id, contradictory checks | parser silently picked the LAST line - a lying line won | duplicate id -> contract-malformed, names it (t85) |
| D2 | `--verify AC-99` with typo'd id | "VERIFY-OK nothing-deterministic" - all-clear while ACs unmeasured | unknown-ac-id rc4, names it (t86) |
| D3 | `iteration=banana` in state.rec | reached arithmetic silently | numeric keys validated, offending key named (t87) |
| D4 | judged artifact path with a space | bound at the first space - "out/my not found" | greedy match up to `digest:` (t6b/P6b GO) |
| D5 | objective score negative (-10) | `sed 's/^[^0-9]*//'` ate the minus sign; AND tolerance `(1-t)*b` flips the band under zero | both fixed; band = best +/- abs(best)*t (t88) |
| D6 | check rewrites .goal/ mid-rerun | tree digest is blind to .goal - measured one body, reported another | `ledger_digest` before/after both rerun modes (t89) |
| D7 | manual `--false-complete yes` + mechanical ratchet | double count -> first caught claim BLOCKED instantly | flag ignored with NOTE when the gate runs (t90) |
| D8 | `objective: maximize` at a judged AC | surfaced mid-loop as score-missing | stamp refuses at t=0 (t91) |
| D9 | goal.md without `approved:` placeholder | stamp silently no-ops - "success" with unstamped contract | stamp refuses loud rc4 (t92) |

**Non-defects**: CRLF ledger round-trip (scrubbers everywhere, GO as
expected); missing expected:/check: (fail-closed was already in place,
P2/P2b CONFIRMED); digest-frozen contract (contract-tampered caught P9b+).

Findings stay in this folder only - zero case content in generic surfaces
(C6 holds).
