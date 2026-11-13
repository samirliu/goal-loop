# 本轮证据与独立重放

本轮实现说明见 [deepening-execution.md](../../deepening-execution.md)，机器交付回执见 [delivery-receipt.json](delivery-receipt.json)。
本目录只记录新目标；旧36次对照没有恢复。本轮最多四次新任务调用，已全部用完并停止。

## 首先核对的结果

- 最终macOS完整277项通过；Linux完整275项无失败、2项实际能力skip，后续最终学习/地图18项delta通过。源码不同的完整结果不混用。
- 原始四次真实调用：before2/2、after1/2通过。第三位置产物42/42但没有契约/收账，Gate4，CLI超时124，保留失败。
- 修复首次无契约入口后只有本地生产路径与完整回归证据，没有第五次模型调用。整体提速、跨任务收益及优于裸 `/goal` 均未证明。
- 示例实际消费归档策略并撤回；晋升trial遥测受控，只证明机制。实际tokens/费用null，SDK估算单列。

## 归档与版本

每个tar包含 `ARCHIVE-MANIFEST.json`：有效载荷路径、sha256、字节、模式和原mtime。
tar成员统一所有者/mtime；校验文件内容和模式，原mtime只作为来源记录。
[archive-index.json](archive-index.json) 记录六个tar的SHA256；[archive-member-verification.json](archive-member-verification.json) 记录1253个有效载荷的逐项核对结果。
[SHA256SUMS](SHA256SUMS) 覆盖本目录最终交付文件，自身不递归哈希。

| 归档 | 内容与用途 |
| --- | --- |
| [source-before82.tar.xz](source-before82.tar.xz) | 本轮开始的82份源码及来源清单；复现旧前驱失效/外部客户端入口 |
| [source-context-before-fix.tar.xz](source-context-before-fix.tar.xz) | 早期148份源码及清单；复现上下文借锁误批准 |
| [source-matrix149.tar.xz](source-matrix149.tar.xz) | 核心149份源码及清单；macOS/Linux完整275及两平台其他检查对应此版 |
| [source-final149.tar.xz](source-final149.tar.xz) | 最终bootstrap修复149份源码及清单；macOS完整277、Linux最终18项对应此版 |
| [mechanism-run.tar.xz](mechanism-run.tar.xz) | 可运行示例的实际项目、坏单元、局部修复、归档程序、晋升/撤回、audit/Gate与消融回执 |
| [native-four.tar.xz](native-four.tar.xz) | 四次真实试验冻结源码、任务、检查器、预注册、driver、全部SDK事件、结果和工作区；posthoc运行span另存 |

源码清单的149是**源码条目数**，tar另有来源清单与归档清单。before82不是完整回归发行包，只用于所述负例。
最新工作区相对最终149源码仅有开发工具权限参数增量；见 [source-check.json](source-check.json) 和 [补丁](developer-permission-delta.patch)。
补丁把开发工具默认改为保留宿主权限；原四次预注册与命令仍保留当时用户已授权的bypassPermissions。
最终文档和本目录测量/核对材料不在149份源码清单内，不追认完整277项。

## 不调用模型的独立重放

从仓库根目录执行。只需现有Python3、bash、gawk等项目依赖；不需要claude-haha或模型账户，不运行 `evaluate_entry.py`。

```sh
EVIDENCE_DIR="$PWD/docs/evals/learning-edge-20261113"
REPLAY_DIR=$(mktemp -d /tmp/goal-evidence-replay.XXXXXX)
cd "$EVIDENCE_DIR"
shasum -a 256 -c SHA256SUMS
cd -
tar -xJf "$EVIDENCE_DIR/source-before82.tar.xz" -C "$REPLAY_DIR"
tar -xJf "$EVIDENCE_DIR/source-context-before-fix.tar.xz" -C "$REPLAY_DIR"
tar -xJf "$EVIDENCE_DIR/source-final149.tar.xz" -C "$REPLAY_DIR"
tar -xJf "$EVIDENCE_DIR/native-four.tar.xz" -C "$REPLAY_DIR"

python3 -B "$REPLAY_DIR/source-final/devtools/replay_learning.py" \
  --baseline "$REPLAY_DIR/source-before" \
  --context-before "$REPLAY_DIR/source-context-before" \
  --current "$REPLAY_DIR/source-final" --output "$REPLAY_DIR/counterexamples.json"
python3 -B "$REPLAY_DIR/source-final/devtools/verify_entry.py" \
  "$REPLAY_DIR/native/trials" --output "$REPLAY_DIR/native-verified.json"
python3 -B "$EVIDENCE_DIR/measure_native_trace.py" \
  "$REPLAY_DIR/native/trials" --output "$REPLAY_DIR/trace-metrics.json"
```

六个tar根下的同名 `ARCHIVE-MANIFEST.json` 会在连续解包时被后一个替换；每包内部清单仍可直接用 `tar -xOf ARCHIVE ARCHIVE-MANIFEST.json` 查看。
源码各自的 `SOURCE-MANIFEST.json`/基线 `manifest.json` 不重名。解包目录只供复核，未写回原现场。

已经在全新目录实际执行以上关键重放：[counterexamples-portable.json](counterexamples-portable.json) 为verified=true；
[native-portable-replay.json](native-portable-replay.json) 为verified=true、accepted=3、normal_deliveries=3。
独立脚本重新运行冻结grader和对应版本的原audit/Gate，不调用模型。复核产生新运行span属于posthoc，不是原生调用成本。
正常及优化解释器复核分别见 [native-independent.json](native-independent.json)、[native-independent-optimized.json](native-independent-optimized.json)。
四个验收器变异的正反检查见 [verifier-mutants.json](verifier-mutants.json) 和 [-O结果](verifier-mutants-optimized.json)，测试脚本为 [verify_entry_mutants.py](verify_entry_mutants.py)。

## 原始日志索引

| 范围 | 文件 |
| --- | --- |
| 最终macOS完整277 | [mac-full-final-277.log](mac-full-final-277.log)、[final-source-manifest.json](final-source-manifest.json) |
| 核心macOS275、阶段276 | [mac-full-4-green.log](mac-full-4-green.log)、[mac-full-5-green.log](mac-full-5-green.log) |
| 核心Linux275完整与其他检查 | [linux-matrix-275/result.txt](linux-matrix-275/result.txt)、[python.txt](linux-matrix-275/python.txt)、同目录shell/parser/forge/docs/shellcheck/environment |
| Linux阶段17、最终18 | [linux-phase-17/tests.log](linux-phase-17/tests.log)、[linux-bootstrap-18/tests.log](linux-bootstrap-18/tests.log) |
| shell/parser/forge及最终docs | [shell-final-603.log](shell-final-603.log)、[parser-78.log](parser-78.log)、[forge-10.log](forge-10.log)、[docs-delivery.log](docs-delivery.log)；交付增量的命令与哈希见 [delivery-checks.json](delivery-checks.json) |
| 第一轮Linux缺夹具及补齐后273 | [linux-first-missing-fixtures/](linux-first-missing-fixtures/)、[linux-complete-273/](linux-complete-273/) |
| macOS完整失败，不能用单跑抹去 | [mac-full-1.log](mac-full-1.log)、[mac-full-2.log](mac-full-2.log)、[mac-full-3.log](mac-full-3.log) |
| 借锁、首入口、启动延迟旧反例 | [borrowed-lock-before.log](borrowed-lock-before.log)、[bootstrap-before.log](bootstrap-before.log)、[startup-before.log](startup-before.log) |
| Gate预算/入口预算修复 | [gate-budget-fixed.log](gate-budget-fixed.log)、[entry-budget-fixed.log](entry-budget-fixed.log)；原4.2秒阈值不变 |
| 示例结果、策略版本与消融 | [example-result.json](example-result.json)、mechanism-run归档内result/receipt/ablation及原wave/policy文件 |
| 工具、协议查找、重复Read、SDK估算 | [native-trace-metrics.json](native-trace-metrics.json)，定义和提取脚本一并保留 |
| 原生窗口与posthoc分离 | [native-runtime-classification.json](native-runtime-classification.json)，按span起点是否晚于该位置原记录收尾时间划分 |

真实工具结果正文仅留哈希，思考文本不保存，不能声称逐字核对缺失内容。
“Read重复”不包括Bash源码读取；没有原生Agent调用不能推出所有规划/协调开销为0。
同一任务族的两个种子仅为描述性观察；历史48次工具/161秒不加入同期基线，不追加试验凑优势。
