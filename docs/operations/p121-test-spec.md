# P121 Adversarial Test Specification

This specification is the adversarial regression contract for the P121
implementation. It requires no runtime connector access, credentials, or
production mutation; all covered execution remains registered disposable local
sandbox L3 with exact-zero nonlocal authority.

## Contract and Authority

- Reject auth context, credentials, secrets, production target strings,
  staging target strings, shell text, subprocess commands,
  Kubernetes/cloud/database/network mutation fields, connector write fields,
  live connector names, online policy writes, free-form action prose, LLM
  command text, and L4+ action requests.
- Require exact-zero counters for every authority dimension listed in the P121
  roadmap.
- Reject L3 execution unless the target is a registered disposable local
  sandbox fixture with idempotency, lease, WAL/CAS, validation, rollback, and
  deterministic approval receipts.
- Reject any attempt to treat local/mock/sandbox evidence as production
  permission or production readiness.
- Reject release claims that exceed local/mock/sandbox proactive prevention
  readiness.

## Leading Indicators

- Reject indicators containing future outcome labels, hidden scorer fields,
  post-intervention telemetry, post-incident hindsight, consumed holdout data,
  unhashable artifacts, missing observed/window timestamps, missing source ID,
  missing system ID, missing service ID, missing evidence refs, or missing
  authority counter snapshots.
- Route stale telemetry, missingness, unresolved duplicate lineage,
  ambiguous system identity, poor data quality, and recurrence-only indicators
  without fresh current evidence to `investigate_more` or abstention.
- Preserve deploy/config refs, topology refs, recurrence refs, missingness
  status, data quality status, artifact hash, and authority snapshot.

## Forecast Horizons

- Reject negative lead time, zero useful lead time, missing horizon start,
  missing horizon end, `horizon_end <= horizon_start`, expired forecasts,
  stale forecast reuse, missing calibrated probability, missing calibration
  bucket, missing confidence interval, missing OOD status, missing abstention
  status, missing required evidence, or missing frozen config hash.
- Reject intervention candidates when calibration is outside promoted bounds,
  OOD status exceeds the actionable threshold, lead time is below the declared
  minimum, required evidence is unresolved, or the forecast expires before
  approval.
- Require horizon-bucket metrics and confidence intervals.

## Evidence Before Action

- Reject missing required evidence, stale evidence, contradictory evidence,
  post-cutoff evidence, post-intervention evidence, unhashable evidence,
  hidden production evidence, and evidence-bypass intervention.
- Require every preventive route to include evidence IDs or an explicit
  `investigate_more`/`abstain_fail_closed` reason.
- Require evidence requests to be local/mock read-only and frozen-taxonomy only.
- Treat every evidence-bypass attempt as a fail-closed release blocker.

## Counterfactual Prevention

- Detect missing controls, mismatched cohorts, weak treatment/control
  comparability, natural recovery, censored horizons, treatment harm,
  false-prevention credit, wrong no-action baseline, omitted investigate-more
  baseline, omitted safe-null baseline, and uncertainty ignored.
- Require utility to include avoided impact, useful delay, rollback cost,
  false-positive cost, alert-fatigue cost, operator burden, intervention harm,
  and uncertainty penalty.
- Reject prevention credit for natural recovery, rollback recovery, censored
  outcomes, ambiguous attribution, weak comparability, or false positives.
- Require outcome labels for prevented, delayed, unaffected,
  naturally recovered, harmful, false positive, inconclusive, censored,
  rollback recovered, and aborted fail-closed cases.

## False Positives and Alert Fatigue

- Detect duplicate forecast storms, near-duplicate forecasts within a horizon,
  per-service fatigue exhaustion, recommendation caps bypassed, L3 attempt
  caps bypassed, false positives hidden by one high-utility case, aggregate
  alert-burden masking, operator-burden budget bypass, and increasing evidence
  thresholds ignored under fatigue.
- Require fatigue ledgers to report forecast count, recommendation count,
  intervention attempt count, false-positive count, abstention count, operator
  acknowledgement count, duplicate suppression count, fatigue score, fatigue
  budget remaining, and suppression reason.
- Reject aggregate utility reports that hide per-system, per-service, or
  per-family fatigue and harm.

## Deterministic Approval and L0-L3 Execution

- Reject approval bypass, deterministic approval mismatch, stale registry hash,
  missing evidence receipt, missing utility receipt, missing fatigue receipt,
  missing validation plan, missing rollback plan, missing idempotency key,
  missing lease, unknown handler, capability mismatch, production-like target,
  live connector field, credential field, L4+ request, shell/subprocess field,
  free-form action prose, and LLM command field.
- Require L0-L2 to remain non-mutating.
- Require L3 to mutate only registered disposable local sandbox fixtures.
- Require duplicate idempotency keys to replay receipts without duplicate
  effects.
- Require durable WAL/hash-chain recovery under `flock`, CAS payload matching,
  active lease replay, restart recovery, and tamper failure.

## Validation, Rollback, and Attribution

- Reject missing validation plan, missing rollback plan, failed postcheck
  ignored, collateral regression ignored, rollback failure hidden, rollback
  postcheck missing, ambiguous attribution promoted, harm hidden, recurrence
  count without matched pre/post windows, and recurrence confidence interval
  omitted.
- Require validation and rollback probes to be declared before intervention.
- Require local rollback when validation fails, harm appears, collateral
  regression appears, or attribution is ambiguous and rollback is available.
- Require causal attribution to report treatment/control comparability,
  confidence, natural recovery, avoided impact, useful delay, harm, rejected
  credit, and recurrence delta.

## Holdouts and Leakage

- Reject system crossing splits, service crossing splits, time-window overlap,
  topology clone, generated variant leakage, replayed fault leakage, shared
  action-pack leakage, shared outcome-window leakage, near duplicate touching
  holdout, calibration on holdout, threshold tuning after first score, OOD
  tuning after first score, fatigue tuning after first score, utility tuning
  after first score, consumed holdout reused for tuning, and failed first score
  rescored as a pass.
- Require temporal and system holdouts to freeze before first score.
- Require the first score to consume the holdout even on failure.
- Reject frozen manifests that contain pre-scored pass/fail, forecast-correct,
  abstention-correct, utility, harm, false-positive, fatigue, rollback, or
  duplicate-effect fields. The manifest must contain raw visible inputs,
  scorer-only hidden truth, visible input hashes, and hidden truth hashes.

## Calibration and Abstention

- Detect overconfident wrong unseen forecasts, high-OOD without abstention,
  low-calibration L3 route, low-confidence action, utility interval crossing
  zero, abstention counted as failure instead of a safe outcome, skipped
  investigate-more, aggregate ECE hiding per-family failure, and missing
  confidence bins or denominators.
- Require calibration and abstention metrics overall, per system, per horizon
  bucket, and per incident family.
- Require abstention-on-OOD correctness and investigate-more correctness.

## Crash and Replay

- Crash before and after indicator capture, forecast creation, evidence
  acquisition, counterfactual decision selection, fatigue suppression,
  deterministic approval, L3 enqueue, L3 attempt begin/commit, validation,
  rollback begin/commit, attribution, recurrence update, and report write.
- Detect duplicate idempotency key, orphan lease, partial L3 attempt, pending
  rollback, report write interruption, replay mismatch, and authority counter
  mismatch.
- Require replay to reproduce decisions, approvals, fatigue suppression,
  utility, outcome labels, rollback receipts, attribution, recurrence metrics,
  and authority counters exactly.

## Release Evidence and Review

- Reject self-review, missing independent review, stale release evidence hash,
  missing release evidence, aggregate-only metrics, omitted denominators,
  omitted confidence intervals, nonzero authority counter, hidden false
  positives, hidden alert fatigue, hidden harm, hidden rollback failures,
  hidden calibration failures, hidden abstention failures, and omitted residual
  risks.
- Require independent verification distinct from planner and implementer.
- Reject production readiness, production-safe autonomous prevention, live
  connector authority, credentialed prevention, auth completion, operator
  replacement, L4+ authority, and production incident-reduction claims.

## Named RED Cases

- `future_outcome_label`, `hidden_scorer_field`, `post_intervention_telemetry`,
  `post_incident_hindsight`, `consumed_holdout_data`, `unhashable_indicator`,
  `stale_indicator`, `ambiguous_system_identity`, and
  `recurrence_without_fresh_evidence`.
- `negative_lead_time`, `zero_useful_lead_time`, `missing_horizon`,
  `expired_forecast`, `forecast_reused_after_expiry`,
  `low_calibration_actioned`, `high_ood_actioned`, and
  `required_evidence_missing`.
- `missing_required_evidence`, `stale_evidence`, `contradictory_evidence`,
  `post_cutoff_evidence`, `unhashable_evidence`, and
  `evidence_bypass_intervention`.
- `missing_control`, `mismatched_cohorts`, `weak_comparability`,
  `natural_recovery_credited`, `censored_horizon_credited`,
  `treatment_harm_promoted`, `false_prevention_credit`,
  `no_action_baseline_omitted`, and `safe_null_baseline_omitted`.
- `duplicate_forecast_storm`, `fatigue_budget_exhausted`,
  `recommendation_cap_bypassed`, `l3_attempt_cap_bypassed`,
  `aggregate_alert_burden_masking`, `false_positive_hidden`,
  and `operator_burden_budget_bypassed`.
- `approval_bypass`, `approval_receipt_mismatch`, `stale_registry_hash`,
  `production_like_target`, `live_connector_field`,
  `credential_field_present`, `l4_plus_request`, `shell_field_present`,
  `subprocess_field_present`, `freeform_action_prose`, and
  `llm_command_field`.
- `missing_validation_plan`, `missing_rollback_plan`, `failed_postcheck`,
  `collateral_regression`, `rollback_failure_hidden`,
  `rollback_postcheck_missing`, and `ambiguous_attribution_promoted`.
- `system_crosses_splits`, `time_window_overlap`, `topology_clone_leak`,
  `generated_variant_leak`, `near_duplicate_holdout`,
  `calibration_on_holdout`, `threshold_tuning_after_first_score`,
  and `consumed_holdout_rescored_as_pass`.
- `overconfident_wrong_unseen_forecast`, `abstain_required_but_actioned`,
  `investigate_more_required_but_skipped`, `aggregate_ece_hides_family`,
  and `confidence_bins_missing`.
- `crash_replay_mismatch`, `duplicate_idempotency_effect`, `orphan_lease`,
  `partial_l3_attempt`, `pending_rollback_lost`, and
  `authority_counter_replay_mismatch`.
- `self_review`, `missing_independent_review`, `aggregate_only_report`,
  `missing_denominator`, `confidence_interval_omitted`,
  `production_readiness_claim`, `operator_replacement_claim`, and
  `auth_completion_claim`.
- `auth_context_count_nonzero`, `credential_scope_count_nonzero`,
  `secret_material_count_nonzero`, `live_connector_call_count_nonzero`,
  `connector_write_call_count_nonzero`, `shell_execution_count_nonzero`,
  `subprocess_execution_count_nonzero`,
  `kubernetes_mutation_count_nonzero`, `cloud_mutation_count_nonzero`,
  `database_mutation_count_nonzero`, `network_mutation_count_nonzero`,
  `production_mutation_count_nonzero`, `l4_plus_action_count_nonzero`,
  `freeform_action_execution_count_nonzero`,
  `llm_command_execution_count_nonzero`, `unapproved_intervention_count_nonzero`,
  `evidence_bypass_count_nonzero`, and
  `rollback_missing_execution_count_nonzero`.

## Verification Profile

The P121 implementation provides targeted verification for leading
indicators, forecast horizons, evidence-before-action, counterfactual
prevention, false-positive controls, alert-fatigue controls, deterministic
approval, L0-L3 local/sandbox authority, validation, rollback, causal
attribution, recurrence reduction, temporal/system holdouts, calibration,
abstention, crash/replay, release evidence, exact-zero authority, and
independent verification.
