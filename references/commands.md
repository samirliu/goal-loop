# 目标管理命令

插件使用 `/goal-loop-host:goal-loop <command>`；独立 skill 使用 `/goal-loop <command>`。
无参数查看状态，`continue` 和 `继续` 是 `resume` 的兼容别名。管理子命令只接一个词；
附带目标或选项时显示 help，不把它们保存为原始请求。

原生 UserPromptSubmit 返回绑定真实 backend/session 的准确 CLI，skill 优先消费它。
没有 hook 的宿主用 `python3 -I "${GOAL_SKILL}/scripts/goal_commands.py" COMMAND --project PROJECT`；
恢复时提供真实 `--backend` 和 `--session`。不从历史 prompt 的先后顺序猜当前身份。

| 命令 | 执行与边界 |
| --- | --- |
| status | 共享锁下读取账本，汇总目标、迭代、任务、阻塞、worker；预算取契约、runner 和继承截止的最早值。不会重跑检查或授予完成。 |
| pause | 先确认没有待恢复的账本事务；排他锁下提交暂停围栏，再把宿主会话设为暂停并请求所属 worker 取消。取消确认仍来自实际宿主 interrupt/terminal 回执。 |
| resume | 拒绝 pending、过期预算和未确认的取消；沿用 run、原请求、截止和所有尝试历史。可显式绑定新宿主会话；普通 begin 仍不能复活已 end 的会话。成功返回当前执行地图。 |
| clear | 先暂停。未终态 worker、持有锁的 runner 或策略消费者会阻止归档。完整保留旧账本、预算、证据、策略和宿主回执，业务文件不移动。 |
| check | 调用原 receipt，实际重跑 audit/Gate，保留各自输出和退出码。没有完成申报或证据过期时如实返回 NO-GO，不制造 clear 判词。 |
| recover | 调用原 recover；若 clear 中断，则完成同一次归档。恢复不运行业务检查，不重放外部副作用。 |
| doctor | 检查依赖、完整安装清单、生成入口和版本一致性；报告实施根。它不安装依赖、不修改宿主配置。 |
| help | 显示用法和兼容别名，不读写目标。 |

暂停和恢复不冻结墙钟，也不追加工作预算。过期后仍可 check、收账、recover 或 clear。
若存在取消待确认，返回 rc=3 及真实 ticket/agent 标识；skill 应实际 interrupt/reconcile 后重试。
没有可靠终态的 worker 不会被自动标记为已停止。

`control.json` 的内容或缺失标记由原不可变提交保存。暂停/恢复沿用同一提交指针，
发布后才安装文本视图；两者之间中断会拒绝进一步工作，recover 安装同一已提交围栏。
验收脚本创建、修改或删除控制状态会触发门控写入检查，不能得到 GO；被改的已管理控制状态
由原 recover 精确恢复。已有普通事务 pending 时先恢复，避免控制写入改变待恢复事务的基线。
旧清单没有 control 字段仍可读取；下一次控制器写入、管理状态提交，或对已有控制回执执行 check 时，
保留其原内容并纳入当前清单，不重置原目标和预算。

clear 在 `.goal` 目录 inode 的排他锁内移动旧运行的顶层条目到
`.goal/history/<archive-id>/`，保持锁 inode 不变。`clear-pending.json` 先记录项目、
旧 HEAD、run 和条目的设备/inode；每次 rename 后同步目录。中断时普通账本入口拒绝访问，
recover 只接受每个条目恰好位于原处或归档处，且仍是原 inode。冲突时保留现场，
不覆盖新文件。`cleared.json` 保存最近一次归档位置，历史不参与新产物指纹。
下一次目标入口重新 init 空账本，再建立新的宿主预算；旧运行的预算留在历史中。

完成申报被 Gate 拒绝，或产物已经改变时，地图重新提供 verify 和新的 close 提交。
新提交使用当前 revision 与新的 operation_id；旧请求只通过 retry-close 确认历史，
不能用旧复审自动批准新产物。最终完成继续由原 audit/Gate 判断。
