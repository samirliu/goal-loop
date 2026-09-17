---
name: goal-loop
description: |-
  Goal-driven loop combining the DRIVE of the harness /goal (never stop until
  done) with the CREW of /team (parallel teammates sharing one deliverable)
  plus the layer both lack: an EXTERNAL ACCEPTANCE GATE. The controller
  decomposes an objective into an approved acceptance-criteria contract,
  dispatches crew waves of up to 3 parallel subagents, joins their output,
  and re-runs every deterministic check via scripts/goal_gate.sh - the model
  can never self-declare completion. Trigger: "/goal-loop [objective]",
  "loop until done", "keep optimizing until it stops improving", "verify
  every angle". Not for trivial one-pass tasks, pure Q&A, or actions with
  irreversible side effects.
---

# Goal Loop (v2.0.0)

**身份：/goal 的驱动 + /team 的 crew + 一道谁都不能绕过的验收门。**

| | /goal | /team | goal-loop |
|---|---|---|---|
| 驱动 | 干活→停→评估→继续 | 无 | 同 /goal：gate 说 NO-GO 就继续派工 |
| 执行 | 单线程 | crew 分工 | 同 /team：teammates 并行 |
| 状态 | transcript | 共享任务表 | 磁盘账本（`.goal/`） |
| 完成判定 | haiku 评估器 | 自报 completed | **门控重跑确定性检查** |
| 独有 | — | — | **契约**（done 的定义权在用户） |

You are the controller. Your loop has four steps and no fifth:

```
1. 契约   AC-1..N + 命名检查 → 压缩摘要 → 用户一个字批准 → 盖章冻结
2. 派工   ≤3 个并发 subagent 执行互不相交的任务域（接口契约进简报）
3. Join   合并审阅 → gate --check 重跑全部确定性检查
4. 分岔   GO → 交付；NO-GO → 从账本取下一批 → 回到 2（不停）
```

## 停车规则（只有四类，其余不问）

不可逆/破坏性操作；安全敏感动作；工作区外的共享副作用（merge/push/发布）；
契约需要修改（R3：盖戳后你只能提案）。其余一切冲突与歧义：**裁决并入账
（`Ruling: 决定 — 理由 — 错了损失什么`），继续**。错误的裁决浪费的是用户看
得见、可撤销的重工；停在问题上浪费的是用户一整天。

`scripts/goal_hook.sh`（Stop hook，已装）在最后一块账本声称完成而门控回答
rc=2 时物理阻止停车，并把门控 reason 注回——兜底假完成。

## Step 1 契约

- 每条 AC：`- AC-N | <yes/no 陈述> | check: \`<命令>\` | [baseline: delta|abs] | expected: <spec>`
- spec：`exit=0`（默认）/ 数值比较（`>=60`，命令最后一行输出该数）/ `judged`
- **Goodhart 哨兵**：写每条 AC 自问"不推进目标能满足它吗"——能则是代理
  指标，重写或删。尺寸/比例类 AC 必须引用真实规格来源。
- 盖章前冒烟每条检查（跑不了的当场改写）；优化类目标冒烟跑即基线测量，
  写入 `.goal/baseline.md`（forge 契约必须，stamp 校验）。
- 压缩摘要（一屏：目标行 + exit 策略/预算声明 + AC 表含检查命令逐字 +
  基线值）→ 用户回一个字即显式批准。摘要里声明你的推断：exit 策略
  （交付/构建→threshold；优化/尽可能好→forge）、预算、基线标记。
- `--auto`：仍展示摘要，随即盖章记 `auto`。`--time-budget=N`：墙钟保险丝。

## Step 2 crew 派工

- 拆解出互不相交的任务域；**接口先行**：模块边界/共享类型/命名约定写入
  `.goal/interfaces.md`（crew 启动时冻结，改走提案）——worker 间唯一的
  协作通道是文件与你的简报。
- 同一消息并发 ≤3 个 Agent 调用（general-purpose + 角色注入；未注册
  goal-* 类型属正常）。每个简报：任务、确切输出路径、文件域（"只碰
  这些"）、通过条件、"返回证据（命令+输出）"、禁触 `.goal/`、禁 spawn。
- 拆解不出 ≥2 个说得清接口的模块 → 退串行单任务（记录原因）。
- Worker 的执行工艺（怎么调试、怎么组织代码）是它自己的事——不把
  goal-loop 的规则塞进简报。

## Step 3 Join + gate

- 合并审阅：worker 不共享发现，你来补；接口冲突 → 一轮串行修复；
  两轮未解 → 退回串行并记录。
- `bash scripts/goal_gate.sh --check`：重跑全部确定性检查、校验指纹与
  账本——这是唯一的完成判定。`--verify [AC-ID]` 单独复跑。
- loop-log 记 `task=T2[crew:3]` + 各 worker 文件清单。

## Step 4 分岔

- GO（rc=0）→ 交付。NO-GO（rc=2）→ 修 FAIL（确定性：门控复跑即判定；
  按域隔离）→ 下一波。BLOCKED（rc=3）→ 停车四类之一种，报告。
- **冷席终验（judged AC）**：只在第一次准备 claim EXIT_SIGNAL 前，派一个
  全新视觉/判读席（简报只带 AC 原文 + 证据路径 + rubric 锚点，无你的推
  理）。PASS → 绑定裁决交付；FAIL → 修复再来。procedural 3D/视觉任务：
  生产期间你自己每轮看截图（快节奏自视），门控只测确定性面。
- 熔断：`time_budget` 墙钟、`no_progress_limit` 停滞、迭代预算——到期走
  graceful best-so-far 交付。优化类目标（forge）以 `dry_limit` 轮"确定性
  全绿且无新发现"为穷尽退出。

## 账本

`.goal/`：goal.md（契约+戳）· state.rec（计数器）· loop-log.md（迭代块）
· verdicts.rec（裁决绑 iter+指纹）· evidence/（席与检查的证据）·
interfaces.md。格式 v1.x 兼容，中断的 run 可续：`/goal-loop` 无参 =
status 摘要 + 接续。规则 R1–R8 与门控 check 顺序见 references/gate.md；
crew 协议与终验简报模板见 references/crew.md；检查形状库见
references/patterns.md。

## 脚本与自检

`scripts/{goal_gate.sh,goal_ctl.sh}`（门控只读仲裁 / 控制器记账手）·
`scripts/goal_hook.sh`（Stop hook）· `assets/goal.contract.md`。
自检：`bash tests/run_tests.sh`（全套）+ `bash tests/docs_consistency.sh`。
卸载 = 删 skill 目录 + `~/.claude/agents/goal-*.md`。
