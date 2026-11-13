# W3 执行器回归证据

本目录证明所列执行语义，不证明相对 `/goal` 的任务效率优势，也不提供 Linux 平台实测结论。

`manifest.json` 固定旧提交、封存实现/测试 SHA-256、原始回归输出与补丁摘要。三个 `before-*.txt` 来自相同测试复制到旧提交的隔离临时目录：

| 反例 | 旧实现实际结果 | 修复必须满足 |
|---|---|---|
| runner 被杀后保留 zombie | worker 仍写出 leak 文件 | 进程组取消，内核锁释放，resume 不新领预算 |
| 独立 gate 遇到无约束 timeout 工具 | 慢检查跑完且错误通过 | 不调用该工具，检查超时并清理后台进程 |
| gate 被杀后保留 zombie | 原检查仍写出 leak 文件 | 在 owner 尚未被回收时取消检查组 |

另有一次开发中发现的真实缺陷：外层组取消会同时杀死内层监督器，内层独立检查组继续写文件。`before-nested-cancellation.txt` 保存失败；测试先等待内层就绪标记，再杀 owner。修复让监督器脱离 owner 的进程组，通过内核退出事件清理自己的检查组。最终完整 Python 回归包含该测试，不能用前一轮 95 项通过来覆盖它。

`python-regression.txt` 与 `shell-regression.txt` 是封存版本完整输出；未观测的 tokens/费用为 unknown。运行时间只是这些回归的耗时，不能解释成 agent 交付速度提升。

复放当前生命周期测试：

```bash
python3 -B tests/test_runner_lifecycle.py
```

复放封存实现可在独立临时目录展开 manifest 中的 `baseline_commit`，应用 `implementation.patch` 后运行同一命令。补丁只含所需生产文件与本项测试。`restoration-check.json` 记录了隔离目录逐文件字节核对与复测结果。复放旧实现时只复制该测试文件，不应用生产补丁，再按 manifest 的 selector 运行 `-k SELECTOR`。复现开发中的嵌套缺陷时，对封存实现再应用 `reproduce-nested-bug.patch`，运行 `-k outer_executor`。

macOS 硬预算需要能读取系统启动标识；工具沙箱若禁止该只读查询，应明确申请运行测试的权限，不能绕过或静默取消预算约束。

测试同时覆盖 6 个竞争 runner 仅派发 1 个 worker、预算提交点两侧、恢复不延长截止时间、runner 三个投影视图的拒绝/恢复、冻结墙钟与 resume、预算内/迟到交付的区别。这些是正确性证据；crew 净收益和通用自主晋升仍按主优化方案独立验证。
