# P119-008: crash recovery, frozen evaluation, release evidence, and review

## Goal

Prove crash recovery, soak stability, frozen fail-closed evaluation, release
evidence completeness, exact authority counters, and independent verification
for P119.

## Contract

- Cover crash points before and after detection, WAL open, triage, diagnosis,
  evidence request, evidence receipt, selection, approval, operation enqueue,
  lease acquisition, local action attempt, validation, rollback, learning
  write, terminal report write, and replay export.
- Recover from WAL, CAS, idempotency, and lease receipts without hidden
  mutation or duplicate local action attempts.
- Inventory orphaned leases, partial evidence, partial operations, pending
  rollbacks, learning writes, and unterminated incidents.
- Freeze fixture registry, alerts, evidence episodes, P115 packs, P116
  controls, P117 selector config, P118 envelope and approval config, evidence
  taxonomy, state machine, budgets, escalation policy, probes, crash matrix,
  recurrence windows, learning rules, authority scans, seeds, split
  assignments, thresholds, and independent verification inputs before scoring.
- Record failed unseen results as negative evidence, not tuning data.

## Acceptance

Crash recovery is deterministic, duplicate local action attempts remain zero,
terminal replay is read-only and hash-stable, frozen evaluation meets
thresholds or records failure without retuning, release evidence includes
hashes, denominators, counters, authority scan, replay receipts, and
independent verification distinct from planner and implementer.

## Stop Rules

Stop release if evidence is self-reviewed, stale, tampered, tuned after first
score, missing replay receipts, missing per-family metrics, missing exact-zero
counters, hiding production-like targets, weakening fail-closed behavior, or
claiming production-safe autonomous remediation, live canary authority,
credentialed execution, operator replacement, or cross-system generalization.
