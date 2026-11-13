# 实际 agent 提案、反例撤回与迁移复验

本次候选由当前 root agent 根据原始 profile 和监测失败实际写出，
没有使用示例内置的候选或修复代码。执行器、grader 和输入生成器独立于
候选；当前演示的适用范围是局部 Python 去重策略，不代表通用 agent
规划能力或相对原生 `/goal` 的整体成本优势。

| 阶段 | 配对数（开发 / 留出） | 结果 | 实测成本变化 |
|---|---:|---|---:|
| 初始提案 | 6 / 6 | 自动启用 | 留出下降 65.83% |
| 合法整数哈希碰撞监测 | 6 / 未派发 | 自动撤回到原策略 | 开发增加 75.10% |
| 根据实际退化修复 | 20 / 20 | 新留出通过，再启用 | 留出下降 73.11% |
| 路径字符串任务迁移 | 20 / 20 | 同一策略通过另一分布 | 留出下降 77.81% |

合计 98 对、196 份原始输出，包括撤回尝试。所有测得的输出均通过
独立值检查；退化发生在成本。初版直接将整数放入 set，合法整数可有
相同哈希；修复改为保持数值相等关系的规范键，避免本次固定碰撞族。
这不构成对所有恶意输入的复杂度保证。

成本包括临时工作区准备、程序执行、进程清理和 grader；不含提案模型
生成、控制器等待和未暴露的费用。模型生成及整个优化会话的墙钟成本
不能从表内的执行收益推算。候选及材料的原始文件时间保存在归档 manifest。

初始 28 份非候选材料在提案落盘前冻结，最终复核字节未变。后续使用
新输入；3 次留出检验的 alpha 分别为 0.025、0.008333、0.004167，
没有换版本清零统计预算。监测首次因驱动中一个空行导致程序身份不同
被拒绝，未产生试验；随后读取实际启用归档，保留被拒版本和原因。

实际消费使用 `goal_evolve.py run-enabled`，对真实仓库的 156 个重复路径
得到保持首次顺序的 52 个路径。启用指针和归档 SHA-256 同时核对；
迁移验证没有伪造一次新的策略切换。

[初次解包结果](reconstruction-initial.json)与原 [reconstruction.json](reconstruction.json)
保留原貌：当时重算了值与成本，但未将报告中的 policy 身份绑定到 frozen
程序，状态链也部分依赖报告字段；不能把那次 `verified=true` 当作完整
身份/切换证明。[原审阅](../native-host/p0-p1-review.md)保留了被误接受的反例。

强化后的 [独立复核结果](reconstruction-after-audit.json)仍重建同一 98 对、
196 输出与三次 alpha 预算，并从 frozen 程序/归档身份、资格、正反向检验、
阶段完整性重建选择链。身份替换与不足阈值的撤回均被拒绝；后续把 `assert`
改为不会被优化删除的显式检查，普通、`-O`、`PYTHONOPTIMIZE=1` 都验证正反例，
最终 15 项测试通过。见 [完整记录](../native-host/audit-fixes/goal-verifier-optimize-after.json)、
[最终源码 SHA](../native-host/audit-fixes/goal-verifier-optimize-source.sha256)及
[独立重放](../native-host/audit-fixes/final-two-replays.json)。这些是重读既有材料，
没有新策略执行或模型试验；oracle 仍限本组整数、字符串和列表。

```sh
tar -xJf docs/evals/agent-evolution/raw-run.tar.xz -C /tmp
python3 -B examples/evolution-dedupe/verify_agent.py /tmp/goal-real-evolution-20261111
```

归档保存全部原料、输出、两个实际提案、触发 profile、检查器校准、
统计预算、被拒前置请求和每次运行的执行器源码；校验值见 [manifest.json](manifest.json)。
`raw-run.tar.xz` 未改，里面保留实验当时的旧源码；复核器修复不回写原实验。
当前修复版的源码和有失败的完整回归另见 [最终归档](../native-host/final-regression/README.md)。
局部执行收益不能推算为整个 Agent 会话收益；当前无通用进化或 9+ 结论。
