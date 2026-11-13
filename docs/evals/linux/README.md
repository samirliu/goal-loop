# Linux ARM64 完整回归

使用本机已有的 `python:3.12-slim` 镜像，在一次性容器安装 Bash、
GNU awk、Git 和 shellcheck。源码快照只读挂载，测试自行在临时目录
创建项目。实际环境为 Linux 6.12.76、aarch64、Python 3.12.14。

首轮 129 个 Python 测试通过，shell 场景 600 通过、1 失败。
失败来自 shellcheck 检出的未使用读取字段和花括号缺失，两处都已
在源码修复。[修复补丁](lint.patch)可在中间检查点版本上直接应用。

第二轮完整复验 129 个 Python 测试、601 条 shell 断言通过，
shellcheck 通过。pidfd owner 退出、owner zombie、嵌套进程组
取消、并发单写者和预算恢复测试均执行并通过，Python 没有跳过项。
原始输出、依赖版本、源码摘要和两轮结果见[清单](manifest.json)。

可以用已安装的 Docker 重新执行：

```bash
mkdir -p /tmp/goal-linux-output
docker run --rm --init \
  --mount type=bind,source="$PWD",target=/repo,readonly \
  --mount type=bind,source=/tmp/goal-linux-output,target=/out \
  --workdir /repo python:3.12-slim bash docs/evals/linux/run.sh
```

此记录覆盖上述本机容器平台。托管 CI 的 Ubuntu/macOS job 仍需用
对应提交运行。
