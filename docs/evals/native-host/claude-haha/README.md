# claude-haha 原生 hooks 现场

[证据包](native-cli-cases.tar.xz)共141项、58,592字节，[SHA-256](native-cli-cases.sha256)。
运行时为 **claude-haha999-local**（客户端上报 `999.0.0-local`），主模型为
**MiniMax-M3.1-Flash**；不是标准Claude的验证，也不与Work旧cohort比较效率。

| 既有现场 | 结果与范围 |
|---|---|
| `euim07xs` | harness禁用slash，Unknown skill；零API、无worker。控制器因缺prompt缓存结束，不计产品失败。 |
| `0knur70e` | 原Infinity缺陷现场，25次PostToolUseFailure与重试；总计145.972s（末turn142.727s），最终父validate=0、采用且quality=true。25个执行/测量span仍unfinished，保留原貌。 |
| `0ch9wkfr` | F5后30.363s；Agent(Task入口)及4次Bash对应5次PostToolUse、无Failure；父validate=0、采用且quality=true。另有Read尝试保留，不冒领为已验证的工具callback。 |

两次实际worker运行均保留prompt缓存→nonce→ready→native completed→父验证/采用的
回执和账本。SessionEnd虽未在stream尾出现，`work/.goal/evidence/host/event-*.json`
已有实际落盘；计入callback覆盖。SessionStart属于用户全局hook，不计本plugin成果。
F5后4个running记录均为unknown的host-lifecycle点事件；7个执行/测量相关span完成，
不能把未知事件补成零成本或已完成工时。

包内保留三个现场的report、manifest、begin/brief/stamp（存在者）、非thinking事件、
完整`.goal`收据/runtime/不可变账本、control与out.txt。原driver已过滤thinking及
assistant正文；归档又将5份result正文、2份任务叙述改为哈希，其余回执逐字节保存。
每项原始/归档SHA、转换方式、权限和mtime在`ARCHIVE-MANIFEST.json`，最终正文不存明文。

`metadata/driver-current-postfix.*`只代表当前driver补录，不声称旧case均使用该版本。
`metadata/source-resolution.json`按case原manifest匹配139文件冻结版；旧ownerwatch
`d0d8…`、bounded `1c0825…`可从[F5因果源码包](f5-owner-guard/causal-pair-source.tar.xz)复原。
没有拼造缺失的历史driver。

客户端launcher、preload、main、print、hooks、processUserInput、AgentTool等22项
源码的SHA/mtime及Git HEAD/相关源码dirty摘要在`metadata/client-after-run-supplement.json`。
HEAD为`04ca2fc0d28ae169d73b41e45965a1562a6ba799`；捕获时mtime均早于三次run，
但这是**after-run supplement**，不冒充预注册或不可变证明。未读取或归档`.env`/密钥。

W4 trace已处理错误收尾的before记录单列；5项通过、2.501s仅为工具回执摘要，
没有独立raw log。此封存未启动CLI、模型、测试或新cohort，不作完整回归全绿或9+结论。
