# goal-loop

**v4.1.2** — 用冻结的验收契约、共享工作区 subagent 波次和确定性门控推进交付；用测量反馈选择下一轮策略。

当前实现把内容绑定、可恢复收账和局部策略学习接成可执行路径：旧的 `EFFICIENCY` / `STRATEGY-PICK` 保持轻量归因；需要晋升工具策略时，另用固定协议、配对成本测量和新留出实例决定启用、保留或撤回。此前冻结版本的本地测试工作流留出耗时下降约 31%，两个后续实例实际消费合格策略后合计下降约 30%；完整 agent 效用、模型费用与通用迁移仍未证明。原始归档、学习成本和适用范围见[资格与路由评估](docs/evals/qualified-routing-20261114/README.md)。

圣索菲亚真实案例暴露了更重要的验收覆盖缺口：尺寸和像素统计全绿，仍可能交付缺失体量的建筑。现在从原始请求路由视觉质量验收，冻结质量判读、机位与校准锚点，绑定冷席的实际截图复审，未解决缺陷或失败机位不能被 `clear` 放行。这个修复能阻止已复现的假完成，视觉质量本身仍依赖实际参考和可靠判读；见[案例与回归记录](docs/evals/visual-acceptance-20261114/README.md)。

扩展审计还修复了非视觉目标与校准未绑定内容、人工判读漏查外部要求、旧版批准缓存复用、数值截断和带引号脚本漏冻等问题。15 个实际误放行反例现在拒绝，正常校准及等待后结算仍能通过；需求覆盖仍需可靠复审，见[扩展审计与完整验证](docs/evals/acceptance-integrity-20261114/README.md)。

可重跑证据与设计边界见 [本次评估记录](docs/evaluation-design.md)。门控复跑证明的是契约被满足；真实效率、可迁移性必须通过固定预算下的留出任务对照证明。

入口/恢复可用 `goal_host.py enter` 识别唯一真实宿主回执，再用 `goal_ctl.sh context` 获取带版本的执行地图。crew 图 v2 绑定实际输入并复用未失效单元；`--policy-state` 在原作用域、依赖、容量和预算内消费合格路由，撤回后拒绝旧版本。原 Gate、账本和预算保持完成依据。见[端到端小示例](examples/learning-edge/README.md)与[本轮实现记录](docs/deepening-execution.md)；示例受控晋升不代表真实 agent 效用已获证明。

减少机械往返的新路径：`goal_host.py enter … --context` 在绑定宿主与预算后直接返回地图；`submissions.stamp` 运行原冒烟与盖戳，`submissions.close` 直接接收实际判断。通常的确定性契约只填进展、退出意图、复审结论和复审证据四项，程序推导操作身份、检查数并执行原终验；不用先写 proposal 再刷新地图。原调用方式保持兼容，版本过期仍拒绝提交。机制测量和收益边界见[直接提交评估](docs/evals/direct-submit-20261113/README.md)。

本地策略实验要求新比较先用好坏样本校准真实 grader，再执行配对试验；输出直接提供失败证据、当前选择和下一轮新留出样本要求。后续执行与派工核对绑定的资格报告；旧记录仍可恢复，重新启用需在原统计历史中取得新资格。执行地图与指纹路径同时减少重复读取和逐文件临时写入，仍完整验证历史、实际内容及原 Gate。运行方式见[策略实验](examples/evolution-dedupe/README.md)。

```
objective → contract (AC-1..N, each with a NAMED failable check) → user approval stamp
  → loop: crew wave (parallel workers, width fits the work) → join → gate re-runs deterministic checks
    → GO  → deliver
    → NO-GO → next wave (never stop) · BLOCKED → stop & report
  → GO only when every AC holds at THIS digest
    (forge: floors + K-round dry streak + empty completeness critic)
```

---

## Install / 安装

推荐完整插件安装，适用于 Claude Code 及提供同一插件接口的 cc-haha。本轮按本机 `claude-haha` 的真实加载器和 CLI 验证；若你的启动命令叫 `cc-haha`，用它替换下文 `claude-haha`。

```bash
# 在源码仓库里先检查依赖，不安装软件或修改全局设置
python3 scripts/goal_install.py doctor

# 从明确的文件清单构建完整包，隔离源码仓库里的本地文件
python3 scripts/goal_install.py plugin --output /ABS/goal-loop-package
claude-haha plugin validate /ABS/goal-loop-package

# 方式一：当前会话直接使用完整插件（skill、5 个 agent、8 类 hooks）
claude-haha --plugin-dir /ABS/goal-loop-package
# 在会话中调用 /goal-loop-host:goal-loop <目标>

# 方式二：持久安装；先添加本仓提供的 marketplace，再安装插件
claude-haha plugin marketplace add /ABS/goal-loop-package
claude-haha plugin install goal-loop-host@goal-loop
```

本地 marketplace 的安装包目录应保留；本机 cc-haha 的启动读取会直接访问它。开发时也可用 `--plugin-dir /ABS/goal-loop` 直接加载工作树；持久安装使用上面构建的目录，避免宿主把仓库中的本地未跟踪文件一起缓存。

插件使用固定的 `skills/goal-loop` 发现入口，正文从根 SKILL.md 生成，实施路径由 `${CLAUDE_PLUGIN_ROOT}` 绑定。即使插件缓存目录名是版本号，调用名仍是 `/goal-loop-host:goal-loop`。5 个角色使用 `goal-loop-host:` 前缀；可选 companion 也可直接调用 `/goal-loop-host:contract-forge`。更新后重新加载插件/开启新会话；4.1.2 的版本号用于区别旧缓存。

仅安装 skill 时，下面一条命令同时复制运行资源、参考文档、示例和 5 个原生角色，避免漏复制 agent 或协议文档。必须显式指定配置目录；不会覆盖已有同名 skill/agent，不会改写 settings.json。

```bash
python3 scripts/goal_install.py skill --config-dir ~/.claude --with-companion
# 新会话使用 /goal-loop <目标>，或 Skill 工具的 goal-loop
```

安装后用 `claude-haha agents` 核对 5 个 `goal-*` 角色。本机源码版 `999.0.0-local` 的默认文件搜索会静默漏载全局 agent；使用下面的宿主选项可恢复发现，或直接选择完整插件。这个选项不写入设置，启动后续会话时也需携带。官方 Claude Code 2.1.83 的相同安装无需该选项。

```bash
CLAUDE_CODE_USE_NATIVE_FILE_SEARCH=1 claude-haha agents
CLAUDE_CODE_USE_NATIVE_FILE_SEARCH=1 claude-haha
```

| 模式 | skill / 角色 | 原生事件接入 |
| --- | --- | --- |
| 完整插件（推荐） | 2 个带命名空间的 skill、5 个角色 | 自动加载本插件的 8 类 hooks |
| skill 安装 | goal-loop、5 个全局角色；companion 可选 | 使用显式 host bridge；不自动注册 hooks |

skill 模式的脚本和协议能力完整，但没有自动事件覆盖。需要自动预算/worker 生命周期事件时使用完整插件，见[宿主适配](references/host.md)。两种模式都保留判断校准、视觉判读、优化/forge、外部结算、crew、学习/回滚和恢复入口。安装文件由 `assets/install-files.json` 明确列举；构建不携带 `.git`、本地设置、缓存、未跟踪文件或外层模型客户端。随包保留仓库的离线参考/历史证据，因此完整包约 200 MiB。

依赖：POSIX Python 3.10+（验证版本 3.12/3.14，需 `fcntl.flock` 与进程组）、Bash 3.2+、GNU awk 和常见 UNIX 工具；工作树指纹还需 `sha256sum`、`shasum` 或 `openssl` 中之一。无 jq、无 GNU timeout 硬依赖。macOS 可用系统 Bash 3.2，需另备 `gawk`（如 `brew install gawk`）；Linux 可用 `apt install gawk`。Doctor 只检查，不自动安装依赖。原生 Windows Python 不支持当前 POSIX 锁；git-bash 本身不能补齐这一能力，完整 Windows 运行未验证。

安装后冒烟（不调用模型 API）：

```bash
python3 ~/.claude/skills/goal-loop/scripts/goal_install.py doctor
bash ~/.claude/skills/goal-loop/examples/quickstart-one-shot/run.sh
# 应得到真实 GO；完整回归在源码仓库运行：
bash tests/run_tests.sh
bash tests/docs_consistency.sh
```

开发者可用本地 cc-haha 源码重复验证安装（隔离配置、不启动推理会话）：

```bash
python3 devtools/check_claude_install.py --harness-root /ABS/claude-code-haha --output /TMP/fresh-install-check
```

检查会保留实际 CLI/加载器回执、默认角色发现结果、路径搬移后的 GO 和 hook 命令回放。回放不代表已验证模型执行期间的实时 hook 投递。

## Quick start — in-session / 快速开始 — 会话内

如果收账进程中断，`.goal/store/pending` 会保留写入前的账本与本轮原始证据文件快照。此时外部 gate、status 及后续控制器操作返回 `recovery-required`。先执行：

```bash
bash scripts/goal_ctl.sh recover --project /path/to/project
```

版本化账本的 state/log/scores、判词、检查器冻结记录与受管理原始证据会在读取前核对提交快照；发现 `ledger-view-mismatch` 时也用 recover 重建视图，gate 不会自行修账。升级旧账本若返回 `ledger-migration-required`，先运行 `bash scripts/goal_ctl.sh migrate --project /path/to/project`。迁移只确认一致的旧账本，不接受与已提交历史冲突的手改内容，也不修改业务 AC。

恢复会核对提交指针：提交前中断则回滚，提交后中断则按已提交快照补全；不会重新运行测量或外部工具。init/stamp/bind/close 共用提交历史，可重试的调用应提前选定并复用 `--operation-id ID`。历史重试输出 `REPLAY`，不代表当前产物通过验收。日志损坏时拒绝恢复；成功确认只在提交完成后输出。这些测试覆盖进程中断和注入的 I/O 故障，尚未验证真实断电。控制器写入及门控/status/audit/Stop hook 的读取共用目录锁，冲突时报告 `ledger-busy`；带外部缓存的门控独占访问。完整事务仍有待完成项，具体保护范围、重试及恢复边界见 [事务状态说明](docs/transaction-state.md)。

可执行的局部策略实验见 [配对成本实验与自动撤回](examples/evolution-dedupe/README.md)：冻结策略版本、grader 和任务，用新留出实例判断是否启用候选，并在反例出现后撤回。它目前支持单文件 Python 工具策略，衡量实际运行与验证时间；不把本地实验结果包装成相对原生 `/goal` 的通用优势。

```
/goal-loop <objective>
```

Four steps, no fifth / 四步循环，没有第五步：

1. **Contract / 契约** — decompose into `AC-1..N`, each a yes/no statement
   **plus the exact command that settles it** (a check must be able to FAIL).
   You approve with one word → AC section frozen by a sha1 stamp (R3).
   每条 AC = 可判定陈述 + 能让它失败的指名检测命令；你回一个字即盖章冻结。
2. **Dispatch / 派工** — choose serial or concurrent workers using measured startup and coordination costs;
   interfaces frozen in `.goal/interfaces.md` first.
   小任务和启动成本未知时先串行；证据支持净收益时，才在不相交文件域共享工作区并行。
3. **Join + gate** — merge review, then `bash scripts/goal_gate.sh --check`
   re-runs every deterministic check. This is the **only** completion authority.
   合并审阅后门控重跑全部确定性检查——唯一的完成判定。
4. **Branch / 分岔** — GO → deliver. NO-GO → fix and take the next wave
   (the loop does not stop). BLOCKED → stop under the four parking rules.
   GO 交付；NO-GO 继续派工；BLOCKED 停车上报。

Judged quality claims are reviewed **once** by a fresh cold seat before you
claim exit — never by the producers. 判断类 AC 在 claim 前由全新冷席终验一次，
生产者不自裁。

## Flags / 参数

```
/goal-loop [--auto] [--time-budget=N] <objective>
```

| flag | meaning / 含义 |
|---|---|
| `--auto` | still show the full contract summary, stamp immediately, ledger records `approval=auto` / 仍展示摘要，随即盖章记 `auto` |
| `--time-budget=N` | whole-loop wall-clock fuse; on expiry deliver best-so-far / 墙钟保险丝，到期优雅交付 |

Exit policy is a **contract field**, not a mode: `exit: threshold` (default,
delivery/build) or `exit: forge` (maximization). No modes matrix. 退出策略写在
契约里（`exit: threshold|forge`），不再有 quick/standard/deep 模式矩阵——
exit 策略/预算/基线由控制器在摘要中推断声明，旗标只是覆写。

**forge** (optimization objectives / 优化类目标): GO requires floors **plus** a
K-round dry streak (`dry_limit`, default 3 — critic finds no new evidence-backed
finding) **plus** an empty completeness-critic answer; `max_iterations` is a pure
fuse (rc=3 `budget-fuse`). Metric ACs default to `baseline: delta` — stamping
requires `.goal/baseline.md` (smoke run = baseline measurement, repeats≥2).
forge 退出 = 地板全过 ∧ dry_streak≥dry_limit ∧ critic 空答案；盖章前必须有基线。

In-session bookkeeping is one Bash call: `scripts/goal_ctl.sh close-iteration ...`
(forge contracts require `--dry yes|no`). 会话内记账一条命令。

## 外部开发运行器（显式选择）

正常 skill/plugin 由宿主执行模型与 subagent，不启动第二个宿主。独立开发验证的外层运行器已移到仓库 `devtools/`，不随上面的 skill 安装复制。旧 `scripts/goal_loop.sh` 只返回迁移提示和 rc=4，不再调用客户端。

```bash
bash devtools/goal_loop.sh --init      # 仅在源码仓库，显式选择外部验证
# 填好 .goal/goal.md 的 AC 并取得批准戳后：
bash devtools/goal_loop.sh --continue --max-iterations=6
```

The outer shell loop trusts **only the gate's exit code** — 0 DELIVERED, 3 BLOCKED,
4 state error, anything else → next round. `--dry-run` exercises it without calling
the API. 外层循环只信退出码；`--dry-run` 可不调 API 演练。

## The gate / 门控速查

| rc | meaning / 含义 | typical reasons / 常见原因 |
|---|---|---|
| 0 | GO, deliverable / 可交付 | — |
| 2 | NO-GO, keep iterating / 继续迭代 | contract-tampered, not-claimed, verdicts-stale, open-FAIL, **check-broken, check-mutated-tree**, evidence-missing, unverifiable-excessive, **not-dry (forge)** |
| 3 | BLOCKED, stop & report / 停止上报 | breaker-open, false-completes≥2, stagnation, repeated-error, **budget-fuse (forge)**, time-budget-exhausted |
| 4 | state error / 状态错误 | no-goal-dir, missing-key, unknown-flag |

Every judged verdict is bound to `(iteration, tree-digest)`. Touch one file under audit and
all judged verdicts go stale — the loop must re-judge (R7); deterministic ACs are exempt —
the gate re-runs them at every exit. Check 4b blocks the loop when two consecutive
iterations grind on the same error signature.
判断类裁决绑定 `(迭代号, 树指纹)`；树一动全部过期、强制重判（R7）；确定性 AC 豁免——门控
每次出口亲自重跑。连续两轮踩同一错误签名会被熔断（4b）。

## Anti-gaming rules R1–R19 (legacy index) / 防作弊规则（旧编号索引）

- **R1** false-complete counting: two gate-caught false claims → halt BLOCKED / 假完成两次即熔断
- **R2** re-running a **seat judgment** is illegal while its files are unchanged (gate re-runs are measurement, always legal) / 指纹未动的判断席复跑不算工作（门控重跑是测量，不受限）
- **R3** the stamped contract is frozen / 契约盖章即冻结
- **R4** UNVERIFIABLE ≤ ⅓ of judged ACs, always with PROBE/REASON / 不可验证项限额且必须给出探测与理由
- **R5** checker briefs carry verbatim AC text + paths only — never the producer's reasoning (judged seats; deterministic ACs are gate-evidenced) / 简报零污染
- **R6** workers never touch `.goal/` / worker 禁触状态目录
- **R7** stale judged verdicts are void after any digest move / 过期裁决作废
- **R8** findings must bind evidence — manufactured discoveries are as forbidden as manufactured passes / 发现项必须绑证据：制造发现与制造通过同罪
- **R9** verify the verifier: metric/maximize numbers need a passing `probe:` (instrument alive) / 数字必须先过仪器自检
- **R10** `progress=no` must carry `strategy_delta=` (what changes next) / 无进展必须写策略修订
- **R11** `objective: maximize` never delivers below `best_score` / 主指标不许倒退交付
- **R12** controller self-audit before claiming / claim 前自审控制器（goal_audit.sh）
- **R13** score↔judge divergence refuses the claim / 分数与冷席背离拒 claim
- **R14** measurement honesty: metric regex, ANSI strip, artifact-bound judged PASS / 测量诚实面
- **R15** judge calibration (v2.6): judged ACs with `calib: good= bad=` need `#good`=PASS ∧ `#bad`=FAIL on the fixtures before any claim / 认不出坏样本的席，好样本上不算数——判断面的"验证验证者"
- **digest 剪枝 (v2.6)**: 非 git 仓的树指纹默认跳过 node_modules/.venv/build 等重型目录（`.goalignore`/`GOAL_PRUNE` 可调）；真实源码的任何改动仍会被指纹抓住

## State / 状态文件（`.goal/`，纯文本，grep 即查询）

`goal.md`（契约+批准戳）· `state.rec`（计数器）· `loop-log.md`（迭代账本）·
`verdicts.rec`（裁决记录，6 字段管道分隔）· `work-plan.md`（任务队列正本）·
`interfaces.md`（crew 接口契约）· `baseline.md`（forge 基线）· `evidence/`（席与检查证据）

## 与普通目标循环的区别

额外机制是冻结成功定义、可恢复账本、校准检查器、确定性重跑和策略反馈。它们针对长任务中的验收漂移、假完成和重复无效尝试；是否胜过宿主提供的 `/goal`，取决于任务、模型版本与总预算。

比较时固定模型、起始工作区、验收器和总预算，用未参与调优的任务配对多次运行；报告交付率、全部尝试的总成本、交付时间与失败。不能把波数少或 shell 检查便宜等同于总成本更低，也不能把当前测试套件当作真实任务胜率。

门控是独立执行的检查程序，**不是操作系统权限边界**：控制器与检查器仍共享用户权限；脚本冻结也不等于冻结所有传递依赖。对不可信执行器需要隔离环境和外置验收器。避免叠加两个会强制续跑的外层循环，以免覆盖彼此的预算与停车语义。

## When NOT to use goal-loop / 何时不要用

Two orthogonal axes decide the instrument. **Do not force goal-loop into the
wrong quadrant.** 两个正交轴决定用什么工具，别把 goal-loop 塞进错误象限。

| | low iteration density / 低迭代 | high iteration density / 高迭代 |
|---|---|---|
| **enumerable done** / 完成信号可枚举（tests · benchmarks · invariants） | **goal-loop home turf** — migrate / build / harden | hybrid: gate for regression, let the craft loop run free |
| **non-enumerable done** / 不可枚举（逼真 · 手感 · 文采 · 洞见） | **dangerous** — split into sub-goals + human final review | **`/goal` (or producer self-view) home turf** — visual · copy · UI · research |

**Why the bottom-right rejects goal-loop / 右下象限为什么不要用**:
when the contract can only be written as proxy metrics, Goodhart is structural —
the loop optimizes the proxy, not the goal (a tris-count floor can be “passed”
by densifying geometry without making a better aircraft). Cold-seat rounds also
destroy the “change → look → tweak” cadence that perceptual craft needs.
契约只能写代理指标时 Goodhart 是结构性的；冷席往返还会摧毁感知工艺的改→看→调节奏。

**Do not use when / 不要用的场景**:
- trivial one-pass tasks / 一眼就能做完的琐事
- pure Q&A or exploration with no deliverable / 无交付物的问答与探索
- irreversible side effects (merge · push · prod writes · deletes) / 不可逆副作用
- “make it beautiful / realistic / moving” with no measurable acceptance /
  无可测验收的“更好看/更逼真/更动人”
- you only want a parallel task board — bare Agent Teams is cheaper /
  只要并行分工面板：裸 Teams 更便宜，别套验收门

**Do use when / 该用的场景**: the predicate of “done” is itself the goal
(checks, benchmarks, migrations, audit trails), or you need delivery + metric
deltas + regression protection that must survive later review.

**Physical tooth / 物理的牙**：register `scripts/goal_hook.sh` as a Stop hook
(see the install snippet in the script header) and the harness blocks stopping
only when a claimed exit is denied by the gate (rc=2) — /goal's tooth, without
its discretionary evaluator. rc=0/3/4 pass, fail-open.

## More docs / 更多文档

- `references/gate.md` — five invariants, R1–R19 legacy index, check order, schemas（门控规格与旧规则索引）
- `references/crew.md` — crew protocol, judged-seat brief（派工协议与冷席简报）
- `references/patterns.md` — failable check shapes per artifact type（可失败检查形状库）
- `references/companions.md` — companion skills + cross-machine install（组合技能与跨设备安装）
- `assets/goal.contract.md` — contract template（契约模板）

## Provenance / 出处

This repository is a clean-room reimplementation fusing ideas from
[ralph-claude-code](https://github.com/frankbria/ralph-claude-code) (MIT) and the
fable-mode checker-panel conventions — no verbatim source text from either.
本仓库是对两者思想的无原文重实现：ralph-claude-code（MIT）× fable-mode 面板纪律。

Self-audited with its own protocol (v1.2): 5 acceptance criteria (4 deterministic,
gate-re-run; 1 judged, cold seat), a real bug caught by the seat
(close-iteration refusals left an orphan loop-log block — fixed + regression-tested),
final line `GATE: GO ... ac=5 pass=5 unverified=0 mode=threshold` — the skill certified
itself by the same gate it ships. 本 skill 用它自己的协议审计了它自己（v1.2）：
卖的门，先过自己。
