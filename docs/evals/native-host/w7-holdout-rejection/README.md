# W7：开发获益、留出退化时拒绝新候选

本证据关闭原计划§9.3的一项直接分支覆盖缺口。trial 遥测受控；生产 `goal_evolve.experiment`、目录锁、持久报告、启用指针及实际 `run-enabled` 均未替换。它证明决策和归档选择的正确性，不是新的模型运行或策略效用试验，不加入既有98对/196输出。

先用现有夹具完成一次晋升，保存已验证 incumbent 的实际程序字节、启用指针和原始记录；下一协议将该程序作为 baseline，提供行为不同的新 candidate。受控数据为：开发六对成本下降50%；完整留出八对成本增加50%，质量资格均通过。保留原收益阈值、时间预算与 grader 字节，第二次 alpha 仍为0.008333；增加两个新留出输入以满足该次预算的最小可判别样本数，没有清零统计历史。

实际 `experiment` 得到 `holdout-rejected`。落盘报告保留完整留出失败，`enabled.json` 字节与旧指针完全相同，旧 report/trials/归档字节未改，旧输入曝光记录保留，统计 evaluation 从1增到2。随后真实子进程调用生产 `run-enabled`，exit 0、输出 `candidate\n`，来自旧归档；新程序会输出 `candidate-v2\n`。

[最终定向输出](after-targeted.log)记录 `python3.12 -m pytest -q -s tests/test_evolve.py`：11 passed in1.12s。该文件保存工具返回的完整输出及 command/exit 标记，并非另行重定向的原始日志。首次新增测试在比较内存 tuple 与 JSON list 时失败，其[工具回执摘要](initial-test-tool-receipt-summary.json)保留；修正仅将内存报告规范化为 JSON 再比较，没有修改生产决策或放宽预期。未捕获首次尝试的独立完整 raw log，不补造。

[精确差异](test.patch)、[修前测试](before-test_evolve.py.txt)、[修后测试](after-test_evolve.py.txt)及 `/tmp` 原[清单副本](original-manifest.json)均保留。测试 SHA 从 `be23b98a…b3be32` 变为 `3ee988fb…36b82b`；production `goal_evolve.py` 保持 `e6ff794567ce37409a8cd7cca0efc2efa93b35a0bf968b3d22411ccd908d0ae7`。本次封存未运行测试、模型或生产入口，未改旧档。`SHA256SUMS` 与 `manifest.json` 记录本目录字节；该测试增量不属于先前 source139 完整回归。
