# W5 headless v2：READY 未建立

独立于v1的新run/project、ABBAAB六个预注册位置。保留同一900秒总截止与8个parent turns，去掉不能代表真实账单的客户端美元估价上限，并按真实message ID合并工具流。实际控制器在899.126秒结束，没有延期。

| 位置 | 实际结果 |
| --- | --- |
| single-1 | 原生worker返回，独立21项检查通过并采用；波次273.706秒，worker span267.947秒 |
| crew-1 | T2原生完成；T1原生Agent已启动，但没有通过首工具绑定、没有READY；CLI124，未独立验证或采用整波 |
| 后4个位置 | 未派发，不补样本 |

两份parent prompt均原样包含正确worker prefix。T1的128个工具尝试均有错误结果，91次Bash无一次精确匹配原owned/bare READY；首条是复合shell且内层nonce缺字。T2首条精确复制即成功。实际hook重写使用的解释器路径也与prepare相同，不能把本次失败归因为Python别名差异。

同一message ID下的两个Agent证明同批派发，不证明两个worker都READY或整波成功。没有T1 READY→terminal区间，因此不声称有该口径的实际重叠。没有3+3有效窗口，planner未执行，真实总tokens/money仍未知。

结构化域外Write/Edit和额外scratch测试另由独立检查逐项保留；controller的`protocol_ok`只覆盖它实际检查的派工条件，不能替代完整worker合规判定。由这些原始材料触发的写围栏和短READY入口修复属于后续版本，不回写本批。

[原始归档](raw-run.tar.xz)保存独立冻结副本的182份文件；[清单](manifest.json)与[校验值](SHA256SUMS)核对源码、driver/预注册、全部过滤事件、失败、产物及host/crew/runtime记录。未保存thinking或凭据环境。该结果不证明crew净收益或相对原生`/goal`的整体优势。
