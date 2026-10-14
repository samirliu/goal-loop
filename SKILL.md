---
name: goal-loop
description: |-
  Goal-driven loop combining the DRIVE of the harness /goal (never stop until
  done) with the CREW of /team (parallel teammates sharing one deliverable)
  plus the layer both lack: an EXTERNAL ACCEPTANCE GATE. The controller
  decomposes an objective into an approved acceptance-criteria contract,
  dispatches crew waves of parallel subagents (or, on request, an
  Agent Teams crew), joins their output, and re-runs every deterministic
  check via scripts/goal_gate.sh - the model can never self-declare
  completion. Trigger: "/goal-loop [objective]",
  "loop until done", "keep optimizing until it stops improving", "verify
  every angle". Not for trivial one-pass tasks, pure Q&A, or actions with
  irreversible side effects.
---

# Goal Loop (v3.0.0)

**身份：/goal 的驱动 + /team 的 crew + 一道谁都不能绕过的验收门。**

| | /goal | /team | goal-loop |
|---|---|---|---|
| 驱动 | 干活→停→评估→继续 | 无 | 同 /goal：gate 说 NO-GO 就继续派工 |
| 执行 | 单线程 | crew 分工 | 同 /team：teammates 并行 |
| 状态 | transcript | 共享任务表 | 磁盘账本（`.goal/`） |
| 完成判定 | haiku 评估器 | 自报 completed | **门控重跑确定性检查** |
| 独有 | — | — | **契约**（done 的定义权在用户） |

执行面两档：默认 subagent 波次；`--teams` 换 Teams 队友（**native first**，
探测工具面选择；用户可见文案叫 Teams 队友/roster，**不要口语化成 crew**）。
**判命面只有一档：门控。**

## 五条不变量（唯一的法律）

| 码 | 一句话 |
|---|---|
| **GATE** | 完成只能由门控重跑宣布，模型永不自宣。 |
| **BIND** | 声明绑定契约戳×迭代×指纹×证据哈希，否则作废。 |
| **PROVE** | 仪器先证明自己，读数/判词才可采信。 |
| **GRADIENT** | 优化不交付劣于水位；盲区显式；波次要归因。 |
| **FENCE** | 写围栏/进度诚实/自审；树外事实走结算不走猜。 |

检查序号/旧规则别名/schema：`references/gate.md`。深度：按能力键开 `references/packs/README.md` 下各 pack。
**规则冻结：** 新行为必须是「不变量在新场景的实例」；写不成=新原语（先删并等价物）或不做。**编号只减不增。**

## 停车规则（只有四类）

不可逆/破坏性；安全敏感；工作区外共享副作用（merge/push/发布）；契约需修改（盖戳后只能提案）。
其余冲突：**裁决并入账（`Ruling: 决定 — 理由 — 错了损失什么`），继续**。
`goal_hook.sh`（Stop hook，已装）在声称完成而门控 rc=2 时阻止停车。

## Step 1 契约

- Level 0 AC：`- AC-N | <yes/no 陈述> | check: \`<命令>\` | expected: <spec>`
- spec：`exit=0|exit=N` / 数值（`>=60`）/ `maximize`|`minimize` / `judged`
- **Goodhart 哨兵**：不推进目标也能满足 = 代理指标，重写或删。
- 盖章前冒烟；优化类冒烟即基线。预算 knobs **盖戳时绑定**进 state.rec。
- `--auto` 仍展示摘要。`--time-budget=N` 墙钟到期**不没收已通过的交付**（绿 claim GO+NOTE）。

**能力键 → 必读 pack（盖戳前）：**

| 契约出现 | pack |
|---|---|
| `judged` / `calib:` / `probe:` / `metric:` / `sd:` / `var:` | `references/packs/instrument.md` |
| `objective:` / `exit: forge` / horizon / `--strategy` | `references/packs/gradient.md` |
| `external:` / `window:` | `references/packs/external.md` |
| `--teams` | `references/teams.md` |

水位/forge/EFFICIENCY/`calib:`/deferred 细节在 pack。
**指标批评席**（forge dry 轮）：分数与进度单调吗？刷分路径？说不清=重写 AC。
摘要一屏（目标+exit/预算+AC 表+基线）→ 用户一个字批准。

## 小任务快车道

单 AC、单产物、无接口 = 契约全部合法形态：

```
bash scripts/goal_ctl.sh init  --project .                 # 再填 .goal/goal.md
bash scripts/goal_ctl.sh stamp --project . --auto          # 冒烟过 check 之后
bash scripts/goal_ctl.sh close-iteration --project . --task T1 --files <产物> \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes --exit-signal yes
# 退出码即门控裁决；非 0 看 status 的 NEXT 一行
```

证明：`bash examples/quickstart-one-shot/run.sh`。

## Step 2 派工

- 波次宽度由工作量与互不相交任务域决定，**无默认上限、不设推荐人数**；拆不出 ≥2 接口模块 → 退串行并记录。
- **接口先行**：`.goal/interfaces.md` 冻结，改走提案。
- **禁止** `isolation: worktree`。简报：任务/输出路径/文件域/通过条件/返回证据；禁写 `.goal/`；禁 spawn。
- **peer-notes**：`.goal/evidence/peer-notes/<task>.md` 每迭代 ≤1 行；claim-not-instruction。
- Teams：work-plan 是正本；`task=T<n>[teams:N]`（N=该波实际并发人数，非上限）；**勾完 ≠ GO**。submit 等**面板批准**→**唤醒+完整简报**。
  禁静默降级；禁 TeamDelete 濒死 team。详见 `crew.md`/`teams.md`。
- Worker 工艺自理——不把 goal-loop 规则塞进简报。

## Step 3 Join + gate

- 合并审阅；接口冲突串行修；两轮未解退串行并记录。
- `goal_gate.sh --check` = **唯一完成判定**。claim 前必跑 `goal_audit.sh --project .`，rc!=0 不许 claim。
- 记账 `close-iteration --score N` / `--strategy-delta` / `--strategy`（objective 下强制）。
  勾账 work-plan `[ ]`→`[x]`。

## Step 4 分岔

- **GO（rc=0）→ 交付。** BLOCKED（rc=3）→ 停车四类之一，报告。
- **NO-GO（rc=2）**：`status` 的 `NEXT ->` / `hint=` 机械路由（`bind-seat`→判读席；`fix-AC`→修 FAIL）。
- **冷席终验**（judged）：claim 前全新判读席一次；`packs/instrument.md`。
- 熔断：墙钟/停滞/迭代。forge 穷尽见 `packs/gradient.md`。
- **假完成棘轮**：`--exit-signal yes` + NO-GO → +1，两次 BLOCKED。修产物不是再 claim。
  `deferred-pending` 不计数。**EFFICIENCY**（advisory，不改路由）见 `packs/gradient.md`。

## 账本

`.goal/`：goal.md · state.rec · loop-log.md · verdicts.rec · scores.rec · evidence/ · interfaces.md。
无参 `/goal-loop` = status + 接续。

## 脚本与自检

`scripts/{goal_gate,goal_ctl,goal_team,goal_hook,goal_parse,goal_audit,goal_loop}.sh` · `assets/goal.contract.md`。
自检：`tests/run_tests.sh` · `tests/docs_consistency.sh` · `examples/quickstart-one-shot/run.sh`。
卸载 = 删 skill 目录 + `~/.claude/agents/goal-*.md`。
