#!/usr/bin/env bash
# case-independent-repro — domain-neutral multi-AC reproduction kit.
# NOT author-domain (no TSP / CLI / SVG). Proves the gate on a stranger's
# shape of task: one deliverable, three failable checks, NO-GO then GO.
#
# Run:  bash examples/case-independent-repro/run.sh
# Exit 0 = both phases delivered (broken product denied, fixed product GO).
set -u
here=$(cd "$(dirname "$0")/../.." && pwd)   # skill root
SRC="${GOAL_CASE_SRC:-$HOME/goal-loop-case-independent-repro}"
CTL="$here/scripts/goal_ctl.sh"
GATE="$here/scripts/goal_gate.sh"

if [ ! -d "$SRC/verify" ]; then
  echo "case tree missing: $SRC (clone/create goal-loop-case-independent-repro)" >&2
  exit 4
fi

P=$(mktemp -d); trap 'rm -rf "$P"' EXIT
echo "== independent-repro: project=$P"

# Copy the frozen case tree (fixtures + checks + deliverable).
cp -r "$SRC"/. "$P"/
rm -rf "$P/.goal"
bash "$CTL" init --project "$P" >/dev/null

# Contract is authored in the case tree (three ACs, all can FAIL).
cp "$SRC/.goal/goal.md" "$P/.goal/goal.md" 2>/dev/null || true
if [ ! -f "$P/.goal/goal.md" ]; then
  echo "contract missing in case tree" >&2
  exit 4
fi

# Smoke every named check before stamp (protocol Step 1).
echo "-- pre-stamp smoke (checks must be runnable)"
for c in verify/run_ok.sh verify/match_golden.sh verify/rejects_bad.sh; do
  bash "$P/$c" >/dev/null 2>&1; echo "   smoke $c -> $?"
done

bash "$CTL" stamp --project "$P" --auto >/dev/null

# Phase A: deliberately break the deliverable — gate must refuse.
echo "-- phase A: broken product must NOT go"
printf '#!/usr/bin/env bash\necho wrong\nexit 0\n' > "$P/csv_summarizer.sh"
bash "$CTL" close-iteration --project "$P" --task T1 --files csv_summarizer.sh \
  --checks-pass 0 --checks-fail 3 --checks-unverifiable 0 \
  --progress no --exit-signal yes --false-complete yes \
  --strategy-delta 'rewrite summarizer to match golden and reject bad input'
arc=$?
echo "phase A gate rc=$arc (expect non-zero)"
[ "$arc" -ne 0 ] || { echo "FAIL: broken product got GO"; exit 1; }

# Phase B: restore the real deliverable — gate must accept.
echo "-- phase B: fixed product must GO"
cp "$SRC/csv_summarizer.sh" "$P/csv_summarizer.sh"
bash "$CTL" close-iteration --project "$P" --task T2 --files csv_summarizer.sh \
  --checks-pass 3 --checks-fail 0 --checks-unverifiable 0 \
  --progress yes --exit-signal yes
brc=$?
echo "phase B gate rc=$brc (expect 0)"
[ "$brc" -eq 0 ] && echo "independent-repro: PASS — denial then delivery both real"
exit "$brc"
