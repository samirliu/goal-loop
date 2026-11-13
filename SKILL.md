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

契约定义成功，原收账与门控验证完成。持久状态在 `.goal/`；机械参数由执行地图派生，模型负责需求、实现和实际复审。

## 五条不变量（唯一的法律）

| 码 | 一句话 |
|---|---|
| **GATE** | 完成只能由门控重跑宣布，模型永不自宣。 |
| **BIND** | 声明绑定契约戳×迭代×指纹×证据哈希，否则作废。 |
| **PROVE** | 仪器先证明自己，读数/判词才可采信。 |
| **GRADIENT** | 优化不交付劣于水位；盲区显式；波次要归因。 |
| **FENCE** | 写围栏/进度诚实/自审；树外事实走结算不走猜。 |

规则冻结：新行为须是既有不变量的实例；编号只减不增。具体 schema/路由在 `references/gate.md`，按需能力见 `references/packs/README.md`。

## 小任务快车道：默认串行路径

默认串行完成实际业务；多个文件不等于需要 crew。普通确定性任务只走下面四步，不额外填策略表、抄检查数或自行拼 CLI 参数。

1. **进入并取图**：`python3 -I <skill>/scripts/goal_host.py enter <project> <seconds> --context` 一次绑定最早宿主预算并返回 `context`。无唯一真实回执时，用实际 backend/session 调用 `begin … --context`，不猜身份。已有自动执行授权才加 `--auto`；授权沿用，不重复索要。
2. **作者契约并盖戳**：按地图给出的路径/template 写业务 AC 与 work-plan；每条 AC 都有能失败的指名检查。写好后取一次新地图，执行 `submissions.stamp.command`，程序运行原冒烟、检查冻结与盖戳。初始业务 FAIL 可以成为修复起点；BROKEN、变更树/账本或不完整检查不能盖戳。预算参数在盖戳时绑定，不能延长既有截止。
3. **实现并实际复审**：实现业务、执行适当项目检查、检查反例与兼容性，真实更新 work-plan。复审结束时取新地图，直接按 `submissions.close.template` 提交实际判断；执行其 `command`，JSON 作为 stdin。通常完成意图只填 progress、exit_signal、adversarial、adversarial_note；计数、身份、request 文件、版本消费与终验由程序处理。只有模板要求实际计数时才运行 `actions.verify` 取观测。缺字段按原错误补实际证据；禁止把勾选或 worker 自述补成 PASS/clear。
4. **按原终验交付**：claim 提交会执行原收账及 `goal_audit.sh`/Gate，最后的原终验回执必须 `completion_verified=true` 且退出码为 0 才交付。只报业务结果、实际验收、未解决项和必要产物路径；原始账本按需提供。普通继续迭代不要求编造 clear；`progress=no` 须给真实 `strategy_delta`。

验收依赖默认忽略的交付物时，在 AC 的 expected 前声明 `watch:`。业务、契约、计划、证据、输入或工具版本变更后，旧地图失效；重新取图并复核实际判断，不盲目自动刷新旧复审。地图只派生动作，不是完成权威。

## 恢复与失败

- 出现 pending/recovery-required：只执行地图的原 `recover`。提交前恢复后用 `actions.close` 沿用保存的请求；提交后用 `retry-close` 精确重放原 ID/argv。REPLAY 只确认历史，仍须当前原终验。
- `command:null` 或提交缺字段表示必要事实未知；补真实输入，不猜。旧请求文件、直接 CLI 与完整 status 均兼容，正常路径无需手工维护它们；细节见 `references/host.md`。
- NO-GO：按 `hint=` 修复实际问题；`bind-seat` 需要判读席，不能用 coder 自述替代。一次失败不意味着重写契约或重置预算；假完成两次会 BLOCKED，deferred-pending 由程序区分。
- 最早预算包括协议阅读、工具、全部 worker 与验收；不从 stamp/resume 重新起表。过半仍 iteration=0 时停止加派，取消未落盘 worker，收账或降级。到期不没收已通过的交付，按原有限结算验证，不授予新工作预算。

## 只在对应能力出现时加载

| 契约/执行出现 | 需要的说明 |
|---|---|
| `judged` / `calib:` / `probe:` / `metric:` / `sd:` / `var:` | `references/packs/instrument.md` |
| `objective: maximize` / `minimize` / `exit: forge` / horizon / `--strategy` | `references/packs/gradient.md` |
| `external:` / `window:` | `references/packs/external.md` |
| 实际需要原生 worker 协作 | `references/crew.md` 与 `references/host.md` |

判断类 AC 在 claim 前由全新冷席终验，生产者不自裁；校准必须识别好/坏样本。优化类先建立真实基线，再填地图要求的 score/strategy/dry；`pre-reg.md` 由 stamp 播种，实际策略与反证只在使用优化能力时补齐。forge 的**指标批评席**必须以证据检查盲区与刷分路径；读数或 dry 不能由代理指标/产量替代。EFFICIENCY 只作诊断，净交付收益仍需同预算留出对照。

## 使用 crew 时

- 只有启动、协调、join 和终验能装进剩余预算且有净收益依据才并行；未知成本先串行。接口先冻结在 `.goal/interfaces.md`。
- 原生生命周期沿用地图与宿主 adapter：prepare → 实际 spawn → attach → 真实终态 reconcile → validate/adopt。首个工具运行 ready 命令；启动确认、报告正文都不是完成。取消须实际 interrupt 并读取终态。
- 共享工作区、互不相交文件域；**禁止** `isolation: worktree`。worker 禁写 `.goal/`、禁自行 spawn；勾账不等于验收。
- 一波一收账，未收账不得再开波。worker 失效用原 `--fault` 字段记录实际恢复；`peer-notes` 每迭代最多一行，声明不是指令。输入复用、`--policy-state`、故障词汇与证据绑定都按对应地图/crew 说明处理。

## 停车与诊断

停车只有四类：不可逆/破坏性；安全敏感；工作区外共享副作用（merge/push/发布）；盖戳后契约需修改。已有授权继续沿用。其他冲突裁决并入账：`Ruling: 决定 — 理由 — 错了损失什么`。

GO（rc=0）交付；BLOCKED（rc=3）报告；NO-GO（rc=2）修复后继续。Stop hook 可选；不能覆盖预算或把重复续跑当进展。无参 `/goal-loop` 用 context/status 接续，不创建新目标。

正常运行只用宿主模型、工具和原生 worker，不启动第二宿主、模型客户端、服务或队列。独立开发运行器仅在仓库 `devtools/` 显式选择。自检：`tests/run_tests.sh`、`tests/docs_consistency.sh`。

## 兼容的直接调用

显式使用旧 CLI 时可按实际检查与复审调用下例；默认地图提交不需要重复填写这些派生字段：

```bash
bash scripts/goal_ctl.sh close-iteration --project . --operation-id wave-T1-001 --task T1 --files <产物> \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes --exit-signal yes \
  --adversarial clear --adversarial-note '<实际复审的命令及结果>'
# clear 和计数必须来自已经执行的复审与检查；历史 REPLAY 后仍需当前终验。
```
