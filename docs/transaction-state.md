# 当前事务保护与证据边界

此文记录优化方案 A3/A4 的实际接入状态；平台与效用证据按已运行范围声明。

## 锁的范围

`goal_ctl.sh` 的 init、stamp、bind、close-iteration、recover 使用 `.goal` 目录 inode 的排他 `flock`；status 使用共享锁。`goal_gate.sh` 的 check、verify、baseline-check、checkpoint，以及 `goal_audit.sh` 和 Stop hook，在读取前取得共享锁并持有至本次操作结束。目录锁不创建、删除或覆盖锁文件，读取者不修改账本来获取锁。init 创建 `.goal` 后才有可锁定的目录。

普通读取者可并发执行；与 writer 冲突的调用立即返回 rc=4、`ledger-busy`，调用者应等当前操作结束后再重试。这个结果没有完成或失败的产品含义。Stop hook 保留其原有的 fail-open 政策：锁冲突允许用户停止，但不证明 GO。

带 `external:` 的门控可能追加影响后续判定的缓存记录，因此使用排他读取模式。实现保守地检测契约中的 `external:` 字节串，文字中的同名内容也可能触发串行执行；不影响验收语义。内部 gate 继承当前 controller 的所有权，允许在收账期间检查自己的新视图；用户检查调用的嵌套 writer 会被拒绝。

检查、probe 与 external 命令运行前关闭目录锁和收账锁的描述符。等待命令结果的中间 shell 同样关闭这些描述符，避免后台后代或被 SIGKILL 的 gate 遗留锁。锁由实际控制器/门控持有，不通过删除他人的文件解锁。元数据只用于同一运行的协作，不构成对同一用户恶意进程的权限隔离。

内部受信 gate 需要借用 controller 的锁，因此由监督器管理。监督器先注册 macOS kqueue NOTE_EXIT 或 Linux pidfd 退出事件，再释放受监督的 Bash 子进程；父 controller 即使尚未回收尸体，也会触发借用者终止。监督器持有自己的未回收子进程，避免清理时向复用的借用者 PID 发信号。正常返回保留子进程退出码；无法建立退出事件时拒绝无监测执行。事件身份在注册时绑定，不能声称已证明注册前的 PID 身份。用户检查与 runner 命令的进程组监督见下节。macOS 与 Linux ARM64 的完整回归已通过。Linux 原始结果见[复验记录](evals/linux/README.md)。

独立 `--digest` 仅计算产物指纹，不判定完成，保留没有 Python 的 shell 路径；它不提供账本版本读取保证。

## 权威文本视图

当前控制器提交保存完整的受管理视图及 `.ledger-views.json` v2 清单，包含每个路径的 SHA-256 或缺失标记。范围是 state、loop-log、scores、verdicts、check_freeze、对抗/故障收据及规范命名的原始验证文件。gate/status/audit 在持有目录锁时校验提交链、清单和实际文件；不一致时 rc=4、`ledger-view-mismatch`，不执行产品检查、不写回视图、更不会给 GO。

清单还绑定首次批准标记。将已批准 goal 的 `approved:` 清回 PENDING 不能再走一次自动 stamp，也不能通过 migrate 接受一个放宽后的契约。修改业务 AC 仍由 R3 判定；这里补的是批准身份不能被重置。已批准契约的变更须经用户审阅并作为新的受审运行处理，不允许抹掉标记重新盖戳。新入口只从实际取得或已验证继承的锁推导写入身份，不信任单独残留的 `GOAL_ACCESS_MODE=write`。

即使没有 pending，recover 也可从当前提交重建受管理视图；提交索引丢失、generation 损坏或批准身份冲突则拒绝猜测。goal 内容、work-plan、pre-reg 等作者材料不作为普通控制器投影覆盖；业务契约仍遵守既有冻结与用户审阅边界。

旧账本或旧清单需显式迁移：

```bash
bash scripts/goal_ctl.sh migrate --project /path/to/project
```

迁移不修改业务 AC，先核对旧历史、迭代序列和文本视图；已有提交与当前文件矛盾、重复/截断轮号或历史批准标记冲突时拒绝。已版本化账本不能借 migrate 确认手改内容。门控自身始终只读；测量缓存和 runner 辅助状态的边界仍按下文说明。

## 收账中断与恢复

close-iteration 完成预检及测量后，在首次修改账本前写入 `.goal/store/pending`。v3 日志包含提交身份、请求摘要、基线 HEAD，以及本轮写入前的 state、log、scores、对抗与故障收据和本轮原始验证文件的内容或缺失标记。字段集合、版本类型和 SHA-256 校验在恢复前验证；未知或损坏内容会被拒绝。旧 v1/v2 日志仍可读取：缺少基线 HEAD 的日志仅在没有提交历史时回滚；v2 若匹配当前已提交操作，可按快照前滚；无法证明版本关系时拒绝恢复。

收账成功路径先核对本轮 state、scores、log 与原始证据，确认历史没有被覆盖，再同步所有写入文件及目录。随后把最终文件快照及返回码写入 `.goal/store/commits` 的不可变 generation，并原子发布 `current` 指针；**指针发布是收账提交点**。之后删除 pending、同步其目录，最后报告 `CLOSE ok`。关键写入失败、文件同步失败或进程被杀时，pending 可能留存。外部 check/verify/baseline-check、status、audit 与后续控制器操作不能继续使用待恢复账本。

```bash
bash scripts/goal_ctl.sh recover --project /path/to/project
```

recover 取得控制器排他锁后，先核对提交历史。提交点之前中断：确认 current 仍等于日志基线 HEAD 后恢复原内容，删除本轮新生成且原先不存在的原始验证文件。提交点之后中断：确认操作就是当前提交，再按快照补全最终内容，保留已消费的轮号及计数。两种情况都不重放外部工具，然后删除 pending。恢复本身若中断，保留日志，下次继续写回同一版本。如果 pending 的基线或已提交操作与 current 矛盾，会拒绝恢复，避免把新账本倒退。

## 重试提交身份

有可能重试的调用应由 controller 在首次调用前选定身份，并在重试时保持相同参数：

```bash
bash scripts/goal_ctl.sh close-iteration --project /path/to/project \
  --operation-id wave-20261110-T1 --task T1 --files artifact.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --no-gate
```

ID 为 1—128 位 ASCII 字母、数字及 `._-`，首位为字母或数字，作用域是当前项目提交历史。省略时生成 UUID 并在 `CLOSE ok` 中输出；未提前保存身份的调用在丢失确认后不具有可自动判断的重试身份。

init、stamp、bind 也支持固定 `--operation-id`，并使用相同的 commits/current 指针。它们的 v4 日志保存 kind、严格的文件范围、基线 HEAD 和请求摘要；恢复采用同样的提交前回滚、提交后前滚规则。bind 的请求摘要还绑定原始 stdin 字节，整批行先验证再追加；与旧版“跳过坏行、保留已追加好行”不同，坏批次现在 rc=4 且不追加任何行。缺少 approved 占位行的 stamp 在首次写入前拒绝。

objective 的 `best_score` 只由通过质量资格的实际读数更新。收账和 bind
在各自事务内调用 `gate --quality`，重跑全部地板和校准 horizon，并检查
指纹、账本、截止与质量背离；它返回 `QUALITY-OK`，不代表 GO，也不替代
交付要求的 claim、工作计划、adversarial 和 forge 覆盖。普通任务不增加这次检查。
原始失败读数仍留在 scores.rec，不能抬高/压低合格水位或污染 R13 比较。

`best_score_basis` 以 SHA-256 绑定与 stamp 相同的语义表面及 check_freeze，
普通备注不会重置水位。`last_quality_score/judge` 独立保存最近一次通过资格的
比较点，含同分的新判断；不能用全局最佳分的旧判断代替它。
旧版未证明资格的水位保留在提交历史，并明确记为 legacy-unqualified；
它不能冒充当前契约的合格水位。首次有界资格检查后再建立新水位。
bind 的新写范围包括 state.rec，保证判词和资格更新共同提交/恢复；
旧 verdicts-only 日志与已提交操作按其真实历史范围恢复和重放。

相同 ID、相同请求再次调用，直接返回保存的历史收账返回码，并输出 `CTL: REPLAY ... historical-result=...`。不会重跑测量、重复加分、增加假完成计数或消费另一轮；重放较早 ID 也不会把 current 或文件倒退。请求摘要按原始参数序列计算，仅排除项目路径和 operation-id；改变顺序、显式增加默认参数等也会作为不同请求拒绝，避免猜测语义等价。

重试结果是历史收账确认，**不证明当前产物仍然满足契约**。产物即使已变化或消失，原提交仍然存在；最终交付仍须重新运行 gate。发生在提交前的测量证据、外部缓存及外部工具副作用，不因为回滚账本而被当作未发生。

## Runner 所有权、预算与取消

只有 `--continue` 获取 `.goal/store/runner.lock` 固定 inode 的非阻塞排他 flock。文件不被删除、替换或以 PID 检查模拟互斥；`.goal/lock` 仅保留供人读取及识别旧 runner 的收据。只读检查和拒绝重复启动不会删除它。新版收据可凭已释放的内核锁回收，即使原 runner 仍是 zombie；旧格式活进程仍会阻止启动。

runner 的 `runner.clock`、`runner.deadline` 与 `runner.json` 由目录排他锁保护，进入主账本同一 commits/current 历史。先在内存构造完整快照，原子提交指针后再安装文本视图。提交前故障不改变既有预算；提交后安装中断则所有普通入口拒绝混合视图，`ctl recover` 恢复已提交的截止时间，不运行 worker。未升级的旧 sidecar 在首次 runner 启动时验证并导入最早 deadline / 最高 clock；不能用恢复清除旧预算。已导入后，直接手改三个 runner 文件会被拒绝并可精确恢复。

每次启动沿用 runner、契约与新参数中的最早截止时间。时长使用单调时钟；同一系统启动内还持久化单调截止时间，因此冻结墙钟后 resume 也不能重置预算。Linux 用 boot_id，macOS 用只读 kern.boottime 区分启动；无法读取时拒绝硬预算运行。系统重启后只沿用仍有效的 epoch 截止，墙钟未前进或回退则拒绝恢复。预算观测范围明确标为 `script-entry`，不声称计入更早的模型思考。

runner 执行器预留剩余时间的 10%（最多 3 秒）供结算；runner 与独立 gate 都先计算契约、持久化 runner 和继承 envelope 的最早截止。门控取得权威视图后，外层监督器覆盖指纹准备、probe、external、AC 检查与收尾；内层命令仍受 check_timeout 约束。耗尽后最多再做一次 3 秒的最终结算。嵌套检查共享该结算截止，不逐条重新领时。普通调用不能仅靠 GOAL_GATE_SUPERVISED 环境标记绕过监督，首次访问会清除它。没有总预算的契约仍保留逐条检查超时，不凭空创造总预算。gate 通过后保存实际完成时点与 `within-budget` / `after-deadline`，产品 GO 与预算内成功分开。

runner 与独立 gate 的 check/probe/external 复用 `goal_owner_watch.py` 的退出事件监督，均不依赖 GNU timeout。超时、owner 退出（包括未回收 zombie）或命令结束时清理所属进程组，先清理再回收 group leader，避免 PID 复用。通过不持有 IO/锁的组内守卫保留可发信号的成员，以处理仅剩 zombie 的组返回 EPERM 的行为。runner 锁留在监督器直到清理完成，不传给用户命令。监督器脱离 owner 的进程组，避免外层取消把内层监督器一并杀死，留下独立检查组。

边界仍包括：遵守协议的 POSIX 本机入口，不是对任意同用户进程的权限隔离；主动 setsid 脱离所属组的工具、监督器自身被 SIGKILL、真实断电、网络文件系统和平台差异不能由这些本地测试推断。作者材料与 external 测量缓存不等同于控制器投影，也不声称整个文件系统都已事务化。W4—W9 的行为与效用评估继续独立完成。

## 实际执行耗时

监督器将观测写到 `.goal/evidence/runtime/<id>.json`，包含命令/产物摘要、实际契约与 check_freeze 摘要、执行器版本、父事件、开始/结束时间、单调时长和真实返回码。每次执行先发布 running 记录，再原子替换为 complete；超时和取消也保留。监督器中断而未补齐的记录保持 unfinished，不能补成零成本。遥测准备与 fsync 同样消费既定执行预算。

`ctl status` 的 RUNTIME 行只汇总已观测 spans。executor、measurement 与 verification/acceptance 是不同事件，不能把它们当作新的产物版本；父子 spans 重叠，不能相加成墙钟时间。缺失与损坏记录显示 unknown，tokens/费用当前没有采集来源，始终为 unknown。遥测不能改变 gate 返回码或代替质量检查；写入遥测失败仍保留产品结果，并明确报告成本观测缺失。

这些记录是受信本地执行器的观测，不是权限隔离或独立能力评估。输入只覆盖绑定的产物与命令，外部事实、运行环境与传递依赖的身份仍可能未知。恢复/协调阶段、CLI 外的 subagent 派发和首次有效产出尚未全部接入，因此不将 RUNTIME 宣称为所有 agent 工作的完整总成本。

## 策略启用与撤回

`goal_evolve.py` 在同一实验 state 目录 inode 上取得排他锁，首个 trial 前
持久化带校验的 `policy-pending.json` evaluation guard。执行已启用策略
持有同目录共享锁，发现任何未完成 guard/transition 时拒绝启动。
形成最终决定后，日志保存原/目标指针字节、冻结材料摘要和最终报告；
`enabled.json` 的原子替换是切换提交点，随后才发布启用/撤回报告并清理日志。
因此报告写入或确认失败不能让已退化的旧版本继续通过执行入口启动。

```bash
python3 -I scripts/goal_evolve.py recover --state STATE
```

恢复只校验并完成已记录的切换，不重跑 policy、trial 或 grader，也不重置
已曝光输入和统计预算。指针/报告处于原或目标版本时可幂等完成；第三版本、
校验错误或冻结材料变化会保留现场并拒绝覆盖。若崩溃仅留下 evaluating
guard、尚无完整切换决定，使用 `recover --state STATE --abort-incomplete`
保存未完成报告及原指针，将策略安全置空并记为 `interrupted-uncertain`；
它不代表已证实退化或撤回。之后可在同一 state 用新输入重新验证，保留
原 raw 记录、曝光历史及顺序统计预算。正常完成的 instrument-invalid、
预算不足和无充分反证路径仍沿用原选择语义，不自动隔离已启用策略。

## Accepted artifact checkpoints

List only files owned by the trial. The scope supports regular files and
missing leaves under existing project directories. It preserves file bytes and
permissions.

```bash
base=$(python3 -I scripts/goal_store.py incumbent save --project PROJECT --file a.py --file b.py)
# Run the candidate within the declared scope.
candidate=$(python3 -I scripts/goal_store.py incumbent candidate --project PROJECT --base "$base")
python3 -I scripts/goal_store.py incumbent restore --project PROJECT --base "$base" --candidate "$candidate"
bash scripts/goal_gate.sh --check --project PROJECT
```

Save runs the gate and archives its output, artifact digest, and the immutable
ledger version holding its evidence. Capture the candidate only after checking
that the owned files contain the trial's changes. Restore compares every live
file in scope with that captured version before writing. Changes outside the
scope stay in place. Restore retains the current ledger and its history.
Reverify the restored artifact and rebind any stale verdicts before claiming GO.
Save reuses the gate's verified content digest, eliminating one full-tree
digest computation while retaining the final capture consistency check.

For an intermediate artifact, add `--intermediate` to `incumbent save`.
The latest booked artifact must pass fresh mechanical checks, all bound judged
criteria and calibration, the water mark, and the adversarial receipt check.
The gate allows remaining work-plan items and forge exploration. It issues
`CHECKPOINT-OK` within the active budget. Use `goal_gate.sh --checkpoint` to
requalify after restoring. Final delivery still requires `goal_gate.sh --check`.
Both kinds of checkpoint use the existing archive format and can serve as the
baseline for version 2 paired evaluation.

Forge scope approval and dry evidence use the existing transaction history.
The scope digest lives in `check_freeze`, its input/instrument bytes in
`evidence/raw/0.txt`, and executed attempts in the corresponding canonical
raw file. Probe-ledger mutation aborts the close with its recovery journal
visible. Checks also receive a before/after guard over managed evidence.
At commit, the controller confirms that its write scope preserved older
managed records. The active raw output stream is excluded only while its
owning controller writes it.

The existing `migrate` command can bind a legacy forge scope or append probes
to the approved scope. It preserves previous cases, materials, contract and
history, then clears the dry counter so the expanded scope is executed.

Restore publishes a journal before modifying the files. While it is pending,
gate and controller operations refuse access. `goal_ctl.sh recover` can finish
the same restore without replaying checks. Recovery accepts each file at its
candidate or incumbent version. If it encounters a third version, it preserves
that version and leaves the journal pending for conflict resolution. These
checks serialize cooperating entry points and detect edits at the comparison
points. Concurrent writes that ignore the ledger lock can still race a rename.

## 可复放证据

```bash
python3 -B tests/test_ledger_access.py
python3 -B tests/test_controller_writers.py
python3 -B tests/test_close_commit.py
python3 -B tests/test_mutation_commit.py
python3 -B tests/test_owner_watch.py
python3 -B tests/test_runner_lifecycle.py
python3 -B tests/test_gate_budget.py
python3 -B tests/test_runtime_trace.py
python3 -B tests/test_view_authority.py
python3 -B tests/test_worktree_scope.py
python3 -B -m unittest discover -s tests -p 'test_goal_store.py'
bash tests/run_tests.sh
```

访问测试使用真实子进程，覆盖共享读取、写入排斥、external 缓存串行、嵌套写入拒绝、关闭的继承 FD、后台子进程及 gate 主进程 SIGKILL 后的锁释放；还覆盖 controller 在 raw gate 执行中被杀后，两把锁释放并可恢复。收账测试覆盖实际写入中途被杀、恢复前读取拒绝、损坏日志、追加写入失败、恢复重复调用与并发轮号。提交测试在真实控制器的 generation 发布后、current 发布后、成功确认前分别杀死 controller；验证回滚、前滚、同 ID 重试不重测、不重复收账，以及历史重试不倒退、变参冲突及过期 pending 拒绝。存储测试另覆盖 I/O 同步失败和隔离核心行为；这些证据均不代表其余 A3 要求已完成。

`tests/cases.inc.sh` 的旧场景会直接手写账本来构造 gate 语义输入。它们现在通过 `tests/view_fixture.py` 显式提交这些测试前置数据，原断言保持；测试 shell 的 setup hook 不导出给生产子进程。验证未提交改写必须拒绝的 `test_view_authority.py` 等集成测试直接调用生产入口，不使用该夹具发布器。不要把语义夹具发布当作生产恢复途径。
