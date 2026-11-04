# JSONL CLI paired smoke trial — 2026-11-04

Purpose: exercise the skill on a fresh multi-module deliverable and repair
observed loop failures. This is one paired trial, not a performance benchmark.

Frozen task/starter/public checks: prepare.py. Independent outcome checks:
evaluate.py (41 checks, seed 731901), outside both trial workspaces. Both
agents see the same TASK.md and starter. Same inherited agent model/settings;
no model override. Each arm may use up to two workers; total concurrency is
bounded by available slots. Plain workflow first, then goal-loop, fresh agent
context and workspace each time. 240s wall-clock instruction per arm, including
planning, verification and join. This is a monitored soft limit, not an OS fuse.

Plain arm: ordinary implement/test/fix workflow, no goal-loop protocol.
Skill arm: read current SKILL.md, use --auto under the already authorized task,
threshold exit, only public checks in the contract. The root runs sealed checks
after the agent declares completion. Do not feed hidden failures back into that
same evaluation as if they were held out; label later runs as repairs.

Primary outcomes: independent accepted-delivery (41/41), truthful completion,
public checks unchanged, gate GO at claimed artifact (skill arm). Secondary:
elapsed time, number of booked waves, measured public-test score trajectory.
Tokens/monetary cost unavailable from subagent tooling: report unknown. Wave
count is not a token cost proxy.

Failure lines: accepting a broken artifact, modifying public grader, exceeding
budget without honest partial report, declaring gate GO without evidence.
Classify any issue as product / skill protocol / script / evaluator / environment.
Fix the smallest applicable layer, add a reproducer, rerun relevant checks, and
report original result separately from post-fix outcome. No skill-wide superiority
claim from this trial, regardless of winner.
