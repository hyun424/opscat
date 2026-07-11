# P121-005: deterministic approval and L0-L3 local/sandbox intervention

## Goal

Define deterministic approval, WAL/CAS/idempotency/lease behavior, and
registered local/mock/sandbox operation envelopes for P121 prevention attempts.

## Contract

- Require L3 approval receipts to include current forecast, evidence receipt,
  counterfactual utility receipt, fatigue receipt, validation plan, rollback
  plan, idempotency key, lease, registry parity, operation envelope, and
  authority counter snapshot.
- Keep L0 observe/collect, L1 recommend, and L2 dry-run/static preflight
  non-mutating.
- Allow L3 to mutate only registered disposable local sandbox fixtures.
- Fail closed on unknown handlers, capability mismatches, production-like
  targets, staging-like targets, live connector fields, credential fields,
  L4+ actions, shell/subprocess fields, free-form action prose, LLM commands,
  stale registry hashes, approval mismatch, and nonzero authority counters.
- Replay duplicate idempotency keys without duplicate effects.

## Acceptance

No L3 attempt can start without deterministic approval and all required
receipts. L0-L2 remain non-mutating. L3 cannot escape registered disposable
local sandbox fixtures. Authority counters remain exactly zero for production
and nonlocal dimensions.

## Stop Rules

Stop if approval can be bypassed, if L0-L2 can mutate, if L3 can target
anything outside disposable local sandbox fixtures, if idempotency can produce
duplicate effects, if stale registry hashes are accepted, or if the ticket
introduces auth, credentials, live connector calls, production/staging
mutation, connector writes, Kubernetes/cloud/database/network mutation, online
policy writes, shell/subprocess execution, free-form action execution, LLM
command execution, L4+ authority, or nonzero authority counters.
