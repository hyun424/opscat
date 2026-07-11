# P119 Adversarial Test Specification

This specification is a planning handoff for future P119 implementation. It
does not require source-code edits during this documentation turn.

## Contract and Authority

- Reject incident envelopes missing incident ID, schema version, alert
  fingerprint, state, terminal status when terminal, WAL position, CAS version,
  idempotency key, budget snapshot, timeline hash, or authority snapshot.
- Reject unknown major schema versions, mutable incident IDs, unknown states,
  illegal transitions, terminal reopen attempts, missing replay refs, and
  missing fail-closed receipts.
- Reject auth context, credentials, secrets, production target strings, staging
  target strings, shell text, subprocess commands, Kubernetes/cloud/database/
  network mutation fields, live connector names, online policy writes,
  free-form action prose, LLM command text, and L4+ action requests.
- Require exact-zero counters for all nonlocal authority dimensions listed in
  the P119 roadmap.

## Detection, Correlation, and Budgets

- Deduplicate duplicate alert fingerprints into one active incident.
- Correlate near-duplicate fixture alerts without hiding distinct incidents.
- Reject stale alert replay that would reopen a terminal incident without a
  recurrence receipt.
- Route exhausted incident, per-state, evidence, approval, validation,
  rollback, retry, and WAL-size budgets to `investigate_more`, `escalated`,
  `expired`, or `aborted_fail_closed`, never forced action.
- Require every scheduler retry, pause, resume, expiry, and escalation to append
  timeline-visible budget receipts.

## WAL, CAS, Idempotency, and Leases

- Detect WAL corruption, broken hash chains, duplicate WAL positions, missing
  receipts, reordered receipts, and timeline hash drift.
- Reject CAS transitions from stale versions, skipped states, illegal edges, or
  terminal incidents.
- Return the existing incident state for duplicate idempotency keys with
  identical payload hashes.
- Fail closed when a duplicate idempotency key carries a different alert,
  evidence packet, decision episode, operation envelope, or target hash.
- Require a single valid owner lease before local execution, validation,
  rollback, learning write, terminal report write, or replay export.

## Evidence Acquisition and Diagnosis

- Reject evidence acquisition outside the frozen local/mock/sandbox taxonomy.
- Reject hidden production target strings, credentials, connector payloads,
  command text, external URLs, contaminated sources, and unhashable evidence.
- Route missing, stale, contradictory, or value-negative evidence to
  investigate-more, abstention, escalation, or fail-closed behavior.
- Preserve competing hypotheses and contradictions in the timeline.
- Require evidence receipts to bind source hashes, fixture IDs, acquisition
  budgets, and redaction receipts.

## Selection and Deterministic Approval

- Reject invented action IDs, free-form action IDs, P117/P115 mismatches,
  unsigned packs, invalid signatures, revoked packs, stale packs, digest
  mismatches, missing validation plans, missing rollback plans, missing
  prerequisites, unresolved contraindications, mutable target selectors,
  production-like targets, auth-bearing packs, and L4+ packs.
- Preserve `no_action`, `investigate_more`, `escalate`, and `abstain` as
  first-class outcomes.
- Reject forged approval receipts, stale approvals, missing policy hashes,
  fail-open policy, pre-approved flags, and policy configs changed after frozen
  evaluation.
- Require approval receipts to include selected frozen ID, target fixture,
  policy hash, budget snapshot, authority snapshot, and timeline ref.

## Local Execution, Validation, and Rollback

- Reject local operation attempts without approval receipt, operation envelope,
  WAL receipt, CAS success, owner lease, validation plan, rollback plan, and
  exact-zero authority counters.
- Detect split-brain leases, operation envelope mismatch, fixture target
  mismatch, duplicate action attempts, worker without owner receipt, and retry
  without receipt.
- Reject optimistic success when postcheck evidence is absent, stale,
  failed, contaminated, or outside the observation window.
- Require rollback on action failure, postcheck failure, guardrail breach,
  collateral harm, unsafe partial state, ambiguous recovery, or attribution
  uncertainty when rollback metadata exists.
- Require rollback evidence and rollback postcheck evidence before reporting
  rollback recovery.

## Causal Attribution, Recurrence, and Learning

- Reject action-success credit for natural recovery, no-action recovery,
  rollback recovery, missing controls, contaminated attribution windows, stale
  telemetry, incomparable baselines, or recurrence after recovery.
- Require attribution labels to distinguish `action_helped`,
  `no_action_recovered`, `natural_recovery`, `rollback_recovered`,
  `action_harmed`, `no_effect`, `ambiguous`, and `invalid`.
- Require recurrence windows to downgrade or reopen learning status and produce
  escalation when recovery cannot be trusted.
- Reject learning records that write online policy, change live thresholds,
  mutate production state, or tune the frozen evaluation after first score.

## War Room, Redaction, and Escalation

- Require every roadmap event class to appear in at least one adversarial case.
- Detect missing timeline events, out-of-order hashes, missing replay links,
  hidden failures, aggregate-only evidence, and redaction failures.
- Require escalation payloads for blocked operations, human-authorized
  operations, missing evidence, unresolved contradictions, utility intervals
  crossing zero, rollback failure, ambiguous validation, recurrence, authority
  drift, stale hashes, tampering, and self-review.
- Reject escalation payloads that include credentials, secrets, production
  mutation instructions, connector payloads, command text, or executable prose.

## Crash Recovery and Replay

- Crash before and after detection, WAL open, triage, diagnosis, evidence
  request, evidence receipt, selection, approval, operation enqueue, lease
  acquisition, local action attempt, validation, rollback, learning record
  write, terminal report write, and replay export.
- Verify recovery from WAL, CAS, idempotency, and lease receipts without hidden
  mutation or duplicate local action execution.
- Verify orphan inventory for abandoned leases, partial evidence, partial
  operations, pending rollbacks, learning writes, and unterminated incidents.
- Fail release on duplicate local action attempts, missing orphan cleanup,
  terminal replay drift, replay that reruns action logic, or missing
  `crash_recovery_resumed` events.

## Frozen Evaluation and Independent Verification

- Freeze fixtures, alerts, evidence episodes, signed packs, P116 controls,
  P117 selector config, P118 envelope and approval config, evidence taxonomy,
  state machine, budgets, escalation policy, validation probes, rollback
  probes, crash matrix, recurrence windows, learning rules, authority scans,
  seeds, split assignments, thresholds, and verification inputs before first
  score.
- Reject stale hashes, tampered manifests, post-score tuning, hidden production
  targets, nonzero counters, aggregate-only metrics, missing replay receipts,
  self-review, and stale release evidence hashes.
- Require independent verification distinct from planner and implementer.
- Require failed unseen results to be recorded as negative evidence rather
  than tuning data.

## Named RED Cases

- `missing_incident_id`, `unknown_incident_schema_version`,
  `mutable_incident_id`, `missing_terminal_status`,
  `illegal_state_transition`, `terminal_state_reopened`, and
  `missing_authority_snapshot`.
- `auth_context_present`, `credential_scope_present`,
  `secret_material_present`, `hidden_production_target_string`,
  `staging_target_string_present`, `shell_text_present`,
  `subprocess_command_present`, `kubernetes_mutation_present`,
  `cloud_mutation_present`, `database_mutation_present`,
  `network_mutation_present`, `live_connector_call_present`,
  `online_policy_write_present`, `l4_action_requested`,
  `freeform_action_execution_present`, and `llm_command_execution_present`.
- `duplicate_alert_fingerprint`, `near_duplicate_incident`,
  `stale_alert_replay`, `evidence_budget_exhausted`,
  `approval_timeout`, `validation_timeout`, `rollback_timeout`,
  `scheduler_retry_exhausted`, and `incident_expired`.
- `wal_hash_chain_break`, `wal_position_duplicate`, `missing_wal_receipt`,
  `stale_cas_version`, `conflicting_idempotency_key`,
  `terminal_replay_drift`, `lease_split_brain`,
  `lease_takeover_before_expiry`, and `worker_without_owner_receipt`.
- `missing_evidence`, `stale_evidence`, `contradictory_evidence`,
  `contaminated_evidence_source`, `hidden_target_in_evidence`, and
  `value_of_information_negative`.
- `invented_action_id`, `p117_p115_id_mismatch`, `unsigned_action_pack`,
  `revoked_action_pack`, `stale_action_pack`, `pack_digest_mismatch`,
  `missing_validation_plan`, `missing_rollback_plan`,
  `contraindication_present`, `prerequisite_absent`,
  `approval_receipt_forged`, and `approval_fail_open`.
- `action_without_approval`, `operation_envelope_mismatch`,
  `fixture_target_mismatch`, `duplicate_action_attempted`,
  `optimistic_success`, `missing_postcheck`, `failed_guardrail_hidden`,
  `rollback_missing`, `rollback_failed_hidden`, and
  `rollback_postcheck_absent`.
- `natural_recovery_credited_as_action`, `no_action_credited_as_action`,
  `missing_control_window`, `contaminated_attribution_window`,
  `recurrence_hidden`, `online_learning_write`, and
  `post_score_learning_tuning`.
- `missing_timeline_event_class`, `timeline_hash_mismatch`,
  `redaction_failure`, `unsafe_escalation_payload`,
  `replay_link_missing`, `crash_after_action`,
  `crash_during_rollback`, `crash_after_report_write`,
  `orphan_inventory_missing`, `frozen_eval_tampered`,
  `release_self_review`, `stale_release_hash`, and
  `authority_counter_drift`.

## Verification Profile

Future implementation must provide targeted P119 verification for contract,
authority, detection, correlation, budgets, WAL, CAS, idempotency, leases,
evidence acquisition, selection, approval, local execution, validation,
rollback, causal attribution, recurrence, learning, war room, escalation,
redaction, crash recovery, replay, frozen evaluation, release evidence, and
independent verification. Documentation completion does not require those tests
to exist yet.
