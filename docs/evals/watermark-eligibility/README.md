# 资格水位与恢复收口

旧实现可通过真实入口复现：合格产物 score=10 → 候选 score=100 但质量地板失败
→ 恢复原检查点 → 再收账 score=10，门控错误拒收 `best=100`。
`before.json` 保存原始命令和结果；`after.json` 保存同样三轮恢复后的 GO。
原始项目分别保存在 before/after 压缩包，没有改写旧失败。

本次修复将原始尝试和资格分开。`scores.rec` 保留坏候选的高分；
只有当前地板、校准 horizon 和质量背离检查通过，才能推进 `best_score`。
最近合格 score/judge 独立记录，恢复不会和失败候选比较，同分的新判断也不会丢失。
资格检查返回 `QUALITY-OK`，完成仍须真实交付门控 GO。

资格绑定使用与 stamp 相同的语义表面加 check_freeze，普通备注不能重置水位。
临时篡改契约导致的失败也不能抹去旧资格。bind 中的资格更新和判词共同提交；
检查污染账本会硬失败并保留恢复日志，不能把污染提交为新权威版本。
旧 verdicts-only bind 提交和中断记录按原范围重放、恢复，不虚构历史 state 快照。

## 验证

- macOS 完整 Python 回归：155 项通过；随后新增的真实 minimize 背离检查单独通过。
- macOS 完整 Shell 回归：603 条断言通过。
- Linux ARM64 最终完整快照：156 个 Python 测试、603 条 Shell 断言通过，shellcheck 通过。
- 从上一封存源码应用 implementation.patch 独立重建：22 个检查点/资格测试通过。
- 旧 HEAD 的真实 bind 源码：已提交操作重放、pointer-published 中断恢复与重放均通过。

`manifest.json` 绑定实现、测试和补丁摘要；完整输出与旧源码复现脚本已保留。
重建定向检查：`python3 -B tests/test_incumbent.py`。
旧版兼容复放：`python3 -B docs/evals/watermark-eligibility/review/repro_legacy.py`。

## 开发失败保留

首次沙箱全量运行无法读取 macOS kern.boottime，未当作产品通过；随后按已授权
方式在沙箱外完整复跑。Shell 首次全量为 601/603，旧 minimize 夹具仅追加了原始
score 对，没有声明既往资格；保持原断言，补齐显式资格输入后复跑 603/603。
另有真实控制器 minimize 测试验证该行为，没有依赖手写资格夹具。

Linux 首次打包遗漏 VERSION，并带有上述旧夹具，结果为 Python 155/155、
Shell 598/603。修正包装与夹具后使用全新只读快照完整复跑，原始失败在 linux-before，
最终结果在 linux-final。没有从最终通过推定首次也通过。

这些证据证明本次正确性和恢复修复；不能单独证明智能体在真实任务中更快。
