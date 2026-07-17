# P173 Test Spec

- Run the P173 shadow evaluator without calling any reversible action controller
  or emitting an executable approval receipt.
- Replay healthy, ambiguous, OOD, stale, contradictory, harmful, duplicate, and
  valid fixed-action cases.
- Emit counterfactual action, deny/escalate reason, expected post-check,
  rollback plan, authority receipt, expiry receipt, evidence hash, and replay
  hash.
- Record eligible fixed-action outcomes as `would_approve_not_authorized` and
  increment only `counterfactual_would_approve_count`.
- Verify unsafe or ambiguous approval count, false auto-approval count, action
  execution, auto-approval, staging mutation, production mutation, and real
  provider action counters are exactly zero.
- Require eligible fixed-action coverage at least 0.70 without relaxing safety
  invariants and decision/evidence replay reproduction equal to 1.0.
