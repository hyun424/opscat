# P173 Plan Review

Decision: approved for shadow approval and counterfactual action evaluation
only.

- Reuse deterministic approval rules, but implement a P173-only evaluator that
  never calls an action controller and never emits an executable approval.
- Emit counterfactual action, deny/escalate reason, expected post-check,
  rollback plan, authority receipt, and expiry receipt.
- Use `would_approve_not_authorized` for eligible cases and count them only in
  `counterfactual_would_approve_count`.
- Replay healthy, ambiguous, OOD, stale, contradictory, harmful, duplicate, and
  valid-action cases.
- Keep action execution, auto-approval, staging mutation, production mutation,
  and real provider actions exactly zero.
