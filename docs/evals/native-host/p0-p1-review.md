# P0/P1 独立审阅：实现缺陷与证据边界

审阅日期：2026-11-12。对照 [optimization-plan-v4.1.1.md](../../optimization-plan-v4.1.1.md)，审阅当前源码、保留的测试输出及原始实验材料。未修改实现、调用模型、联网、追加实际 cohort、重置截止或重跑完整套件。下列反例只在临时目录使用本地 Git、已有夹具和明确标为合成的决策输入。

**审阅结论：已有机制明显强于原基线，但当前不能判定 P0/P1 全部关闭，也没有支撑综合超过 9 分的效用证据。** 本次发现三个实现缺陷和一个独立复核器缺口。修复应集中于现有内容摘要、比较条件、启用指针及复核器，无须增加角色、常驻规则或另一套调度系统。

## 1. 可复现的实现缺陷

### F1 / W1 / P0：Gitlink 被当成空目录，子模块内容不受绑定

位置：[goal_parse.sh:144](../../../scripts/goal_parse.sh#L144)、[goal_tree_digest.py:70](../../../scripts/goal_tree_digest.py#L70)；shell fallback 同样只记录目录权限，见 [goal_parse.sh:199](../../../scripts/goal_parse.sh#L199)。

父仓库的 `git ls-files` 对子模块或被登记为 Gitlink 的嵌套仓库只返回目录项。枚举没有递归展开，哈希器又把该项作为普通目录，仅散列路径和权限，没有绑定子仓库的实际文件或 Gitlink 对象。因此，子模块源码改变后，当前 `v2-…` 摘要可以不变，旧 judged 裁决仍具有相同绑定身份。这是受审内容遗漏，不是 OS 沙箱边界。

最小重现：在临时父仓库中新建 `component` Git 仓库，提交 `component/artifact.txt` 内容 `A`，在父仓库执行 `git add component`，确认索引条目模式为 `160000`。取得父仓库 digest，把该文件改成 `B`，再取 digest。

本次实际结果：

```text
manifest: 160000 … component
parent status after edit: AM component
before: v2-0ecc804bbe7aad86d7c3c4bd5d4f46768275bb2dca6ba26bdf6aa6f66c78dfba
after:  v2-0ecc804bbe7aad86d7c3c4bd5d4f46768275bb2dca6ba26bdf6aa6f66c78dfba
```

建议在已有枚举层明确定义 Gitlink 语义：绑定实际受审子树，或者拒绝未显式 `watch` 的 Gitlink，提示如何声明范围。仅绑定子模块 commit 仍不能覆盖脏文件。回归至少覆盖脏文件变化、子模块版本变化、未初始化子模块与 shell fallback，且不能静默排除这类目录。

### F2 / W5 / P1：输入变化后仍复用旧的分解式串行/crew 成本

位置：[goal_crew.py:96](../../../scripts/goal_crew.py#L96)、[goal_crew.py:198](../../../scripts/goal_crew.py#L198)、[goal_crew.py:399](../../../scripts/goal_crew.py#L399)。

`condition_key` 包含 graph 中的输入路径，但不包含 `scope_digest(inputs)` 的实际字节。`begin` 另存输入摘要，新增 `batch_condition` 也包含这些摘要；然而 `plan` 首先以旧 `condition` 接受原拆分的记录，只有不匹配时才检查单 worker 的 `batch_condition`。所以同一图的输入内容变化只会淘汰 fused single-worker 基线，保留旧的分解式 inline/crew 观测，继而可能重新推荐 crew。

最小重现使用 `tests/test_crew.py` 的 `Crew` 夹具：

```python
t = Crew(); t.setUp()
try:
    graph = json.loads(t.graph.read_bytes())
    graph['inputs'] = ['fixture.json']
    t.graph.write_text(json.dumps(graph))
    fixture = t.project / 'fixture.json'
    fixture.write_text('[1,2]\n')
    t.cost_inputs(50)  # 已有夹具；合成耗时，仅检验决策语义
    before = crew.plan(t.project, t.graph)
    fixture.write_text('[999999,888888,777777]\n')
    after = crew.plan(t.project, t.graph)
finally:
    t.doCleanups()
```

实际返回：前后 `condition` 相同；`observations` 从 9 降至 6，`single_observations` 从 3 降至 0；输入已变的 `after` 仍是 `choice=crew`、`serial_basis=serial-delegation`、`serial_lower=81`、`crew_upper=21`。这些秒数是合成输入，不能计作实际效率证据。

修复应让两条观测匹配路径都绑定实际输入字节，并使旧缺字段记录保守失效。现有 `test_changed_input_cannot_reuse_frozen_trial` 只覆盖一波进行中篡改输入；`test_single_baseline_cannot_cross_different_frozen_input_bytes` 只保护新增 single 分支，均未覆盖这个跨波复用入口。

### F3 / W7 / P1：撤回报告先持久化，启用指针失败后仍执行已退化策略

位置：[goal_evolve.py:509](../../../scripts/goal_evolve.py#L509)、[goal_evolve.py:304](../../../scripts/goal_evolve.py#L304)。

`experiment` 先写最终 `report.json`，再写 `enabled.json`。两者没有共同提交点或可恢复的待完成状态。撤回时，如果在前一个写入之后、启用指针替换之前崩溃或发生 I/O 错误，报告已声称 `withdrawn` 且指向 baseline，但 `run-enabled` 仅读取旧指针，仍可运行已经观察到退化的 candidate。

本次复现使用 `tests/test_evolve.py` 的受控 telemetry：先正常启用；在新输入上让 candidate 的 `floor=False`；只在 `atomic(enabled.json, …)` 注入 `OSError`，其他写入保持真实。结果：

```text
durable report.status: withdrawn
durable report.enabled: f60fabe523988670cf59c8508f9869964b0b1ffe73e0800462bcbf1b9479018e
enabled_policy().policy: b1b5ba90c098a185c4d07e423f324505bd5a7ec2b15b8037aac61d5a5e3c4f4d
still_selects_regressed_candidate: true
```

这是策略切换的可靠性缺陷，不把它混同于 W2 主账本已经实现的事务承诺。可以复用现有单指针思想，或用最小切换日志让 `run-enabled` 对未完成撤回失败关闭并能恢复。需分别验证切换前、切换后丢失确认，且恢复不重新执行试验副作用。仅把报告和指针的写入顺序对调仍会留下相反的不一致窗口。

## 2. F4 / W7：独立复核器没有完整证明策略身份与状态转移

位置：[verify_agent.py:51](../../../examples/evolution-dedupe/verify_agent.py#L51)、[verify_agent.py:99](../../../examples/evolution-dedupe/verify_agent.py#L99)、[verify_agent.py:104](../../../examples/evolution-dedupe/verify_agent.py#L104)。

复核器确实独立重算了本组输入的值 oracle、196 份输出身份、配对成本、正向符号检验、输入不复用及顺序 alpha 预算。这些是实质证据。

但它分别验证 frozen 文件和 policy archive 的哈希，没有把 `report.policies[side]` 绑定到相应 frozen 程序；启用状态主要通过断言预期的字符串顺序及几个身份关系确认，未逐轮重建资格、反向退化判定和应选指针。

本次在临时 symlink overlay 中只修改修复版报告的一项：把 `policies.candidate` 改为该报告的 baseline hash，保持 `enabled` 指向新 candidate。原始文件和所有 raw 输出均未改。复核仍返回：

```json
{"verified":true,"attempts":4,"pairs":98,"raw_outputs":196,"holdout_evaluations":[1,2,3]}
```

这份报告在自身身份关系上已经矛盾，复核器理应拒绝。应增加 frozen 源码到实际 policy archive 的绑定，独立重建每阶段的资格、质量容差、正反向检验和每次选择，并用上述身份替换及错误撤回作为负向变异。此缺口不推翻现有数值收益，但不能把 `verified=true` 解释为每一次启用/撤回均已独立证明。

## 3. 保留的正向结论与证据限制

| 工作包 | 本次审阅支持的结论 | 关闭范围 |
|---|---|---|
| W1 | 内容 SHA、路径类型/权限、watch、旧格式失效及已有 scope 测试有实际实现 | F1 修复前，不能写“当前无已确认未修复的 P0 缺陷” |
| W2 | `Store` 的不可变完整 generation、单提交指针、幂等身份、主视图核对和恢复路径相互一致；未在本次审阅复现新的主账本缺陷 | 不扩大为任意缓存、策略指针或文件操作均已事务化 |
| W3 | host 起点进入同一持久预算；`prepare`、READY 和 owned command 采用最早截止；取消标记与 native 终态分开 | Work 是显式 bridge。原生安装后 hooks 的全事件覆盖尚未获得真实认证 CLI 试验；不能称透明全局拦截 |
| W4 | crew 生命周期、命名 measurement、first-valid、采用、阶段时间及 runtime 父子 span 已有实现；重复声明不再获得产物收益 | 未经 callback/owned wrapper 的工具覆盖仍有限；观测到的版本数不等于全部实际搜索次数 |
| W5 | 单 worker 基线和 worker 占用权衡修正了“逐项派多个 worker 等于最便宜串行”的错误假设 | F2 仍会污染比较条件；真实 cohort 只有两对完整配对，没有并行净收益结论 |
| W6 | 检查点有明确拥有范围、冲突拒绝和恢复日志；水位从通过 floors/horizon 的资格结果推进，拒绝坏候选抬高水位 | 未在本次审阅发现新的资格水位问题。Python 之外的适配是覆盖扩展，不能临时新增为原方案硬门槛 |
| W7 | 真实提案、合法碰撞退化、新输入修复、路径分布验证及 `run-enabled` 消费归档都有材料 | F3/F4 未关闭；收益限本组局部 Python 策略执行，不等于整个 Agent 会话或通用规划成本降低 |

原生 v3 [报告](/tmp/goal-native-v3-20261112/report.json)记录：

| 完整配对 | single 墙钟 / worker 秒 | crew 墙钟 / worker 秒 |
|---|---:|---:|
| 1 | 298.351 / 285.042 | 299.091 / 509.112 |
| 2 | 263.133 / 261.817 | 263.331 / 474.643 |

四个样本均通过 21 项独立检查并获得 Gate GO。`single-3` 的 worker 固定检查虽然在截止前通过，父级独立验证返回 124，未采用、quality=false、Gate BLOCKED；`crew-3` 未派发。七个已派发 native worker 均有终态。两对的 crew 墙钟基本持平而 worker 占用约为 1.79/1.81 倍，不支持扩 crew；不足三次的窗口不能被补成三次。这些时长包括 reservation、启动/排队及观察延迟，不是供应商 compute、CPU 或费用。

W7 的 65.83%、75.10% 退化、73.11% 修复收益与 77.81% 路径收益应继续保留。成本包含程序工作区准备、执行、清理和 grader，不包括模型提案、控制器等待及未暴露账单。取得完整供应商账单不是本次新增门槛。

## 4. 验证尾项与收口顺序

1. 先关闭 F1/F2/F3，并以负向变异补足 F4。以上均可在现有实现层解决，不需要更多常驻协议。
2. 更新证据索引：`docs/p0-p1-status.md:11` 仍称 v3 正在做三对且仅记录第一对；`native-host/README.md:34` 仍称固定检查入口未完成真实 worker 复验。应写实际已停止、两对有效、第五个样本超时、第六个未开始。
3. 保留版本边界：macOS 187 Python/603 shell 属固定检查入口前快照；Linux 188 Python/603 shell 属其对应后续快照；新增 planner 两例与直接 READY 断言是定向验证。不能把上述完整结果移用到本次审阅修复后的源码。
4. 当前改动上的托管 Ubuntu/macOS CI、已修改路径的必要回归是验证尾项。W8/W9 的完整行为/效用试验属于既定 P2；已停止的 36 次对照及 v3 原截止不因本次审阅恢复。

综合超过 9 分仍应取决于这些正确性缺陷是否关闭，以及相同质量与预算下的真实效用证据。现有失败保留、保守停止和局部策略收益值得保留，但测试数量、更多文档或扩大角色数量不能替代该证据。

审阅时源码 SHA-256：

```text
goal_crew.py       098722d54aae7a63efd415a5f219b0713c78b146c37892aa11486dca7acbffa6
goal_evolve.py     fabae22d1506b52177e93fa9a5d6b1230a70e7653f39579baecc51c44dcdf4fa
goal_parse.sh     81b2444b42d13157f19c487bdccd572f3ea29843a5d087ad84d7e5dd660d809d
goal_tree_digest.py 278d31ee556181063e3664bc7b51e63f7ed278bcdde2664d4ca2c5de44218268
verify_agent.py    33c9164c22629b2676099fa39aff7cf9e26c0ceacd69322e90142de1ffbe98bf
```
