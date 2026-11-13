# F5：无限 FD 上限导致 guard 溢出

macOS、uid 501 的真实子进程继承 `RLIMIT_NOFILE=9223372036854775807`。
旧 `_group_guard` 把该值传给 `os.closerange`，出现 C int 溢出；guard 退出后，
Darwin 对只剩僵尸的组返回 `killpg EPERM`。正文指定退出码7，wrapper却返回4。
见[原始反例](before-normal.json)及[旧版定向输出](before-tests.log)，不是只依据模型诊断。

修复在 fork guard **之前**枚举 `/proc/self/fd` 或 `/dev/fd` 的实际 FD；
guard 仅关闭该快照，容忍枚举自身已关闭的 FD。两种目录均不可读时，
leader 拒绝执行用户命令，不增加 handshake、框架或旗标。

| 真实进程验证 | 修复后结果 |
|---|---|
| 有限 / 无限上限，正文指定7 | wrapper均返回7，无 command-start 错误 |
| 超时 / ticket取消 | 返回124 / 130，无迟写 |
| guard存活时关闭stdout及FD2000锁 | stdout到EOF，独立锁句柄可取得 |
| 两个FD目录都不可用（明确故障注入） | 非零退出，用户命令标记未创建 |

[最终定向输出](after-tests.log)：12 passed、2 skipped、6 subtests passed，4.30s。
两项skip是本机Python3.12缺少waitid的既有测试，真实Infinity分支均执行。
本任务没有运行Linux；实际hard limit有限时，新测试会如实跳过Infinity分支。

Root同时修复了另一个bounded trace收尾问题。因此另做了[固定源码因果配对](paired-manifest.json)：
两组使用字节相同的旧bounded/trace，仅更换ownerwatch，结果仍为
[旧版4](paired-before.json) → [新版7](paired-after.json)，新版stderr为空。
该[配对源码归档](causal-pair-source.tar.xz)和前后源码SHA均保留，原before未覆盖。

具体状态、锁、迟写与源码版本见[摘要](summary.json)、[补丁](owner-watch-guard.patch)及
[文件哈希](manifest.json)。未调用模型、新cohort、完整套件、Docker或申请新权限；
真实Claude hooks现场由主流程另行保留，不把其trace修复或耗时变化归到本项配对。
