# 修复版 auditlog：六个真实位置完成

同一修复版、同一任务和原21项grader，固定ABBAAB六位置；用户提供的claude-haha实际MiniMax-M3.1-Flash映射，不覆盖模型或effort。新批上限1800秒，不续跑旧v1/v2或旧Work。控制器实际1406.782秒结束，六例原grader均通过，九个原生worker终态后分别验证/采用，六波封存后才恢复原STARTERS与权限。

| 配对 | 单worker秒 | crew秒 | 单worker占用秒 | crew占用秒 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 152.660 | 225.237 | 150.364 | 275.234 |
| 2 | 208.920 | 458.224 | 207.216 | 510.292 |
| 3 | 243.817 | 117.249 | 242.036 | 158.275 |
| 均值 | 201.799 | 266.903 | 199.872 | 314.601 |

这些是本批三对的描述值，不是置信区间或总体因果效应。第一、二对crew更慢且占用更高；第三对两个指标均较低，不能只展示这一例。worker span包含reservation、CLI启动/排队和终态观察延迟，不是供应商compute。真实总tokens/money仍为null。

每种job图分别一个condition，六位置同一个batch身份；原planner实际读取6条Python API观测、3条single baseline，无pending/fault；选择`serial`，原因为`startup-coordination-or-dependency-cost`。其observed-range比较为serial lower152.660、crew upper458.224，仍在原剩余预算内，不创建第七波或新预算。[原报告](report.json)与[全部描述统计](descriptive-summary.json)分别保留。

`quality=true`仅指原21项及采用条件；controller的`protocol_ok`只覆盖它检查的派工/并发。真实运行仍有域外Write被拒、跨worker读取和简报之外自检，全部保留，不能称全程简报合规，也不能据此宣传普遍crew净收益或比原生`/goal`更快。原grader的覆盖另作posthoc校准，不回写这六个原成绩。

[453份冻结材料](raw-run.tar.xz)保存预注册、driver、实际命令、源码、所有过滤后的事件、失败与产物、launcher及host/crew/runtime记录；[清单](manifest.json)与[SHA](SHA256SUMS)核对。thinking、凭据环境不入档。原始21项通过与完整任务规格、实际协议遵循、跨任务迁移是分别需要证据的结论。
