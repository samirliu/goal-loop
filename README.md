# goal-loop

**EN** — A Claude Code skill that fuses two open-source disciplines into one loop: *ralph-claude-code*'s dual-condition exit gate with *fable-mode*'s adversarial checker panel. The core promise: **the model can never self-declare completion** — only an external shell gate (`goal_gate.sh`) can certify GO, and every verdict it accepts must be bound to a tree digest with quoted evidence.

**中文** — 一个 Claude Code skill，把两个开源项目的纪律融合进一条循环：*ralph-claude-code* 的双条件退出门控 + *fable-mode* 的对抗式检查员面板。核心承诺：**模型永远不能自我宣布完成** —— 只有外部 shell 门控（`goal_gate.sh`）能发 GO，且它接受的每条裁决都必须绑定树指纹并引证输出。

```
objective → contract (AC-1..N, each with a NAMED failable check) → user approval stamp
  → loop: worker produces artifact → cold checker panel judges → fix, re-check only FAILs
  → claim exit → goal_gate.sh --check decides → GO only when every AC holds at THIS digest
```

---

## Install / 安装

Two pieces, both required / 两件套，缺一不可：

```bash
# 1) skill本体 → Claude Code 的 skills 目录
git clone https://github.com/samirliu/goal-loop.git
mkdir -p ~/.claude/skills
cp -r goal-loop/SKILL.md goal-loop/INTEGRATION.md goal-loop/assets \
      goal-loop/references goal-loop/scripts ~/.claude/skills/goal-loop/

# 2) 5个agent定义 → agents 目录
mkdir -p ~/.claude/agents
cp goal-loop/agents/*.md ~/.claude/agents/
```

- Windows（git-bash）路径同上：`C:\Users\<你>\.claude\skills\goal-loop\` 与 `C:\Users\<你>\.claude\agents\`。
- 依赖：`grep / sed / awk(gawk) / sha1sum / cksum`，**无 jq**；CR 与 `LC_ALL` 已内置处理。
- Smoke test / 冒烟验证（不耗 API）：

```bash
bash ~/.claude/skills/goal-loop/scripts/goal_gate.sh --check
# 无 .goal/ 的目录里应返回 rc=4, reason=no-goal-dir —— 说明门控在岗
```

## Quick start — in-session / 快速开始 — 会话内

```
/goal-loop <objective>
```

1. The controller decomposes your objective into a contract: `AC-1..N`, each a yes/no
   statement **plus the exact command that settles it** (a check must be able to FAIL).
   控制器把目标分解为契约：每条 AC = 可判定的 yes/no 陈述 + 能让它失败的指名检测命令。
2. You approve → the AC section is frozen by a sha1 stamp. After that, criteria changes
   go through proposals, never silent edits (R3).
   你批准后 AC 正文按哈希冻结；之后改标准只能走提案，不能偷改（R3）。
3. One task per iteration: a worker agent produces the artifact; a cold checker panel
   (2× mechanical + 1× requirements; disputes escalate to an adjudicator) judges it with
   ternary verdicts — PASS / FAIL / UNVERIFIABLE — each with quoted command output.
   每迭代一个任务：worker 产工件；冷检查面板裁决（争议升级裁决人）；三元裁决且必须引证输出。
4. Every iteration ends with a `---GOAL_STATUS---` block — which the gate deliberately
   does **not** trust. The authority is `bash scripts/goal_gate.sh --check`
   (0=GO, 2=NO-GO, 3=BLOCKED, 4=state error).
   每轮末尾的状态块门控**故意不读**；唯一权威是门控退出码。

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
| 2 | NO-GO, keep iterating / 继续迭代 | no-approval, contract-tampered, not-claimed, verdicts-stale, open-FAIL, evidence-missing, unverifiable-excessive, budget-exhausted |
| 3 | BLOCKED, stop & report / 停止上报 | breaker-open, false-completes≥2, stagnation, repeated-error |
| 4 | state error / 状态错误 | no-goal-dir, missing-key, unknown-flag |

Every verdict is bound to `(iteration, tree-digest)`. Touch one file under audit and
all verdicts go stale — the loop must re-judge (R7). Check 4b additionally blocks the
loop when two consecutive iterations grind on the same error signature.
每条裁决绑定 `(迭代号, 树指纹)`；树一动全部过期、强制重判（R7）。连续两轮踩同一错误签名也会被熔断（4b）。

## Anti-gaming rules R1–R7 / 防作弊七规

- **R1** false-complete counting: two gate-caught false claims → halt BLOCKED / 假完成两次即熔断
- **R2** re-running a check is illegal while its files are unchanged / 指纹未动的复跑不算工作
- **R3** the stamped contract is frozen / 契约盖章即冻结
- **R4** UNVERIFIABLE ≤ ⅓ of ACs, always with PROBE/REASON / 不可验证项限额且必须给出探测与理由
- **R5** checker briefs carry verbatim AC text + paths only — never the producer's reasoning / 简报零污染
- **R6** workers never touch `.goal/` / worker 禁触状态目录
- **R7** stale verdicts are void after any digest move / 过期裁决作废

## State / 状态文件（`.goal/`，纯文本，grep 即查询）

`goal.md`（契约+批准戳）· `state.rec`（计数器）· `loop-log.md`（迭代账本）·
`verdicts.rec`（裁决记录，6 字段管道分隔）· `logs/`（无人值守日志）

## More docs / 更多文档

- **[INTEGRATION.md](INTEGRATION.md)** — 详细接入指南（中文）：安装、权限建议、故障排查、harness 行为差异披露
- `references/exit-gate.md` — gate checks in order, digest algorithm, scenarios（门控规格）
- `references/checker-panel.md` — panel assembly & brief template（面板规程）
- `references/domain-patterns.md` — failable checks per artifact type（按工件类型的可失败检查库）

## Provenance / 出处

This repository is a clean-room reimplementation fusing ideas from
[ralph-claude-code](https://github.com/frankbria/ralph-claude-code) (MIT) and the
fable-mode checker-panel conventions — no verbatim source text from either.
本仓库是对两者思想的无原文重实现：ralph-claude-code（MIT）× fable-mode 面板纪律。

Self-audited with its own protocol: 10 acceptance criteria, adversarial panel,
final line `GATE: GO ... ac=10 pass=10 unverified=0` — the skill certified itself
by the same gate it ships. 本 skill 用它自己的协议审计了它自己：10 条验收标准、
对抗面板、最终 `GATE: GO` —— 卖的门，先过自己。
