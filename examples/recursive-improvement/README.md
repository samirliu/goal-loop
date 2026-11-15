# 目标执行中的递归策略改进

```sh
python3 -B examples/recursive-improvement/run.py --output /tmp/recursive-policy-new
python3 -B examples/recursive-improvement/run.py --output /tmp/recursive-policy-repair-new --counterexample
```

例子真实测量相邻交换排序 → 插入排序 → 内置排序，两代候选都与当前已启用的父代比较。每代先做开发、独立留出和正反例校准，再在实际带重复值的生产输入上消费归档；最后由原 controller 收账及 Gate 验收。没有 mock 成本、sleep 伪造收益、改阈值或失败重试。机器噪声或预算不足时可以不晋升，保留原始报告。

`--counterexample` 的第二代故意使用会丢失重复值的集合排序；初始独特整数样本没有暴露缺陷。实际生产检查产生反例，新的重复值输入触发撤回到插入排序，再用保留重复值的内置排序修复。评分器、校准及成功门槛不变，留出曝光和检验预算不清零。工作区内保留失败与撤回记录。

候选算法是明确的示例夹具，脚本不调用模型，也不声称自行发明算法。实际使用时由宿主 agent 根据反馈写候选。实测只支持本组本地工具策略的成本/正确性结论，不包含模型提案成本、通用规划能力或模型权重改进。递归深度、真实消费及完整反馈可从 `project/.goal/proposals/policy/` 和 runtime spans 重建；生成了候选或打印建议不算收益。

运行协议和能力范围见 [递归改进说明](../../references/packs/improvement.md)。安装包也携带这个例子；所有输出必须放到新目录。
