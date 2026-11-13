# auditlog medium：原规范的确定性覆盖补齐

只修改 `examples/agent-evals/grade.py` 的 medium 覆盖，保留原21项并新增7项，总计28项。原 TASK、其他任务 family、runtime、roles和SKILL均未改。以下盲点由实际单缺陷 mutant 校准：旧 grader 对五者都给21/21，新独立 probe 和修后 grader 则拒绝对应缺陷。

| 原始 TASK（tasks.py） | 旧遗漏 | 补充检查 |
| --- | --- | --- |
| 25：missing input exit2 | 所有旧CLI输入均存在 | 不存在的输入必须exit2 |
| 23：stderr指明物理行 | 只检查包含字符3，坏行固定第3行 | 第13物理行无效，匹配独立数字13并保留既有输出 |
| 16–18：原integer amount，bool无效 | 只用小整数且用`==`，float可误过 | 小整数与`2**53+1`的原值和`int`类型；false也须ValueError |
| 19–20：iterable和完整统计 | 只测list iterator及小整数 | generator含大整数的精确key/count/total/min/max |
| 20/22/24：skip后仍完整分组 | skip分支只核length/count | 两条坏行、多组有效行，核完整五字段和skipped=2 |
| 21：UTF-8 JSONL | json.dumps默认将Unicode转为ASCII转义 | 真正字面UTF-8中文输入及完整输出 |

没有新增 medium 的“输入不变”要求；该项不在原 TASK 中。原本已经传入`iter(rows)`，所以不把 iterable 描述为完全没测。原子发布仍有明确限制：旧/新增 strict failure检查证明无效输入时保留原输出，未证明发布中I/O失败或并发可见性。没有钉死`os.replace`、fsync、权限或symlink等未承诺机制，也没有添加时序脆弱的CI检查。

[新增自包含测试源码](test_medium_grader.py.txt)生成标准库正确control和五个单缺陷mutant，每次经独立grader CLI进程导入，避免`sys.modules`串样。[before](before-targeted.log)在旧grader下保留control21/21、五bad均被误接受，产生5个预期失败；只换grader后，[after](after-targeted.log)为control28/28、五bad各由对应新检查拒绝，**2 passed、5 subtests passed（1.71s）**。七个新增检查没有替换或删除原21项；原名称和顺序保持为结果前缀。

[原归档校准包](calibration-before.tar.xz)另保留真实single-1基线、五个单缺陷patch、旧21项全部误接受的完整CLI输出、新独立probe拒绝与六份原artifact的42/42 posthoc结果。该校准的原始冻结453文件在前后inventory中完全相同。它与自包含测试分别记录，不冒充真实模型产生了mutant。

用修后grader仅在`/tmp`复制六个冻结v3 artifact做[离线复验](posthoc-six.tar.xz)，六者均 **28/28**，命令完整输出见[posthoc-six.log](posthoc-six.log)。原artifact、archive、原21项成绩和原实测时长均不回写；额外检查成本不回填为原W5成本，也不替换其预注册分母。这些是posthoc质量覆盖材料，不是新模型/效用试验。

[精确补丁](implementation.patch)、[修前grader](before-grade.py.txt)、[修后grader](after-grade.py.txt)与[范围摘要](summary.json)保存版本边界。grader SHA从 `59cf1124…b15a19` 到 `cb4b97f2db0450f2f21eda5bd9d8e8478931d5e7d3394915666130712c22730d`；新增测试SHA为 `6381ef5802a80bbfec70a67f2d4b40ae5e3ca163834e2ca0a428d9acb2b17902`。small/optimization/recovery的AST分支未变，原TASK hash未变。

[139文件完整矩阵](../regression-closed-20261112/README.md)继续对应冻结版及旧grader，不称这些最新eval字节已跑全套；本增量只有上述定向测试和离线复验。没有运行full、模型或网络。日志是工具返回内容的完整保存，加command/exit标记，未伪称独立重定向日志。[archive-index.json](archive-index.json)、`manifest.json`、`SHA256SUMS`及两个tar内层清单保存hash/bytes/mode，压缩后逐项核验。
