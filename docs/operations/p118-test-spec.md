# P118 Adversarial Test Specification

## Contract and Authority

- Reject operation envelopes missing operation ID, schema version, P117 selected
  action-pack ID, P115 digest, fixture target, action level, validation plan,
  rollback plan, approval receipt, lease receipt, WAL position, CAS version,
  idempotency key, or authority counter snapshot.
- Reject unknown major schema versions, mutable operation IDs, missing terminal
  statuses, unknown lifecycle states, and rejected authority fields.
- Reject auth context, credentials, secrets, production target strings, staging
  target strings, shell text, subprocess commands, Kubernetes/cloud/database/
  network mutation fields, live connector names, online policy writes, free-form
  action prose, and L4+ action requests.
- Require exact-zero counters for auth, credentials, executor calls, shell,
  subprocess, Kubernetes, cloud, database mutation, production adapters,
  network mutation, online policy writes, and production mutation.

## Signed Action-Pack Verification

- Reject unsigned action packs, invalid signatures, digest mismatches, unknown
  schema versions, missing signer IDs, missing validation plans, missing
  rollback plans, missing fixture target binding, or allowed levels above L3.
- Reject stale or expired packs and packs listed in the revocation manifest.
- Reject any P117 selected action-pack ID that does not exactly match the P115
  signed action-pack ID and digest.
- Reject packs that contain credentials, auth requirements, production-like
  targets, live connector references, command text, mutable target selectors, or
  online policy writes.

## WAL, CAS, and Idempotency

- Detect WAL corruption, missing WAL entries, broken hash chains, duplicate WAL
  positions, reordered receipts, and terminal replay drift.
- Reject CAS transitions from stale versions, skipped states, illegal lifecycle
  edges, or already terminal operations.
- Return the existing operation state for duplicate idempotency keys with
  identical payload hashes.
- Fail closed when a duplicate idempotency key carries a different payload,
  action-pack digest, fixture target, or precondition hash.

## Lease Ownership

- Require a single valid owner lease before precheck, action, postcheck,
  rollback, rollback postcheck, or report write.
- Detect lease split-brain, concurrent owners, stale renewals, clock-skewed
  renewals, takeover without expiry, and worker polling races.
- Verify bounded retries and deterministic retry receipts.
- Fail closed when a worker cannot prove ownership from WAL and CAS receipts.

## Crash Recovery and Replay

- Crash before and after precheck, action, postcheck, rollback, rollback
  postcheck, and report write.
- Verify recovery from WAL, CAS, idempotency, and lease receipts without hidden
  mutation or duplicate action execution.
- Verify orphan inventory records abandoned leases, partial evidence, pending
  rollback, and unresolved terminalization.
- Fail release on duplicate action counts, missing orphan cleanup, replay drift,
  or terminal replay that re-runs action logic.

## Validation and Rollback

- Reject optimistic success when postcheck evidence is absent, stale, or failed.
- Require rollback attempt after action failure, postcheck failure, or detected
  unsafe partial state when rollback metadata is available.
- Require rollback validation and rollback postcheck evidence before reporting
  `rolled_back`.
- Preserve `rollback_failed` as a terminal failure with measured evidence.
- Reject validation probes that hide production targets, credentials, connector
  calls, command text, or online policy writes.

## Approval Policy Bypass

- Reject attempts to bypass approval with pre-approved flags, stale receipts,
  forged approval receipts, missing policy hashes, or unsigned policy config.
- Reject local/mock/sandbox labels that mask production hostnames, cloud account
  IDs, Kubernetes namespaces, database DSNs, external URLs, or credential-like
  values.
- Reject L4+ or auth-bearing action requests even when the signed pack is
  otherwise valid.
- Require all policy failures to produce fail-closed receipts.

## Frozen Evaluation

- Freeze fixtures, signed packs, P117 selected IDs, policy config, validation
  probes, rollback probes, crash matrix, seeds, split assignments, authority
  scan rules, and release thresholds before scoring.
- Reject frozen evaluation tampering, stale hashes, post-score tuning, hidden
  target strings, aggregate-only reports, missing per-family counters, missing
  replay receipts, self-review, and stale release evidence hashes.
- Require independent review distinct from planner and implementer.
- Fail release if any authority counter drifts above exact zero.

## Named RED Cases

- `missing_operation_id`, `mutable_operation_id`,
  `unknown_operation_schema_version`, `missing_terminal_status`, and
  `rejected_authority_field_present`.
- `unsigned_action_pack`, `invalid_pack_signature`, `stale_action_pack`,
  `revoked_action_pack`, `p117_p115_id_mismatch`, and
  `pack_digest_mismatch`.
- `hidden_production_target_string`, `credential_in_pack`,
  `auth_required_in_pack`, `live_connector_reference`,
  `online_policy_write_field`, and `l4_action_requested`.
- `wal_hash_chain_break`, `wal_position_duplicate`, `cas_conflict`,
  `illegal_state_transition`, `terminal_state_reopened`, and
  `terminal_replay_drift`.
- `duplicate_idempotency_key_same_payload`,
  `duplicate_idempotency_key_conflicting_payload`,
  `duplicate_action_attempted`, and `retry_without_receipt`.
- `lease_split_brain`, `lease_takeover_before_expiry`,
  `worker_without_owner_receipt`, and `stale_lease_renewal`.
- `crash_before_precheck`, `crash_after_action`, `crash_after_postcheck`,
  `crash_during_rollback`, `crash_after_report_write`, and
  `orphan_cleanup_failure`.
- `validation_failure_optimistic_success`, `rollback_failure_hidden`,
  `rollback_postcheck_missing`, and `rollback_evidence_stale`.
- `approval_receipt_forged`, `policy_hash_missing`,
  `sandbox_label_masks_production`, and `approval_fail_open`.
- `frozen_eval_tampered`, `post_score_tuning`, `release_self_review`,
  `stale_release_hash`, and `authority_counter_drift`.

## Verification Profile

Future implementation must provide targeted P118 verification that runs
contract, signed-pack, authority, WAL, CAS, idempotency, lease, validation,
rollback, crash recovery, replay, frozen evaluation, release-evidence, and
independent-review tests. Documentation completion does not require those tests
to exist yet.
