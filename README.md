# goal-loop

**v4.1.1** — 用冻结的验收契约、共享工作区 subagent 波次和确定性门控推进交付；用测量反馈选择下一轮策略。

这一版只深化归因：相邻读数差属于当前波次；缺失证据断链；策略采用最新窗口；噪声信息不足时不推荐。`EFFICIENCY` 和 `STRATEGY-PICK` 共用一个计算内核，删除重复逻辑。入口比 v4.0 更短，命令和账本格式兼容。真实试跑又修正了短预算任务的派工选择，并修复无人值守执行目录及锁清理。

可重跑证据与设计边界见 [本次评估记录](docs/evaluation-design.md)。门控复跑证明的是契约被满足；真实效率、可迁移性必须通过固定预算下的留出任务对照证明。

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

Two pieces, both required / 两件套，缺一不可：

```bash
# 1) skill 本体 → Claude Code 的 skills 目录
git clone https://github.com/samirliu/goal-loop.git
mkdir -p ~/.claude/skills/goal-loop
cp -r goal-loop/SKILL.md goal-loop/VERSION goal-loop/assets \
      goal-loop/references goal-loop/scripts goal-loop/tests \
      goal-loop/examples goal-loop/companions \
      ~/.claude/skills/goal-loop/

# 2) 5 个 agent 定义 → agents 目录
mkdir -p ~/.claude/agents
cp goal-loop/agents/*.md ~/.claude/agents/

# 可选：companion skill contract-forge（盖戳前访谈，不是硬依赖）
# cp -R goal-loop/companions/contract-forge ~/.claude/skills/

# 升级到 v4：清掉旧文件（Agent Teams 后端已整体移除）
rm -f ~/.claude/skills/goal-loop/scripts/goal_team.sh \
      ~/.claude/skills/goal-loop/references/teams.md
```

- Windows（git-bash）路径同上：`C:\Users\<你>\.claude\skills\goal-loop\` 与 `C:\Users\<你>\.claude\agents\`。
- 依赖：`grep / sed / gawk / sha1sum|cksum`，**无 jq**；CR 与 `LC_ALL` 已内置处理。有 coreutils `timeout` 时每条门控重跑检查限时（默认 120s）。
  - **macOS**：系统 `bash` 是 3.2，系统 `awk` 是 BSD —— 脚本已兼容 bash 3.2；`gawk` 必装且会自动发现 `~/.local/bin/gawk`、Homebrew 路径。`brew install gawk`（可选 `coreutils` 提供 `timeout`/`gtimeout`）。
  - **Linux**：`apt install gawk`（通常已带）。
- Smoke test / 冒烟验证（不耗 API）：

```bash
bash ~/.claude/skills/goal-loop/scripts/goal_gate.sh --check
# 无 .goal/ 的目录里应返回 rc=4, reason=no-goal-dir —— 说明门控在岗
bash ~/.claude/skills/goal-loop/tests/run_tests.sh
# 场景套件应 fail=0 全绿 —— 门控语义的完整回归（当前 509 项断言）
# 默认 --jobs=8 并行分片（约 3–4 分钟）；--jobs=1 串行；--only 78-90 增量
bash ~/.claude/skills/goal-loop/tests/docs_consistency.sh
# 文档一致性（活文档字面量）应 CONSISTENT
bash ~/.claude/skills/goal-loop/examples/quickstart-one-shot/run.sh
# 小任务快车道：单 AC 最小契约应 GO（rc=0）—— 证明仪式的下限
```

## Quick start — in-session / 快速开始 — 会话内

```
/goal-loop <objective>
```

Four steps, no fifth / 四步循环，没有第五步：

1. **Contract / 契约** — decompose into `AC-1..N`, each a yes/no statement
   **plus the exact command that settles it** (a check must be able to FAIL).
   You approve with one word → AC section frozen by a sha1 stamp (R3).
   每条 AC = 可判定陈述 + 能让它失败的指名检测命令；你回一个字即盖章冻结。
2. **Dispatch / 派工** — concurrent workers on disjoint file scopes (width fits the work; no default cap);
   interfaces frozen in `.goal/interfaces.md` first.
   默认一波 subagent 并行 worker，共享工作区。
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

## Unattended mode / 无人值守模式（可选）

```bash
bash ~/.claude/skills/goal-loop/scripts/goal_loop.sh --init      # 播种 .goal/
# 填好 .goal/goal.md 的 AC 并取得批准戳后：
bash ~/.claude/skills/goal-loop/scripts/goal_loop.sh --continue --max-iterations=6
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
