# P182 Test Spec

## Claims Under Test

1. Auto-approval is limited to exact reviewed staging actions and targets.
2. Kill switch is authoritative and tested before and during operation.
3. Auto-demotion fails closed on health, evidence, policy, fatigue, or rollback
   anomalies.
4. Every action reaches verified success, rollback closure, or human takeover
   closure.

## Matrix

- Policy tests for allowed/disallowed action, target, provider, confidence,
  evidence, freshness, lease, and concurrency.
- Kill-switch tests for global, target-local, stale, raced, and resumed states.
- Demotion tests for P179 health failure, stale evidence, provider outage,
  confidence drop, fatigue breach, rollback uncertainty, and ledger corruption.
- E2E staged campaign with bounded auto-approved actions and daily operator
  review.
- Three separate-date campaign tests, each including preflight and in-run global
  and target-local kill-switch, auto-demotion, rollback, and human-takeover drills.
- Negative tests for production labels, target expansion, free-form command/URL,
  duplicate request IDs, expired leases, and forged receipts.

## Pass Gates

- `production_mutation_count == 0`.
- `independent_campaign_count >= 3` and
  `campaign_distinct_utc_date_count >= 3`.
- `min_safely_closed_auto_approved_actions_per_campaign >= 20` and
  `total_safely_closed_auto_approved_action_count >= 60`.
- `reviewed_action_family_count >= 2` and `staging_target_count >= 2`.
- `target_escape_count == 0`.
- `unsafe_action_count == 0`.
- `duplicate_side_effect_count == 0`.
- `unresolved_effect_count == 0`.
- `failed_rollback_closure_count == 0`.
- `failed_human_takeover_count == 0`.
- `credential_leak_count == 0`.
- `failed_kill_switch_drill_count == 0`.
- `failed_auto_demotion_count == 0`.
- `global_kill_switch_drill_count >= 3`;
  `target_local_kill_switch_drill_count >= 3`;
  `active_operation_cancel_or_isolate_drill_count >= 3`;
  `auto_demotion_drill_count >= 9`;
  `distinct_auto_demotion_anomaly_class_count_per_campaign >= 3`;
  `rollback_drill_count >= 6`; and `human_takeover_drill_count >= 6`.
- `required_receipt_completeness == 1.0` (100%) and
  `missing_malformed_unbound_receipt_count == 0`.
- `conditional_event_without_trigger_or_not_triggered_receipt_count == 0`.
- `kill_switch_dispatch_block_lease_revoke_p100_seconds <= 5`.
- `active_operation_cancel_or_isolate_p100_seconds <= 10`.
- `auto_demotion_p100_seconds <= 30` and
  `post_demotion_action_dispatch_count == 0`.
- `max_concurrent_auto_actions <= 1`.
- `release_evidence_contains_not_general_operator_replacement == true` and
  `forbidden_production_or_general_autonomy_claim_count == 0`; the validated
  literal is `not general operator replacement`.
