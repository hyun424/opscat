# P121-006: validation, rollback, causal attribution, and recurrence reduction

## Goal

Define validation windows, rollback receipts, causal attribution, rejected
credit reasons, harm accounting, and recurrence-reduction reports.

## Contract

- Declare validation probes, rollback probes, pre-intervention baselines,
  post-intervention windows, counterfactual controls, and rollback readiness
  before L3 intervention.
- Trigger local rollback when validation fails, harm appears, collateral
  regression appears, attribution is ambiguous and rollback is available, or
  rollback policy requires fail-closed recovery.
- Report treatment/control comparability, natural recovery status, avoided
  impact, useful delay, harm score, causal confidence, attribution reasons,
  rejected credit reasons, rollback status, and replay receipt.
- Measure recurrence reduction with matched pre/post windows, matched systems
  or families, denominator-visible slices, and confidence intervals.
- Treat rollback recovery as safety recovery, not prevention success.

## Acceptance

Validation and rollback are preconditions for L3 approval. Harmful, ambiguous,
collateral-regression, failed-postcheck, or rollback-failure outcomes remain
release-visible. Recurrence reduction is reported per system/family with
confidence intervals and cannot be claimed from a single aggregate count.

## Stop Rules

Stop if validation or rollback plans can be missing, if rollback failures can
be hidden, if natural recovery or rollback recovery can be credited as
prevention success, if ambiguous attribution can be promoted, if recurrence is
claimed without matched windows, or if the ticket adds auth, credentials, live
connectors, production/staging mutation, L4+ authority, shell/subprocess
execution, free-form action execution, or nonzero authority counters.
