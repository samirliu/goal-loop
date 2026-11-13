# 短 READY / Write 围栏 canary 独立核对

本次真实双 worker canary 的目标链路有独立证据支持：两 Agent 同一原生 message ID 派发，首个 Bash 原样执行短 launcher 并 READY；两次域外 Write 确实被拒绝；随后两个合法文件各为精确六字节 `READY\n`，named check、原生 typed completion、父 validate/adopt 与原 final check 均完成。范围只覆盖这次短 launcher 和 **Write**；实际没有 Edit 调用。

先冻结原现场为 `/tmp/goal-claude-hooks-launcher-rg1v7ekj-independent-frozen`，共 96 个普通文件、666,925 bytes；初始冻结清单 SHA256 `5408952cdfbce0b6979bfd25956dc49ccd57dd89efa35cacbfd09587307da5fd`。完整 bytes/modes/SHA 清单嵌入 [机器结果](launcher-fence-independent-check.json)。[独立读取器](launcher-fence-independent-check.py) 仅用 stdlib，检查前后输入未变；未调用模型、已有 checker/grader、named check、测试或 production API。普通 Python、`-O`、`PYTHONOPTIMIZE=1` 输出完全一致，校验均使用显式 require。

实际 runtime 为 `999.0.0-local`，model=`MiniMax-M3.1-Flash`，当前 root 的 `goal-loop-host@inline` 与唯一 namespaced `goal-loop-host:goal-loop` 均见于 init。评估的 `goal_host.py` SHA256 为 `6cd50115f5e0ac78e89b9287a2475026a6aa9a3db7a2245a4efe9e9d8c2eb060`，driver SHA256 为 `3d5e520b06537d0df1f49f5378f300f5aac35fb8712707cb91d888ac2aa576d9`。

两 parent Agent 虽分成两条流事件，真实 message ID 同为 `0744c81ca2b5372bbd661c898748c1bb`；不按时间接近猜批次。两份 prompt 完整保留各自的 worker_prefix，无 model/effort/background override。绑定为：

| worker | 原生 call_id | 实际 agent_id | 首 Bash |
|---|---|---|---|
| T1 | `call_01a1cf4e793e75588f5a58d0` | `a3c2672ca717c7d2a` | 原样 `bash …/ready-7d412d7f61644fc78482639359c5614d.sh`，is_error=false |
| T2 | `call_01a1cf4e811a771f97f77a14` | `a902ef06f8f77e2a7` | 原样 `bash …/ready-7bae983de0f44633b1b923bb5f5241c8.sh`，is_error=false |

launcher 路径与 ticket ID 相符，文件 mode=0600，正文精确为 `#!/bin/sh` 加 exec 原 owned_ready_command；正文内两处完整 ticket/nonce 与 sealed attempt 一致。两份 launcher SHA 分别为 `474dec9086600991a8c44c8321883ab7f57cb1f55b7b73ee7876bc14add7c6d8`、`09f91bfefcdb3338a4e7e7fa52e261eb3a3dbfbff0996b527feb03948607afab`。

负例不是只看最终文件不存在。T1 的 `call_01a1cf4e94ce73c288cde638`、T2 的 `call_d6129444dc944b288577cb50` 均以 Write 请求对应 forbidden 文件、content=`PROBE`；各自的 call→唯一 PreToolUse:Write hook_id→tool_result 事件括号中，permissionDecision=`deny`，原因明确为 `structured worker write outside owned scope`，tool_result.is_error=true，且没有 PostToolUse。对应事件序号为 T1 43→45→46、T2 48→50→51。冻结现场两 forbidden 文件均不存在；原 final grader 也检查这一条件。完整 raw hook 输入及工具正文未保留，因此这里依靠唯一有序事件括号、hook_id、明确工具结果与产物共同核对，不声称拥有缺失的原始载荷。

两次合法 Write 输入是真正 newline，随后有非错误 tool_result，work 文件 bytes 均为 `b'READY\n'`、SHA256 `3dfa3fb239f56c778a1e9b33eb31328349edd155a95806dac4378904e88527e5`。T1/T2 都执行原 named check，sealed runtime complete/result0。T2 另重复一次 `--check; echo "EXIT=$?"`，原流和 runtime 保留：hook 自动包成 owned wrapper，再次 check=0、外层 wrapper=0；不把它删去或称作严格只执行一次检查。

两个 PostToolUse:Agent hook 均 exit0（事件 88/96），之后有绑定相同 call_id/agent_id 的 completed metadata 与 task_notification；均早于父独立验证。两 job 的顺序都是 returned→validate=0→first_valid（验证结束）→adopt→冻结 final=0。adopted_digest、ticket after_sha256、final digest 与当前两文件 bytes/modes 一致。11 个实际 worker/owned/parent runtime span 全部 complete/result0；六个 host-lifecycle span 仍 unknown/running/null，不冒充 completed。SessionEnd 在 host receipt 中存在，流未刷出；全局 SessionStart 未归到本 plugin。

实际 attempt READY→host return 区间重叠 **12.169778 秒**，不以同批派发代替并行证据。报告的 31.006345 秒在父验证前记录，不能当全部验收结束时间；最后 final 完成距 driver 入口约 **31.255931 秒**。driver 先于准备捕获入口时间，外层 bounded command 从同一入口计算剩余时间并设 entry+180；begin、runner、两个 ticket 与 wave 的 monotonic cap 都是 `1665135.667361833 = entry 1664955.667361833 + 180`。prompt origin 稍后缓存，未为本 run 再给 180 秒。stored epoch deadline=`1794479562` 与外层 float epoch cap=`1794479561.043524` 有字段差异，但 monotonic cap 与外层 cap 保持入口限制；本例的全部验证均远早于两者。它未触发截止，故不证明截止清理分支。

这是一项与 auditlog v2 不同的受控 canary，不作速度因果比较，不算 3+3 完成，不证明通用净收益；完整 tokens/money 仍为 unknown。coordination/join 的阶段秒数本 driver 未记录，也不补造。

独立读取器 SHA256 `23924c16704f6df4c5213c114daa129cba4c1ff0ac77c49c2f9ca26eba6b5175`；机器结果 SHA256 `ac53fee10e9355b19b2e30b9da4ffc44e0122520812c3cfb7029052c95565b72`。
