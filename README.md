# goal-loop

**EN** — A Claude Code skill that fuses two open-source disciplines into one loop: *ralph-claude-code*'s dual-condition exit gate with *fable-mode*'s adversarial checker panel. The core promise (v1.2.1): **the model can never self-declare completion** — only an external shell gate (`goal_gate.sh`) can certify GO, and since v1.2 the gate **re-runs every deterministic check itself** (zero model in the trust chain); judged quality claims go to cold checker seats. For open-ended "make it as good as possible" objectives, the `forge` exit ends the loop on **verification exhaustion** (K consecutive dry adversarial rounds), not on floors alone. v1.2.1 hardens the gate: the approval stamp also freezes the exit policy, negative assertions (`expected: exit=N`) and CR-safe metric reads are deterministic, and same-digest judged PASSes carry forward without re-seating. v1.3 adds `--time-budget=N` — a whole-loop wall-clock fuse with a graceful best-so-far ending.

**中文** — 一个 Claude Code skill，把两个开源项目的纪律融合进一条循环：*ralph-claude-code* 的双条件退出门控 + *fable-mode* 的对抗式检查员面板。核心承诺（v1.2.1）：**模型永远不能自我宣布完成** —— 只有外部 shell 门控（`goal_gate.sh`）能发 GO，且 v1.2 起门控**亲自重跑每条确定性检查**（信任链零模型参与）；判断类质量声明才交冷检查席。对"尽可能完美"类开放目标，`forge` 退出以**验证穷尽**收尾（连续 K 轮挖不出有证据的新缺陷），而非仅凭地板达标。v1.2.1 加固门控：批准戳同时冻结退出策略（exit: 行）、负向断言（`expected: exit=N`）与 CR 安全的指标读数归入确定性、同指纹的 judged PASS 可 carry-forward 免重开席位。v1.3 新增 `--time-budget=N`——整个 loop 的墙钟保险丝，到期优雅交付 best-so-far。

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

## Modes & flags / 模式与参数（v1.3）

```
/goal-loop --mode=quick|standard|deep [--max-iterations=N] [--min-acs=N] [--auto] [--forge] <objective>
```

两个轴互相正交 / the two axes are orthogonal: `--mode` sets the **budget** (iterations,
AC count, panel size); `exit:` in the contract sets the **exit policy** (threshold vs
forge). Any budget can carry either policy — `--forge` is just sugar for
"`exit: forge` + deep budget".

### Flag reference / 参数一览

| flag | 作用 / effect | 默认 default |
|---|---|---|
| `--mode=quick` | 3 轮 / 2-4 条 AC / 仅 req 席 · for small but multi-check tasks | — |
| `--mode=standard` | 6 轮 / 4-6 条 AC / req 席 · everyday default | ✓ |
| `--mode=deep` | 12 轮 / 6-10 条 AC / req 席 + **每轮强制对抗席**（一个检查席专职合法搞挂一项检查，逼出 fix→recheck 路径；全程一轮全绿不配出 deep） | — |
| `--max-iterations=N` | 覆写模式的轮数预算 override the mode's budget | per mode |
| `--min-acs=N` | 契约 AC 条数下限 floor for AC count | per mode |
| `--auto` | 契约仍完整呈现，但立即盖章开跑不等确认；账本与交付物记 `approval=auto` 供事后审计。不可逆动作照样硬拒 | off |
| `--forge` | = 契约 `exit: forge` + deep 预算（见下） | off |
| `--time-budget=N` | 整个 loop 的墙钟保险丝，秒。盖章即起表；到期 rc=3 `time-budget-exhausted` **优雅收尾**：跑完在飞任务、交付 best-so-far + 未决清单，不是硬中断。续期 = 用户批准后改 state.rec 的 `deadline=` 行。到期前地板全过照常 GO | off |
| | （勿与 unattended 的 `goal_loop.sh --wallclock=SEC` 混淆——那个限制单次 `claude` 调用时长） | |

### Contract grammar in one view / 契约语法一览（v1.2.1）

```
exit: threshold        # 或 forge —— 每一行 exit: 都被批准戳覆盖，盖戳后改 = contract-tampered
- AC-1 | 产物仍是合法 HTML              | check: `bash validate.sh`          | expected: exit=0
- AC-2 | 空输入崩溃不再复现（负向断言） | check: `bash repro_crash.sh`       | expected: exit=1
- AC-3 | 压缩率不低于基线+5%            | check: `python ratio.py`           | expected: >=42.0
- AC-4 | 压缩后代码仍可被人读懂         | check: -                           | expected: judged
```

| `expected:` | 语义 meaning | 谁裁决 who decides |
|---|---|---|
| `exit=0`（或省略） | 命令成功即 PASS | **门控重跑**，零模型 |
| `exit=N` (N>0) | 负向断言：命令必须以 N 退出（"故障不再复现"） | **门控重跑** |
| `>=N` `<N` `==N` 等 | 指标：stdout 末行非空行必须是数字 | **门控重跑** |
| `judged`（或任意散文） | 质量声明，程序判不了（v1.1 旧契约自动落此路由） | 冷检查席，裁决须引证 |

`exit=N` 与 metric 是 v1.2.1 新增：以前"期望命令失败"和"数值阈值"要么写死在命令里、
要么被静默路由成 judged 烧席位——现在都是确定性项，归门控。

### Worked examples / 逐模式实例

**quick — 小目标也要真验证 small-but-multi-check:**
```
/goal-loop --mode=quick "把 src/ 里 AUTH_TIMEOUT 全改成 session_ttl，测试保持全绿"
```
契约 2-3 条 AC，全是确定性：`exit=1`（旧名消失，负向断言）+ `exit=0`（测试套件）。
两轮收工，门控重跑代替面板烧席。

**standard — 日常默认:**
```
/goal-loop "写一个 CSV 去重工具，含 CLI、错误处理和 README"
```
6 轮预算，功能 AC（确定性）+ 文档质量 1 条 `judged`。

**deep — 对抗席常驻 adversarial seat every round:**
```
/goal-loop --mode=deep "给这个解析器补齐边界输入测试并修复暴露的 bug"
```
每轮对抗席专职合法搞挂一项检查——它抓到 FAIL 是成功不是失败。

**forge — 优化到挖不动为止（v1.2 退出策略，v1.2.1 效率补丁）:**
```
/goal-loop --forge "把这个 HTML 压缩器推到尽可能接近无损最优"
```
契约如上面的语法示例（`exit: forge` + 一条 metric AC）。GO 条件：地板全过 **且**
连续 `dry_limit`（默认 3）轮干轮（面板+对抗席+critic 挖不出有证据的新发现、
fix-now 清零）**且** critic 冷答案为空（归档 `.goal/evidence/critic-iter-N.md`）。
记账：`bash scripts/goal_ctl.sh close-iteration --project . --task T4 --files minify.py \
  --checks-pass 3 --checks-fail 0 --checks-unverifiable 0 --dry yes` ——
`--dry` 在 forge 契约上必填；`--dry yes` 与 `checks-fail>0` 并存会被拒（rc=4）。
干轮树通常没动：已判工件的 PASS 按 carry-forward 重绑（`carried=yes`）即可，
不重开席位——这是 forge 长跑最大的 token 节省（v1.2.1）。预算用尽但没干透 →
rc=3 `budget-fuse`：问你续期还是交付 best-so-far，保险丝从不认证完成。

**--auto — 批量活不想等审批:**
```
/goal-loop --auto "把仓库里 47 个配置文件补齐缺失的字段注释"
```
契约秒盖章开跑，账本与交付物带 `approval=auto`；涉及不可逆外部动作的目标两种模式
下都直接拒绝执行。

## Unattended mode / 无人值守模式（可选）

```bash
bash ~/.claude/skills/goal-loop/scripts/goal_loop.sh --init      # 播种 .goal/
# 填好 .goal/goal.md 的 AC 并取得批准戳后：
bash ~/.claude/skills/goal-loop/scripts/goal_loop.sh --continue --max-iterations=6
```

The outer shell loop trusts **only the gate's exit code** — 0 DELIVERED, 3 BLOCKED,
4 state error, anything else → next round. `--dry-run` exercises it without calling
the API. Prefer all-deterministic contracts here: R7 binds judged verdicts to the
tree digest, so a contract with judged ACs re-judges the whole panel every round
unattended. 外层循环只信退出码；`--dry-run` 可不调 API 演练。无人值守契约应尽量
全确定性——judged AC 每轮都会被 R7 强制全量重判。

## The gate / 门控速查

| rc | meaning / 含义 | typical reasons / 常见原因 |
|---|---|---|
| 0 | GO, deliverable / 可交付 | — |
| 2 | NO-GO, keep iterating / 继续迭代 | no-approval, contract-tampered, not-claimed, verdicts-stale, open-FAIL, **check-broken, check-mutated-tree**, evidence-missing, unverifiable-excessive, **not-dry (forge)**, budget-exhausted |
| 3 | BLOCKED, stop & report / 停止上报 | breaker-open, false-completes≥2, stagnation, repeated-error, **budget-fuse (forge)** |
| 4 | state error / 状态错误 | no-goal-dir, missing-key, unknown-flag, **bad-check-timeout (v1.2.1)** |

Every judged verdict is bound to `(iteration, tree-digest)`. Touch one file under audit and
all judged verdicts go stale — the loop must re-judge (R7); deterministic ACs are exempt —
the gate re-runs them at every exit. Exception (v1.2.1): a judged PASS whose digest is
UNCHANGED may be re-bound to a later iteration (`carried=yes`, original evidence cited) —
same bytes, same truth, no re-seat; FAIL/UNVERIFIABLE never carry, and there is no
covered-set sharding across digests. Check 4b blocks the loop when two consecutive
iterations grind on the same error signature.
判断类裁决绑定 `(迭代号, 树指纹)`；树一动全部过期、强制重判（R7）；确定性 AC 豁免——门控
每次出口亲自重跑。v1.2.1 例外：digest 未变的 judged PASS 可重绑到新迭代（`carried=yes`，
引证原 evidence），不重开席位；FAIL/UNVERIFIABLE 永不 carry；跨指纹不搞覆盖集分片。
连续两轮踩同一错误签名会被熔断（4b）。

## Anti-gaming rules R1–R8 / 防作弊八规

- **R1** false-complete counting: two gate-caught false claims → halt BLOCKED / 假完成两次即熔断
- **R2** re-running a **seat judgment** is illegal while its files are unchanged (gate re-runs are measurement, always legal) / 指纹未动的判断席复跑不算工作（门控重跑是测量，不受限）
- **R3** the stamped contract is frozen — since v1.2.1 including every `exit:` line (flipping forge→threshold after stamping is contract-tampered) / 契约盖章即冻结——v1.2.1 起所有 `exit:` 行一并入戳，盖戳后翻转退出策略 = contract-tampered
- **R4** UNVERIFIABLE ≤ ⅓ of judged ACs, always with PROBE/REASON / 不可验证项限额且必须给出探测与理由
- **R5** checker briefs carry verbatim AC text + paths only — never the producer's reasoning (judged seats; deterministic ACs are gate-evidenced) / 简报零污染
- **R6** workers never touch `.goal/` / worker 禁触状态目录
- **R7** stale judged verdicts are void after any digest move; same-digest PASSes may carry forward (v1.2.1) / 过期裁决作废；同指纹 PASS 可 carry-forward 免重席
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
