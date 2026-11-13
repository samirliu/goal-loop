# 直接 skill 入口：Gate 通过，CLI 回合上限触发

本次直接调用用户提供的claude-haha，输入为`/goal-loop-host:goal-loop --auto --time-budget=360`与隔离项目的原small TASK。测试器仅准备TASK/public/starter并监督整场360秒；没有替模型预建契约、ticket、wave或收账。模型自行完成契约、宿主begin、实现、自检与close-iteration。

结果必须分开读取：

- **产物与账本通过**：独立small grader为42/42，audit=0，独立gate=0，输出`GATE: GO … iter=1 ac=2 pass=2`。最终核验距driver入口161.463秒，仍在原360秒内。
- **CLI未正常完成最终回复**：退出1，原生结果为`error_max_turns`、`Reached maximum number of turns (40)`。这是测试器设置的辅助回合上限；不能将Gate通过改写成CLI退出0。
- **入口预算保留**：实际begin使用SDK session `97f8bb8e-71f8-4fd4-b436-ef625bbc4c28`，runner origin为该session的`host-prompt-entry`，未在后续stamp重发预算；外层harness另施加入口360秒硬cap。
- 输入与runtime源码哈希未改变。原small判读器从已冻结源码复制；后续medium grader增量不影响本次small family。

[原始84份材料](raw-run.tar.xz)包含driver、命令、过滤事件、模型实际产生的.goal与代码、冻结判读器、独立检查输出和源码；[清单](manifest.json)、[SHA](SHA256SUMS)保留全部字节/权限。没有thinking或凭据环境。

这是一例完整命令入口的功能验证，不是速度对照或通用优势证明。按用户“完成当前任务后停止”的要求，只封存本次结果，不移除回合上限重跑、不续期、不另开恢复或优化试验。
