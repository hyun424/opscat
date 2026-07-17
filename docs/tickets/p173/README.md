# P173 Tickets

Dependency: canonical P172 active investigation evidence. Owner surface:
P173-only shadow evaluator, deterministic approval-rule reuse, replay fixtures,
and P173 documentation only until implementation begins.

1. **P173-001 — Shadow evaluator boundary.** Reuse deterministic approval rules
   without calling a reversible action controller, executing an action, or
   emitting an executable approval receipt.
2. **P173-002 — Counterfactual receipt.** Emit counterfactual action,
   deny/escalate reason, expected post-check, rollback plan, authority receipt,
   expiry receipt, evidence hash, and replay hash.
3. **P173-003 — Outcome semantics.** Represent eligible cases as
   `would_approve_not_authorized` and count them in
   `counterfactual_would_approve_count`, never `auto_approval_count`.
4. **P173-004 — Replay matrix.** Cover healthy, ambiguous, OOD, stale,
   contradictory, harmful, duplicate, and valid fixed-action cases with
   deterministic replay.
5. **P173-005 — Safety evidence.** Done when unsafe or ambiguous approval count,
   false auto-approval count, action execution, auto-approval, staging mutation,
   production mutation, and real provider action counters are exactly zero, with
   eligible coverage at least 0.70 and replay reproduction equal to 1.0.
