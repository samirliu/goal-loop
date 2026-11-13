# 两个真实worker：短启动、写入拒绝与采用

本次使用用户提供的`claude-haha --permission-mode bypassPermissions`，实际MiniMax-M3.1-Flash映射。180秒从driver入口起算，显式`/goal-loop-host:goal-loop`加载当前插件入口；两个现有goal-worker在同一parent message中派发，不覆盖模型或effort。

两个worker各自先执行校验SHA的短READY脚本，再做一次预先声明的域外Write负例，随后写入自己拥有的产物并运行冻结named check。实际结果：

- 两者均READY并有结构化native完成；父级分别validate=0、adopt，最终集成quality=true。
- 两个域外Write均由PreToolUse拒绝，工具结果报错；两个forbidden文件不存在。随后合法Write各产生精确6字节`READY\n`。
- CLI退出0，无controller异常；CLI结束口径31.006秒，父级验证与final finish另有时间戳，仍在同一个180秒内。
- 原始流只有Write负例；Edit由[实际hook定向测试](../../structured-write-fence/README.md)覆盖，不称本次CLI实测Edit。T2额外重跑一次带echo的check也保留。

[96份原始材料](raw-run.tar.xz)包括driver、冻结grader、当前源码、过滤后的事件、launcher、host/crew/runtime收据和两个产物；[逐文件清单](manifest.json)与[SHA](SHA256SUMS)可重建。没有thinking或凭据环境。两次故意的Write拒绝是预注册负例，不隐藏成零工具错误。

本次验证启动、写域与生命周期；不与旧v1/v2的不同任务时间作因果比较，不补造auditlog的3+3窗口，不证明并行净收益或整个`/goal`效用优势。独立复核单独读取冻结副本，未重跑模型或grader。
