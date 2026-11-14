# 在真实仓库测试工作流上学习路由

这个例子实际运行本仓库测试，不调用模型、原生 Agent 工具或第二个宿主。基线使用原 planner 的未知成本串行路径；候选建议三个独立本地进程并行。目标是完整工作流成本，包括准备、执行、验证、收账、原 audit/Gate 和归档，不把打印 JSON 的速度当作净交付收益。

需要完整源码仓库、POSIX Python 和 gawk；安装包通常不包含 `tests/`。运行：

```sh
python3 -B examples/learning-regression/run.py --output /tmp/regression-learning-new
python3 -B devtools/consume_regression.py --experiment /tmp/regression-learning-new \
  --output /tmp/regression-learning-new/later-observed.json
```

也可加 `--prepare-only`，先审阅冻结协议、grader、方法清单与来源哈希。每阶段固定 6 对、成本改善门槛 15%、单次试验 90 秒、总实验 900 秒；没有重试或换阈值。72 个不同测试实现位置经固定 seed 打乱后分给开发和留出，每个实例三个 job、每个 job 两项测试；另有 12 项实现位置用于两个后续消费实例。排除重继承方法的重复身份，选择不依赖实测速度。

每个 job 在真实监督进程内执行请求的 unittest，写出请求 ID、实际执行数、失败、错误、跳过和成功标记。独立 checker 要求精确覆盖且失败、错误、跳过均为零，不能仅凭退出码或 worker 自述。good 校准完成完整流程；两个 bad 校准分别提供损坏的业务产物和无效路由。实际运行前后核对冻结源码，源漂移使 grader 失败。

测试夹具使用自己的 goal 目录，所以 worker 清除继承的 `GOAL_*` 会话/trace 环境，避免把内部测试的收据写到外层目录。外层真实进程监督器仍持有 job、后代和截止；原测试阈值和断言不变。原 Gate 最终要求所有业务产物通过实际检查。

实验阶段把候选输出用于隔离试验；后续消费通过真正的 `--policy-state`、资格报告、planner、begin 和 dispatch，包含策略检查、执行与复制状态的成本。未配置策略仍沿用原 planner；显式 inline、依赖、文件域、容量和剩余预算约束保持有效。

`raw/` 保存每个完整项目归档、真实进程输出、波次和原终验。`state/` 保存配对、校准、留出预算及实际启用指针。它是可重跑的局部执行实验，不是对模型质量、token 费用、完整原生 agent 效率或跨平台普遍收益的证明。源码、任务形状或平台超出该规则的范围时，应保留基线或重新比较。

本次冻结源码的原始结果、研究成本和局限见[评估记录](../../docs/evals/qualified-routing-20261114/README.md)；不要把生成了程序、打印建议或重复了基线记为新的学习收益。
