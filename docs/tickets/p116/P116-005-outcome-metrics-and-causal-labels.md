# P116-005: outcome metrics and causal labels

## Goal

Define verifier-owned outcome labels and metrics for whether a lab action
causally improved service health.

## Contract

- Labels include `verified_helpful`, `verified_harmful`, `no_effect`,
  `wrong_action_recovered`, `naturally_recovered`, `rollback_verified`,
  `inconclusive`, and `invalid`.
- Recovery time is measured from first unhealthy observation to sustained
  healthy post-window.
- Helpful labels require primary SLO improvement versus matched no-action and
  natural-recovery controls by a predeclared effect size.
- Harm labels take precedence over helpful labels when guardrails regress,
  recurrence appears, rollback fails, or collateral damage occurs.
- Metrics publish numerator, denominator, nullable value, threshold, family,
  fixture version, split, and seed set.

## Acceptance

Metric tests reject aggregate-only success, missing denominators, hidden family
failures, copied success fields, and optimistic labels without comparable
controls.
