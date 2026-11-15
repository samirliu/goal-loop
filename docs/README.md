# 文档索引

当前版本 **4.2.1**。安装和日常使用以[仓库 README](../README.md)、[根 SKILL](../SKILL.md)及下列能力说明为准；插件入口由根 SKILL 生成。历史计划、暂停说明和冻结评估只对各自记录的版本有效。

## 当前实现

| 范围 | 入口 |
| --- | --- |
| 安装、依赖、模式差异、验证 | [README](../README.md#install--安装) / [安装器](../scripts/goal_install.py) |
| 四步工作流和恢复路由 | [SKILL](../SKILL.md) |
| 验收语义与不变量 | [Gate](../references/gate.md) |
| 按原始需求选择能力 | [Packs](../references/packs/README.md) |
| 执行策略的递归改进、实际消费、反例回退 | [Improvement](../references/packs/improvement.md) / [可运行例子](../examples/recursive-improvement/README.md) |
| crew、角色、宿主预算与事件 | [Crew](../references/crew.md) / [Host](../references/host.md) |
| 主账本、锁、提交身份与恢复边界 | [事务状态](transaction-state.md) |
| 可执行示例和历史压力案例 | [Examples](../examples/README.md) |
| 冻结实验、原始反例与复验范围 | [评估索引](evals/README.md) |

4.2.1 修复启用递归改进后，地图的 verify、close 和 receipt 因重复申请账本锁而无法执行的问题；多文件检查点的派生读取同样复用已持有的锁，保留项目身份校验及排他性。回归贯穿实验、正式收账、到期结算、中断恢复和最终 Gate。

4.2.0 引入的固定资源分配、父子代追踪、实际消费、失败反馈及反例撤回继续保留。比较/选用沿用 goal_evolve；完成仍由原 controller/Gate 判断。此前的宿主生命周期、安装与预算修复保持有效。

本地检查或合成 hook 回放不证明模型业务质量、实时 hook 投递或端到端提速。没有声明整体评分或通用迁移收益。每份评估都应按其源码快照、平台与明确限制阅读。

## 历史资料

- [v4.1.1 优化计划](optimization-plan-v4.1.1.md)：原始问题、工作包和验收设计。
- [P0/P1 历史审计](p0-p1-status.md)：当时的接入、暂停与原始失败记录。
- [深化执行记录](deepening-execution.md)及[原评估设计](evaluation-design.md)：已有实验及其不支持整体提速的边界。
- [2026-10-24 断点图](deepen-2026-10-24.md)、[研究笔记](agent-harness-四篇精读.md)、`superpowers/` 与 `run-friction/`：设计和实践背景，不能作为当前调用手册。

清理保留历史源码、日志和失败；临时复跑目录不纳入源码或安装包。修改运行资源、入口或许可证时，应同步 `assets/install-files.json`；修改根 SKILL 后运行 `goal_install.py sync-entry`。源码回归命令集中在 README 和 CI。
