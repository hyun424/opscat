# P120-006: calibration, abstention, and baseline comparison

## Goal

Evaluate cross-system calibration, abstention, investigate-more, no-action,
escalation, utility, and baseline deltas with identical denominators.

## Contract

- Fit calibration only on eligible development/calibration systems.
- Report ECE, confidence bins, abstention precision/recall,
  investigate-more correctness, no-action correctness, escalation correctness,
  and utility intervals overall, per system, and per family.
- Compare against safe-null, P117 deterministic selector, P117 NVIDIA proposal
  path if configured, P119 alert-only/no-action loop, retrieval or
  nearest-neighbor, and majority/prior baselines.
- Use identical denominators for OpsCat and every baseline.
- Treat NVIDIA proposals as proposal-only and gated by deterministic safety.

## Acceptance

Aggregate improvement cannot hide per-system harm, degradation, calibration
failure, abstention failure, harmful-action selection, unnecessary-action
selection, baseline regression, or authority drift. Escalation correctness is
1.0 for human-authorized, auth-bearing, L4+, production-like, or mutation-like
cases.

## Stop Rules

Stop if calibration uses holdout systems, low-confidence or utility-negative
cases are actioned, baseline denominators differ, safe-null or P117/P119
baselines are omitted, NVIDIA proposals gain authority, or aggregate reports
hide per-system failures.
