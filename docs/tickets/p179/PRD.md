# P179 PRD - HA and Self-Monitoring

## Objective

Prove OpsCat can supervise itself well enough to run long evaluations without
silent stalls, stale authority, duplicate decisions, or unobserved failures.

## Product Requirements

- Emit self-health receipts for every runtime dependency.
- Maintain generation-bound ledgers across restart/resume.
- Demote to shadow/human-required on health uncertainty.
- Exercise kill switch and deadman before and during qualification.

## Out of Scope

Production HA deployment, product auth, payment, and new action families.

## Acceptance Criteria

- No heartbeat gap exceeds policy without a demotion receipt.
- Restart/resume is proven with no duplicate decisions.
- Every injected supervisor failure fails closed.
- Maximum claim is `ha_self_monitoring_staging_qualified`.
