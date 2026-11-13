# Forge 只读夹具目录修复

只修改 `companions/contract-forge/tests/run_fixtures.sh` 的 CRLF 临时文件处理：
使用 `mktemp`，EXIT 精确删除该文件，HUP/INT/TERM 退出后执行同一清理；
生成失败返回非零。输入 fixtures、lint 脚本及预期结果均未改。

macOS ARM64、非 root（uid 501）实际运行目录副本，全部目录 `0555`、文件 `0444`：

| 版本 | 实际结果 | 原始输出 |
|---|---|---|
| 修复前 | rc=1；9 通过、1 失败；无法在 fixtures 写入 CRLF 文件 | [before.log](forge-readonly-before.log) |
| 修复后 | rc=0；10 通过、0 失败 | [after.log](forge-readonly-after.log) |

前后目录清单相同、无新增源码文件。TMPDIR 故意含空格、单引号及 `$()`；
运行后清单仍只有调用者原有的 `keep.txt`，证明没有残留或误删。
完整命令、源码 SHA、目录清单与检查结果见 [摘要](forge-readonly-summary.json)、
[before](forge-readonly-before.json)、[after](forge-readonly-after.json)及 [哈希索引](forge-readonly-manifest.json)。
`bash -n` 和 `git diff --check` 通过。[补丁](forge-readonly.patch)保留精确修改。

这是旧冻结版完整回归之后的定向修复；旧归档和失败日志未改，未跑完整套件、模型或 Docker。
