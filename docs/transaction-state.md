# 当前事务保护与证据边界

此文记录优化方案 A3 的实际接入状态，不代表 A 阶段已经完成。

## 锁的范围

`goal_ctl.sh` 的 init、stamp、bind、close-iteration、recover 使用 `.goal` 目录 inode 的排他 `flock`；status 使用共享锁。`goal_gate.sh` 的 check、verify、baseline-check，以及 `goal_audit.sh` 和 Stop hook，在读取前取得共享锁并持有至本次操作结束。目录锁不创建、删除或覆盖锁文件，读取者不修改账本来获取锁。init 创建 `.goal` 后才有可锁定的目录。

普通读取者可并发执行；与 writer 冲突的调用立即返回 rc=4、`ledger-busy`，调用者应等当前操作结束后再重试。这个结果没有完成或失败的产品含义。Stop hook 保留其原有的 fail-open 政策：锁冲突允许用户停止，但不证明 GO。

带 `external:` 的门控可能追加影响后续判定的缓存记录，因此使用排他读取模式。实现保守地检测契约中的 `external:` 字节串，文字中的同名内容也可能触发串行执行；不影响验收语义。内部 gate 继承当前 controller 的所有权，允许在收账期间检查自己的新视图；用户检查调用的嵌套 writer 会被拒绝。

检查、probe 与 external 命令运行前关闭目录锁和收账锁的描述符。等待命令结果的中间 shell 同样关闭这些描述符，避免后台后代或被 SIGKILL 的 gate 遗留锁。锁由实际控制器/门控持有，不通过删除他人的文件解锁。元数据只用于同一运行的协作，不构成对同一用户恶意进程的权限隔离。

内部受信 gate 需要借用 controller 的锁，因此会启动不继承任何账本描述符的所有者监测。确认 controller 已消失后，监测结束仍持锁的借用者，让恢复能够取得锁。这个机制释放的是借用锁的受信进程；不代表所有用户检查工具或其进程组均已取消。当前所有者存活检查基于本机 PID；PID 复用、尚未回收的僵尸状态及平台差异不应被当作已解决的跨运行所有权协议。

独立 `--digest` 仅计算产物指纹，不判定完成，保留没有 Python 的 shell 路径；它不提供账本版本读取保证。

## 收账中断与恢复

close-iteration 完成预检及测量后，在首次修改账本前写入 `.goal/store/pending`。v3 日志包含提交身份、请求摘要、基线 HEAD，以及本轮写入前的 state、log、scores、对抗与故障收据和本轮原始验证文件的内容或缺失标记。字段集合、版本类型和 SHA-256 校验在恢复前验证；未知或损坏内容会被拒绝。旧 v1/v2 日志仍可读取：缺少基线 HEAD 的日志仅在没有提交历史时回滚；v2 若匹配当前已提交操作，可按快照前滚；无法证明版本关系时拒绝恢复。

收账成功路径先核对本轮 state、scores、log 与原始证据，确认历史没有被覆盖，再同步所有写入文件及目录。随后把最终文件快照及返回码写入 `.goal/store/commits` 的不可变 generation，并原子发布 `current` 指针；**指针发布是收账提交点**。之后删除 pending、同步其目录，最后报告 `CLOSE ok`。关键写入失败、文件同步失败或进程被杀时，pending 可能留存。外部 check/verify/baseline-check、status、audit 与后续控制器操作不能继续使用待恢复账本。

```bash
bash scripts/goal_ctl.sh recover --project /path/to/project
```

recover 取得控制器排他锁后，先核对提交历史。提交点之前中断：确认 current 仍等于日志基线 HEAD 后恢复原内容，删除本轮新生成且原先不存在的原始验证文件。提交点之后中断：确认操作就是当前提交，再按快照补全最终内容，保留已消费的轮号及计数。两种情况都不重放外部工具，然后删除 pending。恢复本身若中断，保留日志，下次继续写回同一版本。如果 pending 的基线或已提交操作与 current 矛盾，会拒绝恢复，避免把新账本倒退。

## 重试提交身份

有可能重试的调用应由 controller 在首次调用前选定身份，并在重试时保持相同参数：

```bash
bash scripts/goal_ctl.sh close-iteration --project /path/to/project \
  --operation-id wave-20261110-T1 --task T1 --files artifact.txt \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --no-gate
```

ID 为 1—128 位 ASCII 字母、数字及 `._-`，首位为字母或数字，作用域是当前项目提交历史。省略时生成 UUID 并在 `CLOSE ok` 中输出；未提前保存身份的调用在丢失确认后不具有可自动判断的重试身份。

相同 ID、相同请求再次调用，直接返回保存的历史收账返回码，并输出 `CTL: REPLAY ... historical-result=...`。不会重跑测量、重复加分、增加假完成计数或消费另一轮；重放较早 ID 也不会把 current 或文件倒退。请求摘要按原始参数序列计算，仅排除项目路径和 operation-id；改变顺序、显式增加默认参数等也会作为不同请求拒绝，避免猜测语义等价。

重试结果是历史收账确认，**不证明当前产物仍然满足契约**。产物即使已变化或消失，原提交仍然存在；最终交付仍须重新运行 gate。发生在提交前的测量证据、外部缓存及外部工具副作用，不因为回滚账本而被当作未发生。

## 尚未覆盖的要求

- init、stamp、bind 已互斥，但尚未接入同等的中断恢复日志。进程被杀后的部分写入仍可能保留。
- close 已有可重试的提交身份及提交快照，但 init/stamp/bind 和 runner 尚未进入同一提交历史。
- 还没有覆盖全部视图及所有读取入口的权威版本校验。当前不可变 generation 已用于实际 close 提交及恢复；其他写入、直接编辑后的完整性判定仍待接入，不能由隔离存储测试或 close 的提交核对推断完成。
- runner 的 deadline/clock 等旁路写入、用户直接编辑账本、外部工具直接修改 `.goal` 尚未全部加入目录锁协议。锁只对遵守协议的入口互斥；现有前后指纹检查提供另一层修改检测，不等于事务版本保证。
- 进程组取消、真实断电、网络文件系统上的锁及持久化保证，不可由本地进程故障测试推断。

因此仍不能将 A3 标为完成，也不能用这些回归代替 W4—W9 的真实行为及效用评估。

## 可复放证据

```bash
python3 -B tests/test_ledger_access.py
python3 -B tests/test_controller_writers.py
python3 -B tests/test_close_commit.py
python3 -B -m unittest discover -s tests -p 'test_goal_store.py'
bash tests/run_tests.sh
```

访问测试使用真实子进程，覆盖共享读取、写入排斥、external 缓存串行、嵌套写入拒绝、关闭的继承 FD、后台子进程及 gate 主进程 SIGKILL 后的锁释放；还覆盖 controller 在 raw gate 执行中被杀后，两把锁释放并可恢复。收账测试覆盖实际写入中途被杀、恢复前读取拒绝、损坏日志、追加写入失败、恢复重复调用与并发轮号。提交测试在真实控制器的 generation 发布后、current 发布后、成功确认前分别杀死 controller；验证回滚、前滚、同 ID 重试不重测、不重复收账，以及历史重试不倒退、变参冲突及过期 pending 拒绝。存储测试另覆盖 I/O 同步失败和隔离核心行为；这些证据均不代表其余 A3 要求已完成。
