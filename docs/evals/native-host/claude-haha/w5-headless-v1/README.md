# W5 headless v1：估价上限中断

2026-11-12，用户提供的本地 `claude-haha`，实际模型映射为 MiniMax-M3.1-Flash。预注册900秒、ABBAAB六个位置；控制器在285.319秒停止，不续跑本批。

| 位置 | 实际结果 |
| --- | --- |
| single-1 | 原生worker返回，父级独立21项检查通过并采用；波次162.339秒，worker span159.546秒 |
| crew-1 | T2返回，T1已READY但没有可靠native终态；CLI退出1，`error_max_budget_usd` / `Reached maximum budget ($1)`；未验证或采用整波 |
| crew-2、single-2、single-3、crew-3 | 未派发；没有替换失败或凑配对 |

1美元是实验driver设置的客户端估价上限，未知模型的回退价目不能代表供应商账单。控制器整体退出0仅表示保留记录并按未知终态停止，不表示crew的CLI或任务成功。真实tokens/money仍为null，未请求planner建议，未恢复基线。

同一assistant message的两个Agent被stream拆成两事件。两条保留的`message_id`相同，因此不能将单个stream事件当作完整工具批次；后续解析修正单列，不回写本批报告，也不将未知终态或worker简报偏离改为成功。

[原始归档](raw-run.tar.xz)保存独立冻结副本的179份文件，包括driver、预注册、全部过滤后的事件、实际命令、源码、host/crew/runtime收据、通过样本和未封存crew。未保存thinking或凭据环境。[逐文件清单](manifest.json)与[校验值](SHA256SUMS)可核对全部字节。另一次只读进程核对未找到两个已记录监督PID或对应CLI session；它不证明服务端推理已停止。

新v2另建run/project，不与本批或旧Work池化；本批不支持3+3比较或crew净收益结论。
