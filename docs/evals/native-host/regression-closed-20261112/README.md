# Closed snapshot：2026-11-12 完整回归

本目录封存同一个139文件冻结版的真实终态：macOS 完整 Python256项通过；Linux 完整256项、零失败、2项真实 infinity 能力跳过。所有实际运行的检查 exit 0。它证明本版回归通过，不改写此前失败，也不证明真实 crew 净收益或9+评分。

| 检查 | macOS 26.3.1 ARM64 / Python3.14.8 | Linux ARM64 / Python3.12.14 / uid65534 |
| --- | --- | --- |
| Python | 256 tests，OK，632.458s，无skip | 256 tests，OK，886.022s，2 skips |
| Shell | 603 passed | 603 passed |
| Parser | 78 passed | 78 passed |
| Contract forge | 10 passed | 10 passed |
| Docs | Consistent，exit0 | Consistent，exit0 |
| ShellCheck | 未声称运行 | exit0，原诊断文件为空 |

Linux 两项跳过分别为无限上限下的完整生命周期和 guard FD 检查；原 reason 均为 `actual hard RLIMIT_NOFILE prevents inheriting infinity`。有限上限下的 FD2000/guard/stdout/锁测试实际执行；跳过不计成 infinity 实测通过。完整输出、命令/返回码、环境、依赖日志和 macOS 原 source-check 均在 [full-results.tar.xz](full-results.tar.xz)，没有只摘取成功尾部。秒数采用 unittest 的原报告；macOS 外层命令耗时632.733674秒另由原 `results.json` 保留。

[source139.tar.xz](source139.tar.xz)逐一包含 [source-manifest.json](source-manifest.json)的139份原字节，另加原 Linux driver、manifest 和本次 [snapshot-check.json](snapshot-check.json)。原文件 mode 保留；归档 entry 的所有者和时间戳规范化，原 mtime/mode 记录在内层清单。打包前后全部139项 hash 相符，当前 repo 中对应139项也相同；生成而未列入 manifest 的 bytecode 只在 snapshot-check 中记录排除，未删除或修改原现场。manifest SHA为 `db9793740d657e25a1c95b62ce4c38e326ef3e7b6ed6a7100ef0675546b7ebcc`。

本版包含已知 [Write/Edit FENCE 修复](../structured-write-fence/README.md)、短 READY launcher、[W7 留出拒绝分支](../w7-holdout-rejection/README.md)和两处先前夹具修正。production host SHA为 `6cd50115f5e0ac78e89b9287a2475026a6aa9a3db7a2245a4efe9e9d8c2eb060`。它和之前的 [139文件失败快照](../regression-20261112/README.md)、[137文件失败快照](../final-regression/README.md)分开；这些旧归档及其原失败日志完全不改。

[goal-v3-ready.json](goal-v3-ready.json)是此次 full 终态后主流程记录的 source/ready 对照，也原样收入日志包；它不是一次额外测试。新1800秒 v3六位置 W5 实验另有起点和材料，不能从这里预填成功、并行净收益或最终评分。已完成的 [独立双 worker canary](../claude-haha/launcher-fence-independent-review.md)支持短启动、实际 Write拒绝和采用链；其不同任务不填补 auditlog 的3+3成本窗口。

[matrix.json](matrix.json)给出指标口径；[archive-index.json](archive-index.json)和 [SHA256SUMS](SHA256SUMS)记录包摘要。两个 tar 均含 `ARCHIVE-MANIFEST.json`，逐文件 hash/bytes/mode 在压缩后重新读取核对。本次归档只读取原源码/结果并写入本新目录，未执行测试、模型或生产入口，也未更改旧 raw。
