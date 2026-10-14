# Companion skills — what to install beside goal-loop

goal-loop 本体**不绑定**下列任何 skill。这是**边界拼装**建议：在阶段接口上调用，不吞并进契约/门控。跨设备（例如 Mac Studio + cc-haha）按本清单装齐后，Step 1 评估设计与 NO-GO 诊断会明显变强。

**原则：** GATE/BIND 面永不外包；Worker 工艺自理；组合单位是「难点 → 阶段 → 交接」，不是行业包。

---

## 随仓自带（clone 即得）

| 组件 | 路径 | 装到 | 作用 |
|---|---|---|---|
| **contract-forge** | `companions/contract-forge/` | `~/.claude/skills/contract-forge/` | grilling 式评估访谈 → DRAFT 契约 + stamp 风险 + lint |

```bash
cp -R companions/contract-forge ~/.claude/skills/
bash ~/.claude/skills/contract-forge/tests/run_fixtures.sh   # 应全绿
```

---

## P0 强烈建议（外部 plugin）

| Skill | 阶段 | 为何对 goal-loop 关键 | 安装源 |
|---|---|---|---|
| **grilling** | 盖戳前 | 设计树/frontier 拷问；contract-forge 访谈骨架来源 | `mattpocock/skills` → `productivity/grilling` |
| **superpowers** | 盖戳前 / 宣完成前 | `brainstorming` · `verification-before-completion`（与 GATE 同构）· `systematic-debugging` | `obra/superpowers-marketplace` → `superpowers` |
| **skill-creator** | 元层 | 契约模板/检查形状打成 pack | `anthropics/claude-plugins-official` → `skill-creator` |

```text
marketplaces: mattpocock/skills · obra/superpowers-marketplace · anthropics/claude-plugins-official
```

---

## P1 建议安装（按阶段补强）

| Skill | 阶段 | 用途 | 安装源 |
|---|---|---|---|
| **prototype** | 盖戳前 | spike 实测噪声底 / 指标可行性 | `mattpocock/skills` → `engineering/prototype` |
| **diagnosing-bugs** | NO-GO | 硬 FAIL 诊断（只修产物） | `mattpocock/skills` → `engineering/diagnosing-bugs` |
| **code-review** | Join | 多 worker 合并审 | `mattpocock/skills` → `engineering/code-review` |
| **domain-modeling** | 盖戳前 | 复杂域术语边界 | `mattpocock/skills` → `engineering/domain-modeling` |
| **research** | 盖戳前 | 阈值/基准取证 | `mattpocock/skills` → `engineering/research` |
| **writing-for-agents** | 元层 | 写 companion / skill 文档 | `mattpocock/skills` → `engineering/writing-for-agents` |

---

## P2 按需（非闭环必需；本仓不 vendor）

| Skill | 用途 | 状态 |
|---|---|---|
| **agent-browser** | 感知/视觉 judged 证据 | `vercel-labs/agent-browser` |
| **reverse-engineer-anything** | 逆向/重构类交付的证据与结构分析（REA） | 本机已装；跨机按 REA 环境另配 |
| **multi-search-engine** | 研究阈值/竞品指标 | 无公开 git；偏重，按需自装 |

---

## 明确不要叠

| 组合 | 原因 |
|---|---|
| harness 内置 **`/goal`** + goal-loop | 两个外层循环打架 |
| 裸 **Agent Teams** 当验收门 | 勾完 work-plan ≠ GO |
| 把 grilling/TDD **写死进** goal-loop SKILL | 伤通用与规则冻结 |

---

## 阶段拼装图

```
[0 目标澄清]     brainstorming · domain-modeling · research
[1 契约/评估]    grilling · contract-forge · prototype(测噪)
[盖戳冻结]       goal_ctl stamp（仅用户）
[2 派工并行]     worker 自带 TDD / codebase-design
[3 Join+Gate]    code-review · 门控重跑（零拼装）
[4 NO-GO/进化]   diagnosing-bugs · strategy_delta · eval-gap
[元层]           skill-creator · writing-for-agents
```

---

## 跨设备（Mac Studio / cc-haha）系统依赖

goal-loop 脚本面是 bash + 常见 UNIX 工具，**无 jq**。macOS 注意：

| 工具 | 用途 | macOS |
|---|---|---|
| `bash` ≥4 | 关联数组等 | `brew install bash`（系统 3.2 不够） |
| `sha1sum` | 树指纹 | `brew install coreutils` |
| `timeout` | check 超时 | coreutils `timeout` / `gtimeout` |
| `find` `xargs -0` `sort` `awk` `sed` `grep` | digest / parse | 系统自带 |
| `git` | 可选树指纹 | Xcode CLT / brew |

Teams：优先原生 TeamCreate/SendMessage；无则 portable（`goal_team.sh`）。禁止静默降级。

**建议安装顺序（新机）：**

```text
1. brew install bash coreutils git
2. goal-loop → ~/.claude/skills/goal-loop
3. companions/contract-forge → ~/.claude/skills/contract-forge
4. marketplaces: mattpocock + superpowers + claude-plugins-official
5. 装 P0/P1（上表）
6. 注册 goal_hook.sh（可选 Stop hook）
7. 自检: goal-loop tests/run_tests.sh && contract-forge tests/run_fixtures.sh
```

---

## 验收（装完自测）

1. `goal-loop` 无参 = status；`tests/run_tests.sh` 全绿  
2. `contract-forge/tests/run_fixtures.sh` 全绿  
3. 真目标：**访谈 → DRAFT → lint → 你 stamp → GO/NO-GO**  
4. 未同时启用 harness `/goal`
