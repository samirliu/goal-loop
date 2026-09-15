# goal-loop 接入指南（Claude Code）

一句话：把"契约 → 循环 → 外部门控"装进 Claude Code。模型永远不能自我宣布
完成——只有 shell 门控 `goal_gate.sh` 能发 GO。

## 0. 前置条件

- Claude Code（会话内模式无需任何插件；任意近期版本）。
- bash 环境：Windows 上 Claude Code 自带 git-bash，直接可用。脚本只依赖
  grep / sed / awk(gawk) / sha1sum / cksum / tr，**无 jq**；LC_ALL 与 CR
  清洗已在脚本内置。
- 可选（仅无人值守模式）：`claude` CLI 在 PATH；`HTTP(S)_PROXY` 会被
  `goal_loop.sh` 透传。

## 1. 安装（两件套，缺一不可）

1. skill 本体 → `~/.claude/skills/goal-loop/`（Windows:
   `C:\Users\<你>\.claude\skills\goal-loop\`），10 个文件：
   `SKILL.md`、`INTEGRATION.md`、`assets/goal.contract.md`、
   `references/{exit-gate,checker-panel,domain-patterns,modes}.md`、
   `scripts/{goal_gate.sh,goal_loop.sh,goal_ctl.sh}`。
2. 5 个 agent 定义 → `~/.claude/agents/`：
   `goal-worker.md`、`goal-mech-worker.md`、`goal-checker-mech.md`、
   `goal-checker-req.md`、`goal-adjudicator.md`。
   （`.skill` 包不含 agents——从本仓库取：
   `git clone https://github.com/samirliu/goal-loop && cp goal-loop/agents/*.md ~/.claude/agents/`；
   缺失时降级可跑，见下。）

- 从 `.skill` 包安装：它就是 zip，解压到 skills 目录即可。
- agent 文件缺失也能跑：控制器降级为 general-purpose + 角色文本注入
  （纪律不变：冷简报、三元裁决；失效的只是 haiku/sonnet/opus 成本分层）。
  建议装齐。
- 冒烟验证（不需要 API）：

```bash
bash ~/.claude/skills/goal-loop/scripts/goal_gate.sh --help        # 打印用法
bash ~/.claude/skills/goal-loop/scripts/goal_gate.sh --check       # 无 .goal/ 时应 rc=4, reason=no-goal-dir
bash ~/.claude/skills/goal-loop/scripts/goal_loop.sh --help        # 打印用法
```

## 2. 会话内使用（默认方式）

- 触发：`/goal-loop <目标>`；或自然语言"进入循环直到 100% 满意 / 每个角度
  都构建检查"。
- 流程：控制器把目标分解成 `AC-1..N` 契约（每条 = 可判定的 yes/no 陈述 +
  指名的可失败检测命令）→ 呈给你批准 → 盖 sha1 批准戳（此后契约冻结，R3）
  → 每迭代一个任务：worker 产工件 → 冷检查面板（2×mech + 1×req，争议时
  1×adjudicator）逐项裁决并引证输出 → FAIL 修复后只复跑失败项 → 迭代末
  输出 `---GOAL_STATUS---` 状态块。
- 退出：只有 `bash scripts/goal_gate.sh --check` 返回 0 才算完成。你随时
  可以手动跑它查岗——这是整个系统里唯一有权威的"完成"判定。
- 状态与账本都在项目根的 `.goal/`（纯文本，grep 即查询）：
  `goal.md` 契约 / `state.rec` 计数器 / `loop-log.md` 迭代账本 /
  `verdicts.rec` 裁决记录。

## 3. 无人值守模式（可选，永不该默认）

```bash
bash ~/.claude/skills/goal-loop/scripts/goal_loop.sh --init
# 手工（或让会话）填好 .goal/goal.md 的 AC 并取得批准戳后：
bash ~/.claude/skills/goal-loop/scripts/goal_loop.sh --continue \
     --max-iterations=6 --wallclock=1800
```

- 外层 shell **只信门控退出码**：0=DELIVERED，3=BLOCKED，4=状态错误，
  其余 → 下一轮。模型的状态块文本从不被信任。
- `--dry-run` 不调 API；`--resume` 强制接管陈旧锁；日志在
  `.goal/logs/loop.log`（10MB × 4 轮转）。
- 需要 `claude` 在 PATH；`CLAUDE_BIN` 可覆盖二进制路径。

## 3.5 模式与参数（v1.1）

```bash
/goal-loop [--mode=quick|standard|deep] [--max-iterations=N] [--min-acs=N] [--auto] <目标>
```

- **quick**：3 轮 / 2-4 条 AC；**standard**（默认）：6 轮 / 4-6 条 AC；
  **deep**：12 轮 / 6-10 条 AC，且每迭代有一个**强制对抗席**——它的职责就是
  合法地搞挂一项检查，逼出 fix→recheck 修复路径（全程一轮全绿不配出deep）。
- **`--auto`（无审批模式）**：契约仍在会话里完整呈现，但立即盖章开跑不等
  确认；账本与交付物记 `approval=auto` 供事后审计。R3 冻结、假完成熔断、
  证据强制照常；不可逆动作两种模式下都硬拒绝。默认仍是带审批。
- **检查预检**：契约盖章前每条 named check 先冒烟跑一次，跑不了的当场改写。
- **会话内记账**：`bash scripts/goal_ctl.sh close-iteration --project . --task
  ID --files LIST --checks-pass N --checks-fail N --checks-unverifiable N`
  一条命令完成指纹+账本+状态+门控中继（`init`/`stamp`/`bind` 子命令见
  `goal_ctl.sh --help`）。
- **证据隔离**：检查类命令的产出物（截图/转储）写 `.goal/evidence/`——天然
  被树指纹排除，复跑检查不再移动绑定。

## 4. 门控速查（退出码即真相）

| rc | 含义 | 常见 reason |
|---|---|---|
| 0 | GO，可交付 | - |
| 2 | NO-GO，继续迭代 | no-approval / contract-tampered / not-claimed / verdicts-stale / open-FAIL / not-covered / evidence-missing / unverifiable-excessive / budget-exhausted |
| 3 | BLOCKED，停下上报 | breaker-open / false-completes≥2 / stagnation / repeated-error |
| 4 | 状态错误 | no-goal-dir / missing-key / unparseable-state / unknown-flag |

- `--digest` 打印 12 位树指纹（排除 `.goal/` 与 `.git/`）；每条裁决绑定
  `(iteration, digest)`，树一变全部过期、必须重判（R7）。
- 防作弊七规 R1–R7：假完成两次即熔断；指纹未动的复跑不算工作；契约盖章后
  冻结；UNVERIFIABLE 不得超过三分之一且必须给出 PROBE/REASON；简报只带
  AC 原文与路径；worker 禁触 `.goal/`；过期裁决强制重判。

## 5. 权限与 harness 细节

- 建议在 `settings.json` 放行门控调用，避免每轮迭代手批：
  `Bash(bash scripts/goal_gate.sh --check*)` 与 `--digest` 变体。
- checker 三席是只读的（tools: `Read, Grep, Glob, Bash`）；worker 有
  Write/Edit 但被 R6 禁止触碰 `.goal/`。
- 不同机器的 harness 可能不注册自定义 agent 类型（本机实测发生过）：此时
  控制器按降级路径用 general-purpose 注入角色文本继续运行，纪律等价。
  这属正常差异，不是故障。
- Windows 打包提示：用 `py` 跑 skill-creator 脚本时带
  `PYTHONIOENCODING=UTF-8`（GBK 控制台）。

## 6. 清理与卸载

- 卸载 = 删 skill 目录 + 5 个 agent 文件。项目里的 `.goal/` 是纯文本账本，
  随手归档或删除即可。
- 分发打包：`py .../skill-creator/scripts/package_skill.py <skill目录>
  <输出目录>`。本机已给打包器打过隐藏目录排除补丁（`.goal/` 不会进包）；
  未打补丁的机器请先清理 `.goal/` 再打包。
