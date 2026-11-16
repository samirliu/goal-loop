# 历史证据与分发

默认插件和独立 skill 只携带运行资源、当前说明及可运行示例。历史报告、原始日志、
源码快照和压缩归档保留在源码仓库，不参与日常安装。历史结论只适用于各自冻结版本。

在线阅读：[完整评估索引](https://github.com/samirliu/goal-loop/tree/main/docs/evals)、
[设计与实践记录](https://github.com/samirliu/goal-loop/tree/main/docs)。

常用证据入口：

- [策略提案、退化撤回与修复](https://github.com/samirliu/goal-loop/tree/main/docs/evals/agent-evolution)
- [合格路由的实际消费与成本](https://github.com/samirliu/goal-loop/tree/main/docs/evals/qualified-routing-20261114)
- [执行闭环与研究成本](https://github.com/samirliu/goal-loop/blob/main/docs/deepening-execution.md)

在完整源码仓库中导出独立历史包，保留仓库相对路径：

```bash
python3 -I scripts/goal_install.py history --output /ABS/goal-loop-history
```

需要离线同时阅读运行说明与历史资料时，显式构建完整插件：

```bash
python3 -I scripts/goal_install.py plugin --output /ABS/goal-loop-complete --with-history
# 独立 skill 同样支持 --with-history。
```

精简包不自动下载历史资料，也不能凭空导出未携带的归档；上述操作须从完整源码或完整包执行。
完整包内的历史索引是 `docs/evals/README.md`。独立历史包用于研究，不是可安装插件。
历史包按 `assets/history-files.json` 导出，并携带版本、许可证和清单；精简运行包按 `assets/install-files.json` 构建；
两份数据清单互不重叠。历史证据不因精简分发而删除或改写。
