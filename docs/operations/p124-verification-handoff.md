# P124 Verification Handoff

Schema marker: `p124.verification_handoff.v1`.

Current status: planning complete when this artifact set is accepted;
implementation evidence is pending.

This handoff is the planned evidence template for future P124 verification. It
does not claim source implementation, tests, production accuracy, human
replacement, credentialed access, or mutation authority.

## Scope

Verification must prove only the P124 scope:

- hidden-truth isolation;
- human baseline protocol and adjudication;
- judgment quality scoring and calibration;
- per-slice metrics with denominators and uncertainty;
- failure analysis and claim controls;
- exact-zero authority counters.

## Required Inventory

Future executors must provide changed-file inventory grouped by case schemas,
hidden-truth manifests, baseline protocols, scoring, reports, claim controls,
docs, tests, and generated verification evidence.

## Required Evidence

The completed handoff must include:

- hidden-truth leakage check results;
- human baseline reviewer and adjudication metadata;
- inter-rater agreement results;
- scoring rubric and metric definitions;
- per-slice denominators and confidence intervals;
- failure cases and abstention analysis;
- public claim traceability;
- exact-zero authority counters.

## Dependencies

- Depends on P123 replay receipts for real-artifact shadow inputs when used.
- Blocks P125 resilience claims if quality-report inputs are untraceable.
- Does not unblock live connector, credential, auth, staging, production, or
  mutation authority.

## Stop Conditions

Block verification handoff on hidden-truth leakage, self-reviewed baselines,
aggregate-only metrics, missing denominators, missing uncertainty, stale
holdout evidence, operator-replacement claims, production accuracy claims, or
nonzero authority counters.

