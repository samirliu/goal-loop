# W5 v2 独立重建（2026-11-12）

v2 仍没有完成 3+3 对照，不能支持 crew 净收益。独立核对原始流、带校验和的 host/crew/runtime 收据、store 历史和产物后，结果如下；不以 controller 的 `protocol_ok` 代替 worker 实际行为。

| 位置 | 保留结果 | 原生/验收状态 |
|---|---|---|
| single-1 | sealed；273.705745 秒 | worker returned；独立 public=0、原 private final 21/21；adopted bytes/modes 与归档一致 |
| crew-1 | stopped-unknown-native-terminal | T2 returned；T1 native Agent 已启动，bound agent_id/READY=null；整波未 validate/adopt/seal |
| crew-2、single-2、single-3、crew-3 | not-dispatched | 无替换、无补样本 |

本复核先冻结 `/tmp/goal-w5-claude-auditlog-v2-independent-frozen`，共 182 文件、1,457,265 bytes；[输入清单](w5-headless-v2-independent-inputs.json) 与 [原始归档](w5-headless-v2/raw-run.tar.xz) 的全部文件 bytes/modes 一致。归档 SHA256 `6e0216c992c50093ca285d47051eecbe44b356f5fa1bb4d04a3a465df26a0008`。v1 的原始材料和失败结论保留，未池化。[独立检查器](w5-headless-v2-independent-check.py) 仅用 stdlib，没有 production import、模型调用、测试、grader 重跑或原档写入；普通 Python、`-O`、`PYTHONOPTIMIZE=1` 的 [机器结果](w5-headless-v2-independent-check.json) 完全相同。

原生身份和派发证据成立：实际 runtime=`999.0.0-local`、model=`MiniMax-M3.1-Flash`，当前 root 的 `goal-loop-host@inline` 及唯一 namespaced `goal-loop-host:goal-loop` 注册均出现在实际 init；冻结 manifest 为 `skills:"./"`，driver 的 bootstrap 显式调用该 namespace，取得实际 UserPromptSubmit prompt-origin。没有单独保存展开后的 `skill_command`/SKILL 正文收据，不能冒称存在。crew 两个原名 Agent call 在真实 message ID `0744c290dd7bcd059fe374c6c77a1c47` 下，call_id 为 `call_b3c269edd2f94c5e9d363b79`、`call_d1d705dd62b84b1b999ef981`；两份 parent prompt 均完整保留原 worker_prefix。没有 parent model/effort override 或 background 派发。

实际 READY 结果与同批派发不同。T1 native Agent ID 为 `a21b260d024e52f1e`，但其 128 个 tool_use 全有 is_error=true 返回，91 次 Bash 没有一次在 strip 后等于原 owned/bare READY。首个 Bash（`call_e0d36a668456913c66a56d70`）是复合 shell，含错误 nonce、重定向、echo 和另一次内层 nonce 缺字的命令。attempt 始终没有绑定 agent_id、没有 READY，且没有记录 direct-child owned command runtime span。T2 的首个 Bash 精确复制原命令即成功，实际 ID=`ae9dd886e875e1114`，READY→host return 约 55.080 秒，存在 completed metadata、task_notification 与 named check=0。**这批没有两条已建立的 READY 区间，因此不能报告 READY 口径的实际重叠，更不能补 T1 的终点。**

对 Python 路径别名假说也做了原始证据核对。冻结 `goal_host.py:205–217` 按当前 sys.executable 生成 brief，`:464–470` 再生成并作字面相等匹配，跨解释器路径确有独立源码风险；本批实际 hook 生成的 updatedInput wrapper 则与 prepare 同为 `/opt/homebrew/opt/python@3.14/bin/python3.14`（single 的 9 条、crew 的 1 条，crew events.jsonl 第 168 行）。这是 hook 实际输出，不能拿该潜在风险替代本批已观察的错误命令，也不能仅凭当前 PATH 猜历史 hook argv。尚未在本复核运行该风险的本地反例或生产修复。

worker 范围偏离逐项保留：single 首个 READY 参数曾错误拼接，下一次原样命令才成功；随后实际创建/编辑 `/tmp/auditlog_extra_tests.py` 并运行额外测试。crew T2 Read 了另一个 worker 的 codec/main，原流保存正常 tool_result。crew T1 还尝试读脚本、`/etc/hosts`、非 owned aggregate，尝试写 `.new`、probe 和额外路径；这些都收到错误结果，**只是被拒绝的尝试，不是已读泄漏或已写文件**。机器结果按 call_id 保存输入与可用 tool_result；多个偏离类别可能指向同一调用，不能把分类条目数当不同执行次数。未见 worker 再派 Agent/Task。scope 偏离按原预注册简报判定，不增设新的产品门槛。

single 的 returned→独立 validate→first_valid→adopt→private final 顺序成立；worker_seconds=267.946822 秒，仍是 dispatch→native return 占用 span，不是供应商 compute。crew 没有第二个 assignment final result，末条 result 只是 bootstrap success；最终 CLI returncode=124、phase=assignment，不能把 bootstrap success 当成整波成功。crew 缺少 SessionEnd host receipt；single 有该收据。八个 host-lifecycle span 仍 unknown/running，不补成 completed。本原始冻结快照不证明后续清理状态或远端推理是否仍活跃，单独的 liveness/quarantine 不能补造 native terminal。

预算确为同一入口 900 秒。store 三条 runner 版本保持 run=`1ecbb55829bf4bfbba632f10b22bd95d`、同初始 origin，epoch deadline 始终 `1794478590`，monotonic 仅收紧，没有重置计时；controller 在入口后 899.125842 秒完成退出/记录，约比向下取整后的 epoch cap 晚 0.062 秒收尾，不声称全部 native 工作都在截止前完成。两个实际 Wave 的初始四文件 bytes/modes、输入、合同、producer 与冻结 grader 可独立重算，batch key 相同 `d86992cc2d8e56e94d114ea660dd6cc1a9e6ee9a404939e36de00e1e72f2b780`；两种 condition 各仅一个，未达到各三个。没有第七 Wave，baseline_restored=false，原 planner executed=false。总 tokens/money 保持 null，CLI 估价不作真实账单。

结论仅限该 auditlog/backend/cohort：真实 namespace/原生同批派发和 single 验收已有证据；双 worker READY、完整 3+3、planner 实测选择及净收益尚未完成。没有新的模型实验或通用 agent 效用结论。

检查器 SHA256 `a45e743ccce50f00267e7d7b1baad647ec3e220f1c9ae24e09d7d5e0e7888763`；机器结果 SHA256 `cf45acdbd837c86ddc5b2ea0ff0607596683dd891313c3a622fce5d9a64f83ef`。
