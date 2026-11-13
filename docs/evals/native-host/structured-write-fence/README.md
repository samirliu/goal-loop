# 已注册 worker 的结构化 Write/Edit 写围栏

真实 W5 v2 暴露了既有 FENCE 的实现缺口：worker 简报禁止 brief 外及 `.goal/` 写入，但 `goal_host.owned_shell` 对已注册 worker 的非 shell 工具直接返回。原生流保留了 `/tmp/auditlog_extra_tests.py` 的 Write/Edit；[对应身份与调用元数据](actual-w5-outside-write-metadata.json)记录原四文件 scope、agent/call ID、原 events SHA 和工具结果引用。工具结果正文仅有 hash、`is_error` 为 null，不冒称逐字复核完整响应。原 cohort 由主流程另冻，未用补丁追改其结果。

补丁只处理已有 Claude `Write`/`Edit` 的结构化 `file_path`。先保留现有活跃 ticket/agent 绑定和预算检查，再解析目标路径的实际 symlink/`..` 语义，要求其位于 canonical project root 及原始 `root/row.files` 路径或子树中，并拒绝 `.goal`。**只 resolve 目标，不 resolve scope 来扩大授权**；declared leaf 指向本项目另一个未授权文件也拒绝。合法调用返回 `{}`，继续正常宿主权限检查；deny 不改变 attempt，允许重试。没有 worker agent_id 的父控制器维持原行为。

先只安装新测试，production host 保持 `7cd29ccc…879570`。测试经实际生产 init/stamp/begin/prepare、first-tool hook 绑定与 owned READY 执行，再调用真实 hook CLI。旧 host 对指向域外的 owned leaf Write 返回 `{}`，预期 deny 缺失；`python3.12 -m pytest -q -s tests/test_host.py -k structured_leaf_symlink` 得到1 failed、15 deselected（0.86s）。[完整 before 输出](before-targeted.log)保留该具体返回与断言失败。

再应用 host 补丁，保持同一测试字节，`python3.12 -m pytest -q -s tests/test_host.py` 得到 **16 passed、16 subtests passed（16.86s）**。修后[完整输出](after-targeted.log)覆盖 Write/Edit 的合法绝对/归一化相对路径、其他 task、相似前缀、缺失路径、域外路径、`.goal`、symlink parent/leaf 与 symlink 后的 `..`，并核对 deny 后 attempt 不变及合法重试、父控制器正常行为。没有 mock ownership、transition 或权限保护。

目录子树用例仅验证 hook 的路径规则：fixture 在 prepare 时声明缺失路径，随后创建子树；未伪造 crew finish。现有 crew 最终摘要仍只支持 regular-file scopes，本补丁不宣称新增目录 validator/checkpoint 支持。

| 字节版本 | SHA-256 |
| --- | --- |
| 修前 host | `7cd29cccfbc59672a4393e68e0561bf54e9034a307a111e41949683f08879570` |
| 修后 host | `a33b910a23954aa2f08ce86863a16433d113f582c127723aeaed238c94065e3d` |
| 原 test_host | `1819aca0f08da9dca9cc0e56c0e19cbb1f181d36a3b02c2451ff7c7b48ecc1c5` |
| before/after 实际共用 test_host | `ab8fff931a51c728153912cdc6d50d50bc3394f56edd7302b20a7b680c733489` |

[implementation.patch](implementation.patch)、前后 source、[summary.json](summary.json)、`manifest.json` 和 `SHA256SUMS` 保存精确边界。两个输出文件是工具返回内容的完整拼接，加 command/exit 标记，并非另行重定向的日志。没有运行 full suite、模型或新 cohort；源码先前的完整矩阵不覆盖这个后续生产增量。后续 READY 入口改动也不属于本次配对。

这是对已知结构化工具路径的检查；不分析任意 Bash 副作用，不提供 hardlink、并发恶意替换或 OS 安全沙箱保证。未增加模式、调度框架或自动权限批准。
