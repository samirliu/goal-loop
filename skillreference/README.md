# skillreference/ — vendored companions (no known public git)

这里放**重要且轻**、但**找不到稳定 GitHub 源**（例如 OpenClaw 分发）的 skill 原文，方便 goal-loop 跨设备随仓安装。不是本仓原创；保持原文语义，只作可移植快照。

| 目录 | 用途 | 与 goal-loop 关系 | 体量 |
|---|---|---|---|
| `skill-vetter/` | 装第三方 skill 前安全审计（红旗、权限面、可疑模式） | **仅安装期**；不进 loop/门控 | ~6KB，单文件协议 |

## 安装（到 `~/.claude/skills/`）

```bash
mkdir -p ~/.claude/skills/skill-vetter
cp skillreference/skill-vetter/SKILL.md \
   skillreference/skill-vetter/skill-card.md \
   ~/.claude/skills/skill-vetter/
```

## 刻意不收进本目录的

| Skill | 原因 |
|---|---|
| **multi-search-engine** | 对 goal-loop 闭环非必需；体积/配置面更大（引擎表 + 双 references）。研究阈值时可选另装，见 `references/companions.md` P2 |

## 边界

- 本目录 **不参与** `goal_gate.sh` / 契约语法 / stamp。
- 第三方 skill 装机前仍应用 `skill-vetter` 审一遍（包括本目录快照以外的来源）。
