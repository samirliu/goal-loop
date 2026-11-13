# 协议减负与真实交付对照，2026-11-13

**优化目标未达成，默认保留基线流程。** 18 个真实位置已用完，无补跑。A 裸宿主、B 冻结基线、C 可选精简路径均为 **3/6 合格交付**。C 单位合格交付成本为 **1,048.38 秒**，比更优参考 A 的 974.73 秒高 **7.56%**；比 B 低 0.86%。没有达到多交付两个任务或降成本 20% 的预注册门槛，也没有满足跨类别收益要求。

候选机械路径保留为明确选择的实验选项，未推广为默认。实验完成不代表提效目标完成。费用和回本任务数均未建立。原始目标可复制自 [goal-prompt.txt](goal-prompt.txt)，下一轮须使用新的未见实例与预算，不能把本轮失败补跑成通过。

## 冻结与公平条件

- B：`cc26e0b4d8e847d7bc64fd4ce3f09159ab5724cb`；C 生产源码与收集器：`76140262bab69f6e31c032cb1c2dd760a1bd3a3a`。
- 生产源码在任务细节释放前冻结；此后 53 个安装文件无漂移。完整身份见 [candidate-production-manifest.json](candidate-production-manifest.json)、[final-source-native-audit.json](final-source-native-audit.json)。
- 先冻结 [protocol.json](protocol.json)、[freeze.json](freeze.json) 中的源码、验收器、顺序、标准和 18 份位置清单，再执行模型。开发使用已有轨迹与专用反例，六个留出实例未用于改动调优。
- 18 个全新原生上下文，实际均为 `gpt-6.1-sol`、`effort=max`、`approval=never`、`danger-full-access`，CLI `0.167.2`。不另设模型客户端、宿主、服务或队列。
- 每位置从准备起最多 900 秒，模型及其工具、原生 worker、正常非空终报和真实终态须在 780 秒内完成，至少保留 120 秒独立验收。默认串行；三组允许相同的至多两个内部原生 worker，本轮实际均未使用内部 worker。
- A 无 goal-loop 专属手续；B 使用普通手工收账模板；C 明确选用自动检查数和收账回执。A/C 比较产品流程，B/C 比较代码加显式选择的流程，不能把差异都归因于代码本身。

共同合格条件是冻结的独立业务验收通过、正常终报与真实原生终态均在原执行期限内、整个报告在原 900 秒内；B/C 还须通过原 audit/Gate。独立验收使用可信上游与负例测试，替换提交者的测试文件，不按补丁相似度打分。所有失败照计成本。

## 完整结果

主指标为 **全部尝试墙钟之和 ÷ 合格交付数**，包含准备、失败、检查、收尾和报告。零交付类别的该指标是 undefined，不能写成零。

| 组 | 合格交付 | 全部位置秒数 | 秒/合格交付 | 原生执行 worker 秒 |
| --- | ---: | ---: | ---: | ---: |
| A 裸宿主 | 3/6 | 2,924.19 | 974.73 | 2,686.92 |
| B 冻结基线 | 3/6 | 3,172.41 | 1,057.47 | 2,999.68 |
| C 可选精简 | 3/6 | 3,145.14 | 1,048.38 | 2,892.19 |

六个真实上游需求与全部位置如下。单元格为“位置：结果，全部耗时秒”，不是仅统计成功任务的速度。

| 任务与来源 | A | B | C |
| --- | --- | --- | --- |
| hc01 跨模块异步策略，[tenacity #451](https://github.com/jd/tenacity/pull/451) | 1：通过，609.39 | 2：通过，664.25 | 3：通过，653.88 |
| hc02 线格式重命名联合判别，[cattrs #778](https://github.com/python-attrs/cattrs/pull/778) | 6：通过，500.89 | 4：通过，403.04 | 5：通过，334.86 |
| hc03 flag/env/default 兼容行为，[click #2956](https://github.com/pallets/click/pull/2956) | 8：失败，621.55 | 9：失败，588.85 | 7：失败，668.78 |
| hc04 kw_only 继承兼容性，[attrs #1457](https://github.com/python-attrs/attrs/pull/1457) | 12：失败，493.06 | 11：失败，600.12 | 10：失败，476.32 |
| hc05 multipart 分段集成，[werkzeug #3081](https://github.com/pallets/werkzeug/pull/3081) | 14：失败，435.78 | 13：失败，515.64 | 15：失败，580.45 |
| hc06 stale ID 存储与恢复，[tinydb #616](https://github.com/msiemens/tinydb/pull/616) | 16：通过，263.52 | 18：通过，400.52 | 17：通过，430.84 |

| 类别 | A 合格、秒/合格 | B 合格、秒/合格 | C 合格、秒/合格 | C 对更优参考 |
| --- | --- | --- | --- | --- |
| 跨模块行为修复 | 2/2，555.14 | 2/2，533.64 | 2/2，494.37 | 低 7.36%，一个类别受益 |
| 接口、兼容性与迁移 | 0/2，undefined | 0/2，undefined | 0/2，undefined | 无交付，无法证明无退化 |
| 集成与失败恢复 | 1/2，699.30 | 1/2，916.16 | 1/2，1,011.29 | 高 44.61%，超过 10% 护栏 |

C 耗时比 A 低 2/6、比 B 低 3/6；合格方向没有改善。只有一个类别受益。[summary.json](summary.json) 保留未舍入值、所有失败原因、每个位置的检查和原生身份；`adopt=false`、`net_goal_achieved=false`。

18 个位置均正常终报、真实终态与报告按时，没有本轮启动失败、超时或收集逾期。9 个不合格位置全部是业务验收失败：Click 的默认值/激活/空白环境变量组合，attrs 的继承和兼容行为，Werkzeug 的边界前缀分段组合。attrs 的可信上游套件还包含内部辅助函数参数约定；同时三组确实都遗漏了公开需求中的继承行为，不能把全部失败归为内部实现耦合。原外部收集器在业务失败后不再运行 audit/Gate，因此这些位置的外部 audit/Gate 为未运行，不能写成通过；worker 自己的 GO 也不能替代业务验收。

## 实际减少的模型工作

已有小样本轨迹显示基线工具与协议读取增加，收账还要手填三个检查数、单独取得最终回执。但这些轨迹不能精确分离协议推理时间，也不能证明收账是最大的墙钟来源；本次选择一个可验证的机械边界。

候选只增加可选的 `close-iteration --checks-from-verify --receipt` 及版本绑定的 `measured_template`：

1. 在原 pending 事务内消费原 close 已运行的实际验证输出，严格检查完整性与退出码，再派生 pass/fail/unverifiable。
2. 由原收账路径提交后立即执行原 receipt，省去模型重复抄三个计数字段和一次独立收尾交接。
3. 只支持确定性的 `exit=N` 检查；混合手填计数、缺证据、输出不完整等拒绝或保留 pending。原 exact-intent 重试、预算、恢复、账本、版本绑定和 audit/Gate 继续生效。

进展、退出判断、实际对抗复审和复审说明仍须由模型完成，不派生 clear、worker 终态或 GO。六次 C 的实际 proposal 全部请求 `checks_source=verify` 与 `receipt=yes`，没有手填三个计数字段，也全部保留判断与复审字段，见 [all-candidate-settlement-consumption.json](all-candidate-settlement-consumption.json)。

修改前真实 CLI 对该参数返回 4，见 [measured-close-before.log](measured-close-before.log)；修改后 9 个新回归通过，原 19 个 context 测试通过。首任务 B/C 工具调用为 29/19，但耗时仅 664.25/653.88 秒，调用差异还包含业务策略差异，不能把全部 10 次差异归为本功能，更不能据此宣称净收益。

## 收集缺口先修复

旧位置曾在 326.122 秒正常终报，控制器到 381.187 秒才收集，超过原 360 秒；历史失败保留。本轮先增加单个有界本地收集进程，在准备前启动，持续消费真实原生日志，核对实际身份、设置、全部后代终态与非空 final，直接启动冻结的独立验收和原 audit/Gate，不依赖父模型及时进入下一轮。

第一位置真实终态后约 1.546 秒自动开始独立验收，原期限内完成。见 [automatic-collection-first-proof.json](automatic-collection-first-proof.json)。22 个机制测试覆盖晚到/伪造终态、活动后代、身份漂移、原缺口重放与取消预算，另有 14 个 supervisor、7 个已有交付测试。它解决的是采集可靠性，不能代替业务交付收益。

## 全成本与回本

原生 host 暴露了数值 token 计数，已按原日志前缀 SHA 绑定补录；原资格与耗时报告未改。最初报告里的 `tokens=null` 是收集器当时没有采集，不是零，补录在 [usage/](usage/)、[capture_usage.py](capture_usage.py)。

| 组 | input（含缓存） | cached input | output | total |
| --- | ---: | ---: | ---: | ---: |
| A | 4,642,243 | 4,408,064 | 90,670 | 4,732,913 |
| B | 8,988,488 | 8,630,912 | 113,121 | 9,101,609 |
| C | 6,329,713 | 5,968,384 | 109,308 | 6,439,021 |

缓存计入 input；reasoning 可能已计入 output，不能重复相加。缓存命中差异显著，token 总数不等于费用，C 的各类计数也并非统一更低。未获得账单价格、服务计算和停止计费信息，全部为 unknown。

- 研究/工具修改：有界收集器 worker 1,260.243 秒，2,512,109 个报告 total token；其中已含工具开发，不能再加一次。
- 留出准备：任务 curator 两轮完整原生跨度合计 1,653.113 秒，9,124,452 个报告 total token。准备过程中失败、坏源/金标筛选、公共与私有检查、适配器 r1 修正记录均保留；89 个准备验收尝试不冒充真实编码位置。
- 核心开发：父模型与研究、工具审查、开发重叠，无法可靠独立拆分墙钟或 token；相关字段明确为 unknown。已知新回归 47.637 秒、原 context 回归 122.052 秒属于该阶段，不能再当不重叠总成本。
- 留出执行：全部位置 9,241.735 秒；从首位置准备到最后报告 10,246.794 秒，位置间编排另占 1,005.059 秒。父编排成本没有塞进单个 solver 的得分，也没有从总研究成本中省略。
- 父模型截至补录截点报告 total token 67,435,701，其中 input 67,136,733、cached input 66,864,768、output 298,968；这是含大量重复缓存的 SDK 计数，**不是**原生 goal meter 的计数或美元。按响应完成时间分阶段记在 [root-native-usage-observed.json](root-native-usage-observed.json)，阶段边界请求的精确归属和最终尾部 unknown。
- 后续：没有新增真实评测；最终归档通过/失败重放分别约 9.32/6.10 秒。整理、CI 等仍单列，最终尾部 unknown。人工业务介入 0；用户设定目标与审阅用时 unknown。

完整分项见 [cost-accounting.json](cost-accounting.json)。这些时间窗口相互重叠，不相加伪造总墙钟或账单。**回本任务数未建立**：相对更优参考没有可信正节省，不能按减少字段、调用次数或相对较差基线的 0.86% 点估计推出回本。

## 证据与独立重放

- [archives/inputs.tar.gz](archives/inputs.tar.gz)：冻结 A/B/C 输入、业务初始树、任务说明、独立 grader/validator、真实上游坏版本与金标、准备失败及验收证明。来源提交、URL 和哈希另见 [task-sources.json](task-sources.json)、[holdout-readiness.json](holdout-readiness.json)。
- `archives/position-001.tar.gz` 至 `position-018.tar.gz`：每个位置原 prompt/manifest、提交业务文件和 goal 状态、已筛选并脱敏的原生事件、原始报告、独立检查 stdout/stderr/status 与业务验收记录。原生推理文本、账户/限额数据和凭据不导出。
- [archive-manifest.json](archive-manifest.json)、[SHA256SUMS](SHA256SUMS)：最终归档身份。早先 `export-*.json` 是导出时历史回执；缓存过滤前后的映射与保留成员内容哈希见 [archive-cache-filter-revision.json](archive-cache-filter-revision.json)，原归档仍保存在本机独立临时目录。历史失败和源文件未删。
- 原收集器会脱敏键名含 password 的路径所对应的指纹值，曾导致导出器误判漂移；修正仅限导出比较，原报告未改。对应原元数据不可恢复部分标为 unknown，见 [export-redacted-metadata-counterexample.json](export-redacted-metadata-counterexample.json)。
- 数值统计实现的两次后续修正仅修复未知执行时长被算零、补读已暴露 token；冻结门槛、原报告、最终资格和主指标未改，修正回执独立保留。

在仓库根目录，使用现有 CPython 3.12 与独立目录重放业务验收：

```sh
python3 -B docs/evals/protocol-efficiency-20261113/replay.py \
  --position 1 --dest /tmp/goal-loop-replay-new-001 \
  --python312 /opt/homebrew/bin/python3.12 \
  --wheels /tmp/goal-protocol-efficiency-xpw3677q/holdout-private/wheels
```

脚本核对归档和全部 26 个 wheel 的 SHA，在新 venv 离线安装并运行冻结验收器。wheel 缓存和已安装环境不进 Git；原包仍保存在上述目录，跨机器需按 `archives/dependency-wheels.json` 和归档内 `requirements.lock` 获取同哈希包。运行环境记录为 macOS ARM、CPython 3.12.13，不宣称业务重放跨平台完全相同。

最终缓存过滤后的归档已实际重放位置 1（返回 0）和位置 7（返回 1），见 [portable-final-summary.json](portable-final-summary.json) 与各自原始日志。重放不调用模型，不重置历史期限，不把事后通过补算到原资格。第一次历史提取遇绝对 pytest 测试软链接的失败也保留；现在只提取受控运行输入，不执行历史 scratch。

生产源码完整 CI 在 `7614026` 已实际通过 macOS 与 Ubuntu：各 603 个主场景、341 个 Python 测试；macOS 无 skip，Ubuntu 仅两个原有 RLIMIT skip。原日志和回执见 [verification-7614026/](verification-7614026/)，[GitHub CI](https://github.com/samirliu/goal-loop/actions/runs/43385957103)。没有删除断言、新增 skip 或增大既有超时。最终证据提交还须通过同样的完整 CI；它自己的回执在工作区 `verification-final/`，不递归提交到被验证的同一提交。

## 结论边界

六个任务是公开历史需求，每类只有两个实例，每组每任务只有一次；留出仅相对于本轮调优，无法排除模型预训练见过。没有独立重复批次，不能宣称普遍稳定。可信本机原生日志未经签名；只验运行前后快照，无法发现中途改动后恢复；未知/不透明工具内容不当作已验证。

本轮证据支持“机械检查数和收尾交接可以在原保障下程序化”，也支持“原收集逾期缺口已得到有界流程覆盖”。它**不支持**“复杂任务更高交付率或更低净交付成本”。保留默认基线，候选不推广，真实调用按 18 次上限停止，优化目标保持未达成。
