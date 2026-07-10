# P106-002 - Eligibility Adapter and Fallback Semantics

## Goal

Route only P104-sufficient evidence and P105-qualified forecasts to scoring.
Everything else returns a specific observe/escalate/fail-closed reason.

## Contract

- P104 must include `sufficient_for_policy_handoff=true`, fresh critical
  evidence IDs, no unresolved contradiction, and no natural recovery signal.
- P105 must pass the release prerequisite or a test fixture explicitly marked as
  local planner input.
- Supported families are limited to closed registry coverage.
- Forecast probability and false-alert denominator must be present before
  intervention scoring.

## Acceptance

Contradicting evidence, stale evidence, absent critical evidence, distribution
shift, unsupported family, low probability, missing false-alert denominator, and
natural recovery produce observe/escalate with operator-readable reasons.
