# W3/W4 宿主接入与 W5 实际失败收口

2026-11-12收尾：当前状态见[状态页](../../p0-p1-status.md)。后续[同源双平台完整回归](regression-closed-20261112/README.md)已通过，[六位置真实W5](claude-haha/w5-headless-v3-independent-review.md)完成且planner选择串行，[grader校准](grader-coverage/README.md)补齐五个反例。[直接skill入口](claude-haha/native-skill-flow/README.md)的独立检查和Gate通过，CLI回合上限失败也保留。用户已要求收尾停止，目标保持暂停。以下137文件及旧Work/v3表格属于历史版本，不能替代这些后续记录。

36 次对照保持停止。本目录保留生产适配、真实宿主回执、权限失败与
实际取消证据；不将本轮集成开发数据解释为无偏的效率对照。

最终修复版的 [137 文件源码、完整输出和哈希索引](final-regression/README.md)
已冻结归档。macOS 完整 Python 237 项有 1 项计时失败；Linux 同版
237 项有 2 项失败，另有只读目录导致的 forge 夹具失败。两平台的
shell 603、parser 78 与文档检查通过；不能写成完整回归全绿。
隔离复跑只作为工具回执摘要保留，不覆盖完整失败。当前仍无 9+ 结论。

已实现并验证：同一 runner 截止从 prompt/tool 入口继承；随机 ticket
绑定原生 worker；启动确认、first-tool-ready、宿主终态、检查通过和采用
分开；原始报告正文不参与成功决定。runtime 保留 worker、measurement、
owned command 的父子关系、产物前后摘要及未知成本。

实际取消使用真实 Work worker 启动的心跳孙进程。观察到 3 次写入后，
控制器写入该 ticket 的取消标记；清理后和宿主终态后的复测均保持 3，
工具返回 130。模型随后正常返回，因此回执记录 returned，而非伪造
interrupted。更早的四次尝试没有启动心跳，全部保留，不计作该验证通过。

| 实际波次 | 结果 | 解释 |
|---|---|---|
| 串行委派 | 独立集成检查通过；2283.13 秒 | 包含明显控制器等待；不是有效的纯执行时间基线 |
| 第一 crew | 未完成；2040.19 秒 | READY 均未执行；权限请求等待及用户中断，不重置预算 |
| 预检后的 crew | T2 检查并采用；T1 有产物但被中断；1336.85 秒 | T1 自检的内联 shell 再次进入权限审核，等待 991 秒 |
| 到期后恢复派发 | 机械拒绝 | `time-budget-exhausted; no dispatch` |
| 父控制器有界结算 | GO + time-budget-exhausted NOTE | 只检查已存在的字节，记为迟到接受，不回填按时成功 |

实际失败揭示两个接入点：派发前完成所需的精确权限预检；命名检查用
固定的 `check_command`，避免模型生成新的 heredoc/复杂 shell 触发另一项
审批。前缀已批准不保证新复杂命令获批，也不能解除已经挂起的请求。
权限仍由真实宿主管理，不扩大许可或伪造 READY。

`goal_host_command.py --check PROJECT TICKET` 直接加载冻结图的 job check，
以项目 cwd 运行并继承当前最早截止和取消标记，只记录 measurement；
first-valid/采用仍须终态后的独立验证。新增入口的 13 项宿主测试及
4 项命令测试通过。后续v3波次中，7个实际原生worker通过该固定命名检查；
这些自检不会代替父级验证或授予采用。

v3在同一1800秒总截止、同一项目与冻结检查下运行，原始报告见
[native-v3-report.json](native-v3-report.json)。没有重置预算或替换失败样本：

| 案例 | 独立验收 | 墙钟秒 / worker占用秒 |
|---|---|---:|
| single-1 | 21/21，GO | 298.351 / 285.042 |
| crew-1 | 21/21，GO | 299.091 / 509.112 |
| crew-2 | 21/21，GO | 263.331 / 474.643 |
| single-2 | 21/21，GO | 263.133 / 261.817 |
| single-3 | 父级验证124，未采用，BLOCKED | 341.745 / 309.069 |
| crew-3 | 未派发 | — |

single-3的worker自检在截止前约58秒完成，但父级终态观察、独立验证和结算
未赶上截止。七个已派发worker均有真实终态；不能把自检成功回填成预算内交付。
只有两对完整配对，crew墙钟几乎持平，worker占用约1.79/1.81倍。
起点至首次prepare的230.608秒单独计入suite，未藏进零成本准备。
阶段时长和worker reservation包含观察延迟，不能当作供应商compute或费用。

planner没有在失效现场恢复基线：最新样本quality=false且六例条件未满足，
恢复守卫拒绝；3+3门槛仍不足。此次实测不支持默认扩crew。
修复后的planner把实际输入字节纳入全部比较身份；公共CLI可读取API产生
的记录，但不会把两种producer的数据混合。旧源码观测不重新贴为新版本。

新入口前的完整源码封存在 `tested-before-check-command.tar.gz`，对应
187 个 Python 测试、603 条 shell 断言通过。新增入口之后只补跑了与其
直接相关的 17 项测试，不把旧完整结果冒充新入口的完整覆盖。
文档一致性和本机 Claude plugin validate 通过；author 缺省警告保留。

固定检查入口对应的Linux快照另有188项Python测试、603条shell断言通过，
见[完整输出](check-command-linux-results/result.txt)及
[源码清单](check-command-linux-source-manifest.json)。该快照先于输入缓存、
Gitlink和进化切换的审查修复；不能作为修复后最终版的完整结果。

初次完整 Python 回归在 2 秒预算夹具上失败，独立复跑通过。夹具改用
5 秒总预算、8 秒迟写，仍断言仅一次派发、恢复不延长和无迟写。
初次完整日志误被后续复跑覆盖，只保留工具返回的失败摘录；文件名
`before-check-command-goal-host-full-python-initial-failure-excerpt.txt` 明确标记
这一证据缺口，没有将摘录称为完整原始日志。

当前 Work 使用显式 bridge，不能声称仓库 hooks 透明拦截了 Work。
Claude/Codex 原生 hooks 已提供配置与解析测试，真实安装后的全事件覆盖
仍需验证。供应商总 tokens/费用保持 unknown。两对真实 single/crew 配对
没有证明并行净收益；planner 保持 3+3 同条件观测门槛。

[原始归档](raw-native-host.tar.xz)保存618个文件，包括v3全部五个尝试和
未开始项、早期权限/中断失败、五次取消探针的正负结果及源代码。
[清单](raw-native-host-manifest.json)记录每项原始路径、时间、权限和SHA-256。
可独立检查实际spawn/终态、冻结检查、产物、预算和失败；没有追加模型试验。
独立审查与修复后的第二次审查分别保留在
[原审阅](p0-p1-review.md)、[复审](p0-p1-followup-review.md)，反例及定向修复记录
在[audit-fixes](audit-fixes)。
