#!/usr/bin/env bash
# docs_consistency.sh - form-level regression for the skill's documentation.
# Protocol changes are cheap to make and expensive to notice when they rot;
# this catches the mechanical rot classes in seconds:
#   C1 every referenced skill-internal file exists
#   C2 the version markers agree with the VERSION file
#   C3 every numbered TOC entry has a matching ## heading
#   C5 teams-backend protocol markers stay wired (dual-layer rule)
# Run from anywhere:  bash tests/docs_consistency.sh
# Exit 0 = consistent. (Semantic review still belongs to humans + the loop.)
set -u
export LC_ALL=C.UTF-8

here=$(cd "$(dirname "$0")/.." && pwd)
cd "$here"
fail=0
ok(){ echo "  ok   - $1"; }
bad(){ fail=1; echo "  FAIL - $1"; }

# C1 file-reference resolution (docs may cite skill-internal paths, or paths
# of OTHER installed skills - e.g. the packager of skill-creator). External
# references are verified only when other skills ARE installed locally;
# on machines without them (CI runners) they degrade to a skip - a bare
# environment must not fail the check for a reference it cannot see.
refs=$(grep -ohE '(references|scripts|assets|tests)/[A-Za-z0-9_][A-Za-z0-9_./-]*' \
        SKILL.md INTEGRATION.md references/*.md assets/goal.contract.md 2>/dev/null |
      sed 's/[.,;:)]*$//' | sort -u)
missing=0; skipped=0
skills_dir="$HOME/.claude/skills"
while IFS= read -r r; do
  [ -n "$r" ] || continue
  [ -f "$r" ] && continue
  if [ -d "$skills_dir" ] && ls "$skills_dir/"*/"$r" >/dev/null 2>&1; then
    ok "C1 external reference resolves: $r"
  elif [ -d "$skills_dir" ]; then
    bad "C1 broken reference: $r"; missing=$((missing+1))
  else
    skipped=$((skipped+1))
  fi
done <<< "$refs"
[ "$missing" -eq 0 ] && ok "C1 all internal cited files exist (external skipped=$skipped)"

# C2 version agreement with the VERSION file
if [ -f VERSION ]; then
  V=$(tr -d '[:space:]' < VERSION)
  grep -q "(v$V)" SKILL.md && ok "C2 SKILL.md title says v$V" || bad "C2 SKILL.md title does not say (v$V)"
else
  bad "C2 VERSION file missing"
fi

# C3 numbered TOC entries (from the Contents line ONLY) have matching ## headings
for f in references/*.md; do
  cont=$(grep '^Contents:' "$f") || continue
  for n in $(printf '%s\n' "$cont" | grep -oE '\[[0-9]+' | tr -d '[' | sort -un); do
    grep -qE "^## $n( |:|\$)" "$f" && ok "C3 $f TOC $n has a heading" || bad "C3 $f TOC entry $n has no ## heading"
  done
done

# C5 teams backend: dual-layer iron rule and both wave markers stay in the docs.
# The backend is opt-in, but once documented the "team queue != court" split is
# load-bearing - silent drift here re-opens the dual-truth hole it closed.
while IFS='|' read -r f needle; do
  [ -n "$f" ] || continue
  if grep -qF "$needle" "$f" 2>/dev/null; then
    ok "C5 $f has: $needle"
  else
    bad "C5 $f missing: $needle"
  fi
done <<'EOF'
references/crew.md|Teams backend
references/crew.md|NEVER a GO signal
references/crew.md|task=T2[teams:3]
references/crew.md|work-plan.md
references/crew.md|No `isolation: worktree`
references/crew.md|fallback:teams-unavailable
references/crew.md|Do not invent new loop-log keys
references/gate.md|never WRITE `.goal/`
references/crew.md|INLINED
references/teams.md|own inbox file
references/gate.md|task=T2[teams:3]
references/teams.md|TeammateMessage
references/teams.md|goal_team.sh
references/teams.md|NEVER a GO signal
scripts/goal_team.sh|TeammateMessage
SKILL.md|task=T2[teams:3]
SKILL.md|禁止
SKILL.md|worktree
references/gate.md|R9
references/gate.md|R10
references/gate.md|R11
references/crew.md|native first
references/teams.md|detection, not by flag
references/teams.md|native wins
references/gate.md|probe:
references/teams.md|process-backed
references/teams.md|SendMessage
references/crew.md|never TeamDelete
references/crew.md|review_pending
SKILL.md|面板批准
references/gate.md|R12
SKILL.md|goal_audit.sh
references/crew.md|calibration anchors
SKILL.md|指标批评席
references/gate.md|R13
references/gate.md|DIVERGENCE
scripts/goal_gate.sh|DIVERGENCE
scripts/goal_ctl.sh|judge-score
scripts/goal_gate.sh|probe-failed
scripts/goal_gate.sh|score-regressed
scripts/goal_gate.sh|missing-strategy-delta
scripts/goal_ctl.sh|strategy-delta
scripts/goal_ctl.sh|(exit|objective):
scripts/goal_gate.sh|(exit|objective):
scripts/goal_ctl.sh|hash_std
references/teams.md|5.1b After approval lands
SKILL.md|唤醒+完整简报
SKILL.md|不要口语化成 crew
SKILL.md|minimize
references/gate.md|low-water for minimize
scripts/goal_gate.sh|minimize)  echo "minimize"
scripts/goal_gate.sh|dir=minimize
scripts/goal_ctl.sh|obj_dir
SKILL.md|盖戳时绑定
scripts/goal_ctl.sh|BIND at stamp
EOF

# C6 generality: case knowledge stays in examples/. Generic skill surfaces
# must not name any validation case or its domain recipe.
leak=$(grep -nE 'tsp-minimize|logcli|svg-dash|goal-loop-case-|波音|b747|threejs|THREEJS|goal-loop-747' \
        SKILL.md references/*.md scripts/*.sh tests/*.sh assets/* 2>/dev/null | grep -v '^tests/docs_consistency.sh:' || true)
if [ -z "$leak" ]; then
  ok "C6 no case knowledge leaked into generic skill files"
else
  bad "C6 case knowledge leaked: $leak"
fi

echo "== docs consistency: $([ $fail -eq 0 ] && echo CONSISTENT || echo DRIFT) =="
exit $fail
