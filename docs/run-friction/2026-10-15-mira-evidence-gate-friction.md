# goal-loop 运行摩擦（执行器实时 append）

格式：
## <ISO 时间> — <一句话现象>
- 期望:
- 实际:
- 猜想根因: skill / harness / Mira 债 / 用户裁决
- 证据: gate-runs 条目 / .goal/ 片段 / 错误输出

## 2026-10-15T22:15:00+08:00 — 原生 TeamCreate/TeamPlan/SendMessage 不在本执行器工具面
- 期望: 派工优先用原生 Agent Teams（用户指令 + skill teams.md native first）
- 实际: 本会话工具列表仅有 Bash/Edit/Read/Write/Glob/Grep/Skill 等，无 TeamCreate/TeamPlan/SendMessage，也无 Agent/Task 派工工具
- 猜想根因: harness（子代理执行器未注入 Teams/Agent 工具面）/ skill 假设 controller 有完整工具面
- 证据: 工具面清单；teams.md §2「detection by tool list」；本条 friction 本身

## 2026-10-15T22:15:30+08:00 — migrate_evidence_log_v1_to_v1_1.py 对 6 个 legacy 包全部 skipped_non_v1
- 期望: 优先跑迁移升 v1.1 并去掉 legacy_evidence_schema: true
- 实际: 6/6 返回 skipped_non_v1；schema 分属 3 族（baba 近 v1 但缺列+CSV 引号破损；gold/huichuan/jcet 为 claim_id,layer,source 族；tencent/xiaomi 为 claim_id,source_tier 族）
- 猜想根因: Mira 债（历史 schema 未统一）/ skill 文档假设存在 v1 头
- 证据: `python3.12 scripts/migrate_evidence_log_v1_to_v1_1.py --dry-run cases/*/evidence-log.csv` → skipped_non_v1 ×6

## 2026-10-15T22:16:00+08:00 — 去掉 legacy flag 会级联 calculation-ledger / decision-log 严格校验 ERROR
- 期望: 迁移 evidence 后去掉 flag 即可消 WARN
- 实际: is_legacy_evidence_schema 同时跳过 evidence/calculation/decision 三处校验；去 flag 后 6 包合计 100+ ERROR（decision_type 不在 RESEARCH_ACTIONS、calc 头非 canonical、evidence_log_ref 悬空）
- 猜想根因: Mira 债 + validate_repo 单一 flag 耦合三类产物
- 证据: monkeypatch is_legacy=false 后调用 validate_* 逐包计数（baba: ev1+calc13+dec10 等）
