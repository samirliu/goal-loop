# W1–W7 完成度独立复审：2026-11-12

> 收尾说明（root补记）：下文保留v3运行期间的复审与六维评分草稿，不是当前最终评分。此后v3已完成并经[独立复核](claude-haha/w5-headless-v3-independent-review.md)，grader五个盲点已[校准修复](grader-coverage/README.md)，[直接skill入口](claude-haha/native-skill-flow/README.md)的产物/audit/gate通过但CLI触发测试回合上限。用户现已要求收尾停止，未重新评分或追加试验；当前事实以[状态页](../../p0-p1-status.md)为准。

本次沿用[原计划](../../optimization-plan-v4.1.1.md)的成功定义与六个评分维度。本轮只读核对当前源码、保留材料与版本边界。此前另经 root 授权补了 W7 留出拒绝分支测试，并按真实 W5 反例修复已知 Write/Edit 的 FENCE 缺口；各自前后证据独立封存。没有为本审阅运行模型、旧策略实验或全套回归。历史审阅与旧失败未改写。

**当前未找到仍未修复的具体 P0 反例；真实 W5 新暴露的结构化写围栏缺口已有旧版反例和修后定向通过，READY 长命令重抄失败也已改为校验过的短入口。新139文件冻结版两平台 full 已终态通过，独立双 worker canary 也已核对通过；claude-haha v3真实1800秒六位置成本批次仍在运行，故下方分数保留为草稿，不发布最终9+或净收益结论。** 不把“新 backend 必须跑赢串行”另设为验收条件；若实测更贵，保守选择串行是正确结果。

| 原始工作包与验收 | 当前实现、直接证据与判定 |
| --- | --- |
| **W1 / P0：实际字节绑定，漏读失败关闭，旧裁决过期** | [共享枚举](../../../scripts/goal_parse.sh#L128)与[内容摘要](../../../scripts/goal_tree_digest.py#L96)绑定路径、类型、权限、实际内容；显式 watch 纳入忽略产物，符号链接绑定链接文本。真实 Git fixture 覆盖脏文件再改、暂存后修改、特殊名称、增删、Gitlink、子项目与 linked worktree。先前 Gitlink 和顶层漏读保留旧 GO 的两个反例均经[独立重放](audit-fixes/final-two-replays.json)拒绝；无 Python 的 Gitlink 明确拒绝。**原硬项在所述范围关闭。** |
| **W2 / P0：非法请求不提交，唯一提交点，单写者与不重放恢复** | [Store.commit](../../../scripts/goal_store.py#L227)以校验过的不可变 generation 加原子 current 指针提交，幂等身份绑定实际请求；[读视图核对](../../../scripts/goal_store.py#L730)与 pending 拒绝避免混账。init/stamp/bind/close 和 runner 共用历史；目录 inode 的 SH/EX 锁贯穿生产入口。`test_close_commit`、`test_mutation_commit`、`test_controller_writers`、`test_view_authority` 直接覆盖指针前后、丢失确认、并发、迁移、损坏与拒绝操作。恢复只安装已提交视图，不重跑测量。**未发现新的未关闭主账本缺陷。** 外部缓存和作者材料不是跨所有文件的事务承诺。 |
| **W3 / P1：同一最早截止、resume 不续期、所属进程取消、有界结算** | [adopt_host](../../../scripts/goal_runner.py#L222)只收紧 epoch/monotonic cap，boot/时钟异常失败关闭；[gate_limit](../../../scripts/goal_runner.py#L284)整批共用有限结算。[真实 hooks 核对](claude-haha/INDEPENDENT-REVIEW.md)证明 prompt 缓存、begin/brief/wave 沿用最早 cap，而非把脚本入口冒称更早思考。F5 在真实 macOS 无限 FD soft limit 下先复现旧 guard 的 C-int overflow，再用[冻结 bounded 的因果配对](claude-haha/f5-owner-guard/README.md)只换 owner-watch，旧 wrapper4/新用户退出7；超时124、取消130、无迟写与 FD/锁/stdout 检查另有实进程证据。后续实际 nonce 复制失败与 Write/Edit 越界另见下文，不能从旧 smoke test 跳过这些负例。**已从本地内核推进到实际特定客户端接入。** Work 仍是显式 bridge；未观测服务端取消、主动逃逸进程组及监督器被强杀不属于已证明保证。 |
| **W4 / P1：实现、测量、声明、恢复分开，不能用重复声明赚收益** | [策略事件派生](../../../scripts/goal_strategy.awk#L36)直接复放原三轮为一次产物版本、两次声明；相同 digest 的分差只记新测量，恢复与未知身份断开策略归因。`test_strategy_events.py` 同时走真实 controller。[Trace](../../../scripts/goal_trace.py#L96)记录命令/仪器/产物/契约身份、实际耗时和缺失成本，嵌套 span 不相加为墙钟。真实 F5 后的3个 owned command、1个 named check 均完成；后续独立双 worker canary 中11个实际 worker/owned/parent span 均 complete/result0，父验证/采用顺序成立。handled setup error 结算为4；canary另6个 host-lifecycle 点 span 保留 unknown，不能计作活跃 worker。**原事件口径已实现；覆盖范围随实际观察明确标示。** |
| **W5 / P1：按依赖、启动与协调成本决策，保留故障和质量** | [planner](../../../scripts/goal_crew.py#L381)绑定实际输入字节、起始 owned scope、契约/仪器及 API producer，最近窗口保留失败；可比较 fused 单 worker 与分解 crew，二者均能满足期限但 crew 更费占用时保留串行。[原本地真实进程对照](../crew-cost/README.md)已有低/高启动成本反转、独立任务收益、故障保留与有限恢复；低启动留出1.908→0.902秒，高启动1.884→8.930秒。**该机制验收已有证据，但不能外推成模型并行普遍获益。** 旧 Work v3 只完成2对；新 claude-haha v1/v2 各保留 single 通过与 crew 未完成，没有完整配对。双 worker canary 只验证后续接入修复，不能补作成本窗口中的新样本。 |
| **W6 / P1：可恢复 incumbent、公平配对、先资格后收益、噪声不足不晋升** | [检查点归档与恢复](../incumbent/README.md)验证多文件字节/权限、用户编辑冲突及恢复中断；[多文件配对](../checkpoint-evolution/README.md)与[资格水位反例](../watermark-eligibility/README.md)验证地板/horizon 先于 best，坏候选不能污染恢复。`goal_evolve.compare` 在相同冻结条件下保留样本、波动和双向检验，单次偶然高分与不合资格候选不能晋升；`STRATEGY-PICK` 仅是局部观察。**原限定机制关闭。** Python 执行适配与 regular-file owned scope 是实现边界，不凭空增加“支持任意语言”的硬门槛。 |
| **W7 / P1：真实候选→留出→启用→退化撤回，冻结定义与保留失败** | [实际 root-agent 提案](../agent-evolution/README.md)保留初始6+6、合法碰撞成本退化75.10%撤回、修复20+20留出获益73.11%、路径分布20+20获益77.81%，并由 `run-enabled` 实际消费归档。最终 verifier 从 frozen/归档身份、独立值 oracle、双向统计与阶段完整性重建98对/196输出和三次 alpha，不再照抄报告状态；普通/优化解释器的原反例已关闭。新 pending guard/commit-point 恢复与下述留出拒绝测试补全了两个具体缺口。**已证明局部程序策略闭环，不能称通用规划自我进化或全 Agent 成本下降。** |

W7 切换的生产语义已不再允许“报告 withdrawn 但已知退化旧指针仍可执行”：首 trial 前持久化 evaluating guard；[run-enabled](../../../scripts/goal_evolve.py#L481)在同目录共享锁内拒绝未解决 guard；[切换恢复](../../../scripts/goal_evolve.py#L182)校验材料和 before/after 指针，以 `enabled.json` 为提交点，随后发布最终报告并清理 pending。指针前后、报告写失败、丢失确认、CAS/材料修改、真实归档执行和 version2 多文件均有故障测试。无完整决定的 evaluating 崩溃可显式 `recover --abort-incomplete` 安全置空为 interrupted/uncertain，保留原 pointer、raw、used-holdout 与统计预算，不重跑 trials，也不冒充已证实撤回。正常仪器无效或证据不足继续保留已启用版本。

本次逐项核对发现原§9.3“开发获益、完整留出退化时保留 incumbent”缺少直接 production 分支证据，已用[新增测试](../../../tests/test_evolve.py#L86)关闭：先提交已验证 incumbent；新候选 development 六对成本下降50%，holdout 八对成本增加50%，原第二次 alpha=.008333、收益阈值和预算不改。实际 `experiment` 产出 holdout-rejected，真实指针字节完全不变、旧原始记录保留、统计 evaluation 从1进到2，真实 CLI `run-enabled` 仍执行旧程序并输出 `candidate`。`tests/test_evolve.py` 的11项通过（1.12秒）；trial 遥测受控，因此只证明这个决策/切换分支，不新增真实效用样本。新测试 SHA 为 `3ee988fb804527001d5a9d943ce82af58fb40313e9690607a71413b2ab36b82b`，production `goal_evolve.py` 仍为 `e6ff7945…d0ae7`。[完整证据](w7-holdout-rejection/README.md)封存命令、日志、差异和首次 JSON tuple/list 测试错误工具摘要；首次失败不属于产品决策错误。

真实 W5 的负例均保留。旧 Work v3 的1800秒原截止已经结束，只有2对完整配对，第5项独立验证124，第6项未派发；不续期、不补造第三对。[claude-haha v1 独立复核](claude-haha/w5-headless-independent-review.md)保留 single-1 验收通过162.339406秒、crew 触发客户端辅助 `$1` 估价上限后 T1 native terminal 未知、其余4项未派发。该 CLI 估价不是供应商账单。两次 Agent 流共享真实 message_id，经 call_id 去重确为同一 assistant 批次；READY/activity 重叠下界46.678639秒，但未知 T1 终点不能补成完整并行时长。worker 跨域读写和额外测试也保留，所以不能把 parent batch 成立等同全协议合规。

[v2 独立复核](claude-haha/w5-headless-v2-independent-review.md)确认原900秒同一起点和截止未延长，保留 single-1 273.705745秒、原 public/private21项通过；crew 两个原生 Agent 同批启动，但 T1 的128个工具调用均错误、91次 Bash 无一次精确等于原 READY，始终没有绑定/READY，T2 独立完成。controller 在原截止退出，CLI124，其余4项未派发，没有 validate/adopt/seal 整波、baseline reset 或 planner。**这批没有两个已建立 READY 区间，不能报告实际 READY 重叠。** Python 路径别名有源码风险，但原流实际 updatedInput 使用同一解释器，不拿该风险替代本批已观察的抄写错误。v1/v2 各一个条件样本，仍不足 planner 最近3+3窗口；这是未证明的成本/效用范围，不要求新 backend 强行胜出，也不为补分追加 cohort。

上述 v2 single 的真实 `/tmp/auditlog_extra_tests.py` Write/Edit 是已有 FENCE 缺口，不能归为纯“worker 不听话”而关闭。`owned_shell` 当时在登记后直接放行非 shell。随后[旧版反例→修复](structured-write-fence/README.md)先用同一新增测试在旧 host 观察到 symlink 域外 Write 返回 `{}`，再只换 host 为原始 root/row.files 锚定的结构化路径检查；host16项与16子用例通过。检查拒绝其他 task、`.goal`、域外和 symlink 逃逸，deny 后可重试；合法调用和 parent 保持正常权限。只覆盖已知 Claude Write/Edit；任意 Bash 副作用和 OS 隔离不在本补丁的承诺内。目录 hook 用例不冒充 crew 目录摘要支持。

READY 的后续最小修复在 [ready_launcher](../../../scripts/goal_host.py#L205) 与 prepare：冻结 `command_python`，为每张 ticket 写入有 SHA 绑定的 `ready-ID.sh`，worker 首命令只执行短 `bash <path>`；hook 在首次绑定和重用时核对 regular path/字节 SHA。原 owned READY 仍兼容，不改变 nonce ticket 身份或正常权限。root 返回的4个 launcher 定向检查通过（16 deselected，2.61秒，工具回执口径）。随后[真实 canary 独立复核](claude-haha/launcher-fence-independent-review.md)在冻结96份原材料后核对原流、hook、ledger、runtime和字节，没有重跑模型/grader。两 Agent 同一实际 message_id，首 Bash 均原样 launcher 并 READY；两次 forbidden Write 的调用→唯一 hook→明确 deny→is_error=true 链成立，随后合法文件均为精确 `READY\n`。原生 completed→父 validate=[0,0]→adopt→final0/quality=true 顺序和摘要相符。实际 READY→return 重叠12.169778秒；CLI口径31.006345秒，最终验收口径约31.255931秒，均在同一180秒 cap。这里只实测 Write，Edit仍由定向 hook 测试覆盖。不同 auditlog 任务和旧 v2 不作速度因果比；不补为3+3净收益证据，也不从未触发截止的 canary 声称清理分支实测。

[source139 完整矩阵](regression-20261112/README.md)保留 Mac248/1 failure 与 Linux248/1 failure/2 capability skips；不能写全绿。两处失败已定位为新计时观察起点和 FD2000 准备夹具，修正保持4.2秒阈值及实际高 FD/guard/EOF/锁断言，定向复验另列。namespace manifest/hook 的后续生产 delta 与本次新增 W7 测试不属于该 full snapshot。按原§13.1，最终应按实际源版本列适用验证，不能把旧 full 结果移花接木；这属于版本/验证尾项，不应重标为已经复现的产品 P0。

新139文件 `/tmp/goal-p1-final-20261112-closed/source` 已逐项读取核对，打包前后139项和当前对应源码均相符；manifest SHA为 `db9793740d657e25a1c95b62ce4c38e326ef3e7b6ed6a7100ef0675546b7ebcc`。该版包含 FENCE、launcher 和新增 W7 拒绝测试；host SHA为 `6cd50115f5e0ac78e89b9287a2475026a6aa9a3db7a2245a4efe9e9d8c2eb060`，test_host为 `76a4be36a263a703f2c613c873b97fd8ce11ec1b32031d96e013b23fb887f864`。[本版完整原始结果与源码归档](regression-closed-20261112/README.md)确认 macOS256项OK（632.458秒）；Linux256项零失败、2项真实infinity能力skip（886.022秒）；两者shell603/parser78/forge10/docs均通过，Linux另shellcheck0。原始输出和环境完整保留，没有用单例复跑覆盖失败。上一失败快照和本版虽同为139文件，字节与结论分别保存。

claude-haha新 v3 `/tmp/goal-w5-claude-auditlog-v3` 已在本版 full 终态后启动，`goal-v3-ready.json` 的源/结果对照已收入上述归档；六个预注册位置共用新入口起算的1800秒。这是新 cohort，旧 Work v3与claude-haha v1/v2保持原停止、预算和失败历史，不池化。**当前 v3终态及独立成本核对仍 pending，不预填成功率、完整配对或planner结论。**

六维评分草稿如下，**不是最终评分**；待当前 v3终态及独立材料核对后审定。已完成的同版 full 与 canary只补充各自正确性/接入证据，不预先证明 v3 效用。评分沿用原维度，是工程审阅判断，不是统计估计，不按文件/断言/晋升数量加分。

| 原维度 | 草稿 /10 | 依据与限制 |
| --- | ---: | --- |
| 架构与职责划分 | 8.5 | 受审内容、提交权威、runner 截止和 native 收据职责清晰；未新增 agent 服务或调度平台。宿主与已有控制器仍有适配复杂度。 |
| 核心正确性 | 8.8 | 已知 P0、切换崩溃、资格污染、无限 FD、已知工具写域与 READY 失败均有具体修复和直接验证；同版回归与独立 canary 已完成。复杂真实任务的跨轮稳定性证据仍有限，v3尚待结算。 |
| Evals质量 | 8.0 | 原失败、冻结版本、独立重建、负例与成本分母均可审查；真实 v1/v2 完整配对缺失，canary 不替代效用对照，模型正文未完整保留的地方明确限制。 |
| 执行效率 | 6.5 | 本地进程能根据启动/协调成本反转决策，局部策略有真实执行收益；真实模型 crew 尚无同条件净收益，nonce 失败曾消耗大量预算，31秒异任务 canary不能证明 auditlog 交付变快。 |
| 自主进化能力 | 8.5 | 实际 agent 提案、独立留出、合法反例撤回、修复/跨分布与崩溃恢复已形成可执行闭环；结果只支持已测局部程序范围，不是通用规划或整个会话成本收益。 |
| 可维护性 | 8.0 | 状态核心、故障恢复、旧版迁移和审查重建已有明确接口；仍需维护跨宿主 hook/解释器/权限差异及较多持久状态，不能仅凭入口变短给满分。 |

按六项等权仅作展示，草稿约8.1/10；并非原计划新增的验收算法或承诺分数。P0/P1 机制收口与综合9+不是同一命题；不把远程 CI、账单或通用泛化改成硬门槛，也不因本次目标要求9分而修改实际成功定义。

远程托管 CI、供应商未暴露的完整账单、通用规划迁移和额外语言适配均不是原 P0/P1 硬门槛。当前客户端为 `claude-haha999-local` / `MiniMax-M3.1-Flash`，不冒称标准 Claude 或旧 Work backend；所有费用缺失保持 unknown。原 W8/W9 属 P2，36次对照继续保持停止状态，不为补分重开。
