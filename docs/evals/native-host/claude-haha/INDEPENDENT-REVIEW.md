# 真实 claude-haha 接入：独立核对

2026-11-12。只读核对 `0knur70e`（F5 前）和 `0ch9wkfr`（F5 后）两份现场；没有调用模型、执行生产入口或检查器、重跑全套或改动原始记录。[标准库检查器](independent-check.py)使用显式 `require`，普通 Python 与 `-O` 输出相同。[机器结果](independent-check.json)包含原目录清单摘要、身份、逐项时间及保留的失败。

**当前 plugin hooks 与注册 worker 的真实运行有交叉证据；当前 root SKILL 的实际选中版本尚未证明，而且客户端存在同名旧全局 skill 优先的风险。不能将这次运行写成“当前版本 skill 已完整安装验收”。**

| 核对项 | 独立结果 |
|---|---|
| CLI / plugin / 模型 | 原命令为 `claude-haha --plugin-dir /Users/m/repo/goal-loop`；两次 init 均列出 `goal-loop-host@inline`、当前仓库角色，实际 runtime 为 `999.0.0-local`、模型为 `MiniMax-M3.1-Flash`。不代表标准 Claude CLI / Claude 模型。 |
| prompt 起点 | 第一轮 `UserPromptSubmit` 时间窗口内的缓存 origin 与 `runner.origin` 相同；第二个 prompt 未刷新起点。after 的 begin、brief、wave 保持同一或更早截止，未超过最初 180 秒 cap。 |
| worker 身份 | Task 在流中实际名为 `Agent`；prompt 首行精确匹配 nonce/header。`call_id`、原生 `task_started` 的 `tool_use_id/task_id`、`SubagentStart` 收据及最终 attempt 一致；首个 Bash 为注册的 owned READY。 |
| 完成与采用顺序 | after：READY 11.683s → PostToolUse 27.864s / 结构化 native completion 27.864s → 父验证开始 30.364s → first_valid 30.438s → adopt 30.439s → 最终复验 30.513s，均从 CLI 起点计。`report.elapsed=30.363s` 是 CLI 结束口径，不包含后续约 0.15s 父级验证。 |
| 产物与冻结仪器 | 直接读取 `out.txt`，恰为 6 字节 `READY\n`。原 control grader SHA-256 为 `ad524844…ca0b8d`，与冻结 wave 一致；原 check_freeze、验证命令摘要、运行仪器摘要、采用产物摘要均吻合。未运行 grader 来生成新结果。 |
| F5 前失败保留 | CLI 最终返回且父级产物验收通过，但 25 个 owned command / named-check span 留在 running、result=null，另有 PostToolUseFailure。不能把最终产物通过解释为监督器全部成功，也不能把未知收尾硬算作 25 次用户命令失败。F5 的独立因果配对另见 [guard 证据](f5-owner-guard/README.md)。 |
| F5 后收尾 | 3 个 owned command、1 个 named check 均 complete/result=0；两个父级验证也有独立 runtime 和冻结摘要。另保留一次 `Read` 不可用的工具拒绝，随后 owned Bash 读字节成功；“干净”仅指这四个已执行命令及监督器收尾。 |
| 未知生命周期 | 两次各有 4 个 `host-lifecycle` span，result/finished/elapsed 仍为 null，未冒称完成。SessionEnd 未出现在捕获的流中，但 host event 和对应 runtime 已落盘。流中的 SessionStart 不是本 plugin 注册的 hook，不计入本 plugin 覆盖。 |

完整结构化 `tool_response` 正文未保留：驱动只保留部分工具回执的内容摘要。核对依据是原生 call/agent/completed 事件、PostToolUse hook 成功、校验过的 host 收据、验证前快照及后续独立采用时间，不能据此声称完整响应正文已逐字复核。模型 COMPLETE 正文不参与产物成功判定。

## SKILL 选择风险与最小消歧方案

项目链接确实为 `work/.claude/skills/goal-loop/SKILL.md → /Users/m/repo/goal-loop/SKILL.md`；全局 `~/.claude/skills/goal-loop/SKILL.md` 是未修改的旧普通文件。init 同名两项只能证明注册，不能证明当前项目正文优先。[源码摘录与 SHA](independent-loader-evidence.json)记录了当前本地客户端的以下路径：

- `src/skills/loadSkillsDir.ts:717–721`：managed → user → project；`:729–769` 只按 realpath 去重，不按同名覆盖。
- `src/commands.ts:460–469` 保留该顺序；`src/cli/print.ts:2147–2151` 在 ask 前按 name 做 first-wins 去重；`src/commands.ts:689–698` 和 `src/utils/processUserInput/processSlashCommand.tsx:525–526` 选第一个匹配。

因此，在默认 userSettings 启用且该旧副本被加载时，普通 `/goal-loop` 先选旧全局项。现存 raw 未记录最终 selected skill 的路径/正文，未将上述源码推断冒充运行时正文读取证明。

建议最小改动为在 plugin manifest 声明 `"skills": "./"`；在当前仓库目录名为 `goal-loop` 的布局下，使用 `/goal-loop-host:goal-loop`：`src/utils/plugins/schemas.ts:486–496` 接受额外 skill 目录；`src/utils/plugins/loadPluginCommands.ts:699–705` 检查目录本身的 `SKILL.md`，`:714–726` 加载并生成 `${pluginName}:${basename(skillsPath)}`。本审查未修改 plugin、全局安装或任何生产源码；这项后续修复的安装验证应另留现场。

本材料只支持两个真实接入现场的上述结论，不是 W5 净收益对照、全 Agent 成本优势、全仓回归通过或综合评分。36 次 P2 对照继续停止；后续全回归与新 backend 配对由主流程另行记录，不在这里提前判定。
