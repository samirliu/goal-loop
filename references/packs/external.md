# Pack: external (FENCE · out-of-tree settle)

**Open when:** AC declares `external:` and/or `window:`.

**Invariant: FENCE** — out-of-tree facts settle via a cache, never by guessing.
**Also touches BIND** — deferred verdicts live in `.goal/evidence/deferred.rec` (digest-exempt by design).

Legacy aliases: `R18` → FENCE (settle) / BIND (`deferred.rec`).

---

## 1 Additive rule (never mask the floor)

- `external: \`<command>\`` settles the AC against an **out-of-tree** source (CRM, prod metrics, async reviewer).
- The in-tree `check:` floor **still runs**. A floor FAIL/BROKEN is decisive — “something is still pending” never masks a failure.

## 2 rc=75 = DEFERRED (wait, not deliver)

- External command `rc=75` means “not ready yet”. The AC settles DEFERRED.
- Claim routes `deferred-pending` / `hint=wait-for-source`. The loop keeps working; the claim does not deliver.
- DEFERRED never delivers and never covers an in-tree FAIL.

## 3 `window:` cache

- `window: <seconds>` (default 3600) is the cache validity for the external verdict.
- Inside the window, the recorded row in `.goal/evidence/deferred.rec` **is** the measurement (one query per window, not one per gate exit).
- `deferred.rec` fields: `id|verdict|tstamp|detail` — append-only; latest-per-id wins by (tstamp, file order).
- Evidence directory is digest-exempt: cache writes do not trip `check-mutated-ledger`.

## 4 Ratchet exemption (patience ≠ lie)

- An rc=2 whose reason is `deferred-pending:*` does **not** count toward the false-complete ratchet.
- NOTE: `deferred-wait-not-counted`. The ratchet catches lies, not waiting.

## 5 Stamp rules

- `window:` without `external:` is refused at stamp (window caches an out-of-tree check — declare both or neither).
- Only `window:` with no `external:` is a contract lie.

## 6 Authoring shape

Use for facts that live outside the tree and settle slowly. Do **not** use `external:` to replace a check that can run in-tree — that is measurement evasion, not settlement.
