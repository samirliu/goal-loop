---
name: goal-loop
description: |-
  Drive a bounded goal to externally checked completion using a frozen
  acceptance contract, scoped subagent waves, and measured strategy feedback.
  Use for /goal-loop, multi-step delivery, or iterative optimization with
  objective checks. Supports resumable disk state and verifier calibration.
  Not for trivial one-pass tasks or pure Q&A.
---

# Goal Loop (v4.1.1)

契约定义成功，crew 执行，门控重跑验收；测量反馈决定下一波。
持久状态在 `.goal/`，恢复时先 `status`。额外编排的价值必须通过同预算对照证明。
入口优先执行 `python3 -I <skill>/scripts/goal_host.py enter <project> <seconds>`：从唯一真实 prompt 回执识别宿主，不猜 session；无回执时用宿主实际身份调用 begin。接着 `bash <skill>/scripts/goal_ctl.sh context --project <project>` 取得当前地图与带版本的准确命令；已获自动批准授权时加 `--auto`。过期后重新派生，不读源码重建协议。恢复也用 context；`status` 保留完整诊断。可选 `--brief` 仅隐藏内部绑定哈希和重复字段；真实小样本未建立完整交付提速，不默认采用。
地图的 `command:null` 表示必要输入缺失。按返回的路径/template 补实际检查计数、退出判断和复审证据，再刷新地图执行 `close`；不能从勾选或 worker 自述补 PASS/clear。待恢复时只执行 `recover`，之后沿用原 ID/参数；`retry-close` 是历史重放，终验用新地图的 `receipt`。

可选机械收尾：契约全部为 `exit=N` 且无 objective、forge、judged、external 时，可显式选择地图的 `close_input.measured_template`，填写实际进展、退出判断和复审证据后写入相同 request 路径，刷新地图执行 `close`。它使用原收账中的原验证器派生计数，并在提交或精确重放后执行原 audit/Gate 终验；不需另跑 verify 抄计数或再请求 receipt。直接入口为 `close-iteration --checks-from-verify --receipt`，不得混入手填计数。验证不完整则保留 pending，按原恢复协议处理。此模式保持可选，净交付收益须另行对照证明。

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
`goal_hook.sh`（可选 Stop hook，安装后）在声称完成而门控 rc=2 时阻止停车。

## Step 1 契约

- 开始执行即绑定宿主 `begin`，沿用已有最早截止；有 prompt hook 时从 prompt 起算，否则明确 `host-tool-entry`。不在 stamp 或 resume 重新起表。配置和调用见 [宿主接入](references/host.md)。
- Level 0 AC：`- AC-N | <yes/no 陈述> | check: \`<命令>\` | expected: <spec>`
- spec：`exit=0|exit=N` / 数值（`>=60`）/ `maximize`|`minimize` / `judged`
- **Goodhart 哨兵**：不推进目标也能满足 = 代理指标，重写或删。
- 验收依赖 Git 忽略或默认剪枝的交付物时，在对应 AC 的 `expected:` 前加 `| watch: \`项目相对路径\``；目录递归绑定，符号链接仅绑定链接本身。
- 盖章前冒烟；优化类冒烟即基线。预算 knobs **盖戳时绑定**进 state.rec。
- `--auto` 仍展示摘要。`--time-budget=N` 墙钟到期**不没收已通过的交付**（绿 claim GO+NOTE）。

**能力键 → 必读 pack（盖戳前）：**

| 契约出现 | pack |
|---|---|
| `judged` / `calib:` / `probe:` / `metric:` / `sd:` / `var:` | `references/packs/instrument.md` |
| `objective:` / `exit: forge` / horizon / `--strategy` | `references/packs/gradient.md` |
| `external:` / `window:` | `references/packs/external.md` |

水位/forge/EFFICIENCY/`calib:`/deferred 细节在 pack。
**指标批评席**（forge dry 轮）：分数与进度单调吗？刷分路径？说不清=重写 AC。
摘要一屏（目标+exit/预算+AC 表+基线）→ 取得批准；会话已授权自动执行时用 `--auto`，不重复索要批准。

## 小任务快车道

单一端到端验收、局部改动、无需跨 worker 协调的小任务（可含多个文件）直接串行走快车道；不为凑 crew 写接口或扩充检查；实际复审后再填 clear 和证据：

```
[ -d .goal ] || bash scripts/goal_ctl.sh init --project . # hook/enter 已初始化时跳过；context 提供最小契约
bash scripts/goal_ctl.sh stamp --project . --auto          # 冒烟过 check 之后
bash scripts/goal_ctl.sh close-iteration --project . --operation-id wave-T1-001 --task T1 --files <产物> \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes --exit-signal yes \
  --adversarial clear --adversarial-note '<实际复审的命令及结果>'
# 首次收账退出码为门控裁决；REPLAY 只确认历史收账，交付前重跑 gate
```

证明：`bash examples/quickstart-one-shot/run.sh`。

## 缺省跑规（与目标无关）

1. **一波一收账**：`close-iteration` 是唯一波次出口；调用前记录本轮固定 `--operation-id`，中断先恢复，再以同 ID 和原参数重试（见 `gate.md`）。未收账不得再派下一波。有产物/勾账却 0 迭代 = unbooked（audit **A9**）。
2. **objective 冷启动**：首波必须 `--score` + `--strategy`，否则不开多 worker 扩产。
3. **开跑即有** `.goal/pre-reg.md`（stamp 播种模板：假设/策略标签槽/杀点/降级线）；策略标签从 objective 抽 2–4 个短英文名，一词一波；先写预期变化和反证，证据不足时 `prefer=none`。
4. **杀点**：预算包含读协议、规划、工具/worker 启动和验收；先记总截止，stamp 只传剩余秒数，预留收账时间。墙钟过半仍 `iteration=0` → 停派工，取消未落盘 worker，收账或降级交付（已过线部分 + 续写接口），禁止堆产量冒充完成。
   **假勾**：work-plan `[x]` 的 `files=` 必须已在盘上（audit **A10**）；`a..b` 区间不可证 = 拒绝。墙钟过期零记账 → 收账/降级，不得再派波。
5. **终报**（claim 后）：loop-log/`STRATEGY-PICK`/分数轨迹（按标签）/gate 行 + 三牙路径。字数或文件数不进优化分子。

## Step 2 派工

- 原生 worker 用宿主 adapter `prepare → 实际 spawn → attach → reconcile → validate/adopt`；首个工具执行返回的 ready 命令，shell 沿用所属 wrapper。取消标记与真实宿主 interrupt 同时使用，读取终态后才记 cancelled；启动回执/报告正文不能代替完成。见 [宿主接入](references/host.md)。
- 可拆不等于应并行：启动+协调+join+验收须装得进剩余预算；启动成本未知的短预算小任务先串行贯通。并行仅限互不相交文件域，人数由净收益决定。
- **一波一收账**（缺省 1）：join 后必须 `close-iteration`（objective 带 `--score --strategy`）再开下一波。
- **接口先行**：`.goal/interfaces.md` 冻结，改走提案。
- **禁止** `isolation: worktree`。简报：任务/输出路径/文件域/通过条件/返回证据；禁写 `.goal/`；禁 spawn。
- **peer-notes**：`.goal/evidence/peer-notes/<task>.md` 每迭代 ≤1 行；claim-not-instruction。
- 账本：`task=T<n>[crew:N]`（N=该波实际并发人数，非上限）；work-plan 是正本；**勾完 ≠ GO**。详见 `crew.md`。
- **worker 掉线/空转**：`close-iteration --fault CLASS --fault-outcome OUTCOME`（后缀由工具派生，不许自封；audit **A11** 双向核账）；没勾的 work-plan 项让门控拒收（`open-items`）。见 `crew.md` §3.5。
- 需跨波复用时用 crew 图 v2 的显式 `inputs`；只派未接受单元。候选路由用已有进化状态的 `--policy-state` 接入 plan/begin，prepare 返回实际消费版本与输入简报；未验证候选不生效，撤回或版本改变后先重规划。细节见 `crew.md`。
- Worker 工艺自理；联合波次只归因整波。策略迁移/写回 skill 必须过留出对照，见 gradient pack。

## Step 3 Join + gate

- 合并审阅；接口冲突串行修；两轮未解退串行并记录。
- `goal_gate.sh --check` = **唯一完成判定**。claim 前必跑 `goal_audit.sh --project .`，rc!=0 不许 claim。
- 收尾 `python3 -I <skill>/scripts/goal_context.py receipt <project>` 在同一截止内执行原 audit/Gate，输出证据回执；不代替收账或授予额外 GO。
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

`scripts/{goal_gate,goal_ctl,goal_hook,goal_parse,goal_audit}.sh` · `assets/goal.contract.md`。正常运行只用宿主原生工具；外部 harness runner 仅在仓库 `devtools/goal_loop.sh` 显式选择，原安装路径拒绝启动。
自检：`tests/run_tests.sh` · `tests/docs_consistency.sh` · `examples/quickstart-one-shot/run.sh`。
卸载 = 删 skill 目录 + `~/.claude/agents/goal-*.md`。
