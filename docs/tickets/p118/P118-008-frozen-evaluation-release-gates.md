# P118-008: frozen evaluation and release gates

## Goal

Define the frozen evaluation manifest, release evidence, independent review,
per-family metrics, exact authority counters, and fail-closed release gates for
P118.

## Contract

- Freeze operation fixtures, signed action packs, P117 selected IDs, policy
  config, validation probes, rollback probes, crash matrix, lease conflict
  cases, WAL/CAS/idempotency cases, seeds, split assignments, authority scan
  rules, release thresholds, and evidence bundle hashes before scoring.
- Report per-family metrics for contract rejection, signed-pack verification,
  approval, WAL, CAS, idempotency, leases, validation, rollback, crash recovery,
  replay, authority counters, and release evidence.
- Require independent review distinct from planner and implementer.
- Fail stale hashes, self-review, frozen evaluation tampering, post-score
  tuning, aggregate-only reports, missing rollback evidence, missing replay
  receipts, hidden production target strings, and any nonzero non-local
  authority counter.
- Preserve the product claim as local/mock/sandbox reactive execution substrate
  readiness only.

## Acceptance

One fresh frozen evidence set passes all release thresholds, independent review
finds no authority blocker, per-family metrics are present, release hashes
match, fail-closed receipts are complete, and auth/credential/production/
connector/online-policy/L4+ counters remain exactly zero.

## Stop Rules

Stop release if evaluation is self-reviewed, stale, tampered, tuned after first
score, missing per-family metrics, missing replay receipts, missing exact
counters, hiding production-like targets, weakening fail-closed behavior, or
claiming production-safe autonomous remediation.
