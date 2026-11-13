# 局部纠错与学习消费

```sh
python3 -B examples/learning-edge/run.py
```

无需 API、模型或新依赖。输出路径包含项目、原始失败检查、波次回执、策略归档、统计预算、最终 audit/Gate 回执及 `result.json`。

例子先让一个复制单元失败，只重派该单元并保持另一个的字节；再从 W5 原始开销报告形成有范围和反证条件的候选。策略试验的 trial 遥测明确受控，用于验证既有晋升/撤回状态机。随后实际执行归档策略，`begin` 将 crew 请求限制为 inline，第二个并发 dispatch 被生产入口拒绝。回归后撤回，未消费的旧计划不能再派工，新的计划恢复基线。最后仍需原控制器收账、audit 和 Gate。

这个例子证明机制接通，不证明串行候选的真实效用。输出的 `agent_utility=unproven`，受控成本不能加入真实任务成本统计。新候选必须接受冻结的真实留出任务比较，证据不足时保留旧策略。

`ablation.json` 对照两个独立 audit/Gate 入口与一个聚合回执入口：仍实际执行两项原检查，正确产物同样通过，改变已接受产物后同样拒绝。只减少一次公开入口调用，不据此推算模型耗时或token收益。

图 v2 沿用原格式，仅为 job 增加 `inputs`。局部复用绑定真实输入、输出字节/权限、接口、检查器、契约和路由版本。上下文中的路径白名单不是 OS 文件隔离。

独立复放旧版生产反例：

```sh
python3 -B devtools/replay_learning.py --baseline /path/to/frozen-before --current . --output /tmp/learning-replay.json
python3 -B tests/test_learning_flow.py
```

完整本轮证据入口为 [执行记录](../../docs/deepening-execution.md)。
