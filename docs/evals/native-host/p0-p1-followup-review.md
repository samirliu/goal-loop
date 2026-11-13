# F1–F4 修复后独立复审

日期：2026-11-12。范围仅为 `goal_parse.sh` / `goal_tree_digest.py`、`goal_crew.py`、`goal_evolve.py` 和 `examples/evolution-dedupe/verify_agent.py`。未修改实现或测试，未派发模型/worker，未重启真实 cohort、恢复截止或运行全套回归。[原审阅](p0-p1-review.md)保留为历史记录。

**本次快照中，F2、F3 的原反例已关闭；F1 的 Gitlink 原反例、F4 在普通解释器下的身份与状态转移缺口已修复。但仍复现两处入口：顶层 Git 枚举漏读目录后继续 GO，以及优化解释器下的 verifier 静默失效。不能据此宣布四项全面关闭。**

## 修复成立的范围

| 项目 | 当前实现与独立复验 | 本次结论 |
|---|---|---|
| F1 | Gitlink 绑定父索引对象、实际 HEAD 和递归工作区字节；未初始化、替换、循环及无 Python 的 fallback 均保守拒绝。原 A→B 脏文件反例现在改变摘要。另跑 4 个定向 scope 测试，全部通过。 | 原 Gitlink 遗漏已关闭；下述顶层枚举入口仍未关闭。 |
| F2 | 两条匹配路径均绑定实际 `scope_digest(inputs)`；记录 producer transport，CLI 读取 API 记录时保持 producer 身份，混合 producer 不池化，缺身份旧记录失效。独立运行输入变化、CLI/API 读取及混合 transport 三项测试，全部通过。 | 未复现输入改变后仍凭旧成本推荐 crew 的原问题。 |
| F3 | 试验前持久化 evaluating guard；`run-enabled` 在读锁内拒绝 pending；选择、报告及确认有可恢复 transition。独立运行指针写失败、四个进程崩溃点及 intent 发布失败三项测试，全部通过。 | 未复现观察退化后因切换失败继续运行旧策略的原问题；恢复不重放 trials。 |
| F4 | 普通解释器下，原始归档重建成功；candidate 冒用 baseline 身份现在被拒绝。源码已从 frozen 程序绑定 archive，并独立重算资格、正反向检验、阶段完整性及选择链。 | 原身份替换反例在普通运行模式下已关闭；优化模式仍有下述缺口。 |

F2 的耗时输入来自既有本地合成夹具，仅用于比较条件和决策语义，不能计入真实效用证据。F3 的试验 telemetry 也受控，不是新真实 cohort。

## 剩余反例 A：顶层 Git warning 仍允许旧 GO

位置：[goal_parse.sh:144](../../../scripts/goal_parse.sh#L144)。顶层三次 `git ls-files` 只检查退出码；Git 对无法读取的未跟踪目录会警告并以 0 退出。相比之下，新增的 [goal_tree_digest.py:62](../../../scripts/goal_tree_digest.py#L62) 已在子 Gitlink 枚举时拒绝非空 stderr。

本次以 uid=501 在临时 Git 仓库建立一个已跟踪文件，以及**未忽略、未跟踪**的 `untracked/artifact.txt`。把目录设为 `000` 后取摘要；临时恢复权限，把内部 A 改成 B，再设为 `000` 后取摘要。两次均返回 0，输出相同：

```text
v2-f0f87352b5e9925e5eca06c0b202b0b783ee80b10bcc40ae8db9a81692457097
warning: could not open directory 'untracked/': Permission denied
```

又按已有 judged → close-iteration → bind → check 流程验证实际 gate。内容改变前后均返回 0，且均给出：

```text
GATE: GO digest=v2-1a9249796a57c8cb6599724e3f3902a6e2de1b1eda28fdabfb4e1873984c8720 iter=1 ac=1 pass=1 unverified=0 mode=threshold
```

stderr 保留了 Permission denied，但未阻止 GO。第二次没有新裁决或采用。这是既有默认工作区范围的静默遗漏，仍可保留旧 judged 结论，属于未关闭的 P0 入口；无需增加角色、评分条件或另一套传感器。把顶层枚举失败处理与子 Gitlink 的保守行为对齐即可针对这一反例。

完整命令和原始结果：[摘要探针](audit-fixes/followup-results.json)、[实际 GO 反例](audit-fixes/followup-gate-unreadable.json)。临时探针为 `/tmp/goal_p0_followup_review.py` 与 `/tmp/goal_p0_followup_gate.py`；原始仓库及实验归档未被修改。

## 剩余反例 B：优化解释器使 verifier 接受身份矛盾

位置：[verify_agent.py:60](../../../examples/evolution-dedupe/verify_agent.py#L60) 及该文件的其余 `assert` 检查。检查已经实质增强，但 Python `-O` 会删除这些断言，当前入口没有先拒绝优化模式。

仅在归档的临时解包副本中，把 holdout evaluation=2 的 `report.policies.candidate` 改成该报告的 baseline hash，其余 raw 输出不改。结果为：

| 调用 | 实际结果 |
|---|---|
| 原始副本，普通 Python | exit 0，`verified=true` |
| 身份变异，普通 Python | exit 1，`candidate policy does not match frozen program` |
| 同一身份变异，`python -O -B verify_agent.py …` | exit 0，`verified=true` |

因此，这不推翻普通调用下原始 98 对 / 196 份输出的数值证据，也不重新打开已修好的普通模式身份检查；但当前 CLI 复核器仍能静默接受自身身份矛盾。`PYTHONOPTIMIZE` 同样能够启用 Python 优化，不能把所有 `verified=true` 都当成断言确实执行过。显式拒绝优化解释器，或使用不会被优化移除的检查，就能关闭这个具体入口，无需增加新的效用门槛。原始 stdout/stderr 见同一 [results.json](audit-fixes/followup-results.json)。

## 本次验证与边界

- [4 个 scope 定向测试](audit-fixes/followup-scope-focused.json)：嵌套 Gitlink、未物化/替换/循环、shell fallback、旧 judged 绑定失效，全部通过。
- [3 个 crew 定向测试](audit-fixes/followup-crew-focused.json)：输入字节变化、CLI 读取 API producer、混合 producer，全部通过。
- [3 个 policy transition 定向测试](audit-fixes/followup-policy-focused.json)：指针写失败、进程崩溃恢复、intent 发布失败，全部通过。
- verifier 只读取既有真实归档并修改临时副本，没有执行新策略试验。本次没有代领可能正在运行的 12 个 verifier / 18 个 crew 测试的结果。

这是一轮针对旧反例与相邻失败入口的复审，不是所有并发、文件系统断电故障、适配平台或 CI 的穷举证明。F3 的 version 2 archive 执行/恢复路径已读源码，但本次三个定向测试不包括该路径；这只是覆盖边界，不把其他语言适配或额外平台新增为本轮硬门槛。真实 v3 cohort 继续保持原停止状态，两对完整配对、第五个样本截止失败及第六个未派发的结论不变。

本次唯一仓库写入是本文。原 `p0-p1-review.md` 的 SHA-256 为 `b617dea0d62795dfffbeee691fb2c3e1fe1f3cb00ee1c41ff5e11eaa4b2ec913`，复审前后未变。

本次被审快照 SHA-256：

```text
goal_parse.sh       a26c26a2d177dba4d2e23bd287e19be0e5a08d7bc0cb84c4efd06a0a46cd21dd
goal_tree_digest.py f4533f37e2787ce9d73cba3dbf557cfb2c58a8471311bb98bbe2d1c94fead97d
goal_crew.py        f0bf48438a6c2d4eecbc7a1be03c9d6b990da94a686dbde1e251c58a7c23bae9
goal_evolve.py      e6ff794567ce37409a8cd7cca0efc2efa93b35a0bf968b3d22411ccd908d0ae7
verify_agent.py     b7e4e0461ec44d06270e3b505bd5f74a9c618d990fae1011e5323b561020b69b
```

## 最终定向复验补记（2026-11-12）

上文保留发现时的源码与结论。本节仅复验随后针对剩余反例 A/B 的两处修补，不重开全仓审阅。**独立重放确认：顶层 Git 漏读后保留旧 GO，以及优化解释器下的身份假验证，这两个明确入口均已关闭。** 上文“仍复现两处入口”的结论适用于所列旧 SHA 快照。

复用原 `flat` 现场及其既有 judged 绑定，将同一非忽略目录设为 `000`，不重写账本或增加裁决：

| 重放入口 | 实际退出码 | 实际结果 |
|---|---:|---|
| `goal_gate.sh --digest` | 4 | stdout 为空；`incomplete-git-inventory` / `unreadable-project` |
| `goal_gate.sh --check` | 4 | stdout 为空，无 GO；同样拒绝不完整枚举 |
| 强制无 Python accelerator 的 `--digest` | 4 | stdout 为空；同样以 `incomplete-git-inventory` 失败关闭 |

verifier 的正例来自原始归档的新临时解包副本；负例复用本次最初保留的 `candidate=baseline` 身份矛盾副本，没有修改 raw 输出。修补后的显式 `VerificationError` 在三种模式均有效：

| 解释器模式 | 原始归档 | 同一身份矛盾副本 |
|---|---|---|
| 普通 Python | exit 0，`verified=true`，98 对 / 196 输出 | exit 1，`candidate policy does not match frozen program` |
| `-O` | exit 0，相同重建结果 | exit 1，相同 `VerificationError`，stdout 为空 |
| `PYTHONOPTIMIZE=1` | exit 0，相同重建结果 | exit 1，相同 `VerificationError`，stdout 为空 |

独立命令、完整 stdout/stderr 和前后源码哈希保存在 [final-two-replays.json](audit-fixes/final-two-replays.json)，重放脚本为 `/tmp/goal_p0_final_two_replays.py`。源码在重放期间未变：

```text
goal_parse.sh       368fdcbb5838c8a8d64570f409b1ea713ec3ce24938825a8dc5f9f2ed1a85bdb
goal_tree_digest.py f4533f37e2787ce9d73cba3dbf557cfb2c58a8471311bb98bbe2d1c94fead97d
verify_agent.py     6dce55331e40e0dd6c73d2116b73bfddc05cafb25088058496e4f7a7f5874716
```

本次只追加本文，未改源码、测试或原审阅；未执行模型、策略程序、新 cohort 或全套回归。两个原反例的关闭不扩大为全仓穷举证明；正在运行的同一冻结版 macOS/Linux 全套结果由主流程另行记录，本补记不代领该结果。
