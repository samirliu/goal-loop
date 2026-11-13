# 真实交付成本与学习增量：2026-11-13

本轮保留默认基线，不启用新学习策略。两类串行任务的主要六位置均合格，裸宿主平均墙钟成本约 215 秒／交付，冻结当前版约 264 秒，精简展示版约 316 秒；没有观察到完整交付率提高或净节省。`--brief` 只保留为可选诊断，撤回其默认推荐。小样本不支持跨任务、跨宿主或费用收益结论。

开始时分支为 main，HEAD 与 origin/main 均为 `accbe9a52627a08e4e83f558a76be81ba3167a59`。已从真实 Actions API 核对该提交的 macOS、Ubuntu 完整成功，而不是依赖历史回执。既有 `.archify`、缓存、用户文档、旧失败和未跟踪的 accbe9a 验收材料保留；未合并、发布、安装、修改全局配置或权限。

| 已知证据 | 尚未证明 | 最小干预 | 可推翻结论的验收 |
| --- | --- | --- | --- |
| accbe9a 双平台完整通过；旧真实四次属于旧版 | 当前额外编排的价值 | A：真正裸宿主与冻结当前版 | 相同业务验收、预算和正常终报；goal-loop 另负担原 audit/Gate |
| 旧离线流程 7.455→7.543 秒，地图输出增大 | 精简展示是否降低合格交付成本 | B：同一冻结当前版与只精简展示的版本 | 两例均不丢交付且每次合格交付墙钟至少节省 20% |
| 旧串行 copy 规则重复基线 | 新规则是否改变实际动作 | C：最多筛选一条未变化阶段的地图复用规则 | 实际动作差异、合格消费、留出及计入研究成本后的正节省 |

## 冻结与分组

[主要协议](protocol.json) 的 SHA256 是 `1a1c9e5675d3a010302b380c55ed4b21032daeaa9f7c54b156bcb5a99b9753bd`。开发实例为 small/131101，留出实例为 medium/131102；先冻结任务、独立 grader、源码、顺序、假设、门槛和停止条件。顺序是 small 的 bare→current→candidate，medium 的 candidate→current→bare。B 共享 A 的两个 current 控制位置，不把共享位置当成独立重复样本。

bare 是原生宿主串行执行，完全没有加载 goal-loop，也不承担契约、账本、收账或 Gate。current 是 accbe9a 的真实源码快照。candidate 只改变地图展示及其推荐入口。旧 `evaluate_entry.py` 的 before/after 两侧都会加载 goal-loop，已在入口和独立复核器中明确标为历史 B；没有把旧 before 改名为裸宿主。新 `devtools/evaluate_delivery.py` 只准备和收集原生试验，不创建模型客户端。

每个位置由实际 `collaboration.spawn_agent(fork_turns="none")` 启动，全新上下文；模型 `gpt-6.1-sol`、effort `max`、工具目录和宿主权限固定。每位置最多 360 秒，从复制初始工作区之前起表，330 秒执行和正常终报，30 秒独立验收。位置串行，无内部 worker。评测 worker 本身的启动、规划、工具、实施、收账和验收时间计入整位置成本；“内部 worker=0”不表示这个原生 worker 免费。

共同成功条件为同一冻结业务 grader 通过、输入不变、原预算内有正常非空终报；goal-loop 还须原 audit 与 Gate 实际通过。检查计数和工作勾选不授予合格。独立重放只复核字节和判定，不能补救原预算内缺失的终报或验收。隐藏 grader、其他位置、答案和调优讨论没有进入冻结简报；实际业务输入的字节与模式和原始收集时一致。原生参数中的 message 在宿主日志里加密保存，因此 [启动审计](native-launch-audit.json) 将传输明文字节相等性记为 unknown，没有冒称能从密文独立恢复；fork=none、实际模型、effort、权限、工具目录及产物身份可核实。主要六位置没有启动失败、超时、取消或补跑；最终位置 8 的独立验收截止失败单列。

## 主要六位置

| 位置 | 实例 | 组 | 合格／正常终报 | 全位置秒 | 显式协议阅读调用 |
| --- | --- | --- | --- | ---: | ---: |
| 1 | small | bare | 是／是 | 186.368 | 0 |
| 2 | small | current | 是／是 | 223.277 | 2 |
| 3 | small | candidate | 是／是 | 313.759 | 2 |
| 4 | medium | candidate | 是／是 | 319.159 | 2 |
| 5 | medium | current | 是／是 | 304.182 | 3 |
| 6 | medium | bare | 是／是 | 244.163 | 0 |

| 组 | 尝试 | 合格 | 正常终报 | 失败／超时 | 全部尝试秒／合格交付 | 显式协议阅读 | 人工输入 | tokens／费用／服务端计算 |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- |
| bare | 2 | 2 | 2 | 0／0 | 215.266 | 0 | 0 | unknown |
| current | 2 | 2 | 2 | 0／0 | 263.729 | 5 | 0 | unknown |
| candidate | 2 | 2 | 2 | 0／0 | 316.459 | 4 | 0 | unknown |

两例中 current 相对 bare 观察到的墙钟分别增加约 19.8%、24.6%；candidate 相对 current 分别增加约 40.5%、4.9%。这些是观察差异，不把服务延迟或控制器观测延迟归因给展示代码。每组仅两个实例，不能估计总体效应；中位数等于本表均值，按 nearest-rank 取的样本 p90 分别是 244.163、304.182、319.159 秒，并非总体尾延迟估计。

原生工具调用共 bare 9、current 34、candidate 21；工具更少没有带来本轮可证的端到端节省。[独立轨迹统计](native-trace.json) 保存首次实际工具时间、worker 可观察窗口、模型可见工具结果字节及逐调用明细；首次工具不是首 token 或 first-valid。冻结 verifier 的粗计数会把同批 `cat work-plan && bash goal_ctl context` 误计为查找，原数保留在原报告。最终表使用 [measure_trace.py](measure_trace.py) 经正负命令校准后的显式协议读／搜索与 `--help` 调用；变量绑定动作另列供复核。该事后诊断不改变资格、原耗时或预注册主指标。

## 必要实现、反例与最终版本

`goal_context.py` 增加纯展示函数：可选隐藏内部 binding 哈希和重复 sources，执行前仍在原锁内编译完整绑定。actions、revision、缺失字段来源和恢复后的精确提交值保持可见。原 Gate、预算、账本、恢复、策略及晋升阈值未改。

相同离线状态的完整地图 8,939 字节、精简地图 6,052 字节，减少 32.3%；revision、动作、缺失判断相同，见 [context-size.json](context-size.json)。这只证明展示变化。实现初稿去掉提交 values 后，原恢复断言实际失败，已恢复该字段；完整失败日志 [context-after.log](context-after.log) 保留。最终两种展示的 19 项生命周期检查覆盖空入口、单交付、原生地图、伪造检查数、改产物／请求／证据、原提交前后中断、历史重放、到期和更短继承截止。

离线还发现 macOS Bash 3 在 `set -u` 下展开空参数数组报错。已保留 [原失败](bash-array-before.log) 和 [修复结果](bash-array-after.log)；最小修复让参数数组始终包含原来的 `show PROJECT`，没有改权限或验收。[最终源码清单](final-source-manifest.json) 对应冻结测试目录与当前代码字节。相关回归为地图 19、评测器 7、学习主路径 19、策略切换 13 和原预算检查；早期失败和各版本日志不覆盖。

发现兼容反例时，已冻结的六位置继续沿用原字节，未中途替换。预先保存 [剩余位置计划](reserved-validation-plan.json)，再冻结 [最终源码验证协议](protocol-final-validation.json)：全局位置 7、8 只验证修复兼容性且保留原默认推荐的最终源码，同输入再验证不当作新的独立留出或效率样本；总位置仍最多 8，没有第九次。其结果与前六位置分开记账，见最终源码复核回执。

| 最终验证位置 | 实例 | 原预算内合格 | 正常终报 | 全部观察成本秒 | 原预算内独立检查 |
| --- | --- | --- | --- | ---: | --- |
| 7 | small | 是 | 是 | 299.363 | 业务、audit、Gate 全部 0 |
| 8 | medium | 否 | 是 | 381.187 | 收集时截止已过，三项均未执行 |

最终源码验证 **1/2 合格、2/2 正常终报**，一个独立验收截止失败，无模型超时或取消。位置 8 的 worker 在 326.122 秒完成正常终报和内部新鲜 audit/Gate；控制器直到 381.187 秒才完成收集，错过 360 秒截止。没有在原截止后执行原位置的独立检查，也没有补跑；21.187 秒的超限观察成本仍完整计入，不截断成零。事后业务／audit／Gate 均通过，也不能补成原合格。失败及成本见 [原始偏差记录](position-8-deviation.json)、[最终验证复核](final-validation-verified.json)。最终验证全部尝试成本 680.549 秒／1 次合格交付；此数不混入原 A/B 收益。所有真实 worker 的 completed 终态已核实，服务端 compute 仍未知。

## 学习决定与成本

唯一筛选候选为“未变化阶段复用地图、避免读实现重建协议”。触发是位置 2 的协议和地图成本；实际轨迹在 `05:17:56.884Z`、`05:18:34.338Z`、`05:18:46.345Z` 已消费缓存地图，没有实现源码查找。在已审查条件下没有新增动作；任何绑定变化后的省略刷新会违反 BIND。因此在生成策略程序或占用 C 效用位置前拒绝，保留基线，详见 [learning-screen.json](learning-screen.json)。

新候选消费版本为 null，开发／留出／启用后效用任务均为 0；没有把只打印建议或受控遥测算作消费，也没有新建策略状态、重置历史失败或统计预算。旧 two-copy 串行家族及其失败、撤回和 evaluations 历史保持原样。原有不适用、留出退化、版本变化、切换中断与撤回后旧计划拒绝的 19+13 项机制回归另列，不能加入真实学习收益。

研究成本分为提案与检查、工具及离线修复、开发位置 1–3、留出位置 4–6、最终源码验证 7–8、收集与独立重放、CI。[CI 前成本账](research-costs-before-ci.json) 中，原开发位置共 723.403 秒，原留出共 867.504 秒，最终验证共 680.549 秒，全部八次观察成本合计 2,271.457 秒。开始记录之前的检查时间、提案模型时间、tokens、费用和服务端计算为 unknown；研究总墙钟包含 worker 与控制器重叠窗口，不能重复相加当作账单。筛选脚本的约 0.001 秒只是严格下界，绝不是全部研究成本。CI 运行成本补在同提交验收回执。后续启用策略的真实合格任务为 0，可证正节省没有建立，所以 `研究及验证总成本 / 每个后续合格任务正节省` 的分母未建立，回本次数 unknown。

## 原始材料与复核

归档包含两个冻结协议、全部八个原始位置的工具调用／结果、错误、终报、产物、账本、时间戳、真实宿主回执和工具源码。过滤器只保存允许的工具与最终消息，不复制 reasoning 或凭据；原生账单和不可观察服务端计算保持 unknown。Git 已有的 accbe9a 源码不重复塞入大包，按固定提交与明确 overlay 重建；每份源码随后逐字节及模式对照原协议。

```sh
python3 docs/evals/delivery-value-20261113/restore.py /tmp/goal-delivery-restored
python3 /tmp/goal-delivery-restored/native/frozen/verify_delivery.py /tmp/goal-delivery-restored/native
python3 /tmp/goal-delivery-restored/validation/frozen/verify_delivery.py /tmp/goal-delivery-restored/validation
```

独立重放产生的新 runtime spans 在 [runtime-classification.json](runtime-classification.json) 标为 posthoc，不计入原位置成本；所有原始已收集文件的字节保持不变。恢复和重放不调用模型，不重放原 worker，不覆盖失败。[归档清单与摘要](archive.json) 记录完整性入口。

最终 macOS、Ubuntu 完整 CI 必须由最终相同 HEAD 的实际 Actions 结果确认。提交后生成的 `verification-<HEAD>/receipt.json`、原始两平台日志和 run/headSha 是最终证据；缺回执不算通过。本轮到上述范围结束，旧 36 次对照与 P2 均未恢复。
