# goal-loop

**EN** — A Claude Code skill that fuses two open-source disciplines into one loop: *ralph-claude-code*'s dual-condition exit gate with *fable-mode*'s adversarial checker panel. The core promise (v1.2): **the model can never self-declare completion** — only an external shell gate (`goal_gate.sh`) can certify GO, and since v1.2 the gate **re-runs every deterministic check itself** (zero model in the trust chain); judged quality claims go to cold checker seats. For open-ended "make it as good as possible" objectives, the `forge` exit ends the loop on **verification exhaustion** (K consecutive dry adversarial rounds), not on floors alone.

**中文** — 一个 Claude Code skill，把两个开源项目的纪律融合进一条循环：*ralph-claude-code* 的双条件退出门控 + *fable-mode* 的对抗式检查员面板。核心承诺（v1.2）：**模型永远不能自我宣布完成** —— 只有外部 shell 门控（`goal_gate.sh`）能发 GO，且 v1.2 起门控**亲自重跑每条确定性检查**（信任链零模型参与）；判断类质量声明才交冷检查席。对"尽可能完美"类开放目标，`forge` 退出以**验证穷尽**收尾（连续 K 轮挖不出有证据的新缺陷），而非仅凭地板达标。

```
objective → contract (AC-1..N, each with a NAMED failable check) → user approval stamp
  → loop: worker produces artifact → gate re-runs deterministic checks · cold seats judge quality claims
    → fix, re-check only FAILs → claim exit → goal_gate.sh --check decides
  → GO only when every AC holds at THIS digest (forge: floors + K-round dry streak + empty completeness critic)
```

---

## Install / 安装

Two pieces, both required / 两件套，缺一不可：

```bash
# 1) skill本体 → Claude Code 的 skills 目录
git clone https://github.com/samirliu/goal-loop.git
mkdir -p ~/.claude/skills
cp -r goal-loop/SKILL.md goal-loop/INTEGRATION.md goal-loop/assets \
      goal-loop/references goal-loop/scripts goal-loop/tests ~/.claude/skills/goal-loop/

# 2) 5个agent定义 → agents 目录
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
# 场景套件应 52/52 全绿 —— 门控语义的完整回归
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
3. One task per iteration: a worker agent produces the artifact. Deterministic ACs are
   re-run BY THE GATE (`goal_gate.sh --verify` / inline at exit) — no model involved; a
   cold requirements seat judges the `judged` quality claims and nominates missed claims.
   Ternary verdicts — PASS / FAIL / UNVERIFIABLE — each with quoted command output.
   每迭代一个任务：worker 产工件；确定性 AC 由**门控亲自重跑**（零模型参与），判断类
   质量声明交冷检查席裁决（并提名遗漏声明）；三元裁决且必须引证输出。
4. Every iteration ends with a `---GOAL_STATUS---` block — which the gate deliberately
   does **not** trust. The authority is `bash scripts/goal_gate.sh --check`
   (0=GO, 2=NO-GO, 3=BLOCKED, 4=state error).
   每轮末尾的状态块门控**故意不读**；唯一权威是门控退出码。

## Modes & flags / 模式与参数（v1.2）

```
/goal-loop --mode=quick|standard|deep [--max-iterations=N] [--min-acs=N] [--auto] [--forge] <objective>
```

**EN** — `quick` = 3 iterations / 2-4 ACs · `standard` = 6 / 4-6 · `deep` = 12 / 6-10 with a **mandatory adversarial seat** (one checker is assigned to legitimately break a check each iteration, exercising the fix→recheck path). `--auto` skips the approval wait: the contract is still shown in full, stamped immediately, and the ledger records `approval=auto` for after-the-fact audit. **`--forge`** (or `exit: forge` in the contract) switches the exit policy for maximization objectives: GO requires floors **plus** a K-round dry streak (`dry_limit`, default 3 — panel + adversarial seat + completeness critic find no new evidence-backed finding) **plus** an empty completeness-critic answer; `max_iterations` becomes a pure fuse (rc=3 `budget-fuse` → extend or deliver best-so-far). In-session bookkeeping is one Bash call: `scripts/goal_ctl.sh close-iteration ...` (`--dry` is mandatory on forge contracts).

**中文** — `quick` = 3 轮 / 2-4 条 AC · `standard` = 6 / 4-6 · `deep` = 12 / 6-10 且带**强制对抗席**（每轮一个检查席专职合法搞挂一项检查，逼出修复路径）。`--auto` 跳过审批等待：契约仍完整呈现、立即盖章，账本记 `approval=auto` 供事后审计。**`--forge`**（或契约写 `exit: forge`）为最大化目标切换退出策略：GO = 地板全过 **且** 连续 `dry_limit`（默认 3）轮"面板+对抗席+completeness critic 挖不出任何有证据的新发现、fix-now 发现项清零" **且** critic 冷答案为空；`max_iterations` 退化为纯保险丝（rc=3 `budget-fuse` → 续期或交付 best-so-far）。会话内记账一条命令：`scripts/goal_ctl.sh close-iteration ...`（forge 契约必带 `--dry`）。

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
| 2 | NO-GO, keep iterating / 继续迭代 | no-approval, contract-tampered, not-claimed, verdicts-stale, open-FAIL, **check-broken, check-mutated-tree**, evidence-missing, unverifiable-excessive, **not-dry (forge)**, budget-exhausted |
| 3 | BLOCKED, stop & report / 停止上报 | breaker-open, false-completes≥2, stagnation, repeated-error, **budget-fuse (forge)** |
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

Self-audited with its own protocol (v1.2): 5 acceptance criteria (4 deterministic,
gate-re-run; 1 judged, cold seat), a real bug caught by the seat
(close-iteration refusals left an orphan loop-log block — fixed + regression-tested),
final line `GATE: GO ... ac=5 pass=5 unverified=0 mode=threshold` — the skill certified
itself by the same gate it ships. 本 skill 用它自己的协议审计了它自己（v1.2）：5 条
验收标准（4 条确定性由门控重跑、1 条判断类交冷席），冷席抓出并修复了一个真实 bug
（close-iteration 拒绝后遗留孤儿账本块——已修 + 回归测试），最终 `GATE: GO` ——
卖的门，先过自己。
