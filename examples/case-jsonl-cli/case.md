# JSONL CLI：实际试跑与修复

2026-11-04。目标是实现一个三模块、仅依赖 Python 标准库的日志 CLI，
覆盖统计分位数、查询过滤、严格输入校验及错误时 stdout 原子性。
任务与初始代码由 prepare.py 生成，公开检查固定；evaluate.py 在任务目录外，
执行者不得查看。验收覆盖41个固定边界与随机输入检查（seed 731901）。
这测的是实际模型执行，不是用手工分数序列模拟工作。

## 原始结果与开发复测

| 流程 | 执行方式 | 执行者报告耗时（含规划） | 独立验收 | 门控 |
|---|---|---:|---:|---|
| 普通实现/测试/修复 | 串行 | 196s | 41/41 | 不适用 |
| v4.1 修复前 | 两个并行 worker | 240s 截止仍未完成 | 0/41 | 无 GO |
| v4.1.1 开发复测 | 串行 | 207s | 41/41 | GO，rc=0 |

相同240秒软预算、相同起始代码、独立上下文、继承相同模型/工具设置，
未切换模型。这里的普通流程不是宿主内置 `/goal` 的实测。外部验收完成时点
也记录在 results/manifest.json：普通组从派发到根验收完成约215秒，开发复测约231秒。
执行者报告时间与根验收时间不同，不能混成一个精确速度指标。

修复前组截止时没有源文件实现、账本0轮；快照在截止后约16.6秒取得，
执行者同时明确报告截止时未完成，并停止 worker。后来补录的账不能回填为
截止前交付。原始截止状态保存在 results/skill-deadline-state.json。

开发复测是看过首轮失败、修改政策后的同任务测试，不能算新的留出试验。
其三轮账本实际是：一次实现收账、一次缺复审证据的拒收、一次补齐证据后通过。
**不是三轮实现优化。** 公共检查文件没有被改写；根代理独立重跑共享公开检查4/4、
封存验收41/41，以及实际门控，均通过。

## 问题 → 最小修复

1. **短预算并行净收益为负。** 前期读取、契约/测试和 worker 启动耗尽预算。
   修改快车道和 crew 选择：多文件小任务可以串行；启动成本未知且预算紧时先
   贯通，再考虑扩并行。预算包含规划和启动，不从首条 shell 命令才开始计。
2. **`--project` 只绑定验收，未绑定执行器 cwd。** 替身执行器读到仓库调用目录，
   而非含空格的目标路径。修复 run_claude 在项目目录的子 shell 中执行。
3. **退出 trap 会删其他进程的锁。** 只读检查和被拒的重复启动都会误删。
   现在仅已取得锁且锁文件 PID 仍是本进程时清理。此修复不声称把文件锁升级成
   完整的分布式/原子并发锁。
4. **快车道示例漏了复审证据参数。** 模型照流程先 claim，得到一次假完成计数。
   修正 SKILL.md 代码片段，要求先真实复审，再携带 clear 与具体证据。
   新测试直接提取并执行文档中的 claim 命令：首 claim GO，false_completes=0。
   另在全新目录复放真实 CLI 补丁并实际复审41/41，再执行文档命令，也在iter=1
   取得 GO、false_completes=0；原始输出见 results/repair-first-claim-after-doc-fix.txt。

运行器复现采用替身执行器，控制器、门控和锁生命周期是真实脚本，没有额外模型调用。
回归块137：修复前4通过/3失败，修复后7/7。块138：文档代码执行3/3。
完整场景套件509/509。

## 可独立复放的原始材料

- pre-reg.md：事先固定的任务、预算、失败线与结论边界。
- results/summary.json、manifest.json：结果、时间戳、候选版本与评估器哈希。
- results/{plain,repair}.patch：两个实际交付的源代码补丁。
- results/*grade.json：每条独立验收的 stdout/stderr、退出码与结论。
- results/repair-loop-log.md、repair-state.rec、repair-gate.txt、复审及 raw 输出。
- results/runtime-*：运行器修复前后的原始复现输出。

复放实际交付产物（无需模型/API；从仓库根运行）：

```bash
trial_root=$(mktemp -d)
python3 examples/case-jsonl-cli/prepare.py "$trial_root/project"
patch -d "$trial_root/project" -p1 < examples/case-jsonl-cli/results/repair.patch
python3 examples/case-jsonl-cli/evaluate.py "$trial_root/project"
# 预期41/41；将 repair.patch 换成 plain.patch 可复放普通组。
bash tests/run_tests.sh --only 137-138
```

这次证据支持：发现并修复了短预算派工选择、执行目录、锁清理和示例缺参。
它不支持“比普通流程更快”：复测207秒仍略慢于普通组报告的196秒，且每组仅一次，
时序/调度有噪声。tokens 与费用未暴露，均为 unknown。并未运行多次留出任务、
优化型 forge 任务或 Claude Code 原生 Stop hook 集成，不能外推这些能力。
