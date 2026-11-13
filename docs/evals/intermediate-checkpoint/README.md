# 中间检查点与失败测量

生产测试用一个仍有待办和未达 dry 上限的 forge 任务，保存已
通过地板、水位、horizon 和校准的中间产物。修改候选后恢复
原文件，重新资格检查得到 `CHECKPOINT-OK`，最终 `--check` 仍
报告 `not-claimed`。缺少 horizon 裁决、评估器没有正确校准、
裁决为 `UNVERIFIABLE`、机械地板失败和预算耗尽都拒绝保存。

数值检查原先会接纳失败或超时前打印的数字，以及 `1.2.3`
这类格式。修复后这些输入返回 `BROKEN`。单独跑目标测量时，
控制器需要验证整个批次成功并读取 PASS 行，避免错误 stderr
中的 `observed=` 文本写入水位。

在旧实现上运行同样的测试，复现了[缺少中间检查点](checkpoint-before.txt)、
[失败测量被接纳](measurement-before.txt)和[错误水位](water-mark-before.txt)。
从 [W5 的基线提交](../crew-cost/manifest.json)依次应用 W5、
[检查点](../incumbent/implementation.patch)、
[配对试验](../checkpoint-evolution/implementation.patch)及[本次补丁](implementation.patch)，
可重建被测源码。重跑命令如下。

```bash
python3 -B tests/test_incumbent.py -v
bash tests/run_tests.sh --only 160
```

重建目录结果见[检查点复验](checkpoint-replay.txt)和[测量复验](measurement-replay.txt)。
