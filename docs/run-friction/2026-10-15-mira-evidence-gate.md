# goal-loop 缺陷候选（修 skill 用）

| id | 现象 | 根因假设 | 严重度 | 建议修复 | 状态 |
|----|------|----------|--------|----------|------|
| SB-1 | AC 行多行 heredoc/命令导致 `expected:` 落在续行，gate 报 contract-malformed:AC-N（no expected: token） | goal_parse.sh `gp_ac_line_for` 只认单行 `^- AC-N`；契约模板示例未禁止多行 check | high | stamp 前强制 AC 单行化，或 parser 支持续行 AC；坏契约应 stamp-refused 而非 mid-loop NO-GO | open |
| SB-2 | 修契约后 restamp 触发 verdicts-stale + false-complete 棘轮 +1 | 同 digest 绑定是 BIND 不变量正确，但 contract-malformed 的 claim 被计 false-complete 惩罚作者而非产物 | med | contract-malformed 的 close-iteration 不计 false-complete（惩罚错对象） | open |
| SB-3 | 用户期望「原生 TeamCreate/TeamPlan 派工」，但执行器工具面无 Teams/Agent 工具；skill teams.md 要求 native first 且禁静默降级 | harness 子代理未注入 Teams 工具；skill 未写「工具面缺失时的强制降级记账」最短路径 | high | teams.md 增加：探测失败必须写 friction + 回退 controller 自做/ portable，并在 loop-log task= 标 `(fallback:teams-unavailable)` | open |
| SB-4 | migrate_evidence_log_v1_to_v1_1.py 只吃严格 v1 头，实际仓库 6 个 legacy 包 3 族异构头全部 skipped_non_v1，文档仍写「优先 migrate」 | skill/Mira 文档假设 v1 占比高；无 skipped 时的 archived 路径门禁 | med | migrate 脚本报 skipped 时打印 archived 路径指引；或提供 v1.1 目标态映射器（保留旧列） | open |
| SB-5 | `legacy_evidence_schema: true` 同时跳过 evidence/calculation/decision 三类校验，去 flag 级联 100+ 历史 debt ERROR | validate_repo 单 flag 耦合三产物；归档语义被放大到 aux ledger | high | 拆 flag：legacy_evidence_schema 仅 evidence；aux 用 legacy_aux_ledgers；避免「消 evidence WARN」被 calc/decision 债绑架 | open |
| SB-6 | close-iteration 的 --files 逗号串极长，CTL 无长度/存在性校验 |  bookkeeping 只记账不验文件 | low | close-iteration 对 --files 做存在性抽检，缺失写 loop-log 警告 | open |
| SB-7 | 观测 wrapper goal_gate 在 rc=2 时 reason=tail-1，contract-malformed 等多行原因被截断到 200 字符且单行 | 假设 gate 原因单行 | low | gate 输出 JSON reason 字段或保留多行 | open |
| SB-8 | work-plan.md 由 init 创建空文件，Write 工具拒绝覆盖未读文件，需 bash printf 绕过 | 非 skill 缺陷（工具层），但影响 ledger 写入习惯 | low | ctl init 可写入 work-plan 模板骨架 | open |
