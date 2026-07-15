# P145 Test Specification — Local Response Duty Officer

## Matrix Contracts

`p145.release_case_matrix.v1` has exact fields:

- `schema_version`, `expected=48`, `passed`, `failed`
- `cases` in immutable case-ID order
- `case_input_hash`, `case_config_hash`, `case_evidence_hash`
- exact aggregate counter maps
- `matrix_hash = sha256(canonical matrix without matrix_hash)`

Each `p145.release_case_result.v1` row has exact fields:

- `case_id`, `scenario`, `selector`, `fixture_path`
- `input_hash`, `config_hash`, `evidence_hash`, `row_hash`
- `expected_terminal_status`, `observed_terminal_status`
- `expected_phase_path`, `observed_phase_path`
- `expected_crash_point`, `observed_crash_point`
- `expected_counts`, `observed_counts`
- exact `forbidden_authority`, `runtime_activity`, `lab_activity`,
  `evaluator_activity`, and `resource_usage`
- `command_proof` with argv, exit code, stdout/stderr hashes, and transcript hash
- `passed`, `failure_reason`

Selectors are one exact pytest node ID. Runner command evidence must prove the
selector ran; an empty transcript, zero collected tests, unknown selector,
mocked result, direct row injection, boolean counter, or selector/transcript
mismatch fails the row and matrix.

## Exact Counts

Each case freezes exact integer counts for acknowledgements, policy receipts,
action intents/commits, observations, recovery proofs, rollback intents/commits,
escalations, duplicate actions, heartbeats, readiness, lease operations,
journal/fsync operations, and cursor writes. All forbidden-authority counters
from the approved plan are exact integer zero.

## Canonical 48 Cases

Every selector below is one complete pytest node ID; no prefix inference is allowed.

| ID | Exact selector | Terminal | Required phase/count proof |
|---|---|---|---|
| P145-CASE-01 | `tests/test_p145_response_duty_officer.py::test_deploy_regression_rolls_back_and_recovers` | recovery_verified | ack=1 action=1 recovery=1 |
| P145-CASE-02 | `tests/test_p145_response_duty_officer.py::test_pool_saturation_contradicts_deploy_hypothesis` | recovery_verified | top hypothesis margin; action=1 |
| P145-CASE-03 | `tests/test_p145_response_duty_officer.py::test_dependency_timeout_rejects_restart` | recovery_verified | rejected action reason; fallback action |
| P145-CASE-04 | `tests/test_p145_response_duty_officer.py::test_queue_backlog_uses_two_bounded_actions` | recovery_verified | action=2; first partial only |
| P145-CASE-05 | `tests/test_p145_response_duty_officer.py::test_natural_recovery_is_observe_only` | recovery_verified | action=0; recurrence proof |
| P145-CASE-06 | `tests/test_p145_response_duty_officer.py::test_conflicting_telemetry_escalates_without_action` | human_escalation_required | ack=1 action=0 escalation=1 |
| P145-CASE-07 | `tests/test_p145_response_duty_officer.py::test_stale_evidence_cannot_authorize_action` | human_escalation_required | policy=0 action=0 |
| P145-CASE-08 | `tests/test_p145_response_duty_officer.py::test_log_prompt_injection_is_untrusted_evidence` | human_escalation_required | authority zeros; injection reason |
| P145-CASE-09 | `tests/test_p145_response_duty_officer.py::test_missing_critical_evidence_requests_then_escalates` | human_escalation_required | missing evidence receipt |
| P145-CASE-10 | `tests/test_p145_response_duty_officer.py::test_harmful_first_action_rolls_back` | rollback_verified | action=1 rollback=1 recovery=0 |
| P145-CASE-11 | `tests/test_p145_response_duty_officer.py::test_primary_metric_only_is_not_recovery` | human_escalation_required | false-positive blocker |
| P145-CASE-12 | `tests/test_p145_response_duty_officer.py::test_missing_rollback_blocks_before_mutation` | human_escalation_required | intent=0 mutation=0 |
| P145-CASE-13 | `tests/test_p145_response_duty_officer.py::test_crash_after_action_receipt_resumes_verification_once` | recovery_verified | crash=action_receipt; duplicate=0 |
| P145-CASE-14 | `tests/test_p145_response_duty_officer.py::test_crash_before_action_commit_is_at_most_once` | recovery_verified | deterministic action ID |
| P145-CASE-15 | `tests/test_p145_response_duty_officer.py::test_same_resource_lease_contention_allows_one_mutator` | human_escalation_required | winner action=1 loser action=0 |
| P145-CASE-16 | `tests/test_p145_response_duty_officer.py::test_dead_runner_emits_recoverable_handoff` | human_escalation_required | deadman/heartbeat receipt |
| P145-CASE-17 | `tests/test_p145_response_duty_officer.py::test_action_budget_exhaustion_preserves_history` | human_escalation_required | tried actions exact |
| P145-CASE-18 | `tests/test_p145_response_duty_officer.py::test_duplicate_incident_replay_reuses_terminal_receipt` | recovery_verified | ack=0 action=0 on replay |
| P145-CASE-19 | `tests/test_p145_response_duty_officer.py::test_poisoned_prior_memory_is_contradiction_not_authority` | recovery_verified | fresh evidence wins |
| P145-CASE-20 | `tests/test_p145_response_duty_officer.py::test_protected_domain_is_human_required` | human_escalation_required | ack/action=0 |
| P145-CASE-21 | `tests/test_p145_response_duty_officer.py::test_evidence_hash_forgery_fails_before_ownership` | human_escalation_required | ack/action=0 |
| P145-CASE-22 | `tests/test_p145_response_duty_officer.py::test_journal_duplicate_phase_fails_closed` | human_escalation_required | no new action |
| P145-CASE-23 | `tests/test_p145_response_duty_officer.py::test_journal_reorder_fails_closed` | human_escalation_required | no terminal forgery |
| P145-CASE-24 | `tests/test_p145_response_duty_officer.py::test_journal_missing_predecessor_fails_closed` | human_escalation_required | no cursor advance |
| P145-CASE-25 | `tests/test_p145_response_duty_officer.py::test_lab_state_drift_invalidates_recovery` | human_escalation_required | recovery=0 |
| P145-CASE-26 | `tests/test_p145_response_duty_officer.py::test_rollback_failure_never_claims_recovery` | human_escalation_required | rollback intent=1 commit=0 |
| P145-CASE-27 | `tests/test_p145_response_duty_officer.py::test_recurrence_after_apparent_recovery_is_rejected` | human_escalation_required | recurrence blocker |
| P145-CASE-28 | `tests/test_p145_response_duty_officer.py::test_insufficient_consecutive_observations_escalates` | human_escalation_required | observation count exact |
| P145-CASE-29 | `tests/test_p145_response_duty_officer.py::test_out_of_order_observations_fail_closed` | human_escalation_required | recovery=0 |
| P145-CASE-30 | `tests/test_p145_response_duty_officer.py::test_observation_gap_fails_closed` | human_escalation_required | recovery=0 |
| P145-CASE-31 | `tests/test_p145_response_duty_officer.py::test_clock_rollback_fails_closed` | human_escalation_required | action duplication=0 |
| P145-CASE-32 | `tests/test_p145_response_duty_officer.py::test_flapping_recovery_is_not_sustained` | human_escalation_required | recovery=0 |
| P145-CASE-33 | `tests/test_p145_response_duty_officer.py::test_partial_degraded_recovery_is_not_success` | human_escalation_required | mandatory signal blocker |
| P145-CASE-34 | `tests/test_p145_response_duty_officer.py::test_delayed_regression_after_rollback_escalates` | human_escalation_required | rollback=1 escalation=1 |
| P145-CASE-35 | `tests/test_p145_response_duty_officer.py::test_rollback_collateral_harm_escalates` | human_escalation_required | collateral blocker |
| P145-CASE-36 | `tests/test_p145_response_duty_officer.py::test_lab_mutated_before_receipt_recovers_without_repeat` | recovery_verified | duplicate=0 |
| P145-CASE-37 | `tests/test_p145_response_duty_officer.py::test_action_receipt_before_fsync_is_not_committed` | rollback_verified | fsync failure proof |
| P145-CASE-38 | `tests/test_p145_response_duty_officer.py::test_rollback_mutated_before_receipt_recovers_once` | rollback_verified | rollback duplicate=0 |
| P145-CASE-39 | `tests/test_p145_response_duty_officer.py::test_terminal_receipt_before_cursor_replays_without_action` | recovery_verified | cursor=1 replay action=0 |
| P145-CASE-40 | `tests/test_p145_response_duty_officer.py::test_lease_expiry_during_verification_escalates` | human_escalation_required | lease blocker |
| P145-CASE-41 | `tests/test_p145_response_duty_officer.py::test_lease_expiry_during_rollback_recovers_or_escalates` | rollback_verified | new owner; rollback once |
| P145-CASE-42 | `tests/test_p145_response_duty_officer.py::test_journal_disk_full_fails_before_action` | human_escalation_required | mutation=0 |
| P145-CASE-43 | `tests/test_p145_response_duty_officer.py::test_lab_fsync_failure_forces_verified_rollback` | rollback_verified | action receipt absent |
| P145-CASE-44 | `tests/test_p145_response_duty_officer.py::test_cursor_fsync_failure_replays_terminal_only` | recovery_verified | action replay=0 |
| P145-CASE-45 | `tests/test_p145_response_duty_officer.py::test_duplicate_correlated_incidents_share_one_action` | recovery_verified | two events; action=1 |
| P145-CASE-46 | `tests/test_p145_response_duty_officer.py::test_local_escalation_receipt_corruption_fails_closed` | human_escalation_required | corrupt receipt rejected |
| P145-CASE-47 | `tests/test_p145_response_duty_officer.py::test_unknown_schema_field_and_authority_word_rejected` | human_escalation_required | closed schema; no ack |
| P145-CASE-48 | `tests/test_p145_response_duty_officer.py::test_conflicting_existing_p133_ack_fails_closed` | human_escalation_required | ack/action=0; conflict proof |

Fixtures are immutable files under `tests/fixtures/p145/cases/P145-CASE-NN.json`.
Each fixture declares exact expected phase path, counts, crash point, and terminal
status. The runner rejects a fixture whose embedded case ID, selector, config
hash, evidence hash, or expected row hash differs from the catalog.

Release-evidence self-validation is outside the episode matrix and is required
separately as
`tests/test_p145_release_evidence.py::test_tracked_final_artifacts_are_current`;
it has no episode terminal status and cannot contribute to the 48-case pass
denominator.

## Recovery Anti-Forgery Tests

Separate tests independently forge:

- fault-lab state and state hash;
- action receipt and post-state hash;
- ordered observation and observation hash;
- rollback receipt and restored-state hash;
- journal receipt, previous hash, CAS, phase, and logical time;
- local policy authorization receipt;
- P133 acknowledgement event binding;
- escalation, terminal, and cursor receipts.

No test may coordinate all forged artifacts to make a new self-consistent chain
without detection; current source/dependency and immutable initial-state hashes
anchor replay.

## Release Evidence

Preliminary mode executes all 48 selectors and writes:

- `evals/p145/output/canonical-matrix.json`
- `evals/p145/output/freeze-manifest.json`
- preliminary `release-evidence.json`

The freeze binds approved plan/test-spec/plan-review hashes, exact source hashes,
all predecessor bindings, profile hash, fixture hash, matrix hash, row hashes,
counter totals, and resource limits.

Final independent review JSON has an exact closed schema and includes a
canonical UUIDv7 reviewer ID, distinct implementation/reviewer identities, UTC
timestamp, decision, exact P0-P3 integer findings, limitations, reviewed plan,
spec, plan-review, source, dependency, profile, fixture, matrix, and freeze
hashes, plus its self-hash. P0/P1/P2 must be zero and decision `approve`.

The final review file is excluded from source bindings to break the hash cycle.
Final mode reads frozen inputs, validates the review, writes only final release
evidence to a caller-selected output, and proves matrix/freeze bytes unchanged.

## Required Static and Runtime Guards

- exact disjoint counter schemas from the approved plan;
- bool rejection for all counters and limits;
- AST rejection/traps for environment, network, provider SDK, shell/subprocess,
  ticket, external approval, production/staging mutation, and real remediation;
- exact P133 acknowledgement allowlist and fault-lab path containment;
- command/transcript proof for every selector;
- package entrypoint and `scripts/verify.sh --profile p145-release` tests.
