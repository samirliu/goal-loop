# Teams Runtime Robustness — Design

**Date:** 2026-10-14
**Scope:** goal-loop `--teams` runtime fault tolerance (detect → classify → fix → wake or re-run)
**Non-goal:** new completion semantics (gate still sole GO authority); no health-sentinel agent in v1

---

## 1. Problem

`--teams` couples the loop to Agent Teams. One teammate that dies, stalls, or
throws mid-wave blocks the whole loop. Unattended multi-hour runs need the
controller to notice, repair, and resume **that work-item** without waiting
for a human.

Existing protocol covers only session/process death (revive ×2 → honest
fallback). It does **not** cover stall (alive but no progress) or tool/runtime
errors (exploded mid-call), and has no mechanical health surface.

## 2. Goals / Non-goals

### Goals (v1)
1. **Stall detection** — idle teammate with open work, no progress signals.
2. **Tool/runtime error detection** — closed vocabulary of failure marks in last output / transcript extract.
3. **Death detection reinforcement** — same as today, plus progress-aware resume vs re-run.
4. **Mechanical health probe** — `goal_team.sh health`, disk/protocol only.
5. **Controller watchdog** — join-window poller + recovery playbook; selective re-run of the failed work-item only.
6. Honest ledger suffixes; never silent fallback; never mid-run TeamDelete.

### Non-goals (v1)
- Health-sentinel peer agent (option B).
- Contract self-edit, auto publish, cross-run fleet monitoring.
- Gate-side recovery (gate remains product judge only).
- Changing GO/BLOCKED semantics or loop-log top-level schema.

## 3. Architecture (A + C)

```
dispatch wave
  └─ controller WATCH WINDOW (until join / fuse)
        │
        ├─ C: goal_team.sh health     (pure disk/protocol probe)
        │       per member: liveness | idle_s | last_touch | open_items | err_tag
        │
        └─ A: controller watchdog     (decision + repair)
                classify → fix env/brief? → wake → wake#2 → re-run item → fallback
```

- **C** never decides; it reports.
- **A** never declares GO; it only keeps the wave alive.
- Portable and native share the playbook; signals differ (see §5).

## 4. Error taxonomy (v1)

| Class | Mechanical signal | Controller confirm |
|---|---|---|
| **death** | roster `stopped`/`terminated` + wake yields no heartbeat | transcript/session resumable? |
| **stall** | `idle_s ≥ stall_sec` (default **300s**, override `GOAL_STALL_SEC`) AND open work-item has no progress | skim last output: long tool vs stuck |
| **tool-error** | last message/extract matches closed error vocab (see §5.3) | one-line root cause from transcript |

**Progress signals** (any one resets stall clock):
- mtime change under the member's `--scope`
- new inbox message from/to that member
- work-plan tick or explicit intermediate artifact named in the brief
- explicit progress note in return/MSG line

Thinking-only / empty spin does **not** count as progress.

## 5. Mechanical health surface (C)

### 5.1 `goal_team.sh health --project DIR`

Read-only. Prints one line per roster member:

```
name|liveness|idle_s|last_touch|open_items|err_tag
```

- `liveness`: `active` | `idle` | `stopped` | `terminated` | `unknown`
- `idle_s`: seconds since last progress signal (best effort)
- `last_touch`: ISO or epoch of last signal
- `open_items`: count of work-plan rows still `[ ]` assigned to this name
- `err_tag`: empty | `death` | `stall` | `tool-error` (probe-side hint only)

Exit 0 with report; exit 4 if no team. **No writes.** Safe for audit and humans.

### 5.2 Heartbeat sidecar (portable / when native has no liveness)

`.goal/team/heartbeat/<name>.ts` — controller or wake flow may touch on
successful SendMessage / probe. **Digest-exempt** (same spirit as
`.goal/evidence/`). Native path prefers roster `isActive`/`terminated` +
inbox mtime; sidecar is fallback signal, not required when native is rich.

### 5.3 Tool-error vocabulary (closed list, extendable only with tests)

Match on last non-empty extract (case-insensitive):

- `error:`, `exception:`, `traceback`, `panic:`
- `exit status [1-9]`, `exit code [1-9]`, `rc=[1-9]`
- `permission denied`, `command not found`, `no such file or directory`
- `EACCES`, `ENOENT`, `API Error`, `rate limit`

Probe sets `err_tag=tool-error`; controller still owns diagnosis (the tag is
not a verdict).

## 6. Recovery playbook (A)

User-approved default: **resume-first, 2-strike boundary, unknown → re-run.**

```
classify death|stall|tool-error
  → env_fixable?  (missing dep / wrong path / bad brief / permission)
        yes: fix workspace or brief → wake (breakpoint brief)
        no:  wake (nudge / error-correction brief)
  → still no progress → wake #2
  → 2 wakes failed OR not resumable:
        re-run THIS work-item (mark OPEN; dispatch live member or new worker)
        task= suffix records failure mode
  → re-run failed again → existing teams-fallback / BLOCKED parking
```

**Resume** when partial products/progress exist: SendMessage continue from
saved conversation + breakpoint brief (done / missing / check command).

**Re-run** only the open failed item; CLOSED items stay closed.

**Forbidden:** mid-run TeamDelete; silent backend downgrade; new loop-log
top-level keys.

### 6.1 Breakpoint brief (wake payload)

```
Continue task <id>.
Done so far: <files / checks green>
Still owed: <remaining AC or deliverable>
Blocked by (if any): <root cause one-liner>
Run: <named check>
Do not rewrite unrelated files. (R6)
```

### 6.2 Ledger honesty

Use **task= suffix only** (audit A3 vocabulary), e.g.:

- `(stall-recovered)` — stall path, resumed after wake
- `(tool-error-fixed)` — env/brief fixed then resumed
- `(re-run:stall)` / `(re-run:tool-error)` / `(re-run:death)` — item redone
- existing `(fallback:teams-process-reaped)` / `(fallback:teams-unavailable)` unchanged

No new loop-log keys. Suffixes enter the closed fallback/advisory vocabulary
and are audited like today's A3 list.

## 7. Watch window (A) in the loop

Insert **between dispatch and join** (crew.md §3→§4):

1. Poll `goal_team.sh health` on a quiet interval (default 60s sleep between
   polls; first poll immediately).
2. If any member `err_tag` non-empty or `idle_s ≥ stall_sec` or liveness
   death → run playbook for that member only; others keep working.
3. Watch ends when: all wave items closed, OR controller calls the wave
   after fuse (`GOAL_WATCH_MAX_SEC`, default aligned with `time_budget`
   remaining / 3600s floor).
4. Join proceeds with whatever closed; open failed items follow §6.

Gate-only rounds and default (non-teams) backend are unchanged.

## 8. Components / files

| File | Change |
|---|---|
| `scripts/goal_team.sh` | add `health` (read-only probe) |
| `references/teams.md` | new § Runtime watchdog (taxonomy, playbook, suffixes) |
| `references/crew.md` | watch window before join; fail attribution points at playbook |
| `scripts/goal_audit.sh` | A3 closed vocabulary += recovery suffixes (same “no invented tokens” rule as fallback) |
| `tests/docs_consistency.sh` | pin new literals (health, suffixes, GOAL_STALL_SEC) |
| `tests/cases.inc.sh` / `run_tests.sh` | scenarios: stall→wake, tool-error→fix+resume, 2-wake fail→re-run, probe rows, suffix audit |
| `SKILL.md` / `README.md` | one-line mention under Teams / Step 2–3 only if needed; keep always-on thin |

## 9. Testing plan

Deterministic, no live Agent Teams required (fake rosters + mtimes + inbox lines):

1. health lists members and idle_s from heartbeat/scope mtime
2. stall threshold fires `err_tag=stall`
3. tool-error vocab hits and misses (false-friend strings)
4. resume-vs-re-run is documented decision table; mechanical teeth are probe
   flags + suffix allowlist + work-plan item returned to `[ ]` on re-run
5. recovery suffixes accepted by audit closed vocab; unknown suffix still bad
6. digest ignores heartbeat sidecar
7. docs_consistency pins
8. full `run_tests.sh --jobs=8` stays 395+ and green

## 10. Risks / open points

- Native liveness fields differ by harness version — probe must degrade to
  `unknown` + sidecar, never invent `active`.
- Stall false positives on long single tool calls: progress includes scope
  mtime; `GOAL_STALL_SEC` is the pressure valve.
- Watchdog is the controller itself: if the **lead** is stuck, this design
  does not self-heal the lead (out of scope; parking rules still apply).

## 11. Invariant mapping

| Behavior | Invariant |
|---|---|
| health probe read-only; gate still sole GO | GATE |
| breakpoint brief / suffixes / no mid-run TeamDelete | BIND / FENCE |
| closed error vocab; probe not a verdict | PROVE (instrument honesty) |
| resume-first / watermark not applicable (no score) | FENCE (honest progress) |
| work-plan canon; selective re-run | FENCE |
