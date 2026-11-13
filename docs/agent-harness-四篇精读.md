# AI Agent 工程四篇长文精读

> **来源**：4 条 X 长文（均为 X Article 长文形式，正文以 t.co 外链发布）
> **抓取时间**：2026-11-10（`opencli twitter article` 抽取为 Markdown）
> **一句话总览**：四篇是同一条梯子的四段——**环境（harness）→ 图（graph）→ 循环与图的接缝（loops）→ 人的复利（teaching）**。
> 前两篇讲"系统怎么搭"，第三篇讲"搭哪里最容易搭错"，第四篇讲"人怎么在这套系统外继续增值"。

---

## 0. 阅读地图

| 层 | 文章 | 作者 | 发布 | 核心问题 | 体量 |
|---|---|---|---|---|---|
| L1 环境 | Harness Engineering: The Complete Guide to Building AI Agents That Don't Fall Apart | @LunarResearcher | 2026-09-06 | 为什么 agent 老是散架？因为失败在环境层，不在推理层 | 19 节，最系统 |
| L2 图 | Graph Engineering: how to build the agent system that replaced loops | @0xShoopy | 2026-08-06 | 一个 agent 干五件事会崩，怎么拆成 specialists + 路由 | 11 节，90% 是 how-to |
| L3 接缝 | Loops and Graphs: how to stop babysitting agents and only approve the last step | @hanakoxbt | 2026-08-23 | loop 和 graph 的分界线在哪，最容易搭错的四个地方 | 9 节，最锋利 |
| L4 人 | The Karpathy Playbook: How Teaching Became the Most Valuable Skill in AI | @DmitroCP | 2026-10-25 | 模型会写代码之后，人的不可替代部分是什么 | 9 节，人物叙事 |

> 说明：四篇都用大量配图承载枚举清单（如"四种记忆类别""三个边类型""五个图形""Karpathy Loop 八步"）。本文在正文可提取之处逐条展开；纯图给出的部分已明确标注，不臆测补齐。

---

# 第一篇 · Harness Engineering（@LunarResearcher）

## 核心命题

> "Most people are trying to improve AI agents at the wrong layer."

失败的表现是 agent 做错事，于是人们改 prompt、加指令、换模型、加工具、扩大上下文窗口，然后祈祷下次行为不同。但作者断言：

> **很多 agent 失败不是推理失败，是环境失败。**

他列出环境失败的具体形态——每一条都不是"模型不够聪明"：

- agent 不知道哪些文件重要
- 在对的地方用了对的工具，但时机/位置错
- 上一个会话做出的决定丢了
- 没跑检查就宣称成功
- 部分失败后又重复了一次同样的动作
- 拿到了本该需要审批的权限

> "The model was not necessarily the problem. The system around the model was incomplete."

而这个"系统"就是 **harness**（承载环境）。作者的定位很关键：

> "A prompt changes one attempt. A harness changes every attempt."
> （prompt 改变一次尝试，harness 改变每一次尝试。）

## 1. 模型不是 agent

模型能推理、生成、比较、选择；但 agent 还必须：理解任务、找到相关上下文、选对工具、保持状态、遵守权限、检查结果、从失败恢复、**证明工作已完成**。

> "The model is the reasoning engine inside that system. The harness is everything that makes the reasoning operational."
> "A powerful model inside a weak harness is still a weak agent."（弱 harness 里的强模型，依然是弱 agent。）

harness 工程的目标不是消除模型的不确定性，而是**把一个能观察、能验证、能恢复的系统套在不确定性外面**。

## 2. 先写任务契约（Task Contract）

大多数 agent 任务起点是模糊意图，比如"改进 onboarding 流程"。这句话对聊天够用，对自主执行不够。**动手前必须转成契约**，回答五个问题：

1. 必须存在什么结果？（outcome）
2. 什么在范围内？（scope）
3. 什么不允许改变？（constraints）
4. 什么证据能证明完成？（evidence）
5. 哪些动作必须人工审批？（approval）

这一步改变的是 agent 的自问方式：

> 从 "What should I do next?"（我下一步该做什么）
> 变成 "What action moves the environment toward the contracted outcome?"（什么动作把环境推向契约结果）

> "Without a contract, the agent optimizes for plausible activity."
> "With a contract, it can optimize for verified completion."
> （没有契约，agent 优化的是"看起来合理地在忙"；有了契约，它才优化"可验证的完成"。）

## 3. 给地图，不要给手册（Give a Map, Not a Manual）

把整个仓库、整套文档、全部对话历史塞进上下文，不是上下文工程，是**上下文灌水**（context flooding）。

正确做法是**渐进披露**（progressive disclosure）：先给小地图，需要时再取细节。

> "The context should expand because the task requires it, not because the information exists."
> （上下文应该因为任务需要而扩张，不是因为信息存在而扩张。）

"上下文编译器"要回答五件事：

| 问题 | 处理方式 |
|---|---|
| 什么永远需要？ | 常驻 |
| 什么可以之后检索？ | 按需取 |
| 什么已经过期？ | 丢弃 |
| 什么可以摘要？ | 压缩 |
| 什么必须逐字保留？ | 原文保留（错误信息、精确标识符、法规条款） |

> 目标不是最大上下文，是**每 token 的最大信号量**（maximum signal per token）。

## 4. 做工具网关，不要做工具堆（Tool Gateway, Not a Tool Pile）

> "Giving an agent twenty tools does not make it capable. It gives the agent twenty ways to make a mistake."
> （给 agent 二十个工具不会让它更强，只会给它二十种犯错方式。）

harness 应该控制工具**如何暴露、如何使用**：

- 隐藏无关工具（按任务裁剪可见工具集）
- 校验参数（schema 层拦截，而不是靠模型自觉）
- 限制路径与域名（目录边界、网络白名单）
- 附加超时（防止单步挂死整个任务）
- **让重试幂等**（这是最容易被忽略的一条）
- 归一化输出（同一类工具返回同构结果）
- 危险动作强制确认
- **返回证据，而不只是 "success"**

由此形成一条分工：

> "The model can propose an action. The tool gateway decides whether that action is valid enough to execute."
> （模型提议动作，网关决定这个动作是否合法到可以执行。）

## 5. 拆开大脑、双手、历史

很多脆弱的 agent 把所有东西混进一条不断增长的 transcript：推理、工具调用、文件内容、决定、错误、旧观察，全部争抢同一个上下文窗口。

强系统拆成三份职责：

| 角色 | 只需要 | 不需要 |
|---|---|---|
| 模型（大脑） | 当前正确的状态 | 每一条原始事件 |
| 沙箱（双手） | 安全执行一个受限动作 | 理解整个目标 |
| 会话日志（历史） | 在当前上下文消失后保存"发生过什么" | 推理 |

> 这个拆分让长跑 agent 可恢复（resume）、可检查（inspect）、可修复（repair），也让你能替换其中一块而不重建全部。

## 6. 记忆必须变成持久状态

> "Conversation history is not reliable memory. It is an event stream."
> （对话历史不是可靠记忆，它是一个事件流。）

有用的记忆要显式转成状态。

> 注：原文此处用配图给出"至少保留的四类"，正文提取不到清单。可确定的是作者给出的操作方法：
>
> - **原始历史用于审计**（store raw history for auditability）
> - **编译后的持久状态用于执行**（compile durable state for execution）

> 这比"回放五十页对话，指望模型注意到那一行关键信息"有效得多。

## 7. 完成需要证据

> "An agent saying 'done' is not evidence that the task is done. It is only another model output."
> （agent 说'做完了'不是证据，那只是又一个模型输出。）

完成必须由**环境里可观察的变化**来判定。harness 应当先跑最便宜的确定性检查：

> "Do not use another model where a compiler, schema, checksum, query, or test can answer the question."
> "Use models for ambiguity. Use code for plumbing."
> （编译器、schema、校验和、查询、测试能回答的问题，就不要再用一个模型去答。模型处理模糊，代码处理管道。）

> "A model can propose that the task is complete. Only the environment can prove it."

## 8. 验证应该攻击结果（Verification Should Attack the Result）

工人和评审者**不能共享同一个目标**：

- worker 努力造出最强方案
- evaluator 努力找出"应该被拒绝"的理由

> "If you ask the same agent, in the same context, to 'double-check its work,' it often preserves the assumptions that created the mistake."
> （让同一个 agent 在同一上下文里自检，它往往会保留那个导致错误的假设。）

一个有用的验证阶段需要五件东西：

1. 明确的**拒绝标准**（rejection rubric）
2. 能拿到产物本身
3. 能拿到验收契约
4. 必要时有独立工具 / 全新上下文
5. **有权拒绝，且不必负责修复**

> "Verification is not a second opinion. It is an attempted disproof."
> （验证不是第二个意见，是一次试图证伪。）

## 9. 模型提议，策略授权

有些规则绝不能依赖"模型是否记得住"。它们不是 prompt 里的建议，而是**策略**。

> "The safest design keeps policy outside the reasoning loop."
> "The stronger the consequence, the harder the gate."（后果越重，闸门越硬。）

> "Autonomy is not the absence of control. It is the ability to operate freely inside a clearly enforced boundary."
> （自主不是没有控制，而是在一个被明确执行的边界内自由行动。）

## 10. 恢复要针对失败类别

最常见的"恢复"是：出错了，再试一次。作者说那不是恢复，是**重复**。

harness 必须先给失败**分类**再决定下一步；一次重试至少要改变一个相关条件，否则就是在花钱复现同一个失败。

每个循环都需要预算：最大尝试次数、最大时间、最大花费、最大破坏范围、升级（escalation）条件。

> "Reliable agents know how to continue. They also know when continuing is no longer rational."
> （可靠的 agent 知道怎么继续，也知道什么时候继续已经不合理。）

## 11. 指令应该变成基础设施

指令在"解释本地现实"时有用，但**单靠指令是弱约束**。一条规则如果反复重要，就把它往栈的下面移（instruction ladder）：

```
prompt 里的一句话  →  AGENTS.md / 项目规则  →  skill / 模板  →  hook / 脚本  →  工具校验  →  权限策略
      （越往下越硬，越不依赖模型记性）
```

> "The prompt should explain judgment. The harness should enforce invariants."
> （prompt 解释判断，harness 强制执行不变量。）

## 12. 观察过程，而不只是最终答案

一个干净的最终产物可以掩盖糟糕的过程：访问了错误数据、忽略了失败的命令、重复调用了外部动作、烧掉十倍预算、用错误的理由得出正确结论。

有用的 trace 记录八项：状态迁移、上下文来源、工具输入输出、环境变化、验证结果、重试原因、审批决定、成本与延迟。

> "The goal is not surveillance. The goal is local repair."
> （目的不是监视，是局部修复——第 18 步失败时，你能从可信检查点重启，而不是重放整个任务。）

## 13. 每次运行都要有变更回执（Change Receipt）

长 transcript 无法评审。运行结束应编译一份**小回执**：

> "The receipt is not a summary of what the model said. It is a summary of what the system can prove."
> （回执不是"模型说了什么"的摘要，是"系统能证明什么"的摘要。）

> "The best handoff is not 'here is the conversation.' It is 'here is the state, the evidence, and the unresolved risk.'"
> （最好的交接不是"这是对话记录"，而是"这是状态、证据与未解决的风险"。）

## 14. 每次失败都应该升级 harness

> "The weakest teams fix the failed output. The strongest teams also fix the system that allowed it."
> （最弱的团队只修失败的输出，最强的团队同时修"允许它发生"的系统。）

> "A corrected answer helps one run. A corrected harness helps every future run."
> （改对一次答案帮一次运行，改对 harness 帮以后每一次。）

这就是 harness 飞轮：失败留下基础设施。

## 15. harness 也会腐化（Harness Decay）

更多 harness 不等于更好。模型会变强、工具会变好、任务会变，旧的保护措施可能变成纯摩擦——**昨天模型的权宜之计，可能挡住今天模型更好的策略**。

把 harness 组件当生产代码对待，对每个 router、evaluator、memory 层、retry 规则问五句：

1. 它防的是哪个失败？
2. 那个失败现在还发生吗？
3. 它增加了多少延迟和复杂度？
4. 现在有没有更简单的做法能达到同样结果？
5. 删掉它会怎样？

> "The best harness is not the largest one. It is the smallest system that reliably closes the gap between intent and evidence."
> "Build to delete."（为删除而建造。）

## 16. 最小可用 harness（六级）

| 级 | 内容 | 要解决的问题 |
|---|---|---|
| L1 有界任务 | 目标 / 范围 / 约束 / 验收检查 | 任务到底是什么 |
| L2 可读环境 | 项目地图 / 命令 / 本地规则 / 已知依赖 | 环境是否可理解 |
| L3 受控动作 | 有类型工具 / 参数校验 / 路径与权限边界 / 结构化结果 | 动作是否安全合法 |
| L4 持久执行 | 显式运行状态 / 检查点 / 决策 / 教训 | 能否断点续跑 |
| L5 证据 | 确定性检查 / 对抗式验证 / 变更回执 | 完成是否可证 |
| L6 恢复与学习 | 失败分类 / 有界重试 / 升级 / 从复发失败更新 harness | 能否越跑越稳 |

> "Build the smallest layer that eliminates the failure you actually have."
> "Do not begin with a multi-agent architecture because a single prompt occasionally needs clarification."
> "Complexity should be earned by observed failure."
> （先建能消除你手上那个失败的最小一层。不要因为 prompt 偶尔需要澄清，就上多智能体架构。复杂度必须由观察到的失败挣来。）

## 17. 可复用的 harness 规格（spec）

在给 agent 真正的自主权之前，必须先定义这份规格。原文用配图给出字段清单（正文未展开）。

> "If these fields are undefined, the agent is not autonomous. It is improvising."
> （这些字段没定义，agent 就不是自主，是在即兴发挥。）

## 18. 在正确的层级度量

token 数不是最终指标，试过的任务数也不是。

> "The useful unit is accepted work."（有用的单位是**被接受的工作**。）

需要持续跟踪：

- 首次通过率（first-pass acceptance rate）
- 工具失败后的恢复率
- 重复失败率
- 每个任务的人工介入次数
- **无证据的完成声明数**（unsupported completion claims）
- 从请求到"验证过的结果"的耗时
- 各组件带来的 harness 开销

> "An agent can look highly productive while creating expensive review work."
> "The objective is not more agent activity. It is more trusted outcomes per unit of human attention."
> （agent 可以看起来极其高产，同时制造大量昂贵的评审工作。目标不是更多 agent 活动，而是每单位人类注意力换到更多可信结果。）

## 19. 什么时候不需要重 harness

简单 prompt 够用的条件：任务短、输出易检查、失败便宜、无外部副作用、人始终在环。

该加 harness 的信号：跨多个工具或会话、环境会变、动作有真实后果、完成难以人工判断、同一失败反复出现、人类评审成了瓶颈。

> "The purpose of a harness is not to make a demo look sophisticated. It is to make real work dependable."

## 结语：真正的转变

> 第一代 AI 产品围绕 prompt 构建，下一代围绕**环境**构建。
> 问题不再是"怎么让模型答得更好"，而是"怎么构建一个系统，让好动作容易做、危险动作受控、失败可见、完成可证"。
>
> "The model supplies intelligence. The harness supplies structure."
>
> "If your agent keeps falling apart, stop adding adjectives to the prompt. Build the environment it needs to succeed."
> （如果你的 agent 一直散架，别再往 prompt 里加形容词了，去建它需要的环境。）

---

# 第二篇 · Graph Engineering（@0xShoopy）

## 起点：一个 agent 干五件事会崩

单个 agent 在循环里能规划、写码、测试、评审。但任务一复杂就噎住：上下文窗口填满、推理退化，你又回到椅子上读每一行 diff。

2026 年跑得快的人不再给一个 agent 五份工作，而是拆成 specialists：一个写码、一个评审、一个测试，然后用一个负责**路由、共享状态、验证输出**的系统把它们接起来。

> 这个系统就是**图**。2026 年 7 月，AI 工程社区给了它一个名字：**graph engineering —— 设计你的 agent 运行其中的"组织"。**

四层演进（每层都建在前一层之上，没有一层替代前一层）：

```
prompt engineering → context engineering → loop engineering → graph engineering
```

## 01. 三原语，就这些

| 原语 | 是什么 | 关键约束 |
|---|---|---|
| **Node** | 一个专职 agent，只干一件事（planner / coder / reviewer / test runner） | 各自独立的上下文窗口、指令集、工具集。**它看不见的，它就破坏不了** |
| **Edge** | 节点结束后去哪的路由规则 | 无条件（总是去这里）或条件（看某个值再选路） |
| **State** | 沿边流动的共享数据对象 | 携带"做了什么、什么失败了、下一步是什么"；每个节点读它需要的切片、写回输出 |

> **loop 就是最小的 graph**：一个节点，加一条指回自己的边。
> 所以 graph engineering 不替代 loop engineering，它是紧挨在上面的那一层。先学 loop；当一个 agent 干五件事成为瓶颈时，再把工作拆成图。

## 02. 四问过滤器（原文称"任一答案为否，就留在 loop"）

1. 同样的失败是否**反复**发生？
2. 不同失败类型是否需要**不同处理**（缺 env secret ≠ 真 bug）？
3. 写修复的人**是否不该**同时批准这个修复（maker ≠ checker）？
4. 单 agent loop 是否已被证明是**瓶颈**（例如已经知道它误判一半、在修不了的东西上烧 token）？

作者用 CI 失败分诊举例：四项全过，所以值得建图。

> "If your loop works, don't break it with a graph. If your loop is the bottleneck, the graph is the fix."
> （loop 能跑就别用图去破坏它；loop 成了瓶颈，图才是解药。）

## 03. 先画组织图，再碰代码

最常见的错误：一上来就开 Claude Code 造 agent，还不知道图该长什么样。

先纸上回答三个问题：

1. **最终输出是什么？**要具体。"修好 CI"是弱目标；"所有测试通过、lint 干净、开出一个带失败与改动摘要的 PR"才是图能验证的目标。
2. **哪些子任务彼此独立？**并排画。env-secret 修复和 flaky 重试不共享输入 → 可同时跑；fixer 需要 classifier 的输出 → 画箭头。
3. **质量在哪检查？**每一条通往输出的路径都至少要经过一个 gate。没有 gate 就没有验证，你只会得到一排互相说"看起来不错"的 agent。

> "Start on paper. Boxes for agents. Arrows for routing. This sketch becomes your blueprint. Don't skip it. The 10 minutes you spend here saves hours of rewiring later."

## 04. 一个 agent，一个动词（One agent, one verb）

通用型 agent 把整个任务的完整上下文塞进一个窗口，窗口一满（复杂任务必然满），推理开始退化——**输出变差，而对话还在变长**。专职 agent 只拿自己需要的切片：看得更少，但看得更清楚。

> 原文引述：Anthropic 自己的多智能体研究显示，把 agent 拆成有隔离上下文的 specialists，相比单 agent 基线在内部研究基准上有 90.2% 的提升。

每个节点三条规则：

1. **一个节点一个动词。**"分类""修复""评审""重试"。描述里出现两个动词，就是两个节点。classifier 只分类，不修复；fixer 只修复，不评审自己的修复。
2. **收窄工具范围。**reviewer 不该有写文件的权限；fixer 不该有合并 PR 的权限。作用域限定防止专职 agent 越界——**尤其在无人值守时，这些不是建议，是硬墙**。
3. **模型匹配任务。**classifier 只需要快 → 便宜模型；bug fixer 要读失败、理解代码、写精准补丁 → 前沿模型 + 高 effort。loop 给每个任务同一个模型，graph 把成本匹配到难度。

## 05. 边决定谁拿到什么

边决定三件事：谁是下一个、在什么条件下、什么数据沿边走。三种边类型（原文配图），每张图至少用两种。

关键洞察：

> **硬约束不应该活在 prompt 里。**
> "Prompts are advisory. Edges are deterministic. A prompt might be ignored on turn 47 of a long session. An edge is code. It doesn't forget."
> （prompt 是建议式的，边是确定性的。长会话第 47 轮时 prompt 可能被忽略，但边是代码，它不会忘。）

所以"绝不把支付相关失败发给自动修复器"这种规则，要写在**边逻辑**里，不是写在 agent 指令里。

## 06. 状态：图在运行之间写的那个文件

状态是图的记忆。没有它，每个节点从零开始，每次运行忘记上次做过什么；有了它，节点接着上一个节点往下走，明天的运行知道今天已经试过什么。

**设计规则：白名单，不要广播。**

> classifier 拿原始日志；fixer 拿分类结果、失败的测试名、最近的 diff——它不需要完整日志。
> 如果每个节点都读全部状态，你拥有的不是图，是一个塞满步骤的臃肿上下文窗口。

每次运行后状态文件（STATE.md）记录：做了什么、修了什么、学到什么教训、观察清单上还有什么。

> "The graph forgets every run. The state file does not. A graph without state restarts. A graph with state resumes."
> （图每次运行都会忘；状态文件不会。没有状态的图会重启，有状态的图会续跑。）

## 07. 那个说"完成 / 未完成"的节点（Gate）

这是区分"能跑的图"和"一排昂贵且互相点头的 agent"的唯一部件。

> 没有 gate，图产出结果然后自称完成；有 gate，图产出结果，然后由**客观的东西**检查结果是否正确。
> **gate 是唯一决定"完成/未完成"的节点。其他节点干活，gate 判活。**

三种 gate，从强到弱：

| 类型 | 例子 | 性质 |
|---|---|---|
| **硬 gate** | 测试套件、类型检查、linter、构建 | 过或不过，无意见、无判断、无偏见。最强，能上就上 |
| **软 gate** | 让第二个模型评审输出 | 比没有强，但评审模型有自己的偏见和盲区。只能当硬 gate 的补充，不能替代 |
| **人 gate** | 合并/部署/任何不可逆动作前的人审 | 图呈现工作，人做最后决定 |

> **Karpathy 规则**："if a task is verifiable, it is optimizable."（任务可验证，就可优化。）gate 就是你让任务变得可验证的地方。**如果定义不出 gate，这个任务大概不该放进图里。**

> 原文引述：Cherny 给过一个具体数据——给 Claude 有效的验证方法，通常能把最终产出质量提升 2–3 倍。

> **gate 会腐化**：六个月前好用的测试套件可能抓不到今天的失败模式。定期挑几个图批准过的 PR 手工复核，确认 gate 真的抓到了它该抓的东西；没抓到就先更新测试，再继续跑图。

## 08. 五种形状，所有图都由它们拼成

原文配图给出五种可组合模式（Anthropic 工程指南记录、Cherny 围绕它们构建 Claude Code 工具链）：**route（路由）、chain（链）、parallel（并行）、evaluate（评估迭代）、orchestrator-worker（编排-工人）**。它们可以自由组合：两条串起来、一个嵌进另一个、三条并行接线。

作者的 CI 图用了三种：入口 Route（classifier 把不同失败类型分到不同路径）+ 每条路径内 Chain（修完再验）+ 重试时 Evaluate（gate 挑剔，fixer 迭代）。

> "The cheapest structural win in most graphs is routing."
> （多数图里最便宜的结构性收益是路由：入口一个 classifier，把简单任务给便宜模型、难任务给前沿模型，token 账单能砍一半而质量不变。）

## 09. 上线三级：/goal → /loop → Routines

| 级 | 形式 | 说明 |
|---|---|---|
| 1 | 手动 `/goal` | 你敲一次命令，图跑到你设的条件满足为止。**由独立的评估模型检查完成**，写修复的 agent 不是判断"完成了没"的那个 |
| 2 | 定时 `/loop` | 图按节奏检查新失败，你不再是触发器 |
| 3 | Routines | 跑在云端，笔记本可以关。三种触发：定时（cron）、API 调用（webhook）、GitHub 事件（PR opened / push to main） |

> **顺序不可跳过**：先手动跑通并端到端看完第一次运行、读完每一个 diff、确认 gate 真的抓到了预期的东西；**信任 5 次手动运行之后**再升级到定时，最后才进 Routine。
> "Skipping steps is how graphs fail quietly and expensively in production."

## 10. 现在就试（单会话里的玩具版）

给任何 LLM 一段 prompt，它会在一段对话里造出一张图。这版有局限：你仍是触发器、没有持久状态、没有真正并行。但它展示了核心机制——三个各有作用域指令的 specialist，路由到一个合并并评判的 gate。

从这个玩具跳到真正的自主图，需要补四样它缺的东西：

1. 持久状态（STATE.md）
2. 真并行（subagents）
3. 自动化（/loop、Routines）
4. 硬验证（测试套件，而不是模型的意见）

## 11. 图带来的两种债（都随成功而加重）

| 债 | 机制 | 缓解（都不是技术问题） |
|---|---|---|
| **理解债**（comprehension debt） | 图每交付一次你没写过的代码，仓库与你真正理解的东西之间的差距就按复利计息。跑得顺的图很安静，安静像进步 | **读每一个 diff**；不读就是在按复利租借理解债 |
| **认知投降**（cognitive surrender） | 图自己跑起来后，很容易不再形成自己的判断，接受什么就是什么 | 用判断去设计图是解药，用它逃避思考是加速剂——**同样的动作，相反的结果** |

具体缓解措施：

- 读每一个 diff
- 抽查 gate：挑几个图批准过的 PR，手工验证测试真能抓到你在意的失败模式（gate 会腐化）
- **把图限制在小而机器可验证的任务上**：CI 分诊、依赖升级、lint 修复、flaky 测试复现。一旦图碰架构决策、鉴权逻辑、或任何"完成"要靠判断的事，理解债会加速
- 和队友一起设计图，第二双眼睛能抓到图一旦跑起来会永久利用的盲点

## 结语：杠杆又往上移了一层

上下文窗口是编程面（Karpathy）→ loop 自动化了上下文工程（Cherny）→ 当许多 loop 连成一个系统会怎样（Steinberger）→ 答案是图。

> 但真相是：**大多数开发者现在还不需要图。**直到 loop 撞到天花板、任务能拆成并行子任务、maker-checker 的分离需要结构性强制。
> "A graph without a working loop underneath it is just organized complexity."
> （一个底下没有能跑的 loop 的图，只是被组织起来的复杂度。）

---

# 第三篇 · Loops and Graphs（@hanakoxbt）

## 起点：你之所以在椅子上盯每一步，是因为没有别的东西在盯

要离开那把椅子，需要两样东西，而几乎所有人只建了一样：

> "A loop makes a unit of work correct without you. A graph decides which units exist at all."
> （loop 让一个工作单元在你不在时也正确；graph 决定到底有哪些单元。）

## 1. loop 是一个"能失败"的检查

剥掉一切，loop 是四段：**produce → check → correct → repeat until green**。

> "The check is the whole thing."
> （检查就是全部。）

没有能在你不在房间里的时候让工作失败的东西，你拥有的不是 loop，是**调度器**。

这听起来显然，但几乎没人先写检查。他们先建工作，再在末尾拴一个评审，而那个评审又是另一个模型在看输出——**两个乐观主义者在互相点头**。

正确顺序是先写条件，并且写成程序能判的形式。下面这条最容易骗到细心的人：

> **"没有报错"不是"正确"的证据。**
> （Absence of an error is not evidence of correctness.）

在这个基础上建 loop，你会得到一个"自信地把同一个错误重复到预算耗尽、并且全程日志干净"的系统。

## 2. 没人提醒你的天花板

loop 让**一个工作单元**变好，这就是它全部的工作，而且它很擅长。

它无法决定有哪些单元、单元的顺序，也无法注意到五个步骤里有两步根本不需要互相等待。

> 于是你得到一个非常优秀的 agent，跑着错误的三步、以错误的顺序、一次一个。
> **每一步都对，结果仍然又慢又错，而调 loop 修不好它，因为故障不在任何单元内部。**

这就是人们开始怪模型的时刻，也是下一层开始回本的时刻。

## 3. 图是上面那一层

图是**工作的形状**：什么跑、什么同时跑、什么等、什么根本不跑、结果回到哪里。

只有两样东西：

- **node** = 一个工作单元：一个有界的工作，一个输入进，一个输出出
- **edge** = 一个依赖：这个节点的输出是那个节点的输入

> **所有不必要的等待，都来自把 "and then"（然后）当成边。**

"总结文件，然后查天气"——这两者之间没有边，天气并不消费摘要。它们是被线性脚本连起来的两个独立节点，那个连线只来自你打字的顺序。

对现有流水线的每一根箭头问一句：**下一步真的读上一步的输出吗？**

> **"If you cannot name the variable that crosses, there is no edge, and the wait is pure waste."**
> （你说不出跨过去的那个变量是什么，就没有边，那个等待是纯浪费。）

多数链里有 2–3 根这种箭头，找到它们通常是**能拿到的最大单笔提速**。

## 4. 四种节点，其中一种不是模型

完整词汇表：**splitter（拆分器）、worker（工人）、code node（代码节点）、gate（闸门）**。

### splitter

把工作切成单元，站在最前面。**它比任何其他节点决定得更多**，因为按错误的维度切分会浪费下游一切。

> 按文件夹切一个仓库 → 四个 worker 审计同样的三个文件。
> 按爆炸半径切 → 每个 worker 看到的是别人看不到的东西。

### worker

一个单元、一个视角、**在自己的上下文里**。

> 最后半句最常被跳过。给四个审计员一个共享窗口，它们会收敛：第一个写出发现，其余读它，四份报告都围绕同一件事。
> **"You paid four times for one opinion with three echoes."**（你付了四份钱，买到一个意见和三个回声。）

### code node（人们忘了它存在的那一种）

合并、排序、去重、比较改动前后的每一次导出——**这些都不是推理**。每个都有唯一正确答案，每个都是几行代码，走一遍模型只给一个原本没有方差、没有延迟、没有成本的步骤增加了这三样东西。

> **判据：如果这个变换你能不用 judge / decide / assess / summarize 这几个词描述，它就是代码。**
>
> "A graph where every edge is an agent pays rent on its own wiring."
> （每条边都是 agent 的图，在为它自己的接线付租金。）

### gate

见第 7 点。

## 5. loop 到底住在哪里

> **一句话解决全部混乱：loop 住在节点内部，graph 住在节点之间。**

| 位置 | 内容 |
|---|---|
| 一个单元内部 | produce、check、correct、repeat until green |
| 单元之间 | split、fan out、merge、gate、send back |

第二列里没有任何一项能在单个单元内部表达出来。所以不是二选一：

> 没有 loop 的图 = 并行地生产未验证的工作，**比串行更糟，因为量更大**。
> 没有图包着的 loop = 一个非常优秀的步骤，排在一个没人设计过的队列里。

## 6. 两条回边，以及所有人都会跳过的那条

**没有回路的图是流水线**：它产出输出，然后忘掉。下周它从同一个地方、带着同样的盲区重新开始。

能跑的图有两条做不同工作的回边：

| 回边 | 长度 | 修的是 |
|---|---|---|
| **纠正边**（correction edge） | 短 | gate 把一个单元拒回给生产它的步骤，**修的是你正在跑的这一次** |
| **学习边**（learning edge） | 长 | 被接受的结果回到 **splitter**，变成一条约束，**修的是以后每一次** |

> **几乎所有人都建了第一条，跳过了第二条。症状是：系统很快，但永远不会变聪明。**

学习边携带的不是输出，是**从输出里派生出来的约束**。注意它落地的位置：

> **不是 worker 的指令里，是决定"工作怎么被切分"的那份 brief 里。**

一条被确认的病因变成一条规则，于是下一次故障从这一次结束的地方开始。

## 7. 回传单元，不要回传批次

这是返回路径上最贵的错误：

> 移植了四个切片，其中一个测试失败。如果把整批送回去，**三个正确的切片会被重写**。它们的新版本是"不一样"，不是"更好"，因为它们本来没错。然后你要重新验证四个，其中任何一个都可能因为无关原因这次失败。
> 你把一次失败转换成了四个不确定的结果，并为此付费。**一次运行里发生两次，它就永远不会收敛。**
> 从外面看像模型反复失败，实际是返回路径在摧毁正确的工作。

回传时随行四样东西（原文配图，正文给出其中最关键的一样）：

- **scope 行**——它比看起来更重要。没有它，被回传的单元会膨胀：agent 打开文件、注意到旁边两个问题、顺手也改了，你的一次单切片修正变成没人评审过的四文件 diff。
- **上限 3 次尝试**：一个单元三次纠正还不过，问题在那个产出它的计划里，而 loop 看不见计划。

## 8. 按爆炸半径开门，不按置信度

多数文章会造一个置信分、设个阈值、高于阈值就放行。**那是错误的变量。**

> 置信度是那个决定里最弱的输入，理由很简单：**它是模型唯一能影响的输入。**

强变量是"如果这个改动是错的，会发生什么"。按撤销错误的代价排序：

| 车道 | 例子 | 门怎么开 |
|---|---|---|
| **可逆且受限** | 文案改动、一个测试、一个有覆盖的孤立函数 | 错一次代价是一次 revert → 这条道可以最先打开 |
| **可逆但面广** | 共享工具、schema 增补、十几个调用方都会碰的东西 | 用确定性检查 + 干净的轨迹来决定 |
| **难以逆转** | 迁移、删除、任何写生产数据或动钱的 | **这条道不开，不管分数多高** |

> 第三行不是"设得很高的阈值"，而是"一条永远不开的车道"——**区别很重要，因为阈值会被调，关闭的车道不会。**

**车道内部看证据的顺序**（注意模型自评排在最后）：

1. 确定性结果
2. 这次运行的轨迹
3. 这个节点过去被回滚的频率
4. 模型自己的评估

## 9. 从你自己的活开始

拿一件你重复做的事：画出 splitter、车道、merge、一个 gate、一条回边。

**建设顺序**：

1. **先建 gate。**一旦有东西能大声失败，其他一切都会变容易；没有 gate 的图只是"更快地生产未验证输出"。
2. 再建车道（lanes）。
3. **最后建学习边**——在还没有东西在接受结果之前，你无法从被接受的结果里派生约束。

**人放在哪**：放在后果最高、可逆性最低的那一步。批准合并、选择哪些修复要发；**不是**逐条评审中间产物，不是逐步确认。

> "A human in the middle of a graph becomes the slowest node in it, and the graph runs exactly as fast as a person reading things."
> （人一旦站在图中间，就成了图里最慢的节点，图的速度就等于一个人读东西的速度。）

## 三条守则（全文最凝练的部分）

> 1. **Measure the path, not only the answer it landed on.**（度量路径，而不只是它最终落在的答案。）
> 2. **A verdict that does not change what runs next is a report.**（一个不改变"下一步跑什么"的判决，只是一份报告。）
> 3. **Any failure you do not turn into a permanent constraint, you will meet again.**（任何你没有转成永久约束的失败，你都会再次遇到。）

---

# 第四篇 · The Karpathy Playbook（@DmitroCP）

> 这篇不是方法论，是人物路径拆解。**与前三篇的直接关系**：它回答的是"当 harness 把执行变得便宜之后，人还剩什么"。

## 主线

大多数人描述 Karpathy 时列一堆 logo：OpenAI 创始成员、Tesla AI 总监、斯坦福博士。作者说这些都对，但掩盖了真正在运转的东西：

> **他把复杂的东西用尽可能少的代码从零重建，然后解释得清楚到陌生人能跟上。**
> "The logos were the result. Teaching was the engine."（logo 是结果，教学才是引擎。）

## 九段路径（含可迁移教训）

| # | 阶段 | 关键事实 | 可偷的一课 |
|---|---|---|---|
| 1 | 去思想聚集地 | 1986 生于布拉迪斯拉发，15 岁到多伦多；多伦多大学（Hinton 在那里教神经网络）、UBC 硕士、斯坦福博士（师从 Fei-Fei Li），博士卡在视觉与语言的交界 | 把自己放在"正在定义领域的人"旁边，而不是事后解释的人旁边 |
| 2 | 造自己想要的那门课 | CS231n（与 Fei-Fei Li），斯坦福第一门深度学习课，2015 年 150 人 → 2017 年 750 人；课程视频与笔记全部免费公开，多年间是行业学习 CNN 的主要途径 | **一门课不是副业**：它强迫你理解到无法用术语遮掩的程度 |
| 3 | 交付别人跑得起来的东西 | 2015《The Unreasonable Effectiveness of RNNs》配可运行代码，人们拿去喂莎士比亚、Linux 源码、维基百科；ConvNetJS 直接在浏览器里训练网络 | "If people can run it in five minutes, they remember it for five years."（能在五分钟内跑起来，就能被记住五年） |
| 4 | 创始成员，然后最硬的应用岗 | 2015 加入 OpenAI 任研究科学家/创始成员；2017 去 Tesla 任 AI 总监，负责 Autopilot 视觉，向马斯克汇报；同年写《Software 2.0》——神经网络是一种新的代码，你不再手写规则，而是经营产生规则的数据 | 想法来自工作。在那个量级跑数据引擎时，它才不再是理论 |
| 5 | 从职位上往回走 | 2023-02 回 OpenAI，2024-02 离开；2024-07 宣布 Eureka Labs（AI 原生教育公司，AI 助教与真人教师并排工作） | 多数人往更大的 title 爬，他反复往回走向教学。这不是绕路，是斯坦福那一招的升级版 |
| 6 | Zero to Hero：从零重建一切 | YouTube 系列《Neural Networks: Zero to Hero》：从 micrograd（一坐读完的微小自动求导引擎）一路爬到你自己造出一个 GPT | 教训不是"读他的代码"，是**"自己造那个小版本"** |
| 7 | 比别人先命名转向 | Software 2.0（2017）、"vibe coding"（2025-02：用平实语言描述你要什么，接受模型写的代码，靠结果而不是逐行阅读来掌舵）、Software 3.0（2025-06 YC AI Startup School：LLM 是一种用英语编程的新计算机） | 解释得好，你就有命名权 |
| 8 | The Karpathy Loop | 原文此处以配图给出"八步循环"清单，正文未展开文字 | 综合全文可还原的骨架：**在一个想法聚集的地方 → 把它重建成最小可运行版本 → 公开讲清楚 → 用公开产物换取下一个位置** |
| 9 | 本月就能跑 | 见下 | 不需要名校或名企 |

## 本月就能跑的四周计划

| 周 | 动作 |
|---|---|
| W1 | 挑**一个你每天在用、但讲不清楚**的概念（attention、embeddings、RAG、一个 agent loop） |
| W2 | 用尽可能少的代码重建一个玩具版。丑没关系，能跑才是重点 |
| W3 | 对着空白屏幕录自己讲它（不要幻灯片） |
| W4 | 同时发布 repo 和视频，再写一篇"最让你意外的那一点" |

> "The first one will be rough. The fifth one will be better than most paid courses."
> （第一个会很粗糙，第五个会比多数付费课都好。）

## 真正的转向（与前三篇的接口）

> 资历曾经是护城河。现在模型能写代码、总结论文、起草讲义。
> **它做不到的是：决定什么值得被理解、带着品味把它重建出来、让一屋子人真的搞懂。**

> DSH/agent harness 的语境下读这篇：当 harness 让"执行"变便宜，人的增值就移到了**选题、判断、解释、以及把系统设计成能自我验证**这几件事上。这也解释了为什么第一篇文章说"harness 工程正在成为一门工程学科"——它正是那件模型替不了的事。

---

# 四篇横向对照

## 共识（四篇里出现三次以上的观点）

| 观点 | 出现于 |
|---|---|
| **完成必须由机器可判的证据决定，不能靠模型自称** | Art1 §7、Art2 §7、Art3 §1/§7 |
| **制造者与检查者必须分离**（maker ≠ checker） | Art1 §8、Art2 §4/§7、Art3 §4 |
| **硬约束要下沉成代码/策略，而不是写在 prompt 里** | Art1 §9/§11、Art2 §5、Art3 §8 |
| **状态必须落盘，否则每次都从零开始** | Art1 §6、Art2 §6、Art3 §6 |
| **要有一条"学习边"，否则系统只会变快不会变聪明** | Art1 §14、Art2 §6、Art3 §6 |
| **最小可用，别为架构而架构** | Art1 §15/§16/§19、Art2 §2、Art3 §9 |

## 分歧与统一

- Art3 明确说"大多数开发者现在还不需要图"；Art2 给了四问过滤器 —— 两者**同一结论**：图的复杂度必须由观察到的失败挣来。
- Art1 是最上层（含权限、可观测性、回执、度量），Art2 是"图怎么搭"，Art3 是"搭的时候哪四个地方最常错"，Art4 是"人怎么不被这套系统架空"。

## 一句话合成

> **用契约定住任务（Art1 §2），用地图而不是手册喂上下文（Art1 §3），用一个能失败的 gate 定住完成（Art3 §1），把 maker 和 checker 分开（Art2 §4），把重复的工作切成图并用代码节点干管道活（Art3 §4），把每次被接受的结果变成下一条约束（Art3 §6），最后只在最高后果处放人（Art3 §9）。**

---

# 附录 A · 映射到 DSH（本机 harness + 插件）

| 文章原则 | DSH 里的对应能力 | 落地做法 |
|---|---|---|
| 任务契约（Art1 §2） | `goal` / `create_goal` + goal-loop 契约（`.goal-gate/goal.md` 的 AC） | 每个非平凡任务先写 3–6 条 AC，至少一条"能失败" |
| 完成需证据（Art1 §7） | `goal_gate_check`（确定性重跑每个 AC） | 模型不自己宣布完成，GO 只来自 gate |
| 对抗式验证（Art1 §8） | `subagent` / `subagent_fork`、`goal_gate_judge`（独立评审任务） | 评审者用独立上下文 + read-only 预设，只判不修 |
| 模型提议/策略授权（Art1 §9） | 权限预设、sandbox policy、插件的 `confirm: true` | 危险写在 git 干净树里做；评审者收窄工具 |
| 上下文工程（Art1 §3） | `dsh-context`（看上下文构成）、compaction、`skill` 渐进披露 | 先地图后细节；用 dsh-context 查"token 花在哪" |
| 持久状态（Art1 §6） | `hindsight_*`、session log、`STATE.md` | 每次运行写状态/教训；跨会话用 hindsight 检索 |
| 图（Art2 §1） | `workflow` 工具（splitter→workers→merge）、Agent Teams | 并行且检查点不同才用图 |
| code node（Art3 §4） | bash / node 脚本 | 合并、去重、排序、比较一律用代码 |
| 学习边（Art3 §6） | `hindsight_ingest_document`、skill、AGENTS.md | 结论写成约束，落在 brief 层而非 worker 指令层 |
| 观测（Art1 §12） | session log、trajectory、token meter、`job_list` | 失败先分类再重试；有界重试预算 |
| 回执（Art1 §13） | session log 导出、`present` 交付物 | 交接给"状态 + 证据 + 未解风险"，不给对话记录 |
| 自动化三级（Art2 §9） | `schedule`（cron/一次）、`session-superagent`（GitHub 事件唤醒） | 手动跑通 5 次 → 定时 → 事件驱动 |
| harness 腐化（Art1 §15） | `plugin_manager` 启停、`cmd`/skill 精简 | 定期问"它挡了哪类失败"，挡不住就删 |

---

# 附录 B · 落地检查清单（可直接勾）

**任务开始前**
- [ ] 写出目标 + 范围 + 不能改什么
- [ ] 写出 3–6 条 AC，每条有 `check` 命令与期望值
- [ ] 至少一条 AC 是"能失败"的硬检查（测试/类型/构建/schema）
- [ ] 定义这次运行的最大轮次 / 最大时间 / 最大破坏范围

**执行中**
- [ ] 制造者与检查者不是同一上下文
- [ ] 合并、去重、排序用代码，不用模型
- [ ] 每根并行边都能说出"跨过去的变量"
- [ ] 失败先分类，再决定重试还是升级

**收尾**
- [ ] gate 绿了才算完成（不看模型的自我声明）
- [ ] 产出变更回执：改了什么、证据在哪、还有什么没解决
- [ ] 把这次的教训写成一条约束（学习边），落到 AGENTS.md / skill / hindsight
- [ ] 问一遍：这次加的复杂度，下次还用得上吗？（build to delete）

---

# 附录 C · 原文链接

1. @LunarResearcher · *Harness Engineering: The Complete Guide to Building AI Agents That Don't Fall Apart*
   https://x.com/LunarResearcher/status/2096570562625655088 （2026-09-06）
2. @0xShoopy · *Graph Engineering: how to build the agent system that replaced loops*
   https://x.com/0xShoopy/status/2085383231554171098 （2026-08-06）
3. @hanakoxbt · *Loops and Graphs: how to stop babysitting agents and only approve the last step*
   https://x.com/hanakoxbt/status/2091515787366306154 （2026-08-23）
4. @DmitroCP · *The Karpathy Playbook: How Teaching Became the Most Valuable Skill in AI*
   https://x.com/DmitroCP/status/2114303402083856499 （2026-10-25）

## 提取与可信度说明

- 四条推文正文均只有一个 t.co 短链，实际内容为 X 长文（X Article）；本文经 `opencli twitter article` 抽取为 Markdown 后精读。
- 原文大量枚举以配图承载（如"四种记忆类别""三种边类型""五种图形""Karpathy Loop 八步""回传随行四样东西"），凡正文未展开处本文已标注，未作臆测补齐。
- 文中标注"原文引述"的统计数字（Anthropic 多智能体 90.2%、Cherny 的 2–3 倍验证增益、CS231n 150→750 人）为作者在原文中的说法，本文未独立核实。
- 引号内英文为原文原句；中文为翻译，括注了原文以便对照。
