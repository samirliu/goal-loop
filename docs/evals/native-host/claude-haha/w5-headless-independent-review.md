# W5 v1 独立重建（2026-11-12）

这批没有完成 3+3 对照，不能证明 crew 净收益。实际结果为一次 single 验收通过、一次 crew 未完成、后四个位置未派发。crew 的直接停止触发是预注册 CLI `$1` 本地估价上限；T1 原生终态未知，控制器没有重置项目、采用部分结果或运行 planner。v2 属于另一 cohort，本结论不与其池化。

| 预注册位置 | 实际结果 | 原生 attempt | 独立验收 |
|---|---|---|---|
| single-1 | sealed | T1 returned | public=0；原 final grader 21/21；quality=true |
| crew-1 | stopped-unknown-native-terminal | T1 prepared/READY、T2 returned | 未 validate/adopt/seal；quality=null |
| crew-2 | not-dispatched | 无 | 无 |
| single-2 | not-dispatched | 无 | 无 |
| single-3 | not-dispatched | 无 | 无 |
| crew-3 | not-dispatched | 无 | 无 |

输入取自操作前独立冻结的 `/tmp/goal-w5-claude-auditlog-new-independent-frozen`。逐文件 [清单](w5-headless-independent-inputs.json) 覆盖 179 个文件、1,071,417 bytes；与 [原始归档](w5-headless-v1/raw-run.tar.xz) 的全部文件 bytes/modes 一致，归档 SHA256 `9e51eeb05f864c879bb27a4af11294feadd96460423573590879286604649536`。没有改写 raw report、原档或运行新模型/测试/grader。[检查器](w5-headless-independent-check.py) 仅用 stdlib，显式 require 校验；普通 Python、`-O`、`PYTHONOPTIMIZE=1` 的输出完全相同。[机器结果](w5-headless-independent-check.json) 的 `evidence_consistent=true` 只表示保留证据一致，`complete_comparison=false`、`net_benefit_established=false`。

实际 init 两阶段均报告 `999.0.0-local` / `MiniMax-M3.1-Flash`，plugin 为当前 repo 的 `goal-loop-host@inline`，唯一注册的 namespaced skill/command 为 `goal-loop-host:goal-loop`；冻结 manifest 为 `skills: "./"`，冻结 driver 发送字面量 `/goal-loop-host:goal-loop`。这支持明确的 namespaced 入口绑定，不把旧普通 `/goal-loop` 当作本版证明。原流未保存独立 `skill_command` 字段或展开的 SKILL 正文，不能声称存在该正文收据。bootstrap `READY` 只有原文 SHA（精确对应无换行的 `READY`），不是该任务输出文件要求 `READY\n` 的旧 hook smoke test。真实 UserPromptSubmit prompt-origin 收据在两个 session 均存在；这批先由 controller tool-origin begin，再取得 prompt receipt，未把后者改成新计时起点。

crew 的两段 parent Agent 流共享真实 `message_id=0744b2a4bfad9fdd4edffbdcd5cdb5f7`，call_id 分别为 `call_d3e7bcc37a8b6692956485ed`、`call_d3e7bcc37a8b6692956485ee`。按 message_id 合并、按 call_id 去重后确为同一 assistant 批次；均为前台 `goal-loop-host:goal-worker`，无 model/effort override，原名均保留为 Agent。旧 event 当完整 message 的规则会拒绝该批次。最终 raw crew report 因提前停止**没有发出 protocol_ok 字段**；独立结果另列旧规则结果 false 与重建 parent-batch true，不回写或冒称原 report 已判 false。header/nonce → call_id → native task_started agent_id → READY 均能绑定。

同批次不是实际并行证明。crew T2 READY 为 monotonic `1659476.873838791`，T1 READY 为 `1659480.183050291`；T2 host return 为 `1659526.861689375`，T1 同一原生调用在此后仍有 worker 事件，但没有终态。因此两者已观察到的 READY/activity 窗口重叠下界为 **46.678639 秒**；完整 READY→terminal overlap 与 crew 完成时长保持未知，不填补 T1 的终点。

worker 实际偏离也保留，不能由 parent-batch true 代替全协议通过：

- single T1 与 crew T1 的首个 Bash 均把内层 ready nonce 抄短，随后才运行正确 ready；single 还先尝试裸 `ls`，有一次错误项目路径的 wrapper 调用（runtime result=4）。single 额外运行自写 `python -B -c` 行为测试，超出这次 assignment 的 named-check 限制。
- crew T1 用 Grep 和 `cat` 读取 T2 的 aggregate 文件，并执行 `ls -la <work>/.goal`。这里证明的是目录 listing，未证明读取了内部私有 grader/历史正文。crew T2 Read 了 T1 的 codec/main，Write `/tmp/auditlog_scratch/test_agg.py` 并运行自建测试；有裸 shell/前置 cp，未逐项按所给 exact prefix 编写。它还临时破坏自己的 aggregate、运行 named check 得到 result=1，再恢复并通过；失败记录保留。具体 call_id、命令、可用 tool_result 均在机器结果中，末尾无返回的 Write 仅当尝试。
- 没有观察到 worker 再派 Agent/Task。上述越界是相对此次预注册 assignment 的事实，不扩张为新的产品安全门槛；它们使“本批全协议合规”无法成立。

single 的权威验收链可重建：host native returned 在前，随后 production 独立 validate=0，first_valid 恰为该验证结束，再 adopt，最后冻结 private final grader=0。adopted digest、final digest 与归档四文件 bytes/modes 一致；21 个原 grader check 均为 pass。single Wave.elapsed=162.339406 秒，worker_seconds=159.545649 秒（ticket dispatch 到原生返回的占用 span，包含启动/排队，不是供应商计算或账单）。

crew 第二条 result 为 `error_max_budget_usd` / `is_error=true` / `Reached maximum budget ($1)`，CLI supervisor returncode **1**；整体 Python controller 正常 exit0 不能写成 crew CLI0。`1.004334` 只保留为 CLI cumulative estimate，不能当 MiniMax 真实花费。T2 有 completed metadata、PostToolUse 与 task_notification；T1 最后只有 PreToolUse:Write 等活动，缺少 completed，因此仍是 unknown。crew 的 join 未闭合、final_validation/finished/adoption 均 null，partial-artifact 与当时 work bytes/modes 一致。

900 秒起点绑定 controller 入口、早于准备和首轮。内容寻址 store 的三条 runner 版本保持同 run、同初始 origin，epoch deadline 仅由 `1794474626` 收紧至 `1794474625`，monotonic 也仅收紧；整批 controller 285.319058 秒即停止，没有重发 900 秒。两次实际 Wave 的 baseline/输入/合同/producer 可重算，同一 batch key `aa008aac4c307821015e4a229769ee0d663ecf8036ba0ec07848fc18b2d11c9d`；fused/crew condition 各一个且不同，未达到各三个。预算内提前失败不等于所有 native attempt 都已终态。

两个 session 的 SessionEnd 均有 host receipt，九个 host-lifecycle span 保持 unknown/running/null，不冒充完成或活动 worker。后续**单独**的 [精确本地进程观察](w5-headless-v1/owned-liveness.json) 在所记时点没有找到 supervisor PID 11581/13022 或两 session；它不补造原生终态，也不证明远端推理已停止。原 planner 为 executed=false，baseline_restored=false；没有第七 Wave、替换失败样本或 Gate GO 声明，真实完整 tokens/money 仍为 null。W5 对照净收益要求在本批尚未完成。

检查器 SHA256：`c7be18a085c6ac532bd61684abf28fb7d4bf34e8bb5fea6926731922aa6f0398`。机器结果 SHA256：`8eedcbbbca9f099159f7bdc51bbc9b673a779d68f604e8a3fa87d5d97deccbf7`。
