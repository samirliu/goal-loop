# 评估记录索引

本目录保存冻结版本的原始结果；旧记录中的“当前”“最终”“完整通过”只属于那份快照，不能转授给后续工作树。当前安装和执行说明见[文档索引](../README.md)。

| 主题 | 证据入口 | 适用范围 |
| --- | --- | --- |
| 4.1.3 合并前仓库复验 | [冻结审计](repository-review-20261115/README.md) | 当时的修复、清理和实际检查范围；不代表后续版本 |
| 干净安装与 cc-haha 发现 | [Clean install](clean-install-20261115/README.md) | 4.1.2 的原生加载/CLI、角色和合成 hook 回放；未运行模型 |
| 验收完整性 | [Acceptance integrity](acceptance-integrity-20261114/README.md) | 原始请求、校准、外部结算、数值与脚本冻结的反例 |
| 视觉质量 | [Visual acceptance](visual-acceptance-20261114/README.md) | 需求、参考/机位、冷席判读及原案例回放 |
| 合格策略的实际消费 | [Qualified routing](qualified-routing-20261114/README.md) | 局部测试工作流的配对成本与留出结果，非通用 agent 优势 |
| 执行闭环与直接提交 | [Learning edge](learning-edge-20261113/README.md) / [Direct submit](direct-submit-20261113/README.md) | 原地图、恢复、局部返工及机制成本 |
| 宿主、worker 与围栏 | [Native host](native-host/README.md) / [cc-haha](native-host/claude-haha/README.md) | 各快照的真实调用、失效与独立复核 |
| 账本与跨平台回归 | [Linux](linux/README.md) / [资格水位](watermark-eligibility/README.md) | 原冻结回归、失败和恢复 |
| 预算、成本与检查点 | [Gate budget](gate-budget-runtime/README.md) / [Crew cost](crew-cost/README.md) / [Checkpoint](incumbent/README.md) | 同一预算、已测协调开销与内容回退 |
| 策略实验与进化 | [Agent evolution](agent-evolution/README.md) / [Evolution dedupe](evolution-dedupe/README.md) | 明确作用域内的候选、晋升、保留、撤回 |
| 原生 Goal 对照 | [Real agent](real-agent/README.md) / [Protocol efficiency](protocol-efficiency-20261113/README.md) | 失败、取消、未完成和原始效用限制一并保留 |

复验生成的 `verification-*` 目录属于本地派生产物；正式报告、源码归档和原始证据保持跟踪。复验不能覆盖原结果，也不能把受控协议 fixture 当成真实模型观测。
