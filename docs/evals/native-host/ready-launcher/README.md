# 短 READY 入口

真实headless v2的parent简报正确，T1却始终没有原样执行长READY命令：相同nonce需在一条嵌套命令中复制两次，worker改写缺字后持续猜语法。该批128次工具结果报错、没有READY，原失败保留在[v2独立复核](../claude-haha/w5-headless-v2-independent-review.md)。实际hook解释器与prepare一致，不将别名风险冒充本次根因。

现在prepare为Claude ticket原子生成`ready-ID.sh`，脚本内保留原owned wrapper、nonce、解释器、截止和取消逻辑。worker的首命令只需复制`bash <脚本路径>`；hook在绑定agent前核对脚本SHA，缺失、改写或symlink替换均拒绝。prepare幂等复用相同字节，不因重试生成新预算。原ready/owned命令和Work/Codex简报兼容。新ticket固定prepare时的解释器，避免后续读取入口重建不同命令；旧记录不回填。

四项定向检查实际经过hook子进程，并执行原launcher/owned命令：正常绑定与READY、旧入口、幂等和原截止；三种launcher破坏在绑定前拒绝。解释器替换是受控构造器测试，不是实际失败归因。[工具回执](targeted-tool-receipt.json)明确标记转录边界，[源码清单](manifest.json)与前后文件/patch保留精确字节。

[真实双worker验证](../claude-haha/launcher-fence-native/README.md)随后通过短启动、越界Write拒绝、合法产物、原生完成以及父级独立验证/采用。这是接入路径验证，不是旧auditlog任务的速度对照或3+3净收益试验。
