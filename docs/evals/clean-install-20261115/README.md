# cc-haha 干净安装与能力保留检查

结论：4.1.2 的完整插件已通过本机 cc-haha 的真实安装 CLI、Bun 加载器及安装包执行检查。两个 skill、五个角色的原正文/模型/工具清单、八类 hook 配置与全部运行资源保留。独立 skill 的资源同样完整，但不自动安装 hooks；本机 cc-haha 的默认全局角色发现还存在需要启动选项规避的问题。

环境是 macOS / Bash 3.2.57 / Python 3.14.8、cc-haha `999.0.0-local (Claude Code)`；对照使用官方 Claude Code 2.1.83。Linux 安装回归使用 Python 3.12.14、非 root、网络关闭、源码只读挂载。所有安装配置和项目均在临时目录，未替换用户真实 skill、agent 或 settings，也没有推理调用。

## 已复现的问题和修复

| 问题 | 观察 | 4.1.2 的处理 |
| --- | --- | --- |
| 根目录直接声明为插件 skill | 用旧提交的根 SKILL/manifest 构造版本目录发现 fixture，实际名称变成 `goal-loop-host:4.1.1`，companion 也未暴露 | 固定 `skills/goal-loop` 发现入口，完整正文由根 SKILL 生成，实施根由插件变量绑定；缓存目录名不再参与名称 |
| 旧手动复制说明遗漏资源 | `agents/`、`docs/` 未随 skill 根复制，协议及离线示例存在这些依赖 | 显式 1,189 文件清单、自包含构建、五个全局角色注册、可选 companion；不依赖安装后的 Git 或原 checkout |
| gawk 在 PATH 外时函数失效 | 自动发现结束后迭代变量被 unset，函数仍引用该变量 | 为已解析的可执行文件保留稳定变量；强制 fallback 的真实 gawk 测试覆盖 |
| 本机 cc-haha 静默漏载独立 skill 的全局角色 | 默认 `agents` 仅显示内置角色，退出码仍是 0；同一安装在官方 CLI 正常 | 安装说明要求核对角色；`CLAUDE_CODE_USE_NATIVE_FILE_SEARCH=1` 后五角色恢复。完整插件无需该选项；没有修改外部 harness |
| 路径带空格时文档命令截断 | 独立试读执行旧示例得到 rc=2，正确引用后 rc=0 | 根 SKILL 与 host 参考中的路径加引号；生成入口同步 |
| 安装包正文把源码测试作为自检入口 | 根目录两个开发测试脚本不在分发包 | 改为随包 doctor/quickstart，明确源码开发回归与实际目标验收的区别 |

本机 cc-haha 的 cache-only 启动读取会直接使用本地 marketplace 目录，即使版本缓存存在也不能删除源目录。README 因此要求保留固定安装目录。版本缓存本身另经 `--plugin-dir` 实际加载，原源目录搬走后仍保持两个稳定的 skill 名称；这项检查不声称宿主自动改用缓存。

## 证据与检查范围

[report.json](report.json) 是机器摘要；[receipts.tar.gz](receipts.tar.gz) 保存 31 次最终原生命令的 argv/退出码、完整加载提示和角色内容、CLI 输出、声明 hook 的 JSON 回放、测试日志及独立试读原始诊断。[source-sha256.json](source-sha256.json) 绑定本次分发文件与验证工具。旧发现 fixture 只复现名称问题，没有运行其 hook。

[harness-sha256.json](harness-sha256.json) 记录被测宿主加载代码。原生运行后 README 只调整了推荐安装步骤，使持久安装优先注册干净构建目录；最新安装复制回归已重跑。原生包的文件哈希和当时 README 也在归档内，全部运行资源与最终工作树一致。

- cc-haha：marketplace add → plugin install → plugin list，实际启用 4.1.2；官方 CLI 也接受插件和 marketplace 清单。两者只有缺少作者/marketplace 简介的元数据提醒。
- 三种实际插件读取：持久注册、本机生成的 `cache/goal-loop/goal-loop-host/4.1.2`、含空格且原路径已移除的搬移目录。每次均取得两个命名空间 skill、五角色、八类 hooks；全部主协议正文和角色模型/工具/正文保持。
- 独立 skill：实际加载两个 skill；用上述宿主选项和实际 CLI 确认五角色。预存 settings 字节不变；同名 skill/角色拒绝覆盖；缺失资源拒绝产生成功的残缺包。
- 从安装的 skill 和搬移插件分别执行 quickstart，均取得当前实际 GO；两份 companion fixtures 均通过。八类已加载 hook 命令使用明确标注的合成 payload 回放，命名空间目标确实被捕获并可进入 context。
- macOS 安装测试 10/10、Linux 10/10、shell 回归 603/603、解析器 81/81、host 20/20、文档一致性 153 项通过。两个 skill frontmatter 校验通过。ShellCheck warning/error 级通过；全量 lint 仍有原有单引号正则和 `A && B || C` 的 info 提示，原始输出保留。
- 独立试读没有得到预设诊断：从宿主渲染后的插件正文实际寻找资源并制定视觉任务实施前计划，查出上述两处文档问题。归档保留修复前观察，没有将旧包诊断改写为新包已通过。

这证明安装、发现、路径、运行资源和本地协议执行可用。没有验证模型服务端执行、真实运行会话中的 hook 自动投递、视觉冷席模型能力或新的 THREE.JS 产物质量。浏览器、Three.js 和项目依赖仍由实际任务提供。纯 skill 的显式 bridge 不等于完整插件的自动事件覆盖。完整分发约 200 MiB，保留离线文档与历史证据；原生 Windows 不在本次保证内。

## 复跑

```bash
python3 -B -m unittest discover -s tests -p test_installation.py -v
python3 devtools/check_claude_install.py \
  --harness-root /ABS/claude-code-haha \
  --output /TMP/new-install-check
```

第二条需要本地 cc-haha 源码及 Bun；输出目录必须不存在且在 checkout 外。它只使用隔离 `CLAUDE_CONFIG_DIR`，调用管理 CLI、实际加载器和安装包脚本，不启动模型推理会话。默认角色漏载会明确记入报告，不会用成功退出码掩盖。
