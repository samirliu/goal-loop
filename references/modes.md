# Modes, arguments, and the in-session helper

Contents: [1 invocation grammar] [2 the three modes] [3 auto approval] [4
pre-stamp smoke rule] [5 evidence directory] [6 goal_ctl.sh].

## 1 Invocation grammar

```
/goal-loop [flags] <objective>
  --mode=quick|standard|deep   default: standard
  --max-iterations=N           overrides the mode's budget
  --min-acs=N                  floor for the contract's AC count
  --auto                       no-approval mode (section 3)
```

Unknown flags are an error: report them, never silently ignore.

## 2 The three modes

| mode | max_iterations | AC count | panel | extra duty |
|---|---|---|---|---|
| quick | 3 | 2-4 | 2x mech + 1x req | - |
| standard | 6 | 4-6 | 2x mech + 1x req | - |
| deep | 12 | 6-10 | 2x mech + 1x req | adversarial seat, below |

Deep mode's adversarial duty: every iteration, one checker seat receives ONE
check plus the assignment to make it FAIL legitimately - a real input, edge,
or environment that breaks it. A caught FAIL is a success: it routes through
fix-and-recheck and exercises the loop's repair path. A deep run whose every
iteration passes everything on the first sweep has NOT earned its exit.

## 3 Auto approval (--auto)

The contract is still written and still shown in full in the conversation -
but the controller stamps it immediately (`approved: <hash> <date> auto`) and
starts iterating without waiting for sign-off. Guardrails that do NOT bend:

- the stamp still freezes the AC section (R3) - no mid-run criteria edits;
- false-complete counting, evidence rules and the gate are unchanged;
- the loop-log block and the delivery both carry `approval=auto` so a human
  can audit after the fact;
- irreversible-side-effect objectives are refused in auto mode exactly as in
  gate mode (When-NOT-to-run is not waivable by a flag).

Default remains gate mode: present the contract, wait for explicit approval.

## 4 Pre-stamp smoke rule (contract authoring)

Before stamping, smoke-run EVERY named check command once, against a probe or
the in-progress artifact. A check that cannot execute as written (wrong tool
name, missing subcommand, unavailable binary) is rewritten at contract time -
never stamped and later "disclosed-equivalent"-ed by the panel. This rule
exists because it failed once: a contract named `officecli read ...` and the
installed CLI had no `read` subcommand.

## 5 Evidence directory (.goal/evidence/)

Checks that GENERATE files (screenshots, dumps, renders) write them under
`.goal/evidence/`. It lives under `.goal/`, which the tree digest excludes -
so re-running a check never moves the binding and never risks a
verdicts-stale NO-GO. In-tree evidence outputs are a contract-design fault.

## 6 goal_ctl.sh (in-session controller helper)

One entry point per bookkeeping step; the script is the controller's writing
hand and decides nothing (the gate stays the only arbiter):

```
bash scripts/goal_ctl.sh init  --project DIR [--max-iterations=N]   # seed .goal/
bash scripts/goal_ctl.sh stamp --project DIR [--auto]               # hash + stamp, refuses re-stamp
bash scripts/goal_ctl.sh bind  --project DIR < verdict-lines        # id|verdict|iter|digest|command|evidence
bash scripts/goal_ctl.sh close-iteration --project DIR --task ID \
     --files LIST --checks-pass N --checks-fail N --checks-unverifiable N \
     [--progress yes|no] [--exit-signal yes|no] [--error-signature none] \
     [--false-complete no] [--no-gate]     # digest + block + state + gate relay
```

`close-iteration` recomputes the tree digest, appends the loop-log block,
bumps state (streak/breaker bookkeeping included) and relays
`goal_gate.sh --check` unless `--no-gate`. Two Bash calls per iteration
instead of five; the gate's exit code remains the only authority.
