# Terminal source139 regression, 2026-11-12

Both complete Python runs failed. The later focused fixture checks below preserve these full-run outcomes; they do not establish a green full run for the current combined source or a 9+ conclusion.

| Frozen source139 check | macOS 26.3.1 / Python 3.14.8 | Linux aarch64 / Python 3.12.14 / uid 65534 |
| --- | --- | --- |
| Python | **248 tests, 1 failure**, no skips; 596.695s | **248 tests, 1 failure, 2 skips**; 831.007s |
| Shell | 603 passed | 603 passed |
| Parser | 78 passed | 78 passed |
| Contract forge | 10 passed | 10 passed |
| Docs | Consistent, exit 0 | Consistent, exit 0 |
| ShellCheck | No run claimed | Exit 0; empty diagnostic output |

The macOS failure was `test_fresh_future_origin_and_supervision_marker_cannot_grant_time`: its caller elapsed time was 4.250748541904613s against the unchanged 4.2s threshold. The Linux failure was `test_guard_drops_stdout_and_high_lock_descriptor`: inherited `RLIMIT_NOFILE=(1024,1048576)` made `F_DUPFD` with minimum 2000 fail during test setup, before the production guard call. The two Linux skips require an actually infinite hard FD limit. Complete original outputs, exit statuses and environment records are preserved in [full-results.tar.xz](full-results.tar.xz); [matrix.json](matrix.json) provides the machine-readable summary.

The frozen [source139.tar.xz](source139.tar.xz) contains exactly the 139 paths in [source-manifest.json](source-manifest.json), plus original run metadata and an archive-time hash check. All 139 hashes matched before and after packaging. Six generated, unmanifested `__pycache__` files were excluded and listed in [snapshot-check.json](snapshot-check.json); no snapshot files were removed or changed. Source file content is preserved; archive entry ownership and timestamps are normalized. The source includes the existing W7 raw archive because it is explicitly part of the frozen manifest. It excludes unlisted user `.archify` and agent-harness documents.

Two test-fixture followups are archived separately in [targeted-followups.tar.xz](targeted-followups.tar.xz):

- **Gate entry:** the fresh cases now record an independent monotonic timestamp immediately before actual `_access_exec`, while retaining caller elapsed time as a diagnostic. The 4.2s threshold, real two-second view preparation and borrowed-lock elapsed origin remain. Five focused tests returned exit 0 in 25.898s. Negative controls passed with zero dispatched checks, rejected an origin reset even with zero dispatch, and rejected legacy read-then-new-three-seconds behavior at an independently observed 5.101530583808199s. The latest index is `gate-entry/history/goal-gate-entry-access-anchor-evidence-20261112.json`; the corresponding `*-after`, `*-boundary-mutations` and preserved full-failure JSON are retained. Earlier JSON in `history/` records earlier source/test versions, including the 5.839658624958247s original production counterexample; it is not the source139 fixture comparison.
- **Owner guard:** the child raises a finite soft FD limit to 2001 when its real hard limit permits, records before/after limits, and still proves actual FD >=2000, guard/parent alive, stdout EOF and lock release. Real insufficient hard limits explicitly skip without claiming FD2000 measurement. The macOS low-soft before/after pair and the 12 passed / 2 skipped / 6 subtests targeted result are retained. The Linux uid-65534 overlay returned exit 0: 5 tests, no failures/errors, 2 genuine infinity-capability skips, 2.367257251s. It actually observed FD2000 and all descriptor/lifecycle checks true with limits `[1024,1048576]` changing to `[2001,1048576]`. Production owner-watch SHA stayed `fe48a659921070f08c1ee8342de51ae49ee5a428a2a325b6d4d8189ea0d191cd`.

The first Linux overlay test log reported success, but its diagnostic wrapper then returned exit 1 with `TypeError: Object of type GroupGuard is not JSON serializable`. Both wrapper versions and the original test log are retained. `owner-guard/linux-overlay/tool-receipts-transcription.json` records the tool-reported exception and final exit 0; it is explicitly a transcription, not a separately captured raw stderr file. The corrected report and second test log are also present. The original Linux full-run failure remains in `full-results.tar.xz`.

[post-full-delta.json](post-full-delta.json) separates the two test corrections from four namespace-followup files: `.claude-plugin/plugin.json`, `scripts/goal_host.py`, `references/host.md`, and `tests/test_host.py`. Their captured bytes and exact source139-to-current diffs live under `post-full-delta/` in the focused archive. These six changed files do not belong to the frozen full-run source. The namespace production change inherits no full-suite result from this matrix.

[archive-index.json](archive-index.json) records archive hashes, payload counts and capture time; [SHA256SUMS](SHA256SUMS) covers all top-level artifacts. Each compressed archive also contains an `ARCHIVE-MANIFEST.json` with per-file hashes and original paths. This archival task ran no tests, models or CLI experiments, and changed no production/test source or previous evidence archive.
