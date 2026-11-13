# W5 v3 独立重建（2026-11-12）

v3 已完成六个固定位置、3+3 原 grader 实测和原 planner 闭环：六次 final 各 21/21，九个原生 worker 均 returned，三次 crew 都有真实 READY 区间重叠。独立重算与原 planner 的 **serial / startup-coordination-or-dependency-cost** 一致。worker 的 scratch、额外测试、跨 scope 读取等偏离也实际存在；不能把六次质量通过或 controller 的 protocol_ok=true 写成全简报合规，也没有 crew 净收益证明。

先将终态现场冻结为 `/tmp/goal-w5-claude-auditlog-v3-independent-frozen`：453 个普通文件、2,427,415 bytes。[输入清单](w5-headless-v3-independent-inputs.json) SHA256 `a59ebf12c7f3ad3893bb3bba549d49b8b782f397862f12fd7ce318708c2ba2ae`；与 [原始归档](w5-headless-v3/raw-run.tar.xz) 的全部文件 bytes/modes 一致，归档 SHA256 `55d10008495396ecdc1d9ca83550f9f4e48e2501976fff119d1ca01046f74334`。没有修改 live、旧失败、原档或 production，也未重跑模型、grader、测试。[独立 stdlib 读取器](w5-headless-v3-independent-check.py) 以显式 require 校验；普通 Python、`-O`、`PYTHONOPTIMIZE=1` 的 [机器结果](w5-headless-v3-independent-check.json) 完全相同。

实际顺序固定为 single-1、crew-1、crew-2、single-2、single-3、crew-3。以下保留全部位置，Δ=crew−single；worker 秒数是 prepare/dispatch→观察到原生返回的占用 span，含启动、排队和观察延迟，不是供应商 compute 或账单。

| 配对 | single Wave 秒 | crew Wave 秒 | Δ 秒 | single worker 秒 | crew worker 秒 | Δ 秒 |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 152.660 | 225.237 | +72.577 | 150.364 | 275.234 | +124.870 |
| 2 | 208.920 | 458.224 | +249.304 | 207.216 | 510.292 | +303.076 |
| 3 | 243.817 | 117.249 | −126.568 | 242.036 | 158.275 | −83.760 |
| 全位置合计 | 605.397 | 800.710 | +195.313 | 599.616 | 943.802 | +344.186 |

这是全部派发样本的描述性成本：crew Wave 时间合计高 32.26%，worker 占用高 57.40%；第三对的收益保留，没有筛掉快例或慢例。三对、一次任务的观察范围不是置信区间；实际协议偏离进一步限制可比性，不能把差异全部归因为调度、并发或某项源码修复，也不与 v1/v2 的不同预算失败批池化。

身份和比较键独立核对通过。实际 runtime=`999.0.0-local`，所有已记录 parent/worker assistant model 均为 `MiniMax-M3.1-Flash`；六个 fresh CLI session 均 exit0，显式 namespaced bootstrap 的 READY、当前 root 的 `goal-loop-host@inline` 与唯一 `goal-loop-host:goal-loop` 注册可见。各 crew 的两个原名 Agent 按真实 message_id 合并，call_id、完整 worker_prefix、ticket/nonce、实际 task_started agent_id 与 READY 可绑定，无 model/effort/background override。九个首 Bash 均逐字复制短 launcher，launcher 路径、0600 mode、含完整 nonce 的正文与 pinned SHA 一致。

三次 crew 的实际 attempt READY→host return 区间重叠为 **40.912778、38.361743、32.964439 秒**。生产 Wave 的 started 记账点稍晚，原报告口径分别为 40.905982、38.355385、32.933834 秒；两种口径分别重算并保留，未把毫秒级记账差当解析错误，也没有用同批派发替代区间证据。

每个 worker 最后的 named check 均有 complete/result0 测量。总计 13 次 worker named check，其中 crew-1 T1 曾失败一次，随后修复并通过；失败保留。九份 completed metadata 和 task_notification 绑定实际 call/agent，native PostToolUse hook 均在父验证前成功。每个 job 都能重建 returned→独立 validate=0→first_valid（验证结束）→adopt→final；各次 adopted digest、冻结 final command/instrument SHA、归档四文件 bytes/modes 与原 21 项输出相符。117 个 non-lifecycle runtime span 全已结算，其中六个失败返回（一个 named check、五个 owned command）仍保留；不能称零工具错误。30 个 host-lifecycle span 继续 unknown/running/null，六个 SessionEnd 均有 host receipt。完整 raw hook 输入和工具正文未保留，本复核以结构化 metadata、native 通知和 sealed 收据交叉绑定，未声称能够重放缺失的原 hook payload。

实际协议行为单列，不因质量通过消失：

- 三次 single 都尝试向 `/tmp` 写 scratch 测试文件并收到错误结果，随后执行额外 inline/heredoc 行为测试。single-2 有一次错误项目路径的 Read 失败；single-3 有两次 Glob 错误，不能把这些尝试写成成功读取。
- crew 的 T2 均成功 Read 了 T1 的 codec/main；crew-1、crew-3 的 T1 也成功 Read aggregate。crew-2 T1 还通过 shell 循环读取整个 package，执行额外测试，显式 inspect 标准库源码，并通过 owned shell 创建 `/tmp/exp_auditlog2`、`/tmp/exp3` 等实验内容。任意 shell 没有 OS 文件隔离保证，这些实际行为不能被结构化 Write/Edit 围栏覆盖的表述掩盖。
- crew-1 的两份 scratch/project 临时文件 Write 有明确 PreToolUse deny。全批原流共捕获 **五次**结构化写围栏 deny：四次 outside project、一次 outside owned scope。crew-1/crew-3 对 aggregate 的 Write 虽 is_error=true，却未保留对应 PreToolUse deny，不能把其错误原因直接归因围栏；工具正文仅保存 hash，原因保持未知。
- Write 共 34 次（24 个非错误结果、10 个错误结果），Edit 共四次（三个非错误结果、一个错误结果）。Edit 的合法调用已被这批真实执行覆盖，没有观察到 Edit 域外负例。全批 worker 工具错误结果共 22 个；多种审查标签可指向同一调用，标签数不当执行次数。机器结果保留每个 worker 的全部工具输入摘要、完整 shell 命令、结果与原 call_id；没有移除违例来改善成本结论。

准入与截止也有绑定证据。driver SHA 与预审 `aa6db26266ab956a5613a4e31c831b660e990df949e517f93d81ff7c41057a98` 相符，预注册原字节未变；ready 声明当前双平台完整回归终态且通过，运行冻结的 40 项 production/roles/refs/fixture 源码逐项匹配 [closed 139 文件清单](w5-headless-v3-independent-closed-source-manifest.json)，清单 SHA256 `db9793740d657e25a1c95b62ce4c38e326ef3e7b6ed6a7100ef0675546b7ebcc`。本复核没有重新执行该回归。

总预算从 driver 入口起算，requested=1800 秒，整批实际 1406.781991 秒。内容寻址 store 历史保持同一 run、同一原始 entry origin；epoch deadline 只从 1794488622 收紧至 1794488616，monotonic 同步仅收紧，没有逐轮重发预算。六次 final 均在各自原 deadline 内。每次新 Wave 的原四 STARTERS bytes/modes、输入、合同与 producer 一致，前波均已 finish；最终 baseline 恢复后才调用 planner，没有第七 Wave。两种 condition 各一个值、各三个观察，六个 batch_condition 相同；没有从旧项目读取样本。

原 planner 真实读取六条观察、三条 single，pending=0、quality failures=0。独立重算 serial_lower=152.659921、crew_upper=458.223889；serial worker lower=150.364015、crew worker upper=510.292338，与原值一致。planner 调用的剩余时间可界定在 386.356586–386.380037 秒，原规则在这个区间只会返回现有 serial 选择。它支持本批保留 single；并未再派一例来实测该选择的后续收益。原 planner_applicable=true 只覆盖其实际检查的质量、派发和并发条件；全程简报遵守仍为 false。

tokens/money 保持 null，CLI 本地累积估价和最后消息 usage 不当作完整供应商账单。没有 Gate GO、adversarial clear、通用 agent 效用或自主进化提升声明。准确的完成范围是：**六位置原质量与成本观察、实际并发、终态/采用闭环及保留 single 的原 planner 已实测；全简报合规和 crew 净收益未建立。**

读取器 SHA256 `2d2458f6dd6b3d47871cd8bdfa8626d90076fa10211b86a71f4b3105b9ab2b14`；机器结果 SHA256 `a4df92cbcf8c7515926a65517cfac7e03041de119cecc5a47a51a18512175fe8`。
