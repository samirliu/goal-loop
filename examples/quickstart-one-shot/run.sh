#!/usr/bin/env bash
# quickstart-one-shot - the MINIMUM ceremony path, proven runnable.
# One AC, one worker, no interfaces.md, no baseline, no crew. This is what a
# small task should cost: contract with a single failable check, one stamp,
# one wave, one gate call. Every extra protocol surface is optional and only
# the objective earns it.
#
# Run:  bash examples/quickstart-one-shot/run.sh
# Exit 0 = the smallest legal loop delivered. No API, no network.
set -u
here=$(cd "$(dirname "$0")/../.." && pwd)   # skill root
CTL="$here/scripts/goal_ctl.sh"
GATE="$here/scripts/goal_gate.sh"

if ! command -v bash >/dev/null 2>&1; then echo "bash required" >&2; exit 1; fi
P=$(mktemp -d); trap 'rm -rf "$P"' EXIT
echo "== quickstart: project=$P"

# 1) init + contract: one AC whose check can genuinely FAIL.
#    The artifact is a shell script so the example runs anywhere bash runs.
bash "$CTL" init --project "$P" >/dev/null
printf '#!/usr/bin/env bash\nexit 0\n' > "$P/tool.sh"
cat > "$P/.goal/goal.md" <<'EOF'
# Goal contract - tiny fix

## Objective

make tool.sh exit clean.

## Exit policy

exit: threshold

## Acceptance criteria

- AC-1 | tool.sh exits 0 | check: `bash tool.sh` | expected: exit=0

## Approval

approved: PENDING
EOF
bash "$CTL" stamp --project "$P" --auto >/dev/null

# 2) one wave, one worker. close-iteration runs the gate itself and exits
#    with the gate's code - a second --check is unnecessary ceremony.
bash "$CTL" close-iteration --project "$P" --task T1 --files tool.sh \
  --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 \
  --progress yes --exit-signal yes
grc=$?
echo "quickstart: gate rc=$grc (0=GO)"
[ "$grc" -eq 0 ] && echo "quickstart: PASS - one-AC path delivered"
exit "$grc"
