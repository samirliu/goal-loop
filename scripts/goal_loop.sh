#!/usr/bin/env bash
# Compatibility notice: the installed skill never starts another harness.
printf "%s\n" "GOAL_LOOP: external runner moved to the repository devtools/goal_loop.sh; opt in there explicitly. Use goal_ctl.sh and host-native tools in a skill session." >&2
exit 4
