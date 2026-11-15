# goal-loop

**v4.2.0** — 用冻结的验收契约、可恢复账本和确定性门控推进长任务。宿主负责模型与原生 worker，goal-loop 负责目标、证据、预算与完成判定。

默认先串行完成业务；只有测量支持净收益时才使用 crew。视觉逼真度、内容正确性和外部结果需要相应判读或结算，不能用文件存在、像素统计或生产者自评替代。

执行中可使用[受约束的递归策略改进](references/packs/improvement.md)：真实失败/瓶颈 → 提出候选 → 与当前父代独立比较 → 真实任务消费 → 反馈、下一代或撤回。每个目标固定尝试次数、时间储备、验收及评估内核，保留原有留出曝光和统计预算。已验证方法可接入工具、原生 planner 或提案生成器；合格生成器可读取自身归档及反馈，提出自己的下一版本，再由宿主审查和独立评估。当前实现不修改模型权重，也不自动重写已安装插件。

## Install / 安装

推荐完整插件，适用于 Claude Code 和提供相同插件接口的 cc-haha。下文用 `claude-haha`；如果你的别名叫 `cc-haha`，替换命令名即可。官方 Claude Code 使用 `claude`。

在源码仓库检查依赖并生成一个新的固定安装目录：

```bash
python3 scripts/goal_install.py doctor
python3 scripts/goal_install.py plugin --output /ABS/goal-loop-package
claude-haha plugin validate /ABS/goal-loop-package/.claude-plugin/plugin.json
claude-haha plugin validate /ABS/goal-loop-package/.claude-plugin/marketplace.json
```

当前会话使用：

```bash
claude-haha --plugin-dir /ABS/goal-loop-package
# 会话中调用 /goal-loop-host:goal-loop <目标>
```

持久安装：

```bash
claude-haha plugin marketplace add /ABS/goal-loop-package
claude-haha plugin install goal-loop-host@goal-loop
```

本机 cc-haha 启动时会直接读取本地 marketplace，安装包目录需要保留。开发时可用 `--plugin-dir /ABS/goal-loop` 加载工作树；持久安装使用构建目录，避免把未跟踪的本地文件一起缓存。构建目录必须不存在，更新时生成新目录并重新注册/加载，不能覆盖正在使用的包。

插件固定提供 `/goal-loop-host:goal-loop`、`/goal-loop-host:contract-forge`、5 个带 `goal-loop-host:` 前缀的角色及 8 类 hooks。实施资源由 `${CLAUDE_PLUGIN_ROOT}` 绑定，版本缓存目录名不会改变调用名。根 SKILL.md 是正文来源，`skills/goal-loop/SKILL.md` 是生成入口；修改根正文后执行 `python3 scripts/goal_install.py sync-entry`。版本更新后开启新会话。

只安装独立 skill：

```bash
python3 scripts/goal_install.py skill --config-dir ~/.claude --with-companion
# 会话中调用 /goal-loop <目标>，或 Skill 工具的 goal-loop
```

这会复制全部运行资源，并注册 5 个全局角色。companion 可选；不会改写 settings.json 或覆盖同名 skill/角色，`skills/`、`agents/` 必须是配置目录内的真实目录。已有安装请使用新的配置目录验证，或先备份并移走旧安装。

| 安装模式 | skill / 角色 | 宿主事件 |
| --- | --- | --- |
| 完整插件（推荐） | 2 个命名空间 skill、5 个角色 | 自动加载 8 类 hooks |
| 独立 skill | goal-loop、5 个全局角色；companion 可选 | 显式 host bridge，不自动安装 hooks |

本机 cc-haha 源码版 `999.0.0-local` 的默认文件搜索会静默漏载全局 agent；独立 skill 安装后使用下面的选项核对并启动。完整插件和已验证的官方 Claude Code 2.1.83 无需该选项。

```bash
CLAUDE_CODE_USE_NATIVE_FILE_SEARCH=1 claude-haha agents
CLAUDE_CODE_USE_NATIVE_FILE_SEARCH=1 claude-haha
```

依赖：POSIX Python 3.10+、Bash 3.2+、GNU awk 和常见 UNIX 工具；SHA-256 需 `sha256sum`、`shasum` 或 `openssl` 之一。macOS 系统 Bash 可用，需另备 gawk（例如 `brew install gawk`）；Linux 可安装 `gawk`。无 jq、无 GNU timeout 硬依赖。Doctor 只检查依赖，不自动安装软件。

包由 [安装清单](assets/install-files.json) 构建，不携带 `.git`、未跟踪文件、本地配置或 `devtools/`；随包保留离线参考和历史证据，完整包约 200 MiB。分发包含 [MIT 许可证](LICENSE)。原生 Windows Python 的锁/进程组能力未覆盖。

## 使用与完成判定

在会话中给出目标与预算。先保留原始请求，逐项写能失败的 AC；批准后冻结契约。已有自动批准授权才使用 `--auto`。预算从最早可观察入口计算，stamp、resume 和重试不会续期。

```text
原始请求 → 契约与批准 → 实现 / 必要的 crew → 实际检查与冷席复审
        → 收账 → audit + Gate → GO 交付 / NO-GO 继续 / BLOCKED 停车
```

正常执行优先使用 SKILL 的四步和 `goal_ctl.sh context` 返回的当前命令。`submissions.stamp` 合并冒烟与盖戳；`submissions.close` 消费实际判断并调用原收账。普通确定性任务不用手抄检查计数；特殊契约仍须提供真实观测。旧 revision 拒绝执行，REPLAY 只确认历史提交，不能代表当前产物仍然通过。

独立入口使用安装根的绝对路径，包含空格时引用完整路径：

```bash
python3 -I "/ABS/goal-loop-package/scripts/goal_host.py" enter /ABS/project 600 --context
```

`enter` 只使用唯一真实宿主回执；无 hook 时通过显式 bridge 传实际 backend/session 和原始请求，不猜身份。具体见 [宿主适配](references/host.md)。

| 返回码 | 结果 | 后续动作 |
| --- | --- | --- |
| 0 | GO | 当前终验通过后交付 |
| 2 | NO-GO | 修复缺陷后继续 |
| 3 | BLOCKED | 按预算/熔断/阻塞原因停车并报告 |
| 4 | 状态或调用错误 | 按错误修复、恢复或重取地图 |

判断类证据绑定当前迭代、内容指纹和实际 artifact；地板检查由 Gate 重新执行。视觉任务还须校准冷席、读取实际参考及承诺机位的截图，未解决缺陷不能用 `clear` 放行。优化任务的 `exit: forge` 要求质量地板、实际探测覆盖和连续 dry 资格；外部审批/部署等事实须实际结算。

| 需要的能力 | 维护中的说明 |
| --- | --- |
| 检查顺序、错误与不变量 | [Gate](references/gate.md) |
| 内容判读、校准与仪器 | [Instrument](references/packs/instrument.md) |
| 视觉逼真度、参考和冷席证据 | [Visual](references/packs/visual.md) |
| 优化、forge、策略晋升与撤回 | [Gradient](references/packs/gradient.md) |
| 外部事实与延迟结算 | [External](references/packs/external.md) |
| crew 文件域、检查及真实生命周期 | [Crew](references/crew.md) / [Host](references/host.md) |
| 锁、幂等、中断与恢复 | [事务状态](docs/transaction-state.md) |

出现 `recovery-required` 时，先执行返回的恢复命令：

```bash
bash scripts/goal_ctl.sh recover --project /ABS/project
```

恢复不重放外部工具、不重置预算。旧账本若明确要求迁移，再用 `goal_ctl.sh migrate`；不能借迁移接受与历史冲突的手改内容。

## 验证与开发

安装冒烟无需模型 API，也不能替代实际目标验收：

```bash
python3 /ABS/goal-loop-package/scripts/goal_install.py doctor
bash /ABS/goal-loop-package/examples/quickstart-one-shot/run.sh
```

源码仓库的检查与 CI 一致：

```bash
bash tests/run_tests.sh
bash tests/test_parse.sh
bash tests/docs_consistency.sh
bash companions/contract-forge/tests/run_fixtures.sh
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
```

用本地 cc-haha 源码复跑安装/加载检查，输出到不存在的仓库外目录：

```bash
python3 devtools/check_claude_install.py --harness-root /ABS/claude-code-haha --output /TMP/fresh-install-check
```

该检查使用隔离配置、管理 CLI、实际加载器、安装示例与合成 hook 回放，不调用模型 API。回放不能证明真实推理会话中的自动事件投递。

正常 skill/plugin 不启动另一个宿主。需要显式外部开发评测时使用源码中的 `devtools/goal_loop.sh`；旧 `scripts/goal_loop.sh` 仅返回迁移提示和 rc=4。`--dry-run` 可无 API 演练，实际模型调用需要相应任务授权。

当前说明、可运行示例与历史评估入口见 [文档索引](docs/README.md)；历史计划和冻结实验不代表当前工作树已验证。

## 已知边界

门控能验证声明和证据是否一致，需求覆盖仍依赖可靠复审；共享用户权限也不构成 OS 沙箱。预算和取消只覆盖已观察的本机入口与所属进程组，不证明服务端计算已取消。未采集的 tokens/费用保持 unknown。

已有局部工具策略的成本收益证据，不支持相对原生 `/goal` 的通用优势、默认 crew 更快或跨任务自动进化。比较需固定模型、输入、验收和总预算，并保留失败、取消及完整成本；历史数据与适用范围见 [评估索引](docs/evals/README.md)。
