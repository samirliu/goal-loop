#!/usr/bin/env bash
# evidence_cache.sh - measurement-once helper (domain-patterns.md section 11).
# Runs a check command only when the hash of its INPUT FILES changed; on a
# cache hit it replays the previously captured stdout, so metric contracts
# (last stdout line = the number) keep working. Output is archived under
# .goal/evidence/ (digest-excluded). Generic: name the cache, list the key
# files, give any command - no project-specific logic in here.
#
# Usage (from the project root):
#   bash <skill>/assets/evidence_cache.sh <cache-name> -- <key-file>... -- <command...>
#
# Exit code: the command's exit code on a fresh run; 0 on a cache hit; 4 on
# usage errors. A failing run caches NOTHING (rerun happens until it passes).
set -u
export LC_ALL=C.UTF-8

name="${1:-}"; shift || { echo "EVIDENCE_CACHE: ERROR missing <cache-name>" >&2; exit 4; }
# Robust separator handling: the command is everything after the LAST "--";
# the key files are everything between the FIRST "--" and the LAST "--"
# (extra "--" tokens from caller-side quoting are tolerated and dropped).
args=("$@")
first=-1; last=-1
for i in "${!args[@]}"; do
  [ "${args[$i]}" = "--" ] || continue
  [ "$first" -lt 0 ] && first=$i
  last=$i
done
[ "$first" -ge 0 ] && [ "$last" -gt "$first" ] ||
  { echo "EVIDENCE_CACHE: ERROR usage: <cache-name> -- <key-file>... -- <command...>" >&2; exit 4; }
keys_args=()
for i in "${!args[@]}"; do
  [ "$i" -gt "$first" ] && [ "$i" -lt "$last" ] || continue
  [ "${args[$i]}" = "--" ] || keys_args+=("${args[$i]}")
done
cmd_args=("${args[@]:$((last+1))}")
[ "${#keys_args[@]}" -ge 1 ] || { echo "EVIDENCE_CACHE: ERROR no key files" >&2; exit 4; }
[ "${#cmd_args[@]}" -ge 1 ] || { echo "EVIDENCE_CACHE: ERROR empty command" >&2; exit 4; }
for k in "${keys_args[@]}"; do
  [ -f "$k" ] || { echo "EVIDENCE_CACHE: ERROR key file missing: $k" >&2; exit 4; }
done

ev=".goal/evidence"
mkdir -p "$ev"
key=$(cat "${keys_args[@]}" | sha1sum | cut -c1-40)
kf="$ev/$name.key"
of="$ev/$name.out"

if [ -f "$kf" ] && [ -f "$of" ] && [ "$(cat "$kf" 2>/dev/null)" = "$key" ]; then
  echo "EVIDENCE_CACHE: hit ($name)"
  cat "$of"
  exit 0
fi

bash -c "${cmd_args[*]}" > "$of"
rc=$?
if [ "$rc" -eq 0 ]; then
  printf '%s' "$key" > "$kf"
  echo "EVIDENCE_CACHE: ran ($name)"
  cat "$of"
  exit 0
fi
echo "EVIDENCE_CACHE: command failed rc=$rc (nothing cached)" >&2
exit $rc
