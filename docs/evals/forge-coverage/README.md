# Forge 实际探测与有界覆盖

这一版把 dry 资格绑定到冻结的输入、探测仪器、实际执行结果和
绑定到本轮产物的 critic 结论。输入和仪器在 raw/0 归档，每轮
结果进入既有提交历史。重复成功输入记为复测，新增探测可以通过
追加迁移进入范围，旧案例和材料继续保留。

原始样例用两组三元素整数输入检查排序去重，探测器以逐项列表
查询计算参考结果。故意丢弃负数的实现通过正数样例，在负数输入
上被探测器抓到。正确实现三轮的新增成功输入数分别为 2、0、0。
预算不足时保留未执行案例，critic 有 finding、过期或缺失时不给
dry 资格。示例中的 critic 文本是显式测试夹具。

[原始存档](raw-trials.tar.gz)含项目、调用输出和所有捕获到的 raw
版本，覆盖恢复前后的内容。独立核验器直接检查归档字节、输入、
参考结果和恢复记录，不导入 goal 的执行代码：

```bash
python3 -B docs/evals/forge-coverage/verify.py
python3 -B docs/evals/forge-coverage/run.py --output /tmp/forge-replay
```

核验器复验 11 条 dry 尝试和两次迁移故障。故障分别发生在
`generation-published` 和 `pointer-published`。恢复保留前者的
旧版本，完成后者的新版本，重复迁移保持同一提交。开发时曾用错
故障点名称，记录保存在 `harness-development.txt`；修正后已执行
实际故障点，并保存 `migration-faults/results.json`。

[旧版本反例](bare-counter-before.txt)对相同的场景 161 返回错误 GO，
新版拒绝只有计数、缺少实际探测历史的声明。该复放从
`cf198829f9c8efe740d7d30a09de5d0251303b62` 依次应用 W5、检查点、
配对试验、中间检查点和 Linux lint 补丁，再复制当前的测试 helper、
场景和 `goal_forge.py` 供夹具生成绑定头。旧控制器和 gate 保持其
原始行为。运行命令为 `bash tests/run_tests.sh --only 161`。

[本阶段补丁](implementation.patch)可在上述基线上重建当前实现。
隔离重建后的 13 个 forge 测试通过。macOS 与 Linux ARM64 的完整
套件均为 142 个 Python 测试和 603 条 shell 断言通过。
首次全量 shell 运行发现 6 个回归，原始失败保存在 before 目录。
修复恢复了纯 `--digest` 的无 Python 路径，并让旧场景在测试
下一种缺陷前恢复已被拒绝的事务。

只读 subagent 审阅提出了异常路径、动态证据和旧数据迁移风险。
它没有完成修复版的独立复跑。这里的通过结论来自原始输出、
存档核验和隔离重建，真实 Agent 行为与效用继续按 W9 验证。
