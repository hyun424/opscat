# P182 PRD - Limited Auto-Approval

## Objective

Qualify a narrow staging-only auto-approval lane for low-risk reversible actions
with immediate kill-switch and auto-demotion controls.

## Product Requirements

- Auto-approval is disabled by default and enabled only by explicit P182 policy.
- Eligible actions, targets, confidence thresholds, source requirements,
  freshness windows, leases, and rollback plans are pre-registered.
- Operator kill switch overrides every other state.
- Auto-demotion moves the system to shadow/human-required on any anomaly.
- Human takeover is rehearsed and evidence-complete.
- Receipt completeness covers policy, evidence, health, credential/target
  allowlist, lease, idempotency, dispatch, post-check, rollback plan,
  human-takeover readiness, final closure, and all conditional safety events;
  non-triggered conditional events use a signed `not_triggered` receipt.
- Kill-switch, active-operation isolation, and auto-demotion clocks begin at
  durable receipts and are evaluated at p100, not averages or percentiles that
  can hide a slow safety transition.

## Out of Scope

Production auto-approval, product auth, payment, tenant billing, new provider
adapters, and multi-target concurrent automation.

## Acceptance Criteria

- At least 3 independent campaigns run on separate UTC dates, each with >= 20
  successful or safely closed auto-approved actions; total actions >= 60 across
  >= 2 reviewed action families and >= 2 staging targets.
- Every action and drill is fully receipt-bound with required receipt completeness
  exactly 100%.
- Kill-switch dispatch-block/lease-revocation p100 is <= 5 seconds;
  active-operation cancellation or fail-closed isolation p100 is <= 10 seconds;
  auto-demotion p100 is <= 30 seconds.
- Across the minimum 3 campaigns, execute >= 6 kill-switch drills (global and
  target-local), >= 3 active-operation cancellation/isolation drills, >= 9
  auto-demotion drills spanning 3 anomaly classes per campaign, >= 6 rollback
  drills, and >= 6 human-takeover drills.
- No target escape, unsafe action, duplicate side effect, unresolved effect, or
  production mutation occurs.
- Failed rollback closure, failed human takeover, and credential leak counts are
  zero.
- Maximum claim is `limited_staging_auto_approval_qualified`.
- Release evidence contains the exact limitation
  `not general operator replacement` and records zero forbidden
  production/general-autonomy claims.
