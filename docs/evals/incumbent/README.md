# Accepted artifact restoration

The production entry points archive an accepted artifact, record a candidate
that changes and deletes files, and restore the accepted bytes and mode. A new
gate invocation returns GO on the restored tree. The tests also exercise an
out-of-scope user file, a later edit inside the owned scope, and interruption
after the first replacement.

The interrupted run leaves its recovery journal visible. A regular gate call
refuses it. Recovery detects the later user edit before applying any remaining
writes. Once the conflicting version is resolved, the same recovery completes
and a fresh gate passes.

The [manifest](manifest.json) binds the exact source files and [test output](restored-check.txt).
To replay, extract the baseline named by the [W5 manifest](../crew-cost/manifest.json)
into an isolated directory, apply its implementation patch, then apply this
directory's incremental patch. Run `python3 -B tests/test_incumbent.py -v`.
That sequence was run and the reconstructed files matched their source hashes.

The implemented scope is regular files and missing leaves under existing
directories. Capture of a baseline requires a full GO. Paired evaluation of
optimization intermediates remains part of W6.
