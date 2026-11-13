# 配对成本实验与自动撤回

```bash
python3 -B examples/evolution-dedupe/run.py --output /tmp/my-dedupe-experiment
python3 -B examples/evolution-dedupe/run.py --output /tmp/my-dedupe-experiment --counterexample
python3 -B examples/evolution-dedupe/run.py --output /tmp/my-dedupe-experiment --repair
```

第一次对比保持首次出现顺序的两种去重策略：逐项线性查询与 dict 去重。开发集和留出集分别有 6 个内容不同的实例，两种策略始终处理相同输入，轮换运行顺序。grader 另行运行，要求内容正确且输出是列表；策略只收到输入，不收到预期答案。计时包含临时试验准备、Python 启动、策略执行和 grader 执行，不包含模型思考或未观测费用。

只有两阶段都满足质量不退步、至少 15% 的配对成本下降、预注册的单侧符号检验规则，才更新 `state/enabled.json` 指向已归档候选。每次留出验证消耗顺序检验预算 `0.05/[k(k+1)]`，防止反复换标签不断试到偶然胜利；已暴露的留出输入不得复用。这里的检验规则依赖实例和运行条件，不是通用置信保证。

第二次使用新的嵌套列表实例。dict 候选不支持不可哈希元素，地板检查失败；系统立即停止继续花费留出预算，撤回到可执行的原基线。失败、输出、耗时与退出原因都保留，不只统计成功样本。原策略程序和历史报告不会因撤回而删除。

第三次复放依据这条 TypeError 提出的修复版本：可哈希元素走快速路径，不可哈希元素回退到原算法。它使用新的开发/留出随机实例，每组 14 对，包含嵌套列表；第二次留出验证的阈值降为约 0.00833，不通过换版本清零失败或检验历史。示例内置两个候选版本用于复放；实际工作中由 agent 根据原始失败 trace 提出下一版本，执行器负责测量、晋升或拒绝，不声称执行器自行发明代码。每步还会独立执行已启用的归档程序，验证当前产物可复现。

`state/<run>/report.json` 保存每个 trial、聚合结果、波动量、策略/runner 摘要、运行环境、实际耗时和决策；`frozen/` 保存评估原料，`.out` 保存原始产物。tokens/费用没有来源时为 null。`enabled.json` 是实际局部启用指针；实验不改已安装 skill、不放宽 gate，也不发布任何外部变更。

实际 agent 提出的 `def dedupe(items)` 可用 `--candidate-file PATH` 接入；
`--seed-offset` 为新试验生成不同输入，`--pairs` 在运行前声明两阶段样本数。
`--task-family values|paths|hash-collisions` 提供本示例的三种输入分布。
监测必须比较实际启用的归档字节，不能用“逻辑相同”的程序替换版本身份。
一次真实提案、退化撤回、修复和迁移验证已[完整归档](../../docs/evals/agent-evolution/README.md)。

通用入口：

```bash
python3 -I scripts/goal_evolve.py path/to/protocol.json --state .goal/proposals/evolution
```

protocol 的精确格式由本例生成：version、baseline/candidate/grader 的相对文件路径、development/holdout 的 input/expected 对、minimum_pairs、minimum_cost_gain、quality_tolerance、trial_seconds、budget_seconds。策略与 grader 是单文件、标准库 Python 程序；策略 stdin 是原始任务输入，stdout 是产物；grader stdin 是 `{"output":"原始 stdout","expected":"预期原料"}`，输出 `{"floor":true,"horizon":true,"score":1}`。score 越高越好，此入口优化的是质量不退步条件下的总试验成本。

## 多文件检查点

```bash
python3 -B examples/evolution-dedupe/run.py --output /tmp/paired-checkpoints --checkpoint
python3 -B examples/evolution-dedupe/run.py --output /tmp/paired-checkpoints --checkpoint --counterexample
python3 -B examples/evolution-dedupe/run.py --output /tmp/paired-checkpoints --checkpoint --repair
```

版本 2 把 `baseline` 和 `candidate` 换成 [检查点](../../docs/transaction-state.md#accepted-artifact-checkpoints)
的 ID，并加 `entry` 指定两个检查点共有的 Python 入口。调用时传
`--project /path/to/project`。执行器验证同一冻结契约、相同文件范围及
父子检查点关系，然后在独立临时目录还原各自的文件和权限。入口可导入
检查点里的同目录模块或项目包。依赖的静态资源也要纳入 owned scope。
调用 `run-enabled --state DIR --seconds N` 时，执行器校验并运行已启用的归档，
因此后续项目编辑不会更换执行版本。

试验时间从临时目录准备计到评分完成，受单次试验与总截止共同约束。
当计划样本数即使全部获胜也过不了当前统计阈值时，留出阶段跳过，报告
给出最低需要的样本数。新记录的开发输入也不能作为未来留出集。
部分完成的阶段不提供晋升资格。坏 grader、监督器故障和不确定的超时
保留当前指针，已验证的硬失败可以撤回。每个已记录的试验和输出可在
`trials.jsonl` 与对应的 `.out` 中核对。此示例在撤回后用检查点恢复项目，
并独立重跑 gate。

这是可信本地代码的实验执行器，不是 OS 安全沙箱。原材料内容哈希不同不证明任务语义独立，grader/输入的修改检测也不构成针对恶意同用户进程的保密或权限隔离。该例只证明配对测量、自动启用和反例撤回机制；候选代码仍需 agent 提出，通用策略迁移及相对 `/goal` 的真实效用尚未证明。
