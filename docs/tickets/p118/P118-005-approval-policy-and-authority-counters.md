# P118-005: approval policy and authority counters

## Goal

Define deterministic local approval policy and exact authority counters for
P118 local/mock/sandbox L0-L3 operations.

## Contract

- Approve only signed, unexpired, unrevoked P115 action packs selected by P117,
  bound to local/mock/sandbox fixture targets, at L0-L3, with valid
  prerequisites, no contraindications, validation plan, rollback plan, lease
  receipt, WAL receipt, CAS version, and idempotency key.
- Fail closed for auth-bearing, credential-bearing, production-like, stale,
  unsigned, revoked, contraindicated, above-L3, missing-validation,
  missing-rollback, stale-receipt, forged-receipt, or policy-hash-missing
  operations.
- Maintain exact counters for auth, credentials, executor calls, shell,
  subprocess, Kubernetes, cloud, database mutation, production adapters,
  network mutation, online policy writes, production mutation, approvals,
  rejections, rollback attempts, duplicate action attempts, and fail-closed
  decisions.
- Treat any nonzero non-local authority counter as a release blocker.

## Acceptance

Approval decisions are deterministic and byte-stable. Bypass attempts are
accepted 0 times, L4+ requests are accepted 0 times, production-like target
strings are accepted 0 times, and all non-local authority counters remain
exactly zero.

## Stop Rules

Stop if approval can be forged, policy hashes are optional, stale receipts pass,
production-like targets pass, auth or credentials are introduced, L4+ actions
pass, policy fails open, or authority counters are approximate.
