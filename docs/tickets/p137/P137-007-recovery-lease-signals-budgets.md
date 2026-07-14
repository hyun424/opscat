# P137-007 - Recovery, lease, signals, CAS, hash namespace, and budgets

## Scope

Implement one-owner lease, deterministic durable ordering, crash recovery,
idempotent writes, CAS ledger replacement, signal-safe stops, hash namespace
validation, heartbeat/readiness/staleness, bounded continuous mode, and
budget/resource gates.

## Acceptance

- A nonblocking exclusive lease is acquired before any P137 state or fixed P136
  handoff bundle read; competitors perform zero ingest/request/classification.
- P137 checkpoint stores last accepted handoff bundle sequence and hash, rejects
  rollback/fork/torn replacement, and validates the fixed path plus parent
  fsync metadata.
- Handoff rejection tests explicitly cover bundle sequence rollback,
  same-sequence fork, previous-hash discontinuity, and torn fixed-path
  replacement.
- Ingest intent, incident, hypothesis, request, classification, and ledger writes
  follow the roadmap's fsync and directory-fsync order.
- Crash recovery after ingest intent, incident write, request write, and
  classification write before ledger CAS resumes exactly once without duplicate
  atoms, requests, classifications, or ledger entries.
- Equivalent deterministic bytes are idempotent; conflicting bytes, stale CAS
  predecessors, corrupted namespaces, and forked state fail closed.
- Bounded continuous mode uses finite max cycles, fixed handoff path/version
  polling, monotonic cadence, explicit heartbeat cases, explicit readiness and
  stale-handoff cases, and no unbounded monitoring claim.
- SIGINT/SIGTERM stop only at safe boundaries. Signal-driven
  `aborted_fail_closed` is authoritative only when classification write and
  ledger CAS succeed; otherwise classification is `none` with exact signal
  termination/error. Budget/resource exhaustion blocks without deletion or
  authority widening; resource cases define exact expected write deltas before
  failure.
