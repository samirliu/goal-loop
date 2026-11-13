# 独立 gate 总截止与执行成本观测

这里保存原始反例、封存补丁和实际交付的命令记录，不将局部正确性测试解释成 agent 效率优势。

反例：总预算已过期，五条 AC 各需一秒、每条 check_timeout 为十秒。旧执行路径给每条检查独立时间，全部跑完并返回 VERIFY-OK；原始失败见 `before-expired-batch.txt`。现在整批验证（含指纹准备）共用单调截止，过期结算只允许整批一次三秒；后续 AC 不重新领时。环境里的 supervision 标记不能跳过实际监督。`test_gate_budget.py` 也覆盖慢哈希消耗同一预算。

完整回归另外发现很远的合法 deadline 导致 kqueue/poll 等待范围溢出。修复保留绝对截止，只把一次内核等待限制为六十秒；`test_owner_watch.py` 与原场景 159 均验证这条路径，原预期没有放宽。

`delivery-transcript.json` 是一次实际字节交付，`contract.md`、`loop-log.md` 和 `observed-runtime.json` 是对应材料。监督器记录了实际命令、结果、时长、产物与仪器身份以及父子关系。smoke 测量发生在批准前，最终验收发生在批准后，两种契约摘要均按实际读取版本保存。记录没有环境变量快照或内部思维过程。

统计边界：

- 这里记录 supervised command spans；不把它们重新计成产物改进或迭代收益。
- 父 span 含子 span，不把重叠区间相加为墙钟或总资源成本。
- 未完成记录保持 unfinished；损坏、缺失数据为 unknown，不补零。
- tokens/费用没有数据来源；外部/传递输入身份、恢复/协调阶段和 CLI 外 subagent 尚未完整观测。
- 最终 gate 仍实际重跑检查；遥测失败只影响成本结论，不创造 GO。

`manifest.json` 固定版本、源码摘要、补丁和检查结果；`python-regression.txt`、`shell-regression.txt` 是封存版本的完整输出。可在独立目录展开 baseline_commit 并应用 implementation.patch，复跑以下入口：

```bash
python3 -B tests/test_gate_budget.py
python3 -B tests/test_runtime_trace.py
python3 -B tests/test_owner_watch.py
```

旧反例用 `before_implementation` 指向的前一份封存补丁重建，再只复制本轮 test_gate_budget.py、运行 `-k expired_standalone`。`restoration-check.json` 保存隔离目录逐文件复原检查和复跑结果。macOS runner 的硬预算需要读取系统启动标识；独立 gate 的纯契约预算测试不需要该查询。
