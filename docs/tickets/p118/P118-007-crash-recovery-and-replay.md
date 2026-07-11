# P118-007: crash recovery and replay

## Goal

Define crash points, retry semantics, orphan inventory, lease recovery,
duplicate-action prevention, and read-only replay consistency for P118.

## Contract

- Test crashes before and after precheck, action, postcheck, rollback, rollback
  postcheck, terminalization, and report write.
- Recover from WAL, CAS, idempotency, and lease receipts.
- Inventory orphaned leases, partial evidence, pending rollback, incomplete
  reports, and unresolved terminal states.
- Retry only when deterministic receipts prove retry safety and lease ownership.
- Prevent duplicate action execution through idempotency keys, CAS checks, and
  WAL receipts.
- Make terminal replay read-only and stable across repeated runs.
- Preserve exact counters for crash recoveries, retries, orphan recoveries,
  duplicate action attempts, rollback attempts, rollback failures, and all
  non-local authority classes.

## Acceptance

Every crash point reaches a deterministic terminal or recoverable state,
duplicate action count is 0, orphan inventory is complete, replay drift is 0,
and terminal replay never re-runs mutation logic.

## Stop Rules

Stop if crash recovery can skip rollback, retry without ownership, duplicate an
action, lose orphan evidence, mutate during replay, reopen terminal state, or
touch auth, credentials, production systems, live connectors, online policy, or
L4+ authority.
