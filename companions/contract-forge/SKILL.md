---
name: contract-forge
description: |-
  Draft stampable goal-loop acceptance contracts when evaluation and metrics
  are hard to define. Runs a grilling-style interview (done enumerability,
  claim-family classification, objective/Goodhart, noise floor, horizon
  calib, floors, exit policy, budgets), then emits a DRAFT .goal/goal.md,
  optional .goal/proposals/ notes, and a stamp-refusal checklist. Companion
  to goal-loop: never runs gates, never stamps without the user, never edits
  a stamped contract. Trigger: "/contract-forge", "forge a contract",
  "draft acceptance criteria", "评估指标不好定", "怎么验收", "define done
  for goal-loop", "stampable AC", "eval system hard to measure",
  "验收标准不好写", "帮我定契约". Not for trivial one-AC tasks that already
  know their checks, or for running the loop / gate / Teams dispatch itself.
---

# Contract Forge

**身份：goal-loop 的盖戳前评估顾问。产出 DRAFT 契约，不判命、不盖戳。**

| 做 | 不做 |
|---|---|
| 访谈评估面（done/指标/噪声/horizon） | 跑 `goal_gate.sh` / 宣完成 |
| 写 `Status: DRAFT` 的 `.goal/goal.md` | 写 `approved:` 哈希或调 stamp |
| 预测 stamp 拒绝项 + lint | 改已盖戳契约（R3） |
| handoff 到 goal-loop init/stamp | 派工 / Teams / worker 工艺 |

**硬墙：** GATE/BIND 纯净。语法权威在 goal-loop `references/gate.md`。领域无关——只用 claim family，不写行业包。

## 何时用 / 不用

- **用：** 完成可枚举但评估/指标难写；优化要 objective；怕 Goodhart / 噪声阈值 / 缺 horizon。
- **不用：** 单 check 已明确（goal-loop 快车道）；纯美学不可枚举（拆子目标或换工具）；只跑 loop。

## Workflow

0. **发现 goal-loop**（只读）：`GOAL_LOOP_HOME` → sibling `../goal-loop` → `~/.claude/skills/goal-loop`。按需打开 `patterns.md`、`packs/gradient.md`、`packs/instrument.md`。
1. **访谈** — `references/interview-tree.md`（轮次 + ❓/➡️）。
2. **事实用子代理/读环境**（噪声实测、既有测试、fixture 候选）；不问用户可查事实。
3. **共享确认** — frontier 空且用户确认理解后，才落盘。
4. **产出 + lint + handoff**（见下）。stamp **始终由用户**执行。

## 访谈协议（摘要）

设计树 + frontier；整轮提问；`❓ QN` + `➡️` 推荐答案；依赖题进后轮。每条 AC 过 **Goodhart 哨兵**；指标 AC **先测噪声底再定 V**。细节：`references/interview-tree.md`。

**复杂 + Teams + 量化优化默认三层：** floors + `objective: max/min` + horizon（judged+calib 或 `horizon-waived:`）+ `exit: forge`。

## 产出物

| 路径 | 内容 |
|---|---|
| `.goal/goal.md` | `assets/contract.draft.md` 填空；**Status: DRAFT** |
| `.goal/baseline.md` | forge+delta 时行骨架或「盖戳前先测」说明 |
| `.goal/proposals/contract-notes.md` | 可选：否决的 AC、Goodhart 笔记 |
| chat | stamp 风险清单（`references/stamp-checklist.md`） |

## Lint

```bash
bash scripts/lint_contract.sh .goal/goal.md --project . [--strict]
```

Advisory、只读。exit 0 clean · 1 errors · 2 usage。见 `references/stamp-checklist.md`。

## Handoff（确认后打印；不代替用户）

```bash
bash <goal-loop>/scripts/goal_ctl.sh init --project .    # 如需
# 冒烟每个 named check；forge 写 baseline.md（重数 >=2）
bash <contract-forge>/scripts/lint_contract.sh .goal/goal.md --project .
bash <goal-loop>/scripts/goal_ctl.sh stamp --project .   # 用户批准
# 执行：/goal-loop [--teams] <objective>；objective 每波 close-iteration --strategy <label>
```

## 交前自检

语法完整 · objective 目标匹配 · horizon 或 waiver · calib 文件存在且 good≠bad · baseline 计划 · `approved:` 仅占位 · lint 无 error。

## Non-goals

跑 gate/loop；自动 stamp；改已戳契约；Teams 协议；worker 工艺包；行业 pack；复制 goal-loop packs；无噪声测量就定 V。
