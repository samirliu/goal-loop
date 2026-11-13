# 最终冻结版回归归档

[源码归档](source.tar.xz)严格按 [137 文件清单](source-manifest.json)生成，逐项核对 SHA-256；另含该清单本身。没有打包测试生成的 `__pycache__`、用户 `.archify` 或 agent-harness 文档。归档保留完整回归时版本；后续只修正下述一处测试观测，生产源码与计时阈值未改，没有追加模型实验。

| 同一冻结版 | Python 完整回归 | 其他完整检查 |
|---|---|---|
| macOS ARM64 / Python 3.14.8 | 237 项，1 failure；hash preparation 为 4.339360s，阈值 4.2s | shell 603、parser 78、forge 10、文档一致性通过 |
| Linux ARM64 / Python 3.12.14，uid 65534 | 237 项，2 failures：后台进程退出观测；standalone gate 2.161612s 超过 2s | shell 603、parser 78、shellcheck、文档一致性通过；forge 9 通过、1 失败 |

**两平台完整回归均不能写成全绿。** 后续最小诊断确认了后台 PID 的僵尸误判，见下文；forge 失败是只读 `/src` 上无法创建 CRLF 临时夹具。完整失败记录、环境、命令与返回码分别在 [macOS](macos/results.json)、[Linux](linux/result.txt)，原日志见 [macOS Python](macos/python.txt)、[Linux Python](linux/python.txt)与 [Linux forge](linux/forge.txt)。

未改源码或阈值的 hash preparation 隔离复跑，在同一 Python 3.14 解释器及 Python 3.12 各通过一次。仅保留了工具回执，见 [tool receipt 摘要](isolated-hash-preparation-tool-receipts.json)；5.386s / 5.39s 含夹具时间，不能替代完整失败或与断言内计时混为一谈。

完整 macOS 日志中，最终 F1 scope 19 项和 F4 verifier 15 项均通过；F4 另有 [普通 / `-O` / `PYTHONOPTIMIZE=1` 的正反例](../audit-fixes/goal-verifier-optimize-after.json)。这说明相应定向入口被覆盖，不证明全仓无缺陷或取得效用优势。

[机器摘要](summary.json)、[全部测试输出归档](test-results.tar.xz)、[SHA-256 索引](manifest.json)保留精确版本边界。Linux 驱动原文在 [linux-driver.txt](linux-driver.txt)。历史 187/188 项完整结果属于更早源码；新快照不继承其通过结论。

后续在相同非 root、PID1=`runuser`、无网络的容器中，实际观察到被取消的
后台 PID 保持 `Z`：`kill(pid,0)` 仍成功，但无FD、无迟写，ledger/writer
锁均可重新获取。[原始诊断](diagnostics/owner-watch-before.json)保存进程和锁证据。
测试现以“仍执行”判断清理，保留原锁释放断言；
[测试差异](diagnostics/ledger-observation.patch)不修改生产监督器。
[修正后诊断](diagnostics/owner-watch-after.json)同时确认活进程仍被判为运行、
僵尸判为停止、回收后的进程判为停止。macOS原后台检查定向通过；只有工具回执，
不冒充Linux整项复跑。两处完整回归的计时断言及只读forge夹具仍按原结果保留，
没有通过修改阈值或重写旧输出制造全绿。
