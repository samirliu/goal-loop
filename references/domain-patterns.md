# Domain patterns - failable checks per artifact type (R4 basis)

Contents: [1 software/script] [2 research] [3 data] [4 documents]
[5 long-running] [6 how to use].
If the artifact type is listed here and a pattern applies, a claimed
UNVERIFIABLE for it is not admissible - the gate coerces it to FAIL (R4).

## 1 Software / script

| check | command shape | settles |
|---|---|---|
| syntax | `bash -n f.sh` (exit 0) | parses at all |
| run | `bash f.sh; test $? -eq 0` | exits well |
| byte-exact output | `diff <(bash f.sh) expected.txt` -> empty | prints exactly |
| line bound | `wc -l < f.sh` vs stated bound | size discipline |
| error path | run once with a bad input, expect refusal + non-zero exit | refuses when |
| suite | the one named test command, full output shown | regressions |

## 2 Research

- Every load-bearing claim: a source fetched THIS session; cite URL + access
  date; re-read it and recompute any number it states.
- Training-memory claims: label them as such - they are leads, not evidence.
- Absence: state where you searched; absence-of-evidence is not
  evidence-of-absence.

## 3 Data

| check | command shape | settles |
|---|---|---|
| shape first | `head -3 f.csv; wc -l f.csv` | rows/cols as claimed |
| recompute | one subtotal by hand or awk, independently of the artifact | arithmetic |
| nulls/dups | `awk -F, '$1==""' f.csv | wc -l`, dup-key recount | quality |
| totals | `awk -F, '{s+=$3}END{print s}' f.csv` == stated | grand totals |

## 4 Documents

- Read back the RENDERED file (md/docx), not the generator: headings present,
  required sections present, diff against the spec line by line.
- Word/length bounds by `wc`; cross-reference every figure/table by its number.
- Claims in the summary that the body does not carry -> escalated hedge, FAIL.

## 5 Long-running work

- The work log IS the check: testable done criteria written up front; each
  continuation re-reads the log before acting (see loop-log.md format).
- Progress must be observable: a continuation that moves no file, closes no
  check -> stagnation by definition.

## 6 How to use

At contract time (Phase 1): pick the row per artifact, put its command shape
into the AC's NAMED CHECK field verbatim-ready. At panel time: an item whose
type has an applicable row here cannot be UNVERIFIABLE without a recorded
reason why the pattern is inapplicable in this case (no network, no such
tooling, outside the machine's reach) - "hard" or "slow" is no reason.
