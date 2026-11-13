# 五条不变量的定向变异

每个变异从相同源码复制一个临时目录，只改一个判断或写入点。
同一回归先跑原版，再跑变异版。只有原版通过、变异版退出 1，
且日志出现预期失败断言时，才记为抓到缺陷。

| 变异 | 被哪条原有或新增回归抓到 |
|---|---|
| GATE 忽略最终声明 | 未声明的 threshold 波次错误得到 GO |
| BIND 忽略文件内容 | linked worktree 改动后摘要没有变化 |
| PROVE 接受非零退出的数字 | gate 接受失败和超时测量的部分 stdout |
| GRADIENT 跳过水位 | 低于已记录水位的版本错误得到 GO |
| FENCE 先写后拒绝 | 非法 bind 批次退出后账本发生变化 |
| 总截止失效 | 独立验证在结算预算结束后仍跑完五项并返回成功 |

六个原版通过，六个变异命中各自的失败断言。精确修改、两侧
日志和源码哈希见[结果清单](results/manifest.json)。在同一版本复跑：

```bash
python3 -B docs/evals/invariant-mutations/run.py --output /tmp/goal-invariant-replay
```

结果覆盖列出的反例。Agent 实际行为、成本和留出迁移继续按
[效用试验设计](../../optimization-plan-v4.1.1.md#113-首批实际任务)验证。
