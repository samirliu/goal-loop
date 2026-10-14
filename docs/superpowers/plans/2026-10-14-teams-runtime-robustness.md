# Teams Runtime Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `--teams` loops survive stalled / errored / dead teammates via a mechanical health probe + controller recovery playbook (resume-first, 2-strike, re-run), without changing gate GO semantics.

**Architecture:** `goal_team.sh health` reports per-member `name|liveness|idle_s|last_touch|open_items|err_tag` from disk only. The controller watches that surface between dispatch and join, then runs a fixed recovery playbook that only touches the failed work-item. Ledger honesty stays `task=` suffix only.

**Tech Stack:** bash (gawk/sed/find), no jq, no network. Tests = existing `tests/run_tests.sh` scenario suite (TDD: add cases first).

**Spec:** `docs/superpowers/specs/2026-10-14-teams-runtime-robustness-design.md`

## Global Constraints

- Gate remains sole GO authority; no new loop-log top-level keys.
- Workers never WRITE `.goal/` (R6). Health probe is **read-only**.
- Never mid-run `TeamDelete`; never silent backend downgrade.
- Recovery suffixes are a **closed vocabulary** (extend only with tests).
- Stall default `GOAL_STALL_SEC=300`; watch poll default 60s; watch fuse `GOAL_WATCH_MAX_SEC` (default 3600).
- Heartbeat sidecar lives at `.goal/team/heartbeat/<name>.ts` and is **digest-exempt**.
- Portable + native share the playbook; probe must degrade to `unknown` rather than invent `active`.
- Skill copy under `~/.claude/skills/goal-loop/` is synced after green tests.
- Push via proxy: `git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 -c http.postBuffer=1048576 push origin main`

## File Structure

| File | Responsibility |
|---|---|
| `scripts/goal_team.sh` | add `health` subcommand + `touch_heartbeat` helper used by `send` |
| `scripts/goal_parse.sh` | task grammar accepts recovery suffixes; extract helpers |
| `scripts/goal_audit.sh` | A3 closed vocab for fallback + recovery suffixes |
| `scripts/goal_gate.sh` | digest prune includes `team/heartbeat` (already skips `.goal*` — verify) |
| `references/teams.md` | § Runtime watchdog (taxonomy, playbook, suffixes, breakpoint brief) |
| `references/crew.md` | watch window between dispatch and join |
| `tests/docs_consistency.sh` | pin new literals |
| `tests/cases.inc.sh` | scenario tests (extend numbered series) |
| `tests/test_parse.sh` | grammar unit for new suffixes |

---

### Task 1: Task-id grammar + recovery suffix vocabulary

**Files:**
- Modify: `scripts/goal_parse.sh:208-211`
- Modify: `scripts/goal_audit.sh:53-58`
- Test: `tests/test_parse.sh` (append)

**Interfaces:**
- Produces: `gp_task_ok`, `gp_task_fallback`, `gp_task_recovery`, `gp_task_backend`
- Recovery suffix tokens (closed): `stall-recovered`, `tool-error-fixed`, `re-run:stall`, `re-run:tool-error`, `re-run:death`
- Fallback tokens unchanged: `teams-process-reaped`, `teams-unavailable`

- [ ] **Step 1: Write failing parse unit tests**

Append to `tests/test_parse.sh`:

```bash
# recovery suffix grammar (teams runtime robustness)
gp_task_ok "T2[teams:3] (stall-recovered)" && ok "task stall-recovered ok" || no "task stall-recovered ok"
gp_task_ok "T2[teams:2] (tool-error-fixed)" && ok "task tool-error-fixed ok" || no "task tool-error-fixed ok"
gp_task_ok "T2[crew:1] (re-run:stall)" && ok "task re-run:stall ok" || no "task re-run:stall ok"
gp_task_ok "T2[crew:1] (re-run:tool-error)" && ok "task re-run:tool-error ok" || no "task re-run:tool-error ok"
gp_task_ok "T2[crew:1] (re-run:death)" && ok "task re-run:death ok" || no "task re-run:death ok"
gp_task_ok "T2[teams:3] (re-run:evil)" && no "bad re-run token accepted" || ok "bad re-run token rejected"
gp_task_ok "T2[teams:3] (fallback:teams-unavailable)" && ok "fallback still ok" || no "fallback still ok"
[ "$(gp_task_recovery 'T2[teams:3] (stall-recovered)')" = "stall-recovered" ] && ok "recovery extract" || no "recovery extract"
[ "$(gp_task_recovery 'T2[teams:3] (re-run:stall)')" = "re-run:stall" ] && ok "re-run extract" || no "re-run extract"
[ "$(gp_task_recovery 'T2[teams:3]')" = "" ] && ok "recovery empty when none" || no "recovery empty when none"
```

- [ ] **Step 2: Run parse tests — expect new cases FAIL**

Run: `bash tests/test_parse.sh`
Expected: existing 68 pass; new recovery cases FAIL (grammar rejects suffix).

- [ ] **Step 3: Extend grammar in `goal_parse.sh`**

Replace `gp_task_ok` / `gp_task_fallback` / `gp_task_backend` block with:

```bash
# ---- task= id grammar (R12/A1: ledger law, enforced by the writer) ----------
# Optional trailing tag is either a fallback: token or a recovery token.
# Recovery vocabulary is CLOSED (teams runtime robustness).
gp_task_ok(){ printf '%s' "$1" | grep -qE \
  '^T[0-9]+\[(teams|crew):[0-9]+\]( *\((fallback:[a-z0-9-]+|stall-recovered|tool-error-fixed|re-run:(stall|tool-error|death))\))?$'; }
gp_task_fallback(){ printf '%s' "$1" | sed -nE 's/.*\(fallback:([a-z0-9-]+)\).*/\1/p'; }
gp_task_recovery(){ printf '%s' "$1" | sed -nE 's/.*\((stall-recovered|tool-error-fixed|re-run:(stall|tool-error|death))\).*/\1/p'; }
gp_task_backend(){ printf '%s' "$1" | sed -nE 's/.*\[(teams|crew):[0-9]+\].*/\1/p'; }
```

- [ ] **Step 4: Run parse tests — expect PASS**

Run: `bash tests/test_parse.sh`
Expected: `pass=78 fail=0` (or whatever the new total is; zero FAIL lines).

- [ ] **Step 5: Extend audit A3**

In `scripts/goal_audit.sh`, replace the A3 case block with:

```bash
  case "$t" in
    *'(fallback:'*)
      suf=$(gp_task_fallback "$t")
      case "$suf" in
        teams-process-reaped|teams-unavailable) : ;;
        *) bad "A3 fallback-vocabulary:$suf" ;;
      esac ;;
    *'('*) 
      # recovery tags also come from a closed list
      rsuf=$(gp_task_recovery "$t")
      case "$rsuf" in
        '' ) bad "A3 recovery-vocabulary:$t" ;;
        stall-recovered|tool-error-fixed|re-run:stall|re-run:tool-error|re-run:death) : ;;
        *) bad "A3 recovery-vocabulary:$rsuf" ;;
      esac ;;
  esac
```

Also update the A3 header comment to name recovery suffixes.

- [ ] **Step 6: Commit**

```bash
git add scripts/goal_parse.sh scripts/goal_audit.sh tests/test_parse.sh
git commit -m "feat(parse): closed recovery suffix vocabulary on task= ids"
```

---

### Task 2: `goal_team.sh health` probe + heartbeat touch

**Files:**
- Modify: `scripts/goal_team.sh` (add `health` command; `send` touches heartbeat)
- Test: `tests/cases.inc.sh` (append scenario block ~T122)

**Interfaces:**
- Produces CLI: `goal_team.sh health --project DIR`
- Output line: `name|liveness|idle_s|last_touch|open_items|err_tag`
- Sidecar: `.goal/team/heartbeat/<name>.ts` (ISO timestamp)
- Env: `GOAL_STALL_SEC` (default 300)
- Exit: 0 with report; 4 if no team

- [ ] **Step 1: Write failing scenario tests**

Append to `tests/cases.inc.sh` (after 121b):

```bash
# 122 teams runtime health probe (robustness v1)
# 122a health lists members and empty err when healthy
mkproj t122a
bash "$TEAM" init --project "$T/t122a" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122a" --add --name w1 --role backend --prompt 'x' --scope 'src' >/dev/null
mkdir -p "$T/t122a/.goal/team/heartbeat" "$T/t122a/src"
date -u +%Y-%m-%dT%H:%M:%SZ > "$T/t122a/.goal/team/heartbeat/w1.ts"
echo x > "$T/t122a/src/a.txt"
out=$(bash "$TEAM" health --project "$T/t122a" 2>&1); assert_rc "122a health rc0" 0 $?
assert_has "122a health has w1 row" 'w1|' "$out"
assert_has "122a idle is numeric" 'w1|[a-z]+|[0-9]+' "$out"
printf '%s' "$out" | grep -qE 'w1\|[^|]*\|[^|]*\|[^|]*\|[^|]*\| *$' \
  && ok "122a healthy has empty err_tag" || no "122a unexpected err_tag: $out"

# 122b stall fires when idle_s exceeds GOAL_STALL_SEC
mkproj t122b
bash "$TEAM" init --project "$T/t122b" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122b" --add --name w1 --role backend --prompt 'x' --scope 'src' >/dev/null
mkdir -p "$T/t122b/.goal/team/heartbeat" "$T/t122b/src"
# ancient heartbeat
printf '2020-01-01T00:00:00Z\n' > "$T/t122b/.goal/team/heartbeat/w1.ts"
echo old > "$T/t122b/src/a.txt"
touch -d '2020-01-01' "$T/t122b/src/a.txt" 2>/dev/null || touch -t 202001010000 "$T/t122b/src/a.txt"
out=$(GOAL_STALL_SEC=1 bash "$TEAM" health --project "$T/t122b" 2>&1)
assert_has "122b stall tag" 'err_tag=stall\||stall$' "$out" 
printf '%s' "$out" | grep -q 'stall' && ok "122b stall named" || no "122b stall missing: $out"

# 122c tool-error vocab hits
mkproj t122c
bash "$TEAM" init --project "$T/t122c" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122c" --add --name w1 --role backend --prompt 'x' --scope 'src' >/dev/null
printf '{"from":"w1","text":"Error: command not found","timestamp":"2026-10-14T00:00:00Z","read":true}\n' \
  > "$T/t122c/.goal/team/inboxes/w1.jsonl"
out=$(bash "$TEAM" health --project "$T/t122c" 2>&1)
printf '%s' "$out" | grep -q 'tool-error' && ok "122c tool-error tag" || no "122c tool-error missing: $out"

# 122d tool-error vocab false friend (no hit)
mkproj t122d
bash "$TEAM" init --project "$T/t122d" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122d" --add --name w1 --role backend --prompt 'x' --scope 'src' >/dev/null
printf '{"from":"w1","text":"no errors here, all good","timestamp":"2026-10-14T00:00:00Z","read":true}\n' \
  > "$T/t122d/.goal/team/inboxes/w1.jsonl"
out=$(bash "$TEAM" health --project "$T/t122d" 2>&1)
printf '%s' "$out" | grep -q 'tool-error' && no "122d false friend hit" || ok "122d false friend clean"

# 122e open_items from work-plan
mkproj t122e
bash "$TEAM" init --project "$T/t122e" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122e" --add --name w1 --role backend --prompt 'x' --scope 'src' >/dev/null
printf -- '- [ ] T1 | w1 | first | files: a\n- [x] T2 | w1 | done | files: b\n' > "$T/t122e/.goal/work-plan.md"
out=$(bash "$TEAM" health --project "$T/t122e" 2>&1)
assert_has "122e open_items=1" 'w1|.*\|1\|' "$out"

# 122f send touches heartbeat
mkproj t122f
bash "$TEAM" init --project "$T/t122f" --team goal >/dev/null
bash "$TEAM" roster --project "$T/t122f" --add --name w1 --role backend --prompt 'x' >/dev/null
bash "$TEAM" send --project "$T/t122f" --from controller --to w1 --text 'wake' >/dev/null
[ -f "$T/t122f/.goal/team/heartbeat/w1.ts" ] && ok "122f heartbeat written on send" || no "122f heartbeat missing"
```

Note: if `touch -d` fails on this platform, use `touch -t`. Prefer portable `touch -t 202001010000`.

- [ ] **Step 2: Run tests — expect 122 FAIL**

Run: `bash tests/run_tests.sh --only 122 --jobs=1`
Expected: FAIL (unknown command `health` / missing heartbeat).

- [ ] **Step 3: Implement `health` + heartbeat in `goal_team.sh`**

1. Usage header: add `health` to command list.
2. Arg parse: `init|roster|send|inbox|status|health|delete)`.
3. After `need_team_dir` helpers, add:

```bash
touch_heartbeat(){
  mkdir -p "$td/heartbeat"
  now_iso > "$td/heartbeat/$1.ts"
}

# closed tool-error vocabulary (spec §5.3)
err_vocab_re='error:|exception:|traceback|panic:|exit status [1-9]|exit code [1-9]|rc=[1-9]|permission denied|command not found|no such file or directory|eacces|enoent|api error|rate limit'
```

4. In `send)`, after `deliver` for a concrete `--to` (not `*`), call `touch_heartbeat "$to"`. For broadcast, touch each delivered name.
5. New command:

```bash
  health)
    need_team_dir
    stall="${GOAL_STALL_SEC:-300}"
    case "$stall" in ''|*[!0-9]*) stall=300 ;; esac
    hbdir="$td/heartbeat"
    mkdir -p "$hbdir"
    now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    now_s=$(date -u +%s)
    echo "TEAM: HEALTH stall_sec=$stall"
    while IFS= read -r line; do
      [ -n "$line" ] || continue
      nm=$(printf '%s' "$line" | sed -n 's/.*"name":"\([^"]*\)".*/\1/p')
      sc=$(printf '%s' "$line" | sed -n 's/.*"scope":"\([^"]*\)".*/\1/p')
      act=$(printf '%s' "$line" | sed -n 's/.*"active":\([a-z]*\).*/\1/p')
      [ -n "$nm" ] || continue
      # liveness from roster active flag only — never invent "active"
      live=unknown
      [ "$act" = "true" ] && live=active
      [ "$act" = "false" ] && live=stopped
      # last_touch = max(heartbeat, inbox mtime, scope mtime)
      last_s=0
      last_iso=""
      hb="$hbdir/$nm.ts"
      if [ -f "$hb" ]; then
        last_iso=$(tr -d '\r\n' < "$hb")
        last_s=$(date -u -d "$last_iso" +%s 2>/dev/null || date -u -j -f %Y-%m-%dT%H:%M:%SZ "$last_iso" +%s 2>/dev/null || echo 0)
      fi
      ib="$inbox_dir/$nm.jsonl"
      if [ -f "$ib" ]; then
        ims=$(date -r "$ib" +%s 2>/dev/null || stat -c %Y "$ib" 2>/dev/null || echo 0)
        [ "${ims:-0}" -gt "$last_s" ] && last_s=$ims && last_iso=$(date -u -d "@$ims" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "$now")
      fi
      if [ -n "$sc" ] && [ -e "$project/$sc" ]; then
        sms=$(find "$project/$sc" -type f -printf '%T@\n' 2>/dev/null | sort -n | tail -1 | cut -d. -f1)
        [ -z "$sms" ] && sms=$(find "$project/$sc" -type f -exec stat -c %Y {} + 2>/dev/null | sort -n | tail -1)
        [ "${sms:-0}" -gt "$last_s" ] && last_s=$sms && last_iso=$(date -u -d "@$sms" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "$now")
      fi
      [ -n "$last_iso" ] || last_iso="$now"
      idle_s=$(( now_s - last_s ))
      [ "$idle_s" -lt 0 ] && idle_s=0
      # open work-plan items assigned to this name
      open_n=0
      if [ -f "$project/.goal/work-plan.md" ]; then
        open_n=$(grep -E '^\- \[ \]' "$project/.goal/work-plan.md" 2>/dev/null | grep -c "$nm" || true)
        open_n=${open_n:-0}
      fi
      # err_tag hint from last inbox text + stall/death
      err=""
      if [ "$live" = "stopped" ] || [ "$live" = "terminated" ]; then
        err=death
      fi
      if [ -f "$ib" ]; then
        last_txt=$(tr -d '\r' < "$ib" | tail -5 | tr '\n' ' ')
        printf '%s' "$last_txt" | grep -qiE "$err_vocab_re" && err=tool-error
      fi
      if [ -z "$err" ] && [ "$idle_s" -ge "$stall" ] && [ "$open_n" -gt 0 ]; then
        err=stall
      fi
      printf '%s|%s|%s|%s|%s|%s\n' "$nm" "$live" "$idle_s" "$last_iso" "$open_n" "$err"
    done < "$(roster_file)" ;;
```

6. `delete` remains delivery/fuse only (comment already true).

- [ ] **Step 4: Digest exemption check**

Confirm `goal_gate.sh` tree digest already skips `.goal*` (line ~69 `! -path './.goal*'`). Heartbeat under `.goal/team/heartbeat/` is therefore exempt. If not, add prune. Run one digest smoke on a project with heartbeat present.

- [ ] **Step 5: Run 122 suite — expect PASS**

Run: `bash tests/run_tests.sh --only 122 --jobs=1`
Expected: all 122* green.

- [ ] **Step 6: Commit**

```bash
git add scripts/goal_team.sh tests/cases.inc.sh
git commit -m "feat(team): health probe + heartbeat touch for runtime watchdog"
```

---

### Task 3: Recovery playbook docs + crew watch window

**Files:**
- Modify: `references/teams.md` (new § Runtime watchdog)
- Modify: `references/crew.md` (watch window §3.5 before Join)
- Modify: `tests/docs_consistency.sh` (pins)

**Interfaces:**
- Produces doc literals pinned by C5 (see Step 3 list)

- [ ] **Step 1: Append § Runtime watchdog to `teams.md`**

```markdown
## 7 Runtime watchdog (unattended robustness)

Between dispatch and join the controller **watches** the team. Gate still
decides GO; the watchdog only keeps the wave alive.

### 7.1 Health probe (mechanical)

`bash scripts/goal_team.sh health --project .` prints one row per member:

```
name|liveness|idle_s|last_touch|open_items|err_tag
```

- `err_tag`: empty | `death` | `stall` | `tool-error` (hint, not a verdict)
- Stall when `idle_s >= ${GOAL_STALL_SEC:-300}` **and** `open_items > 0`
- Progress = scope mtime ∪ inbox mtime ∪ heartbeat `.goal/team/heartbeat/<name>.ts`
  (digest-exempt). Thinking-only is not progress.

### 7.2 Taxonomy

| Class | Signal | Controller confirm |
|---|---|---|
| death | roster stopped/terminated + wake yields no heartbeat | transcript resumable? |
| stall | idle_s >= stall_sec and open work | long tool vs stuck |
| tool-error | closed vocab in last inbox/extract (error: / exit code / ENOENT / …) | one-line root cause |

### 7.3 Recovery playbook (resume-first, 2-strike, unknown → re-run)

```
classify → env_fixable? → fix workspace/brief → wake (breakpoint brief)
        → no progress → wake #2
        → 2 wakes failed OR not resumable → re-run THIS work-item
        → re-run failed again → existing fallback / BLOCKED
```

**Resume** when partial products exist. **Re-run** only the open failed item.

Breakpoint brief:

```
Continue task <id>.
Done so far: <files / checks green>
Still owed: <remaining AC or deliverable>
Blocked by (if any): <root cause one-liner>
Run: <named check>
Do not rewrite unrelated files. (R6)
```

### 7.4 Ledger honesty (task= suffix only)

Closed vocabulary — no new loop-log keys:

- `(stall-recovered)` — resumed after stall
- `(tool-error-fixed)` — env/brief fixed then resumed
- `(re-run:stall)` `(re-run:tool-error)` `(re-run:death)` — item redone
- `(fallback:teams-process-reaped)` `(fallback:teams-unavailable)` unchanged

Forbidden: mid-run TeamDelete; silent downgrade; inventing suffix tokens.

### 7.5 Watch window defaults

- Poll `health` immediately, then every 60s
- End watch when all wave items closed, or `GOAL_WATCH_MAX_SEC` (default 3600)
- Other members keep working while one is recovered
```

- [ ] **Step 2: Insert watch window in `crew.md` before §4 Join**

```markdown
## 3.5 Watch window (Teams backend)

After dispatch and before join, poll `goal_team.sh health` (first poll
immediately, then every 60s). On `death` / `stall` / `tool-error` for a
member, run the playbook in `teams.md` §7 against **that member only**.
Join with whatever closed; open failed items follow the playbook
(resume-first, 2-strike, re-run). Non-Teams backend: skip this window.
```

In §5 FAIL attribution, add one sentence: "Teams runtime faults are handled
in the watch window (teams.md §7) before join attribution."

- [ ] **Step 3: docs_consistency pins**

Add to the C5 needle list in `tests/docs_consistency.sh`:

```
references/teams.md|goal_team.sh health
references/teams.md|GOAL_STALL_SEC
references/teams.md|stall-recovered
references/teams.md|tool-error-fixed
references/teams.md|re-run:stall
references/teams.md|breakpoint brief
references/teams.md|NEVER a GO signal
references/crew.md|Watch window
scripts/goal_team.sh|err_tag
scripts/goal_audit.sh|recovery-vocabulary
scripts/goal_parse.sh|stall-recovered
```

(Adjust exact strings to match files — the needle is what must appear.)

- [ ] **Step 4: Run docs consistency**

Run: `bash tests/docs_consistency.sh`
Expected: `CONSISTENT`

- [ ] **Step 5: Commit**

```bash
git add references/teams.md references/crew.md tests/docs_consistency.sh
git commit -m "docs(teams): runtime watchdog playbook + crew watch window"
```

---

### Task 4: Audit recovery suffix acceptance + parse/audit regression

**Files:**
- Modify: `scripts/goal_audit.sh` (already partly in Task 1 — finish A3 recovery path + comment)
- Test: `tests/cases.inc.sh` (T123 audit scenarios)

**Interfaces:**
- Consumes: `gp_task_recovery` from Task 1

- [ ] **Step 1: Failing audit tests**

```bash
# 123 audit accepts recovery suffixes and rejects invented tokens
mkproj t123a
printf '## iteration 1\ntask=T2[teams:2] (stall-recovered)\nfiles_modified=a.txt\nchecks_pass=1\nchecks_fail=0\nchecks_unverifiable=0\nerror_signature=none\nprogress=yes\nexit_signal=no\nfalse_complete=no\ndigest=x\nscore=none\nstrategy_delta=none\n' > "$T/t123a/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t123a" 2>&1); assert_rc "123a recovery suffix clean" 0 $?

mkproj t123b
printf '## iteration 1\ntask=T2[teams:2] (re-run:stall)\nfiles_modified=a.txt\nchecks_pass=1\nchecks_fail=0\nchecks_unverifiable=0\nerror_signature=none\nprogress=yes\nexit_signal=no\nfalse_complete=no\ndigest=x\nscore=none\nstrategy_delta=none\n' > "$T/t123b/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t123b" 2>&1); assert_rc "123b re-run suffix clean" 0 $?

mkproj t123c
printf '## iteration 1\ntask=T2[teams:2] (invented:oops)\nfiles_modified=a.txt\nchecks_pass=1\nchecks_fail=0\nchecks_unverifiable=0\nerror_signature=none\nprogress=yes\nexit_signal=no\nfalse_complete=no\ndigest=x\nscore=none\nstrategy_delta=none\n' > "$T/t123c/.goal/loop-log.md"
out=$(bash "$AUDIT" --project "$T/t123c" 2>&1); assert_rc "123c invented suffix fails A1/A3" 1 $?
```

- [ ] **Step 2: Confirm FAIL then ensure audit+parse cover them**

Run: `bash tests/run_tests.sh --only 123 --jobs=1`

- [ ] **Step 3: Fix audit if needed (unknown parens tag must be A1 or A3 violation)**

Ensure `gp_task_ok` rejects `(invented:oops)` (already closed set) **or**
if a looser pattern slips through, A3 must `bad` it.

- [ ] **Step 4: Commit**

```bash
git add scripts/goal_audit.sh scripts/goal_parse.sh tests/cases.inc.sh
git commit -m "test(audit): recovery suffix allowlist teeth"
```

---

### Task 5: Full regression + install sync + README one-liner

**Files:**
- Modify: `README.md` (optional one line under Teams)
- Sync: `~/.claude/skills/goal-loop/`

- [ ] **Step 1: Optional README line under Teams backend**

Add after the hard rules list:

```markdown
- Unattended: controller watch window + `goal_team.sh health` (stall /
  tool-error / death → resume-first playbook in `references/teams.md` §7).
```

- [ ] **Step 2: Full suite**

Run: `bash tests/run_tests.sh --jobs=8`
Expected: `== total: pass=395+N fail=0 shards=8 ==`

- [ ] **Step 3: docs + parse**

Run: `bash tests/docs_consistency.sh` and `bash tests/test_parse.sh`
Expected: CONSISTENT / pass=fail0

- [ ] **Step 4: Sync install + push**

```bash
cp -f scripts/goal_team.sh scripts/goal_parse.sh scripts/goal_audit.sh \
      references/teams.md references/crew.md README.md \
      ~/.claude/skills/goal-loop/scripts/ # and references/ as appropriate
cp -f tests/cases.inc.sh tests/test_parse.sh tests/docs_consistency.sh \
      ~/.claude/skills/goal-loop/tests/
git add -A
git commit -m "feat: teams runtime robustness (health probe + recovery playbook)"
git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 \
    -c http.postBuffer=1048576 push origin main
```

- [ ] **Step 5: Quickstart still green**

Run: `bash examples/quickstart-one-shot/run.sh`
Expected: `PASS`

---

## Self-Review (plan author)

1. **Spec coverage:** health probe (T2), taxonomy+playbook docs (T3), suffix grammar/audit (T1/T4), watch window (T3), tests (T2/T4/T5), digest-exempt heartbeat (T2). Lead self-heal / option B / gate recovery explicitly out of scope. **Covered.**
2. **Placeholders:** none (all steps have code or exact commands).
3. **Type consistency:** CLI `health`; row format `name|liveness|idle_s|last_touch|open_items|err_tag`; suffixes `stall-recovered` / `tool-error-fixed` / `re-run:{stall,tool-error,death}`; helpers `gp_task_recovery`, `touch_heartbeat`. Names match across tasks.
