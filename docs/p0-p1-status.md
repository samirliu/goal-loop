# P0 / P1 收口审计

2026-11-12 后续：用户已清除旧目标并新建“执行效率与学习消费”目标。
新任务实施与证据在 [深化执行记录](deepening-execution.md)，不恢复旧36次对照。
2026-11-13：该新任务的实现、本地回归及四次调用已收尾并停止。旧版2/2、新版1/2通过，
不支持整体提速；首次无契约入口修复仅有本地验证，未追加模型调用。完整结果与源码范围见上链。
以下暂停说明与表格保留为此前收尾时点，不代表新任务状态或新快照通过情况。

对照 `optimization-plan-v4.1.1.md`，按实际入口和证据更新；不按新增代码或断言数量计分。原计划的 P2 范围仍保留。

**当前状态：已按用户要求暂停。当前测试与归档已收尾，不自动续跑，不开启新的优化/模型测试。尚未宣称综合9分以上或相对原生`/goal`的整体优势。**

| 工作包 | 当前证据 | 仍需完成 |
|---|---|---|
| W1 / P0 内容绑定 | Gitlink递归绑定索引、HEAD与实际文件；顶层Git漏读失败关闭。scope19项与原反例独立重放通过；修复版256项完整回归两平台通过 | 未运行远程托管CI；本地两平台、原失败与修复后绿色版分别归档 |
| W2 / P0 主账本一致性 | init/stamp/bind/close 共用提交指针；主账本文本与完整快照核对；提交前后故障、恢复、重试幂等和版本迁移均有直接集成测试。另修复环境身份残留导致错误 GO、重置 approved 后重新盖戳两个实测入口；runner 预算也进入同一提交历史 | 不声称 external 测量缓存、作者材料或任意文件系统操作均已事务化 |
| W3 / P1 预算和生命周期 | 最早宿主起点、ticket、owned tool 共用最早截止；真实 Work 心跳取消、到期拒绝和迟到结算保留。实际 claude-haha 调用发现并修复无限 FD 上限导致 guard 退出的问题；正常7、超时124、取消130及无迟写有真实进程证据 | macOS 入口计时夹具与 Linux FD2000 准备夹具已定向修正，原完整失败不改写。Work 仍为显式 bridge；未观测的模型服务端取消不能推断成功 |
| W4 / P1 事件口径 | 当前插件 hooks 在实际 claude-haha CLI 观测 prompt、原生 Agent、READY、完成、独立验证/采用与 SessionEnd 落盘。handled setup error结算为实际失败。结构化Write/Edit围栏旧反例与修后16项/16子用例保留；后续真实双worker均短启动、Write负例拒绝、合法产物验收并采用，独立复核通过 | 本次真实CLI只测Write，Edit由实际hook测试覆盖；不覆盖任意shell写入或构成OS隔离。供应商总tokens/费用未知，点事件unknown不当作工作进程 |
| W5 / P1 crew 成本 | v3六位置及3+3窗口完成，原21项均通过，九个worker真实returned，整批1406.782秒；独立重算与原planner一致选择serial。单worker均值201.799秒/占用199.872秒，crew266.903秒/314.601秒；三对中只有一对crew同时更低 | 未建立crew普遍净收益或全简报合规；拒绝、失败与额外自检全部保留。旧Work/v1/v2不池化；新grader的28项复验属于posthoc，不回写原成本 |
| W6 / P1 候选比较 | 生产多文件检查点和配对实验已复验。新修复阻止坏候选抬高水位、R13 误阻止恢复、备注/临时篡改重置水位及绑定检查污染账本；独立重建 22 个定向检查通过。Linux 完整 156 Python / 603 shell 通过；macOS 完整 155 Python 加 1 个新增检查、603 shell 通过 | 非 Python 入口及跨任务可比性仍待覆盖 |
| W7 / P1 自主晋升 | 实际提案在合法碰撞输入上退化75.10%后撤回；修复版留出收益73.11%，路径任务77.81%。切换崩溃修复23项测试及11个子用例通过；最终verifier15项与优化解释器正反例通过，独立重建98对/196输出。新增实际experiment的dev获益/完整holdout退化拒绝分支，真实指针和run-enabled保持旧版，11项定向通过 | 新分支trial遥测受控，不加入98对效用数据。原初复核漏洞与旧实验保留；局部程序收益不等于通用规划或整个会话成本下降 |
| W8 / P2 forge 覆盖 | 已冻结并归档输入/仪器，绑定 critic 的迭代、产物和 scope，实际执行后才给 dry 资格。重复输入记复测，预算不足保留未执行范围；支持保留旧案例的追加迁移与提交点两侧恢复。旧裸计数反例被拒绝 | 真实 Agent 是否正确使用 critic/probe 协议仍需 W9 行为试验 |
| W9 / P2 真实效用 | 六个定向变异被捕获；真实宿主 Goal API 与 skill 开发试跑通过。首批正式配置派发 2/36，两次正确、按时且合规；小任务 skill 417.5 秒，比普通执行 330.7 秒更慢。发现水位缺陷后停止派发，现场全部保留 | 修复版另冻新输入完成对照；crew 和策略反馈消融及跨任务迁移结果仍需收口 |

## P0 / P1 未完成项的性质

独立审查及修复记录见[原审阅](evals/native-host/p0-p1-review.md)。原反例和原结论保留；定向修复通过不等于P1全部完成。未完成项按以下口径区分：

| 项目 | 性质 | 收口要求 |
|---|---|---|
| P0 / W1–W2 | F1 Gitlink及相邻顶层漏读入口已修复、独立重放拒绝旧GO；W2未发现新主账本缺陷 | 两处夹具修正后的同源256项两平台完整回归通过；旧失败原输出保留，远程CI未运行 |
| P1 / W3 宿主预算 | runner/gate 内核、Work bridge 与实际 claude-haha hooks 已接通 | 继续按最早可观察入口沿用同一截止；预算含准备和验收。未暴露的更早思考、服务端取消和额外compute保持未知 |
| P1 / W4 事件覆盖 | 实际 claude-haha 自动hooks已有交叉证据；命名空间入口已通过本地插件校验和最早起点测试 | 新六位置试验使用明确命名空间选择当前root SKILL；Work显式bridge不冒充全局自动接通，完整响应正文未保留的旧现场不追认逐字复核 |
| P1 / W5 crew 净收益 | 真实生命周期、短启动/写域及v3完整六位置均已验证；当前实测不支持默认crew优势，原planner保守选择serial | 全简报合规、跨任务净收益与相对原生Goal优势未建立；不删慢例、拒绝或旧失败，不为补分续跑 |
| P1 / W6 比较与恢复 | 核心机制及资格修复已完成；仍有覆盖扩展 | 当前比较执行器限定 Python，非 Python 执行适配属于扩展，不应冒充原方案明确要求的独立 P1 硬门槛；跨任务可比性随真实策略验证补齐 |
| P1 / W7 自主进化 | 局部实际闭环、切换故障、留出拒绝与复核器明确反例已闭合；当前同源完整回归通过 | 崩溃恢复不重放实验、不清零统计预算；不把已测局部范围扩成通用skill自我进化 |

供应商未暴露的 tokens/费用是观测限制，保持 unknown，不把“取得完整账单”新增为功能门槛。
主动脱离进程组、监督器本身被 SIGKILL 等是当前取消保证的边界，不等于本轮承诺实现通用 OS 沙箱。
W8/W9 属于 P2；36 次对照已按用户要求停止，不重开来替代 W3–W5 接入和 W7 实际闭环。

用户现已明确停止 36 次 P2 对照，调整执行顺序为：W3/W4 宿主接入 →
W5 真实 crew 验证 → W7 真实进化闭环。第二批保留 9 次完成、第 10 次
用户主动取消、26 项未派发的全部现场；不把用户取消计作产品失败或按时成功。

## 本轮宿主与实际进化证据

- [宿主适配和真实失败](evals/native-host/README.md)：固定入口、真实心跳取消、权限挂起、到期拒绝与迟到结算。
- [claude-haha 实际调用及独立核对](evals/native-host/claude-haha/INDEPENDENT-REVIEW.md)：本地客户端实际为 MiniMax-M3.1-Flash 映射；hooks/worker证据与旧全局skill选择风险分别报告。
- [无限 FD 真实因果配对](evals/native-host/claude-haha/f5-owner-guard/README.md)：只替换guard的同命令旧4/新7；另保留超时、取消、FD2000锁与stdout释放检查。
- [headless v1独立核对](evals/native-host/claude-haha/w5-headless-independent-review.md)与[v2独立核对](evals/native-host/claude-haha/w5-headless-v2-independent-review.md)：估价中断、实际工具名/分流、READY未建立及全部未派发位置均保留。
- [修复版v3六位置](evals/native-host/claude-haha/w5-headless-v3/README.md)与[独立重算](evals/native-host/claude-haha/w5-headless-v3-independent-review.md)：完整3+3、原planner选择serial及全部偏离/成本。
- [结构化写围栏](evals/native-host/structured-write-fence/README.md)：注册worker的Write/Edit实际hook旧版反例与修复，不改变正常权限流程。
- [短READY修复](evals/native-host/ready-launcher/README.md)与[真实双worker独立复核](evals/native-host/claude-haha/launcher-fence-independent-review.md)：不再让模型在首命令中重复抄nonce；检查SHA后绑定，两个Write负例被拒后仍完成合法交付。
- [留出退化拒绝](evals/native-host/w7-holdout-rejection/README.md)：受控遥测驱动真实production分支、指针与归档执行，独立于效用试验计数。
- [验收器校准与补齐](evals/native-host/grader-coverage/README.md)：旧grader误接受五个单缺陷mutant；新增七项后均拒绝，六份原产物离线28/28，原21项/时长不改。
- [直接skill命令全流程](evals/native-host/claude-haha/native-skill-flow/README.md)：模型自行契约到收账，独立42/42、audit和gate通过；CLI因测试回合上限退出1，分别报告后封存停止。
- [W5 窄上下文预注册](evals/native-host/pre-reg-v3.md)：目标3对，实际2对完成；原截止已结束，没有重置预算或替换失败样本。
- [实际提案闭环](evals/agent-evolution/README.md)：原始材料、自动撤回、修复、迁移以及独立解包重算。
- [修复后独立复审](evals/native-host/p0-p1-followup-review.md)与[最终重放](evals/native-host/audit-fixes/final-two-replays.json)：保留旧结论，并记录后续明确反例的关闭。

## 各冻结版完整回归

[137 文件源码、原日志与哈希索引](evals/native-host/final-regression/README.md)对应同一冻结版；未改源码或阈值，未追加模型实验。

| 平台 | Python 完整结果 | 其他检查 |
|---|---|---|
| macOS ARM64 / 3.14.8 | 237 项、1 failure：hash preparation 4.339360s，阈值4.2s | shell603 / parser78 / forge10 / docs通过 |
| Linux ARM64 / 3.12.14，uid65534 | 237 项、2 failures：后台进程退出观测、standalone gate 2.161612s > 2s；无skip | shell603 / parser78 / shellcheck / docs通过；forge9通过、1项只读目录夹具失败 |

两平台均非全绿。Linux后台进程后续最小诊断确认为Z，不能执行或持锁；测试已改为区分运行与僵尸，并以活进程作反例，证据见[诊断补记](evals/native-host/final-regression/README.md)。这不改写原完整回归。只读目录夹具失败不包装成检查通过。macOS同一hash preparation在3.14与3.12隔离各通过一次，仅有[工具回执摘要](evals/native-host/final-regression/isolated-hash-preparation-tool-receipts.json)，不能抹去完整失败。

后续[139文件冻结版](evals/native-host/regression-20261112/README.md)实际完整结果为：macOS Python248项1 failure（新夹具把wrapper启动计入4.2秒入口阈值）；Linux Python248项1 failure、2 capability skips（FD2000测试在soft1024时准备失败）。两平台 shell603、parser78、forge10、docs均通过，Linux另通过shellcheck。入口夹具改用独立记录的真实入口，4.2秒及反例断言不变；5项定向通过且旧版追加3秒、origin重置负例仍被拒绝。FD夹具只在真实hard允许时提升子进程soft至2001；Linux uid65534定向5项无失败、2项真实infinity能力跳过，实测FD2000、guard存活、stdout EOF、锁释放均通过。这些定向结果不改写248项原完整失败。

上述完整冻结后另有插件命名空间生产改动：manifest声明当前root skill、prompt hook接受显式插件入口。实际客户端plugin validate和两个入口最早预算定向测试通过；该delta不继承较早完整回归的通过结论。

再后的[修复版同源完整回归](evals/native-host/regression-closed-20261112/README.md)覆盖命名空间、两处夹具修正、Write/Edit写域、短READY与W7留出拒绝分支：macOS Python256项通过，Linux256项无失败、2项真实无限FD能力跳过；两平台shell603、parser78、forge10和docs通过，Linux另通过shellcheck。归档时139份源码均与当时字节匹配；旧137/139失败矩阵及原日志仍保留，未回填或覆盖。

此后仅medium示例grader发生评估增量，另新增自包含回归测试；runtime/scripts/roles/SKILL不变。该增量定向2项及5个子用例通过、六份产物离线28/28，不冒称最新grader字节已跑完整256项。原子发布中失败/并发可见性仍是明确覆盖限制。

## 证据入口

- `tests/test_view_authority.py`：直接生产入口的投影/索引损坏、恢复、迁移、批准标记与环境身份反例。
- `tests/test_worktree_scope.py`：子项目边界、linked worktree、带 shell 特殊字符的临时目录清理。
- `tests/test_close_commit.py` / `tests/test_mutation_commit.py`：真实控制器提交点两侧及丢失确认故障。
- `tests/test_ledger_access.py` / `tests/test_owner_watch.py`：并发和进程所有权。
- `tests/test_runner_lifecycle.py`：并发派工唯一性、预算提交点两侧、精确恢复、冻结时钟及 resume、无 GNU timeout 和 zombie 取消。
- `tests/test_strategy_events.py`：原始三轮记录复放、重复声明不得赚取收益、恢复与缺失身份断链，以及真实控制器路径。
- `tests/test_gate_budget.py` / `tests/test_runtime_trace.py`：独立批次共用截止（包括慢指纹准备）、真实耗时/失败保留与缺失成本处理。
- [W3 原始反例与回归](evals/w3-lifecycle/README.md)：包含旧提交失败与开发中嵌套取消缺陷的修复证据。
- [整批预算与实际耗时](evals/gate-budget-runtime/README.md)：封存反例、可复原完整源码补丁及真实交付遥测。
- [P0 反例记录](evals/p0-authority/manifest.json)：旧提交隔离复跑与当前实现复跑；不能以更改预期制造通过。
- [Crew 成本对照](evals/crew-cost/README.md)保存全部 18 轮、新输入复验和掉线恢复。
- [产物检查点复放](evals/incumbent/README.md)验证文件增删、权限恢复、用户编辑冲突及中断恢复。
- [策略进化原始实验](evals/evolution-dedupe/README.md)：候选 → 启用 → 撤回 → 修复 → 新留出验证。
- [多文件检查点配对](evals/checkpoint-evolution/README.md)保存 41 对试验、故障、生产 gate 复验及独立核验脚本。
- [中间检查点与失败测量](evals/intermediate-checkpoint/README.md)验证 forge 探索中的回退、完整 horizon 资格，以及失败和超时测量的拒绝路径。
- [定向变异](evals/invariant-mutations/README.md)在隔离源码中验证六条回归均能捕获相应缺陷。
- [Linux ARM64 回归](evals/linux/README.md)封存两轮完整运行，包含发现并修复的 shellcheck 问题。
- [Forge 实际覆盖](evals/forge-coverage/README.md)封存旧计数反例、11 条 dry 尝试、两侧迁移故障和双平台完整回归。
- [真实 Agent 对照](evals/real-agent/README.md)保存开发试跑、真实宿主 Goal 回执、独立观察器缺陷与修复，以及正式冻结清单。
- [资格水位与恢复](evals/watermark-eligibility/README.md)保存实际坏候选收账反例、资格修复、独立旧版重放、完整跨平台回归及源码重建。

旧 gate 场景夹具原本直接手写账本。现在由仅在测试 shell 中生效、不会导出的 fixture publisher 提交这些预置输入；原产品/协议断言保留。投影一致性等端到端测试不经过这个 publisher。这样分别验证“给定权威输入时 gate 的语义”和“生产入口是否拒绝非权威输入”。

## 评分约束与下一步

当前不能据此判定综合评分超过9。明确反例、同源完整回归与独立复审已有证据，
修复版v3真实任务数据与grader增量已封存；不为评分重开36次对照。真实crew净收益、
通用迁移及相对原生`/goal`的端到端优势仍未证明。

直接skill小任务的独立产物、audit与gate通过，CLI最终回复则被测试器40回合上限截断；原失败状态保留。用户已要求完成当前任务后停止，因此不追加重跑、恢复或进一步优化。六维审查中的8.1仍为此前阶段草稿，不冒充完成本轮数据后的最终评分。

历史版本边界保留在各评估目录：固定检查入口前 macOS187项、对应入口版
Linux188项完整结果均先于本次审查修复，见[旧版范围](evals/native-host/README.md)。
更早的crew、检查点、水位与forge原始结果继续保留在上述证据入口，不能转移
为最终快照的通过结论。Claude CLI403、Codex CLI未返回READY等失败也保留；
后来实际宿主Goal工具的成功回执不覆盖这些失败，见[真实Agent记录](evals/real-agent/README.md)。
