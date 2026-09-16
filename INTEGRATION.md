# goal-loop 接入指南（Claude Code）— v1.4.0

一句话：把"契约 → 循环 → 外部门控"装进 Claude Code。模型永远不能自我宣布
完成——只有 shell 门控 `goal_gate.sh` 能发 GO；**v1.2 起门控还会亲自重跑每条
确定性检查**（证据零模型参与），并为"尽可能完美"类目标提供 forge 穷尽退出。

## 0. 前置条件

- Claude Code（会话内模式无需任何插件；任意近期版本）。
- bash 环境：Windows 上 Claude Code 自带 git-bash，直接可用。脚本只依赖
  grep / sed / awk(gawk) / sha1sum / cksum / tr，**无 jq**；LC_ALL 与 CR
  清洗已在脚本内置。检查命令在项目根执行；有 coreutils `timeout` 则每检查
  限时 `check_timeout` 秒（默认 120s），没有则直跑（挂死风险见 SKILL.md）。
- 可选（仅无人值守模式）：`claude` CLI 在 PATH；`HTTP(S)_PROXY` 会被
  `goal_loop.sh` 透传。

## 1. 安装（两件套，缺一不可）

1. skill 本体 → `~/.claude/skills/goal-loop/`（Windows:
   `C:\Users\<你>\.claude\skills\goal-loop\`）：
   `SKILL.md`、`INTEGRATION.md`、`VERSION`、`assets/{goal.contract.md,evidence_cache.sh}`、
   `references/{exit-gate,checker-panel,domain-patterns,modes}.md`、
   `scripts/{goal_gate.sh,goal_loop.sh,goal_ctl.sh,goal_hook.sh}`、
   `tests/{run_tests.sh,docs_consistency.sh}`。
2. 5 个 agent 定义 → `~/.claude/agents/`：
   `goal-worker.md`、`goal-mech-worker.md`、`goal-checker-req.md`、
   `goal-critic.md`（v1.2 新增，forge 专用）、`goal-adjudicator.md`。
   （**v1.2 起 `goal-checker-mech.md` 已废弃**——确定性检查由门控重跑，
   装了旧文件请删除。`.skill` 包不含 agents，从仓库取：
   `git clone https://github.com/samirliu/goal-loop && cp goal-loop/agents/*.md ~/.claude/agents/`）
   缺失时降级可跑：general-purpose + 角色文本注入（纪律不变）。

- 从 `.skill` 包安装：它就是 zip，解压到 skills 目录即可。
- 冒烟验证（不需要 API）：

```bash
bash ~/.claude/skills/goal-loop/scripts/goal_gate.sh --help        # 打印用法（含 --verify）
bash ~/.claude/skills/goal-loop/scripts/goal_gate.sh --check       # 无 .goal/ 时应 rc=4, reason=no-goal-dir
bash ~/.claude/skills/goal-loop/tests/run_tests.sh                 # 场景套件，应全绿
bash ~/.claude/skills/goal-loop/tests/docs_consistency.sh          # 文档一致性，应 CONSISTENT
```

## 2. 会话内使用（默认方式）

模式预算（详见 `references/modes.md`）：quick = 3 轮 / 2-4 条 AC · standard = 6 轮 / 4-6 条 AC · deep = 12 轮 / 6-10 条 AC（deep 每迭代含强制对抗席）。

- 触发：`/goal-loop <目标>`；或自然语言"进入循环直到 100% 满意 / 优化到
  不再提升为止 / 每个角度都构建检查"。
- 流程：控制器把目标分解成 `AC-1..N` 契约（每条 = 可判定陈述 + 具名检查
  + 机器可判期望）→ 呈给你批准 → 盖 sha1 批准戳（契约冻结，R3）→ 每迭代
  一个任务：worker 产工件 → req 席判 judged 项 + 提名遗漏声明 → FAIL 修复
  → **门控 `--verify` 复跑决定** → 迭代末输出 `---GOAL_STATUS---`。
- AC 行语法（门控解析）：
  `- AC-1 | <陈述> | check: \`<命令>\` | expected: <spec>`
  spec 三种：`exit=0`（默认）/ 数值比较（`>=60`，命令最后一行输出该数）/
  `judged`（判断项，席裁决；需书面 rubric 锚定或 A/B 对判协议）。spec 值内
  不得含 `|`；文本精确比较写进命令里（`test "$(cat x)" = y`）。
- 退出：只有 `bash scripts/goal_gate.sh --check` 返回 0 才算完成。你随时
  可以手动跑它查岗——整个系统里唯一有权威的"完成"判定。
- 状态与账本在项目根 `.goal/`（纯文本，grep 即查询）。

## 3. forge 退出（"尽可能完美"类目标）

- 契约写 `exit: forge`（或调用时带 `--forge`，隐含 deep 预算）。
- GO = 全部 AC 地板 PASS **且** 连续 `dry_limit`（默认 3）轮"面板+对抗席+
  completeness critic 挖不出任何新的有证据发现、fix-now 发现项清零" **且**
  critic 冷答案为空（归档在 `.goal/evidence/critic-iter-N.md`）。
- max_iterations 退化为纯保险丝：耗尽仍未干 → rc=3 `budget-fuse`，问你要
  续期还是交付 best-so-far。
- 优化目标建议盖戳前实测基线存 `.goal/`，AC 写成对基线的 delta，交付时报
  delta。
- 诚实边界：dry_streak 是控制器记账、靠纪律审计，门控的机械獠牙是
  声称退出时的确定性重跑（查出 FAIL 记 false-complete）与 R8 证据规则。
  交付报告里要明说这一点。
- 对抗性对称（R8）：制造发现与制造通过同罪——无证据的发现项无效。

## 4. 无人值守模式（可选，永不该默认）

```bash
bash ~/.claude/skills/goal-loop/scripts/goal_loop.sh --init
# 手工（或让会话）填好 .goal/goal.md 的 AC 并取得批准戳后：
bash ~/.claude/skills/goal-loop/scripts/goal_loop.sh --continue \
     --max-iterations=6 --wallclock=1800
```

- 外层 shell **只信门控退出码**：0=DELIVERED，3=BLOCKED（含 budget-fuse），
  4=状态错误，其余 → 下一轮。模型的状态块文本从不被信任。
- `--dry-run` 不调 API；`--resume` 强制接管陈旧/存活锁（接管存活进程锁
  自担风险）；日志在 `.goal/logs/loop.log`（10MB × 4 轮转）。
- 需要 `claude` 在 PATH；`CLAUDE_BIN` 可覆盖二进制路径。

## 5. 门控速查（退出码即真相）

| rc | 含义 | 常见 reason |
|---|---|---|
| 0 | GO，可交付 | - |
| 2 | NO-GO，继续迭代 | no-approval / contract-tampered / not-claimed / verdicts-stale / open-FAIL / check-broken / check-mutated-tree / not-covered / evidence-missing / unverifiable-excessive / not-dry |
| 3 | BLOCKED，停下上报 | breaker-open / false-completes≥2 / stagnation / repeated-error / budget-fuse（forge） |
| 4 | 状态错误 | no-goal-dir / missing-key（forge 缺 dry 键）/ unparseable-state / unknown-flag |

- `--digest` 打印 12 位树指纹；`--verify [AC-ID...]` 独立重跑确定性检查
  （0 全过 / 2 有 FAIL 或 broken / 4 状态错误），judged 项自动 SKIP。
- 防作弊八规 R1–R8：假完成两次熔断；复跑非法性只约束判断席（门控重跑是
  测量不是工作）；契约盖章后冻结；judged UNVERIFIABLE 不得超过三分之一且
  必须给出 PROBE/REASON；判断席简报只带 AC 原文与路径；worker 禁触
  `.goal/`；judged 裁决绑定 (iter, digest)；发现项必须绑证据。

## 5.5 v1.2.1（安全与效率补丁）

- **批准戳现在覆盖所有 `exit:` 行**：盖戳后翻转 `exit: forge`→`threshold`
  （或偷偷加一行）= `contract-tampered` NO-GO。goal.md 里的 budget-knob
  行仍不被覆盖——那里是摆设，state.rec 才是权威。v1.1 契约没有 `exit:`
  行，旧戳照常验证通过。
- `expected: exit=N`（N>0）：负向断言（"崩溃不再复现"），门控重跑 rc==N
  即 PASS。此前这类检查会被静默路由为 judged。
- **carry-forward**：digest 未动的 judged PASS 可重绑到新迭代
  （`carried=yes`，引证原 evidence），不重开席位——forge 干轮的主要
  节省。FAIL/UNVERIFIABLE 永不 carry；digest 一动全部作废（不分片，
  防漏声明）。
- 门控重跑的输出会剥 CR（Windows 原生程序 CRLF 不再毒死 metric 读数）；
  `check_timeout` 非数字 → rc=4 状态错误。
- unattended 提示：含 judged AC 的契约每轮会全量重判面板——无人值守
  契约应尽量全确定性。

## 5.6 v1.3.0：时间预算 `--time-budget=N`

- **语义**：整个 loop 的墙钟保险丝，单位秒。盖章即起表：
  `goal_ctl.sh stamp --time-budget=1800` 把 `time_budget=1800` 和
  `deadline=<epoch>` 种进 state.rec。到期后门控 check 2c 返回
  **rc=3 `time-budget-exhausted`**——与 forge `budget-fuse` 同类的优雅熔断：
  跑完在飞任务、关账本、跑门控，然后交付 best-so-far + 未决清单；
  控制器在 deadline 已过时不再开新任务（Phase 2 步骤 1）。
- 到期前地板全过 → 照常 GO，保险丝只在"还要继续迭代"时才触发。
- **续期** = 用户明示批准后改 state.rec 的 `deadline=<新epoch>` 行
  （state.rec 是控制器记账，不涉及 R3；goal.md 不动）。
- **不迁移**：旧 `.goal/state.rec` 缺这两个键 = 熔断关闭（time_budget=0
  语义），init/`goal_loop.sh --init` 新播种的都带。
- **不要与 `goal_loop.sh --wallclock=SEC` 混淆**：那个限制的是无人值守
  模式里单次 `claude` 调用的时长，不是整个 loop。
- 示例：`/goal-loop --time-budget=3600 "审计这个仓库的依赖并升级补丁版本"`。

## 5.7 v1.4.0：Stop hook 物理拦截 + 成本三刀

- **goal_hook.sh（opt-in）**：把内置 /goal 的"物理不让停"移植过来，仲裁仍
  是确定性门控。只在唯一时刻阻停：最后一个 loop block 声称
  `exit_signal=yes` 且 `goal_gate.sh --check` 返回 rc=2（假完成高危时刻）。
  注入 reason 经 /goal 式消毒（剥 `<>&`、折叠空白、240 截断、
  `GOAL_LOOP_GATE:` 前缀）。rc=0（GO）/ rc=3（熔断类，用户决策）/
  rc=4（状态坏，fail-open——坏契约需要人修，不是继续磨）/ 未声称退出
  → 一律放行。用户 Esc 可随时越过。hook 以 cwd 下的 `.goal/` 判断是否
  激活，非 goal-loop 项目里是 no-op。安装（settings.json）：

  ```json
  {"hooks": {"Stop": [{"hooks": [{"type": "command",
      "command": "bash ~/.claude/skills/goal-loop/scripts/goal_hook.sh"}]}]}}
  ```

- **成本三刀**（目标：验证开销降到与内置 /goal 的每次停顿评估税同量级）：
  1. **inline-first**：有界、清晰的任务默认主线程直接做——worker 子代理
     复制上下文却不增加验证强度（新鲜眼睛是面板的职责，不是产者的）；
     推理密集或批量机械才 spawn。
  2. **gate-only 轮**：工件全是确定性面、无新 judged 声明的迭代（优化
     polish 轮与 [bundle] 轮的常态）**零席位**——门控即面板，门控是 bash。
  3. **critic-on-demand**：forge 的 completeness critic 只在候选干轮
     （对抗席干净）跑——对抗席出 FAIL 的轮本来就不是干轮，critic 在那里
     无可仲裁。干轮保证不变，成本只花在能改变结果的地方。
- 与内置 /goal 的完整对位（成本模型、何时各自赢、为什么不叠加）见仓库
  README "goal-loop vs the built-in /goal" 一节。



## 6. v1.1 → v1.2 迁移
- 旧契约不用改：无 `exit:` 行按 threshold；`expected:` 是散文的 AC 自动
  路由为 judged（v1.1 里散文期望本来就是模型在判），显式 `exit=0`/数字的
  才进门控重跑。
- 旧 `.goal/state.rec` 缺 dry 键：threshold 模式照跑；要跑 forge 用
  `goal_ctl.sh init` 重播种或手工补 `dry_streak=0`、`dry_limit=3`、
  `check_timeout=120` 三行。
- `close-iteration` 在 forge 契约上必须带 `--dry yes|no`；`--dry yes` 与
  `--checks-fail >0` 并存会被拒（rc=4）。
- 删除 `~/.claude/agents/goal-checker-mech.md`，新增
  `~/.claude/agents/goal-critic.md`。

## 7. 权限与 harness 细节

- 建议在 `settings.json` 放行门控调用，避免每轮迭代手批：
  `Bash(bash scripts/goal_gate.sh --check*)`、`--digest`、`--verify*`。
- 判断席/ critic 是只读的（tools: `Read, Grep, Glob, Bash`，证据写
  `.goal/evidence/`）；worker 有 Write/Edit 但被 R6 禁止触碰 `.goal/`。
- 不同机器的 harness 可能不注册自定义 agent 类型（本机实测发生过）：此时
  控制器按降级路径用 general-purpose 注入角色文本继续运行，纪律等价。
  这属正常差异，不是故障。
- Windows 打包提示：用 `py` 跑 skill-creator 脚本时带
  `PYTHONIOENCODING=UTF-8`（GBK 控制台）。

## 8. 清理与卸载

- 卸载 = 删 skill 目录 + 5 个 agent 文件。项目里的 `.goal/` 是纯文本账本，
  随手归档或删除即可。
- 分发打包：`py .../skill-creator/scripts/package_skill.py <skill目录>
  <输出目录>`。本机已给打包器打过隐藏目录排除补丁（`.goal/` 不会进包）；
  未打补丁的机器请先清理 `.goal/` 再打包。
