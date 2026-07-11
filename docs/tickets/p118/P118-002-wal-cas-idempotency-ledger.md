# P118-002: WAL, CAS, and idempotency ledger

## Goal

Define the append-only WAL, compare-and-set lifecycle transitions,
idempotency-key behavior, hash chaining, terminal replay, and duplicate-action
prevention for P118 operations.

## Contract

- Record every operation transition in an append-only WAL with monotonic
  positions, receipt hashes, previous-entry hashes, operation IDs, lifecycle
  states, CAS versions, lease owner IDs, and authority counter snapshots.
- Advance operation state only through legal CAS transitions from the current
  version.
- Bind idempotency keys to operation ID, P117 selected action-pack ID, P115
  digest, fixture target, precondition hash, and payload hash.
- Return the existing operation state for duplicate idempotency keys with the
  same payload hash.
- Fail closed for conflicting duplicate idempotency keys, stale CAS versions,
  broken WAL hash chains, reopened terminal states, or illegal lifecycle edges.
- Make terminal replay read-only and byte-stable; replay must not re-run
  precheck, action, postcheck, rollback, or report write effects.

## Acceptance

WAL replay reconstructs terminal status, evidence hashes, CAS versions,
idempotency results, and exact counters without drift. CAS conflict acceptance
is 0, conflicting idempotency-key acceptance is 0, and duplicate action count is
0.

## Stop Rules

Stop if WAL entries can be reordered unnoticed, CAS conflicts can advance
state, terminal states can reopen, idempotency keys can trigger duplicate
actions, replay mutates state, or authority counters drift from exact zero.
