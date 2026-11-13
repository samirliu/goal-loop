# 宿主预算与生命周期接入

`goal_host.py` 复用 runner 的同一个截止、crew 的生命周期和 runtime spans。
它不创建 agent、后台队列或新的完成判定。当前 Work 的 collaboration
没有可安装的全局 callback，使用下面的显式 bridge；Claude Code / Codex
原生 hooks 则在安装并信任配置后消费 stdin JSON。

## 最早入口

正常入口先用 `python3 -I ${GOAL_SKILL}/scripts/goal_host.py enter PROJECT SECONDS`。
它只从本项目唯一真实 prompt 回执（或唯一活跃会话）取 backend/session，调用原 begin；
有歧义时拒绝并要求传真实身份，绝不猜 session。无 hook 的显式 bridge 仍用下面的 begin。
随后 `bash ${GOAL_SKILL}/scripts/goal_ctl.sh context --project PROJECT` 输出简短状态和准确命令。
只有会话已授权自动批准时才加 `--auto`；默认不添加自动批准标记。授权选项也是版本绑定的一部分。
首次 hook 只建立账本、尚无 goal.md 时，context 返回最小契约模板和写入路径；不替用户写入或批准，也不要求重新 init 或阅读实现源码。填好并冒烟后重新取 context，才提供带当前版本的 stamp 命令。
每条 action 带账本/产物/工作计划/接口/策略版本；run 消费时在目录锁内重算，过期拒绝后重新派生。
它只是派生地图，不是新账本或完成权威。完整 status 和原始错误仍可读取。

地图覆盖未初始化、契约/冒烟、实施/派工、未收账、恢复及终验。每个 action 给出参数、证据来源、准确 `command` 和底层 `executes`；必要输入未知时 `command` 为 null。把 `close_input.template` 写到返回的 `.goal/proposals/close-iteration.json`，依据实际 verify 输出和复审补齐 null，然后重新取地图。work-plan 只提供任务/文件域，不能提供检查计数或批准。图任务另用 `execution_input` 补实际 mode 和原生 launch/terminal 回执路径；plan/begin/prepare/attach/reconcile/validate/adopt/finish 仍调用原入口，不启动宿主客户端。

输入文件只是调用参数，不是新账本。动作绑定它们的字节、相关回执、产物、策略及工具版本；消费前在原锁下重核，过期或变化后拒绝。context 直接持有读锁，所以 pending 期间也能只读展示 recover。新的原事务 journal 与提交回执保留精确 argv；恢复后 `retry-close` 沿用原请求，只返回历史结果。地图读取有界；到期只提供结算路径，调用各原入口既有的有限验收窗口，不额外改写整次收账预算，更短继承截止仍优先。

`python3 -I ${GOAL_SKILL}/scripts/goal_context.py receipt PROJECT` 在同一截止执行原 audit/Gate，
返回原输出、策略消费版本、单元复用来源与未解决项。只有两者实际通过才有 completion_verified=true。
到期后只使用原有限结算，不能借状态查看开新预算。

显式 `/goal-loop …目标` 或插件 `/goal-loop-host:goal-loop …目标` 的 UserPromptSubmit hook 记录 prompt 起点；普通
对话、无参 status/continue 不创建目标。之后在开始执行时调用：

下文 `${GOAL_SKILL}` 代表已安装 skill 的绝对目录；PROJECT 使用实际项目路径。

```sh
python3 -I ${GOAL_SKILL}/scripts/goal_host.py begin PROJECT BACKEND SESSION SECONDS
```

没有 prompt hook 的宿主记录 `host-tool-entry`，不能回填更早的思考时间。
重复 begin、resume、较大的新预算都不能延长原截止。它可以先于契约初始化；
后续 stamp 只能进一步收紧预算。会话标识来自真实宿主；不要伪造厂商来源。

## 真实 worker

先冻结 crew graph 的接口、文件域、依赖、命名检查及输入，再 `goal_crew.py begin`。
派发前 `goal_host.py prepare PROJECT WAVE TASK`，将返回的 `worker_prefix`
原样放入 worker 简报。它含随机 nonce、所属文件域、同一截止以及首个工具命令。

- 真正调用宿主 spawn。把实际 JSON 回执存为文件，调用 `attach PROJECT TICKET RECEIPT`；
  启动确认只建立身份关系，不表示工作完成。
- worker 首个工具运行 `worker_prefix` 的 `First tool command`。Claude 新 ticket
  使用 `launcher_command`：prepare 原子写入含完整 owned READY 参数的脚本，
  hook 在绑定 agent 前验证其 SHA；模型只复制短脚本入口。缺失、篡改和
  符号链接替换均拒绝，不重新生成或延长预算。原 `owned_ready_command`
  及 Work/Codex 简报保持兼容。新 ticket 固定 prepare 时的解释器路径。
  它是 first-tool-ready，
  不是首 token，也不是 first-valid。禁止 worker 直接编辑 `.goal/`；仅由
  这个固定适配命令记录观测。后续 shell 沿用 `tool_prefix`，整个所属进程组
  同时受 ticket 的取消文件和当前 runner 的最早截止约束。
- worker 的聚焦自检优先使用返回的 `check_command`：它直接运行冻结图中的
  命名检查，在项目 cwd 执行，记录 measurement，不授予 first-valid 或采用。
  这样不必为自检生成内联 shell 或 heredoc。父控制器仍在宿主终态后重跑
  validate/adopt 和最终集成验收。
- 用真实 list/turn/item 回执 `reconcile PROJECT RECEIPT`。支持 Work 的结构化
  `agent_name/agent_status` 与 app-server 的 `agentsStates/turn.status`。
  报告正文不参与判定；失败和取消也形成保留的尝试。
- 完成后 `validate PROJECT TICKET`，通过再 `adopt PROJECT TICKET`。
  独立检查及文件摘要决定 first-valid/采用；Start/Stop 事件不能代替成功结果。
- 协调、join、恢复仍用 crew 的 `stage`。`finish` 重跑集成检查；最后照常
  `close-iteration` / audit / gate。telemetry 不授予 GO。

原生 worker 的首次工具 hook 可凭**完整匹配的 ready ticket 命令**补关联
agent_id，避免把并发 Start 按到达顺序猜给任务。没有可靠关系的事件保留
unknown。上下文、原始推理和 prompt 不写入 runtime 元数据；只记内容摘要。
缺失 tokens/费用保持 null。

已注册 Claude worker 的 `Write/Edit` 按实际解析后的 `file_path` 核对冻结
文件域，拒绝 `.goal`、其他任务路径和 symlink 逃逸；合法请求保留宿主正常
权限，拒绝后仍可修正重试。该检查覆盖这两个结构化工具；任意 shell 写入
不属于此路径检查，也不能把它当作 OS 文件隔离。

## 取消

`cancel PROJECT TICKET` 先落该尝试的取消标记，然后由控制器调用真实宿主的
interrupt。必须再读取 interrupted/cancelled 终态；取消请求的确认不能
充当 worker 已停止。工具 wrapper 在宿主进程仍存活时也清理所属子孙组。
它不终止共享 daemon、不按进程名杀人；主动脱离所属进程组或监督器自身
被 SIGKILL 不在当前保证内。

宿主没有自动取消 API 回调时，控制器必须继续观测截止并调用 interrupt；
本地 wrapper 只能停止工具计算，不能证明模型服务端也已停止推理。

配置了路由策略的波次在 prepare、原生派工 hook、READY 和 owned command 再核对当前指针。
撤回或切换待恢复时拒绝继续旧派工；取消/终态回收仍可进行。已经执行过的服务端推理不追认撤销。

真实 Work 试跑发现权限等待可能耗尽整场预算。已知需要提权的环境，应
在派发前完成 ticket 精确前缀的实际权限预检；不要把等待审批当作 READY。
新增的复杂 shell/重定向仍可能触发新的审核，已批准前缀不会解除已经挂起
的请求。只需命名自检时用 check_command，并分别确认其精确调用权限。
未获得真实授权时保留 pending/unknown，不通过更宽的许可或伪造启动时间绕过。

## 原生配置

Claude Code 可按次加载 adapter，不修改全局配置：

```sh
claude --plugin-dir /ABS/goal-loop
claude plugin validate /ABS/goal-loop
```

插件同时加载仓库根目录的 skill、hooks 和带命名空间的 agents。
按次加载后使用 `/goal-loop-host:goal-loop …目标`，可明确选择当前仓库版本，
避免同名旧全局 skill 的装载顺序影响。普通 `/goal-loop` 仍使用 README 的安装入口。
保留旧的全局 agent 安装时，不要把同一波当成两套 worker。此适配器和旧
`goal_hook.sh` 的完成阻挡作用不同；最终 GO 仍由原 gate 决定。

Codex 配置生成器只向 stdout 输出，不覆盖现有 hook：

```sh
python3 -I ${GOAL_SKILL}/scripts/goal_host_config.py codex > /tmp/goal-loop-hooks.json
```

将其合并进项目 `.codex/hooks.json`，按正常 `/hooks` 流程 review/trust。
更新后重新 review；不能以 trust bypass 代替安装验证。项目配置不等于
已拦截当前 Work 的 collaboration。两个宿主支持的事件不同，勿混用文件。

Claude 的 shell 重写只返回 updatedInput，保留原权限流程。Codex 的重写
要求显式 allow；本适配器改为拒绝未包装的 worker shell 并返回可重试的
规范 wrapper 命令，让宿主照常检查权限。worker 从简报起使用 prefix 可
避免这次重试。其余未受 hook 覆盖的工具必须明确列为未知覆盖。

接口依据：[Claude hooks](https://code.claude.com/docs/en/hooks)、
[Codex hooks](https://learn.chatgpt.com/docs/hooks)、
[Codex app-server](https://learn.chatgpt.com/docs/app-server)。原生 hook 失败
可能放行工具；它不是针对恶意同用户代码的 OS 权限隔离。
