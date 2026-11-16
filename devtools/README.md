# 固定预算的交付收益评测

`evaluate_delivery.py cohort` 冻结新的 v3 配对批次；旧 v2 回执仍由 `verify_delivery.py`
读取。工具负责准备、独立观察、验收和汇总，真实模型会话由宿主显式启动。
工具本身不创建模型客户端、不派发 agent、不安装其他宿主。

## 冻结协议

```bash
python3 -I devtools/evaluate_delivery.py cohort /ABS/new-cohort \
  --current /ABS/goal-loop --model ACTUAL_MODEL --effort ACTUAL_EFFORT \
  --seed-base 441001 --instances 3 --seconds 360 --execution-seconds 330
```

默认四类任务：区间处理、跨文件 JSONL 工具、性能优化、崩溃恢复；每类三个独立种子。
每个实例以相同输入比较普通串行执行和当前 goal-loop，共 24 次、最多 144 分钟的尝试预算。
可用 `--candidate /ABS/other-source` 加第三组；顺序按实例轮换，串行运行。
`--families small medium` 或 `--instances 1` 可做较小试跑，但未达到每类三对时不触发批次收益判定。

模型和 effort 必须显式指定，采集器逐条核对原生上下文。协议固定任务、种子、输入、评分器、
运行源码和总预算。源码按运行清单冻结，独立评测器从产品快照中排除，排除项记入协议。
失败、取消、超时和基础设施故障保留；已有批次不替换位置、不改种子重试。
连续两次未观察到原生会话的基础设施故障会阻止继续派发。旧批次与新版本分开保存。

## 单次执行与收集

从冻结后的工具启动独立采集进程，传入宿主实际规划的 agent 路径和父 thread 身份：

```bash
python3 -I /ABS/new-cohort/frozen/evaluate_delivery.py capture /ABS/new-cohort 1 \
  --agent-path /root/evaluation_001 --parent-thread ACTUAL_PARENT_THREAD
```

等待 `1/capture/ready.json` 和 `1/prompt.txt` 均出现，再通过宿主开启新的独立会话，使用
`prompt.txt` 的原文和截止。采集启动前的元数据准备、工作区复制、派发、协议读取、实现、
正常终报和独立验收共用同一截止；父会话晚返回不会延期，也不会事后补算成功。
评分器留在冻结目录，worker 只获得任务、公共检查和对应产品快照的读取范围。
这是任务范围隔离，同一用户权限不构成 OS 沙箱。

采集器复用 `native_eval_capture.py`，要求原生正常终报、真实 task terminal、独立业务检查；
goal-loop 组还要求原 audit/Gate。所有本机检查由原进程组监督器约束。
`needs-interrupt.json` 出现时，父控制器须调用宿主实际 interrupt，再保存实际终态。
本机超时或取消请求不证明服务端计算已停止。

每次还须保存宿主终态回执到 `N/host-terminal.json`，使用既有归一格式：
`agents` 数组中的 `agent_name` 匹配本次 manifest 的实际路径，`agent_status` 是实际终态。
若宿主返回的字段不同，保留原始回执和适配说明。未完成前一位置的采集与终态确认，下一位置拒绝启动。

## Token、金额与人工介入

没有完整计量时保持 `null`。只有完整尝试范围的宿主或供应商回执可导入；原生 Goal 创建后
的局部计数、成功尝试的局部费用或估算价格不能充作整个尝试成本。

```json
{
  "model": "ACTUAL_MODEL",
  "session": "ACTUAL_NATIVE_SESSION_ID",
  "tokens": null,
  "money": null,
  "currency": null,
  "source": "non-secret host/provider receipt identifier",
  "scope": "whole-attempt"
}
```

```bash
python3 -I /ABS/new-cohort/frozen/evaluate_delivery.py accounting \
  /ABS/new-cohort 1 /ABS/usage-receipt.json --human-interventions 0
```

`0` 只用于实际观察到零次介入；未观察则省略。原始计量回执另存并绑定 SHA-256，模型、
会话、范围、有限非负数值和币种均校验。来源标识不得包含密钥。混合币种不汇成一个金额。
每组输出计量覆盖率，任一尝试缺计量时，该组完整 token/金额成本保持 unknown，不按零补齐。
研究开发、任务准备及未知的服务端计算另外记录，不能重复计费或混入单次交付收益。

## 汇总与解释

```bash
python3 -I /ABS/new-cohort/frozen/verify_delivery.py /ABS/new-cohort \
  --output /ABS/new-cohort/summary.json
```

报告保留每个计划位置，并给出每组/每类任务的成功率、全部尝试耗时、每次合格交付成本，
以及逐实例配对的交付增加、损失和持平。零次合格交付时，单位交付成本无定义。
缺少任何计划位置会拒绝最终汇总，不静默缩减分母。

批次判定要求每类至少三对、原生设置已核对、没有任何配对交付损失，且全部尝试的单位合格
交付耗时降低至少 20%。该判定只描述这份固定批次，不证明统计显著、通用优势或跨任务迁移。
费用有缺口时不宣称金额收益。缺失费用和未派发配置不伪装成零成本成功。

复验重新运行独立检查，但原始资格只由原截止内的回执决定。产物与原有运行收据保持匹配；
统一状态登记表允许追加的观测目录可以新增合法收据，新增观测不改写原始成本或原始判定。
长路径等展示值被脱敏时，原命令与工作目录仍通过 SHA-256 绑定。

`--calibration` 标记合成校准批次，永远不触发真实模型收益判定。CI 中的
`test_delivery_cohort.py` 会实际运行独立采集器、业务 grader 和原 Gate，覆盖好产物、
事后变更、缺失位置、评分器替换、原失败、配对交付损失及计量缺口；这些是机制证据。
