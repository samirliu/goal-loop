# goal-loop

**EN** — goal-loop combines the DRIVE of the harness /goal (never stop until done) with the CREW of /team (parallel teammates on one deliverable) plus the layer both lack: an external acceptance gate with a frozen contract. **/goal 的驱动 + /team 的 crew + 一道谁都不能绕过的验收门。**

**v2.1.0** — two execution backends (default one-shot subagents; opt-in Agent Teams), one judge (the gate). 执行面两档、判命面一档。

**中文** — 一个 Claude Code skill，把两个开源项目的纪律融合进一条循环：*ralph-claude-code* 的双条件退出门控 + *fable-mode* 的对抗式检查员面板。核心承诺：**模型永远不能自我宣布完成** —— 只有外部 shell 门控（`goal_gate.sh`）能发 GO，且门控**亲自重跑每条确定性检查**（信任链零模型参与）；判断类质量声明交冷席终验。对"尽可能完美"类开放目标，`forge` 退出以**验证穷尽**收尾（连续 K 轮挖不出有证据的新缺陷），而非仅凭地板达标。

```
objective → contract (AC-1..N, each with a NAMED failable check) → user approval stamp
  → loop: crew wave (≤3 workers) → join → gate re-runs deterministic checks
    → GO  → deliver
    → NO-GO → next wave (never stop) · BLOCKED → stop & report
  → GO only when every AC holds at THIS digest
    (forge: floors + K-round dry streak + empty completeness critic)
```

---

## Install / 安装

Two pieces, both required / 两件套，缺一不可：

```bash
# 1) skill 本体 → Claude Code 的 skills 目录
git clone https://github.com/samirliu/goal-loop.git
mkdir -p ~/.claude/skills/goal-loop
cp -r goal-loop/SKILL.md goal-loop/VERSION goal-loop/assets \
      goal-loop/references goal-loop/scripts goal-loop/tests \
      ~/.claude/skills/goal-loop/

# 2) 5 个 agent 定义 → agents 目录
mkdir -p ~/.claude/agents
cp goal-loop/agents/*.md ~/.claude/agents/
```

- Windows（git-bash）路径同上：`C:\Users\<你>\.claude\skills\goal-loop\` 与 `C:\Users\<你>\.claude\agents\`。
- 依赖：`grep / sed / awk(gawk) / sha1sum / cksum`，**无 jq**；CR 与 `LC_ALL` 已内置处理。有 coreutils `timeout` 时每条门控重跑检查限时（默认 120s）。
- Smoke test / 冒烟验证（不耗 API）：

```bash
bash ~/.claude/skills/goal-loop/scripts/goal_gate.sh --check
# 无 .goal/ 的目录里应返回 rc=4, reason=no-goal-dir —— 说明门控在岗
bash ~/.claude/skills/goal-loop/tests/run_tests.sh
# 场景套件应 86/86 全绿 —— 门控语义的完整回归
bash ~/.claude/skills/goal-loop/tests/docs_consistency.sh
# 文档一致性（含 Teams 后端铁律字面量）应 CONSISTENT
```

## Quick start — in-session / 快速开始 — 会话内

```
/goal-loop <objective>
/goal-loop --teams <objective>          # optional Agent Teams backend
```

Four steps, no fifth / 四步循环，没有第五步：

1. **Contract / 契约** — decompose into `AC-1..N`, each a yes/no statement
   **plus the exact command that settles it** (a check must be able to FAIL).
   You approve with one word → AC section frozen by a sha1 stamp (R3).
   每条 AC = 可判定陈述 + 能让它失败的指名检测命令；你回一个字即盖章冻结。
2. **Dispatch / 派工** — ≤3 concurrent workers on disjoint file scopes;
   interfaces frozen in `.goal/interfaces.md` first.
   默认一波 subagent；`--teams` 换 Agent Teams 队友（见下）。
3. **Join + gate** — merge review, then `bash scripts/goal_gate.sh --check`
   re-runs every deterministic check. This is the **only** completion authority.
   合并审阅后门控重跑全部确定性检查——唯一的完成判定。
4. **Branch / 分岔** — GO → deliver. NO-GO → fix and take the next wave
   (the loop does not stop). BLOCKED → stop under the four parking rules.
   GO 交付；NO-GO 继续派工；BLOCKED 停车上报。

Judged quality claims are reviewed **once** by a fresh cold seat before you
claim exit — never by the producers. 判断类 AC 在 claim 前由全新冷席终验一次，
生产者不自裁。

## Flags / 参数

```
/goal-loop [--auto] [--time-budget=N] [--teams] <objective>
```

| flag | meaning / 含义 |
|---|---|
| `--auto` | still show the full contract summary, stamp immediately, ledger records `approval=auto` / 仍展示摘要，随即盖章记 `auto` |
| `--time-budget=N` | whole-loop wall-clock fuse; on expiry deliver best-so-far / 墙钟保险丝，到期优雅交付 |
| `--teams` | swap dispatch for an Agent Teams crew (see below) / 换 Agent Teams 后端 |

Exit policy is a **contract field**, not a mode: `exit: threshold` (default,
delivery/build) or `exit: forge` (maximization). No modes matrix. 退出策略写在
契约里（`exit: threshold|forge`），不再有 quick/standard/deep 模式矩阵——
exit 策略/预算/基线由控制器在摘要中推断声明，旗标只是覆写。

**forge** (optimization objectives / 优化类目标): GO requires floors **plus** a
K-round dry streak (`dry_limit`, default 3 — critic finds no new evidence-backed
finding) **plus** an empty completeness-critic answer; `max_iterations` is a pure
fuse (rc=3 `budget-fuse`). Metric ACs default to `baseline: delta` — stamping
requires `.goal/baseline.md` (smoke run = baseline measurement, repeats≥2).
forge 退出 = 地板全过 ∧ dry_streak≥dry_limit ∧ critic 空答案；盖章前必须有基线。

In-session bookkeeping is one Bash call: `scripts/goal_ctl.sh close-iteration ...`
(forge contracts require `--dry yes|no`). 会话内记账一条命令。

## Teams backend / Teams 后端（opt-in，native first）

**Native first.** `--teams` 的选择靠**工具面探测**，不靠 flag 内容：当前
harness 有原生 TeamCreate/TeamPlan/SendMessage 就直接用原生（持久队友 +
面板，一次 roster 审批）；没有才跑便携层。flag 只决定「要不要 team」，
工具列表决定「用哪种」。

**Native first.** Selection is by detection: if TeamCreate/TeamPlan/
SendMessage exist in the controller's tool list this run, native wins —
persistent teammates + panel. The **portable team layer**
(`scripts/goal_team.sh`, cc-haha file protocol: roster, per-agent inboxes,
`TeammateMessage`) is the fallback, guaranteeing multi-role crews work on
any bare harness.

Default = one-shot subagents. `--teams` swaps **only the execution surface**.

| | Work tracking / 工作追踪 | Court / 法庭 |
|---|---|---|
| where | `.goal/work-plan.md` + team roster/inbox | contract + gate + verdicts |
| says a work item is done | controller ticks work-plan | — |
| says the GOAL is done | — | `goal_gate.sh` rc=0 only |

**`TaskUpdate = completed` is NEVER a GO signal.** 任务表/工作计划标完成永远
不是 GO 信号。Hard rules:

- **No `isolation: worktree`** — digest must see every teammate edit. 禁 worktree。
- Negotiation via inbox/`MSG:` lines; interface changes bind only as file
  writes to `interfaces.md`. 可协商，落文件才算数。
- Judged cold seat is never a team member. 冷席永不进 team。
- Protocol: `references/teams.md`. CLI: `scripts/goal_team.sh --help`.

## Unattended mode / 无人值守模式（可选）

```bash
bash ~/.claude/skills/goal-loop/scripts/goal_loop.sh --init      # 播种 .goal/
# 填好 .goal/goal.md 的 AC 并取得批准戳后：
bash ~/.claude/skills/goal-loop/scripts/goal_loop.sh --continue --max-iterations=6
```

The outer shell loop trusts **only the gate's exit code** — 0 DELIVERED, 3 BLOCKED,
4 state error, anything else → next round. `--dry-run` exercises it without calling
the API. 外层循环只信退出码；`--dry-run` 可不调 API 演练。

## The gate / 门控速查

| rc | meaning / 含义 | typical reasons / 常见原因 |
|---|---|---|
| 0 | GO, deliverable / 可交付 | — |
| 2 | NO-GO, keep iterating / 继续迭代 | contract-tampered, not-claimed, verdicts-stale, open-FAIL, **check-broken, check-mutated-tree**, evidence-missing, unverifiable-excessive, **not-dry (forge)** |
| 3 | BLOCKED, stop & report / 停止上报 | breaker-open, false-completes≥2, stagnation, repeated-error, **budget-fuse (forge)**, time-budget-exhausted |
| 4 | state error / 状态错误 | no-goal-dir, missing-key, unknown-flag |

Every judged verdict is bound to `(iteration, tree-digest)`. Touch one file under audit and
all judged verdicts go stale — the loop must re-judge (R7); deterministic ACs are exempt —
the gate re-runs them at every exit. Check 4b blocks the loop when two consecutive
iterations grind on the same error signature.
判断类裁决绑定 `(迭代号, 树指纹)`；树一动全部过期、强制重判（R7）；确定性 AC 豁免——门控
每次出口亲自重跑。连续两轮踩同一错误签名会被熔断（4b）。

## Anti-gaming rules R1–R8 / 防作弊八规

- **R1** false-complete counting: two gate-caught false claims → halt BLOCKED / 假完成两次即熔断
- **R2** re-running a **seat judgment** is illegal while its files are unchanged (gate re-runs are measurement, always legal) / 指纹未动的判断席复跑不算工作（门控重跑是测量，不受限）
- **R3** the stamped contract is frozen / 契约盖章即冻结
- **R4** UNVERIFIABLE ≤ ⅓ of judged ACs, always with PROBE/REASON / 不可验证项限额且必须给出探测与理由
- **R5** checker briefs carry verbatim AC text + paths only — never the producer's reasoning (judged seats; deterministic ACs are gate-evidenced) / 简报零污染
- **R6** workers never touch `.goal/` / worker 禁触状态目录
- **R7** stale judged verdicts are void after any digest move / 过期裁决作废
- **R8** findings must bind evidence — manufactured discoveries are as forbidden as manufactured passes / 发现项必须绑证据：制造发现与制造通过同罪
- **R9** verify the verifier: metric/maximize numbers need a passing `probe:` (instrument alive) / 数字必须先过仪器自检
- **R10** `progress=no` must carry `strategy_delta=` (what changes next) / 无进展必须写策略修订
- **R11** `objective: maximize` never delivers below `best_score` / 主指标不许倒退交付

## State / 状态文件（`.goal/`，纯文本，grep 即查询）

`goal.md`（契约+批准戳）· `state.rec`（计数器）· `loop-log.md`（迭代账本）·
`verdicts.rec`（裁决记录，6 字段管道分隔）· `work-plan.md`（任务队列正本）·
`interfaces.md`（crew 接口契约）· `baseline.md`（forge 基线）· `evidence/`（席与检查证据）

## goal-loop vs the built-in /goal / 与内置 /goal 的对位

Claude Code ships a harness-native `/goal` (Stop hook + prompt evaluator).
Ground truth from the bundled sidecar JS: on **every stop** it spawns a
tool-using evaluator agent (full tool array, structured `{ok, reason}`,
fail-closed on evaluator error), sanitizes the denial reason (`<>&` strip,
240-char cap) into `Goal continuing: <reason>`, and rebuilds the goal
state from the transcript on resume. 内置 /goal 每次停顿起一个带工具的评估
agent（结构化输出、评估器出错 fail-closed、reason 消毒回注、transcript 重建状态）。

| axis / 维度 | /goal (built-in) | goal-loop (this skill) |
|---|---|---|
| verification / 验证 | discretionary - a fresh agent decides each stop what to check / 裁量式，每次停顿自定查什么 | pinned - named checks frozen in the stamped contract, the gate re-runs them exactly / 钉死在契约里，门控原样重跑 |
| regression protection / 回归保护 | none structurally / 结构性缺失 | every deterministic check re-runs at every exit / 出口全量重跑 |
| "done" definition / 完成定义 | one sentence, interpreted post-hoc / 一句话事后解释 | AC-1..N frozen at stamping, user-owned / 盖章冻结，定义权在用户 |
| failure semantics / 失败语义 | continue until the user kills it / 只有不结束 | BLOCKED · breakers · budget-fuse · time-budget · best-so-far |
| cost shape / 成本形态 | pays every stop (evaluator tax), even with nothing claimed / 每次停顿都付 | pays per wave; gate reruns are bash; gate-only rounds ~free / 按波次付费，门控重跑≈0 |
| audit / 审计 | transcript grep only | verdicts.rec + digest binding + evidence/ |
| setup / 门槛 | zero ceremony / 零仪式 | contract + approval, one-time / 契约+审批，一次性 |

**Don't stack them / 不要叠加**：/goal 的评估器会把 goal-loop 的 BLOCKED 判成
"未完成"强行续跑——两个外层循环打架，熔断语义被废。二选一。

Rule of thumb / 经验法则: a vague one-sentence objective with a human watching
→ `/goal` is the cheaper tool; there is no shame in it. Anything that must be
defended later — deliverables, optimization with metric deltas, auditable
completion — needs the pinned checks, regression re-runs and fuse semantics
that only goal-loop has; for optimization specifically, /goal cannot pin a
baseline or a noise floor, so "better" is judged on vibes while goal-loop
spends its tokens on deltas against a measured baseline. 一句话模糊目标、有人
盯着 → /goal 更省；要交付物、要指标 delta、要可审计完成 → goal-loop。
感知型高迭代目标（逼真/手感/文采）也是 /goal 主场——契约只能写代理指标时
Goodhart 必然发生。

**Physical tooth / 物理的牙**：register `scripts/goal_hook.sh` as a Stop hook
(see the install snippet in the script header) and the harness blocks stopping
only when a claimed exit is denied by the gate (rc=2) — /goal's tooth, without
its discretionary evaluator. rc=0/3/4 pass, fail-open.

## More docs / 更多文档

- `references/gate.md` — rules R1–R8, check order, schemas（门控规格与规则）
- `references/crew.md` — crew protocol, Teams backend, judged-seat brief（派工与 Teams 协议）
- `references/teams.md` — portable Agent-Teams layer（便携 team 协议，零 harness 依赖）
- `references/patterns.md` — failable check shapes per artifact type（可失败检查形状库）
- `assets/goal.contract.md` — contract template（契约模板）

## Provenance / 出处

This repository is a clean-room reimplementation fusing ideas from
[ralph-claude-code](https://github.com/frankbria/ralph-claude-code) (MIT) and the
fable-mode checker-panel conventions — no verbatim source text from either.
本仓库是对两者思想的无原文重实现：ralph-claude-code（MIT）× fable-mode 面板纪律。

Self-audited with its own protocol (v1.2): 5 acceptance criteria (4 deterministic,
gate-re-run; 1 judged, cold seat), a real bug caught by the seat
(close-iteration refusals left an orphan loop-log block — fixed + regression-tested),
final line `GATE: GO ... ac=5 pass=5 unverified=0 mode=threshold` — the skill certified
itself by the same gate it ships. 本 skill 用它自己的协议审计了它自己（v1.2）：
卖的门，先过自己。
