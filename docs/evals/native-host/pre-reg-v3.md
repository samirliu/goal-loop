# 窄上下文 controller 的 W5 三对复验

v2 首个单 worker 样本已验收通过，但其墙钟包含 root 长会话的协调等待。
后续切换到实际 canonical identity `/root/w5_controller` 的独立 controller，
使用新项目和新 batch 条件；不将 root 协调的样本池化，全部旧现场保留。
v2 crew 只登记了 reservation，未发起 native spawn，现已请求取消；其
未知状态不伪造为已确认的 native 终态。

除 controller 身份明确绑定外，沿用 v2 的 3 对顺序、相同任务/初始字节/
最终验收器和 1800 秒整套上限。起点用父控制器在真正 dispatch 前读取的
epoch、monotonic 与实际 boot 身份，不从子线程进入脚本时重新起表。
9 个 worker 全新上下文、无模型覆写，固定 READY/CHECK 入口已单独校准。
所有实际回执、失败和阶段时长保留，截止不能延长；样本不足即不推荐 crew。

此轮仅用于修复后同条件模式比较，不能把控制器更换的收益算作并行收益，
不能推断通用 `/goal` 优势。每次准备自动保存实际执行的源码字节与摘要。
