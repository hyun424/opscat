# P119-001: incident state machine and WAL contract

## Goal

Define the durable P119 incident envelope, lifecycle states, legal transitions,
WAL receipts, CAS transitions, idempotency keys, leases, terminal states,
timeline hashes, authority snapshots, and replay contract for
local/mock/sandbox execution only.

## Contract

- Define the incident schema with incident ID, schema version, alert
  fingerprint, current state, terminal status when terminal, WAL position, CAS
  version, idempotency key, budget snapshot, timeline hash, replay refs, and
  authority counter snapshot.
- Define states from `detected` through diagnosis, evidence acquisition,
  selection, approval, local execution, validation, rollback, learning,
  recovery, escalation, fail-closed abort, expiry, and orphan recovery.
- Permit only legal roadmap transitions and append fail-closed receipts for
  illegal transition attempts.
- Hash-chain WAL and timeline entries, and reconstruct current state through
  read-only replay without rerunning action logic.
- Attach exact-zero authority snapshots to every transition.

## Acceptance

State schema coverage is complete, illegal transitions fail closed, WAL hash
chain and CAS conflict tests pass, idempotent replays are stable, terminal
states cannot reopen without recurrence receipts, and all nonlocal authority
counters remain exactly zero.

## Stop Rules

Stop if the contract permits auth, credentials, production or staging mutation,
live connectors, online policy writes, shell/subprocess execution,
Kubernetes/cloud/database/network mutation, free-form action execution, L4+
authority, missing WAL receipts, optimistic terminal statuses, or mutable
incident identity.
