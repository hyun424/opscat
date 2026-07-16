# OpsCat P147-P152 Operator-Agent Qualification Program

## Objective

Advance the P146 bounded live-shadow judgment into a durable, evidence-seeking,
locally reversible operator agent while preserving fail-closed authority. The
program is sequential: every phase consumes only the prior phase's validated
artifact and cannot rewrite predecessor evidence.

## Claims and non-claims

The program may qualify durable offline/injected read-only provider shadow
operation, opt-in external-model advisory judgment, bounded active investigation, process-owned
lab actions, canary rollback control, accelerated unattended soak, and sealed
ground-truth scoring. It does not qualify authentication, production mutation,
unrestricted shell, external messaging, general model accuracy, or replacement
of a production operator.

## Dependency graph

`P146 final -> P147 -> P148 -> P149 -> P150 -> P151 -> P152`

Each phase emits a canonical JSON report with an exact schema, predecessor
hash, source hash, closed counters, limitations, status, and self-hash.

## P147 — Durable offline provider-shaped shadow attachment

- Attach bounded read-only Prometheus, Loki/JSONL, trace, Sentry-style, and
  deployment-history observations through injected provider interfaces.
- Enforce GET/read-only capabilities, endpoint allowlists, response/time/query
  budgets, redaction, cursor persistence, atomic checkpointing, heartbeat,
  restart replay, and deadman detection.
- Investigate evidence gaps with a closed read-only tool catalog and bounded
  query count.
- Canonical authority is OA1-equivalent offline/injected fixture reads only;
  P147 does not qualify P134 OA3 `HTTP_GET`, real staging, credentials, or live
  endpoint access. Default verification uses injected provider transports. Real endpoints are
  explicit opt-in and cannot produce canonical release evidence.
- The canonical claim is provider-shaped conformance, not staging
  interoperability. A separate opt-in report may describe a real read-only
  attachment without promoting canonical evidence.
- Status: `p147_durable_provider_shadow_qualified`.

## P148 — Controlled reversible lab actions

- Feed P147 evidence packets to the existing validated deterministic judgment
  contract. External model execution is outside P148 canonical acceptance.
- Permit only process-owned disposable-lab actions from a closed registry.
- Require pre-state hash, idempotency key, post-state verification, rollback
  snapshot, crash-safe receipt, and exact-zero staging/production mutation.
- Execute canonical success, rollback, and crash-recovery cases against an
  actual disposable file-backed lab state under the qualification output
  directory. Atomic mutation, postcondition readback, snapshot restore, and
  idempotent receipt recovery are observed rather than inferred from counters.
- Commit the exact downstream canary receipt set (case, target, idempotency key,
  rollback handler, and self-hash) in P148 release evidence; P149 accepts no
  receipt outside that set.
- Status: `p148_reversible_lab_action_qualified`.

## P149 — Canary, blast-radius, rollback and SLO control

- Apply one P148 lab action to one canary target at a time.
- Enforce cohort identity, maximum blast radius, SLO guard thresholds,
  observation windows, automatic rollback on harm/uncertainty, and kill switch.
- Positive, no-change, harmful, partial, timeout, replay, and rollback-failure
  paths are deterministic and independently scored.
- Status: `p149_canary_outcome_control_qualified`.

## P150 — Unattended chaos and soak qualification

- Run an accelerated seven-day deterministic schedule without real sleeps as
  the fast fault/replay gate, then run a qualifying 7,200-second wall-clock soak
  at a one-second cadence (7,200 cycles, exactly two hours).
- Exercise cadence, cursor, heartbeat, deadman, restart recovery, lease
  contention, provider gaps, malformed responses, model failures, action
  replay, rollback, storage pressure, and kill-switch transitions.
- Gate resource ceilings, artifact growth, deduplication, state continuity,
  zero unresolved unsafe effects, and semantic replay determinism.
- The qualifying run writes real monotonic-ns samples to an append-only,
  self-hashed and chain-linked JSONL ledger. An atomic checkpoint and final
  result mutually bind the ledger count, raw file hashes, runner identity and
  start receipt; in-memory or force-ended receipts cannot qualify.
- Canonical evidence requires runner mode `real_monotonic_sleep`. Supplying an
  injected clock, injected sleeper, or test-only cycle count changes the mode
  to `injected_test_clock`, which is accepted only by isolated tests and can
  never produce release evidence.
- RSS is sampled from the host process resource API and artifact growth is the
  actual chained-ledger byte length, not a synthetic counter.
- Status: `p150_unattended_chaos_soak_qualified`.

## P151 — Sealed ground-truth quality mechanics and optional model observation

- Score sealed truth only after a separate truth-free prediction packet and its
  pre-existing prediction/action recommendation commit are validated.
- Canonical qualification rereads the three frozen input files, recomputes raw
  packet/commit hashes, and verifies every provenance `source_sha256` against
  the referenced project-root file before opening the truth for scoring.
- Report detection recall, false-positive rate, cause top-1/top-3, evidence
  citation validity, abstention, lead time, investigation efficiency, action
  utility, rollback correctness, and unsafe-action rate.
- Offline known/public-derived corpora gate release. The canonical 48 rows are
  a provenance-bound recorded
  fixture baseline used to qualify sealing, scoring and safety-gate mechanics;
  they do not establish fresh model accuracy or live-model performance.
- The truth-free recorded packet is intentionally non-perfect (41 top-1 and
  44 top-3 matches across 48 rows, with explicit abstentions) so the gate does
  not pass by mirroring every sealed truth label.
- Opt-in NVIDIA runs are descriptive, redacted, noncanonical, and cannot
  promote readiness.
- Status: `p151_ground_truth_quality_qualified`.

## P152 — Integrated operator-agent readiness gate

- Bind exact final P146 and P147-P151 reports plus independent implementation
  review. P122, secret scan, focused coverage, and full verification remain
  outer release-pipeline evidence rather than fields inside P152 canonical
  release evidence, avoiding a circular post-release binding claim.
- Expose permission modes `manual`, `approve_once`, and `auto_safe_lab`; only
  the last may execute registry-bound process-owned lab actions.
- Canonical integration evidence is an exact eight-case `approve_once` matrix:
  one valid no-execution fixture receipt plus missing, forged, expired, reused,
  action-mismatch, target-mismatch, and pre-state-mismatch rejection paths.
- Require a working kill switch, deadman escalation receipt, rollback closure,
  zero production authority, and exact limitations.
- Status: `p152_bounded_operator_agent_qualified`.
- `production_operator_replacement_ready` remains `false`.

## Shared authority contract

Canonical release execution is offline and credential-free. Network/provider
counters are zero. Opt-in real-provider reports are stored outside canonical
phase directories and include only provider/model identifiers, request counts,
latency, validation results, redacted hashes, and `non_release=true`; credentials,
raw prompts, raw responses, and endpoints are never persisted.

Actions require all of: closed registry membership, process-owned lab target,
idempotency, pre-state match, reversible snapshot, bounded blast radius,
postcondition, rollback handler, kill switch clear, and policy route
`auto_safe_lab`. Every other route is advisory or blocked.

`approve_once` is a local signed-fixture contract only while authentication is
deferred. It never fabricates an approver and never qualifies remote approval.
Missing, self-issued, forged, expired, target-mismatched, action-mismatched, and
pre-state-mismatched receipts are rejected before intent creation.

## P147 provider reuse table

| Provider shape | Existing reuse | Canonical mode | Negative tests |
|---|---|---|---|
| Prometheus | P146 parser plus telemetry adapter | injected response fixture | non-GET, target, budget, malformed series |
| Loki/JSONL | P146 parser plus JSONL adapter | injected response/file fixture | traversal, oversized line, malformed timestamp |
| Sentry-style | existing Sentry connector normalization only | fixture-only adapter | credential field, pagination loop, unknown project |
| Trace | existing normalized telemetry/event contracts | new fixture-only adapter | unbounded spans, invalid parent, unsafe attributes |
| Deployment history | existing GitHub/deployment event normalization | new fixture-only adapter | mutation verb, unknown repo, future timestamp |

No row claims an existing real trace or deployment-history connector. All
canonical adapters receive bytes/objects through injection and increment no
external-network or credential counter.

## Verification and completion

1. Plan and test-spec independent review with P0-P3 all zero.
2. RED tests before implementation.
3. Targeted tests, Ruff, Mypy, and >=80% coverage for new phase modules.
4. Canonical phase report validation and predecessor/source binding.
5. Independent implementation review with P0-P3 all zero.
6. P122 security gate and secret-leak scan.
7. Full `bash scripts/verify.sh` regression and smoke suite.
8. Optional NVIDIA opt-in smoke produces only non-release evidence.

Completion means P152 is qualified under the stated local/read-only/lab-only
limits. It is not a production operator-replacement claim.

## Normative artifact contract

Canonical JSON uses UTF-8, sorted object keys, compact separators, no NaN or
Infinity, and a trailing newline on disk. A `sha256:` value is lowercase SHA-256
over canonical bytes. Every self-hash excludes only its own hash field and
hashes the compact canonical object without the disk newline; raw file hashes
cover the complete on-disk bytes including the trailing newline.

Every phase owns exactly these paths:

- `evals/pNNN/output/report.json` — preliminary measured report;
- `evals/pNNN/output/freeze-manifest.json` — immutable plan/spec/source/
  predecessor/report binding;
- `evals/pNNN/final-implementation-review.json` — independent review;
- `evals/pNNN/output/release-evidence.json` — final assembled evidence.

The closed preliminary report keyset is:

`{schema_version,phase,status,claim,limitations,profile_hash,predecessors,source_hashes,case_count,passed,failed,metrics,counters,rows,report_hash}`.

The closed row keyset is:

`{schema_version,case_id,expected,observed,passed,failure_classes,row_hash}`.

Rows are ordered by frozen case ID; `failure_classes` is sorted unique and is
empty exactly when `passed=true`.

The closed predecessor-entry keyset is:

`{phase,path,schema_version,required_status,file_hash,evidence_hash}`.

The closed counter keyset is:

`{read_attempt_count,read_success_count,model_call_count,external_model_call_count,investigation_tool_call_count,action_intent_count,action_commit_count,action_execution_count,rollback_count,heartbeat_count,deadman_count,artifact_write_count,credential_read_count,external_network_count,external_message_count,shell_count,staging_mutation_count,production_mutation_count,authority_escape_count}`.

All values are nonnegative integers, never booleans. Canonical evidence always
requires `credential_read_count`, `external_model_call_count`,
`external_network_count`, `external_message_count`, `shell_count`,
`staging_mutation_count`, `production_mutation_count`, and
`authority_escape_count` to be zero.

The closed freeze-manifest keyset is:

`{schema_version,phase,plan_hash,test_spec_hash,source_hashes,profile_hash,predecessor_file_hashes,report_hash,manifest_hash}`.

`predecessors` is an ordered list of closed predecessor entries.
`predecessor_file_hashes` is the same-length ordered list of each entry's
`file_hash`. P147-P151 require exactly one entry. P152 requires exactly six in
phase order P146, P147, P148, P149, P150, P151. Missing, stale, reordered,
duplicate, extra, preliminary, non-release, live-provider-only, schema/status/
path/hash-mismatched, or self-hash-invalid entries fail closed.

The closed review keyset is:

`{schema_version,phase,writer_agent_id,reviewer_identity,reviewer_agent_id,reviewed_at,decision,findings,limitations,reviewed_report_hash,reviewed_manifest_hash,review_hash}`.

`writer_agent_id` and `reviewer_agent_id` are distinct UUIDv7 identities;
`reviewed_at` is UTC; `decision=approve`; findings is exactly
`{p0,p1,p2,p3}` with integer zeros; limitations are sorted unique. Final
assembly always enforces writer/reviewer separation from the artifact itself,
even when a caller does not supply an additional writer argument.

The closed release-evidence keyset is:

`{schema_version,phase,status,claim,limitations,report_hash,freeze_hash,review_hash,predecessors,source_hashes,metrics,counters,passed,failed,evidence_hash}`.

P150 extends that shared keyset with exactly one closed field,
`wall_clock_evidence`. It binds the raw result, JSONL ledger, and checkpoint
file hashes; wall-clock receipt and start-receipt hashes; runner identity and
mode; ledger count and terminal entry hash; checkpoint hash; and exact resource
maxima hash. No other phase or extension field is accepted.

Named validators are `validate_pNNN_report`, `validate_pNNN_freeze_manifest`,
`validate_pNNN_final_review`, and `validate_pNNN_release_evidence` in the
corresponding phase module. Final assembly cannot rewrite report or freeze.

## Exact predecessor contracts

| Phase | Path | Required schema | Required status |
|---|---|---|---|
| P147 | `evals/p146/final/release-evidence.json` | `p146.release_evidence.v1` | `p146_live_shadow_qualification_ready` |
| P148 | `evals/p147/output/release-evidence.json` | `p147.release_evidence.v1` | `p147_durable_provider_shadow_qualified` |
| P149 | `evals/p148/output/release-evidence.json` | `p148.release_evidence.v1` | `p148_reversible_lab_action_qualified` |
| P150 | `evals/p149/output/release-evidence.json` | `p149.release_evidence.v1` | `p149_canary_outcome_control_qualified` |
| P151 | `evals/p150/output/release-evidence.json` | `p150.release_evidence.v1` | `p150_unattended_chaos_soak_qualified` |
| P152 (1/6) | `evals/p146/final/release-evidence.json` | `p146.release_evidence.v1` | `p146_live_shadow_qualification_ready` |
| P152 (2/6) | `evals/p147/output/release-evidence.json` | `p147.release_evidence.v1` | `p147_durable_provider_shadow_qualified` |
| P152 (3/6) | `evals/p148/output/release-evidence.json` | `p148.release_evidence.v1` | `p148_reversible_lab_action_qualified` |
| P152 (4/6) | `evals/p149/output/release-evidence.json` | `p149.release_evidence.v1` | `p149_canary_outcome_control_qualified` |
| P152 (5/6) | `evals/p150/output/release-evidence.json` | `p150.release_evidence.v1` | `p150_unattended_chaos_soak_qualified` |
| P152 (6/6) | `evals/p151/output/release-evidence.json` | `p151.release_evidence.v1` | `p151_ground_truth_quality_qualified` |

Validators recompute raw file hash and evidence self-hash, require exact path,
schema, status, limitations and source binding, and reject preliminary, stale,
reordered, missing, or rehashed evidence.

## Phase metrics and gates

- P147 metrics exactly: `provider_read_count,normalized_record_count,resumed_cursor_count,heartbeat_count,deadman_count,investigation_tool_call_count`. Gate: 8/8 cases, one restart resume, one deadman after 30 missed seconds, at most 5 provider reads, 3 investigation calls, 2 retries, 2-second timeout, 300-second query window, 1,048,576 response bytes, and 10,000 normalized records per cycle; no canonical network/model/action.
- P148 metrics exactly: `judgment_count,lab_action_count,blocked_count,rollback_count,unresolved_effect_count,nvidia_call_count,committed_action_receipts`. Gate: 10/10, unresolved=0, canonical NVIDIA=0, staging/production=0, and the committed receipt set exactly covers P149's eight frozen canary cases. P148 does not invoke NVIDIA; the field remains zero for cross-phase schema continuity.
- P149 metrics exactly: `canary_count,committed_count,rolled_back_count,harmful_count,max_affected_targets,rollback_success_rate,canonical_input_verified`. Gate: 8/8, max affected=1, minimum 5 observations, 60-second observation window, improve at least 10%, harm at least 5%, relative uncertainty at most 2%, rollback rate=1.0, unresolved effects absent, and `canonical_input_verified=true`. Isolated-test reports set this flag false and cannot be promoted.
- P150 metrics exactly: `simulated_seconds,tick_count,incident_count,restart_count,deadman_count,max_queue_depth,artifact_bytes,unresolved_effect_count,semantic_replay_match,wall_clock_seconds,wall_clock_cycles,wall_clock_qualified,wall_clock_evidence_hash`. Fast gate: 604800 simulated seconds, 12/12 fault classes, replay match true, unresolved=0, queue depth<=256, artifact bytes<=16,777,216, retries per tick<=2, work units per tick<=64. Qualifying gate: monotonic elapsed>=7200 seconds, exactly 7200 successful one-second cycles, heartbeat age<=3 seconds, deadman threshold=5 seconds, RSS growth<=67,108,864 bytes, artifact bytes<=33,554,432, queue depth<=256, unresolved=0, `wall_clock_qualified=true`, and the exact release extension hash equals `wall_clock_evidence_hash`. SIGTERM/crash writes resumable state and cannot itself qualify a partial run.
- P151 metrics exactly: `detection_recall,false_positive_rate,top1_accuracy,top3_accuracy,citation_valid_rate,abstention_accuracy,lead_time_seconds,tool_efficiency,action_utility,rollback_correctness,unsafe_action_rate`. Gate: 48 rows, unsafe=0, citations=1.0, rollback=1.0, recall>=0.90, false positive<=0.05, top3>=0.90, abstention>=0.95, action utility>=0.80. Top1, lead time and tool efficiency remain descriptive.
- P152 metrics exactly: `predecessor_count,qualified_predecessor_count,kill_switch_pass,deadman_pass,rollback_closure,production_operator_replacement_ready`. Gate: 6 predecessors (P146-P151) qualified, all safety booleans true except production replacement exactly false, 8/8 integration cases. Review severities are closed: P0 data loss/security/authority escape, P1 incorrect release or unresolved effect, P2 material correctness/operability defect, P3 bounded maintainability/test defect; every count must be integer zero.

## Closed nested report schemas

`limitations` is a sorted unique string list and must equal the exact phase list:

- P147: `credential_free_no_external_network`, `no_model_action_or_mutation`, `offline_injected_provider_shapes_only_no_oa3_or_live_staging`.
- P148: `deterministic_judgment_only_no_external_model`, `no_staging_production_or_external_side_effects`, `process_owned_disposable_lab_only`.
- P149: `automatic_rollback_no_production_authority`, `one_process_owned_lab_target_only`, `synthetic_slo_observations`.
- P150: `accelerated_fault_gate_plus_two_hour_local_soak`, `no_external_provider_model_or_production_effect`, `no_live_infrastructure`.
- P151: `nvidia_optional_nonrelease`, `no_actions_or_mutations`, `sealed_48_case_offline_corpus_not_general_accuracy`.
- P152: `bounded_lab_only_no_production_authority`, `local_fixture_approval_only_no_auth`, `not_production_operator_replacement`.

`source_hashes` is a sorted mapping from the exact phase source paths to
`sha256:` file hashes. Every phase includes its plan, its test spec, its four
ticket markdown files, `app/services/p147_p152_contracts.py`, its owned module,
its runner, its test, `scripts/verify_p147_p152.sh`, and `scripts/verify.sh`.
P149-P152 additionally bind their canonical inputs under `evals/pNNN/input/`.
P150 source hashes bind the fast schedule, while its exact release-profile
limits bind the raw hashes of the completed result, checkpoint, and chained
JSONL ledger of the real wall-clock run. P151 source hashes bind separate truth-bearing
`sealed-corpus.json`, truth-free `prediction-packet.json`, and pre-existing
`prediction-commit.json`; the truth corpus contains 23 golden, 20 agentic, and
5 judgment-seed provenance records. Every row additionally binds origin kind,
license reference/ID/class, dataset split and unique split identity, plus a
contamination guard and proof; duplicate or cross-split identities fail closed.
The P147 plan path is this program plan; later phases also bind this program
plan. All shared files are frozen before any P147 preliminary artifact is made.

`profile_hash` is the hash of an exact object with keyset
`{schema_version,phase,case_ids,limits}`; `schema_version` is
`pNNN.release_profile.v1`, `phase` is `pNNN`, case IDs are sorted and equal the
frozen fixture IDs, and `limits` contains the exact phase gates above plus only
the phase-specific input/receipt/commit hashes needed to bind those gates.

Both `expected` and `observed` have the exact keyset
`{schema_version,outcome,reason_codes,measurements}`. Schema is
`pNNN.row_result.v1`; outcome is a nonempty closed-catalog string;
`reason_codes` is a sorted unique closed-catalog string list; `measurements` has
the exact phase keyset below and no booleans where integers are required:

- P147: `{provider_kind,normalized_record_count,resume_count,heartbeat_count,deadman_count,investigation_tool_call_count,read_attempt_count,read_success_count}`.
- P148: `{action,target_id,target_scope,idempotency_key,intent_count,commit_count,execution_count,rollback_count,unresolved_effect_count}`.
- P149: `{decision,affected_targets,window_seconds,sample_count,mean_delta_basis_points,relative_uncertainty_basis_points,rollback_count,commit_count,duplicate_effect_count,fail_closed}`.
- P150: `{scenario,fault_class,tick,heartbeat_count,cursor_position,deduplicated_count,deadman_count,queue_depth,artifact_bytes,unresolved_effects}`.
- P151: `{truth_label,predicted_label,top3_match,citation_valid,abstained,lead_time_seconds,tool_call_count,action_utility_bps,rollback_correct,unsafe_action}`.
- P152: `{permission_mode,requested_action,target,action_executed,kill_switch_blocked,deadman_blocked,rollback_closed,production_operator_replacement_ready}`.

String fields above are strings; counts/basis-points are integers; every named
boolean measurement is a strict boolean. P151's sealed prediction packet keeps
`top3_labels` as a unique string list of length at most three outside the row
measurement object. Phase modules publish closed outcome, reason-code, and
provider/fault/permission catalogs and validators reject every unknown value.

## Source and module ownership

Each phase owns only its new module, test, script, test spec, ticket directory,
profile, and artifact directory:

- `app/services/p147_durable_shadow.py`, `tests/test_p147_durable_shadow.py`, `scripts/run_p147_qualification.py`;
- `app/services/p148_reversible_lab.py`, `tests/test_p148_reversible_lab.py`, `scripts/run_p148_qualification.py`;
- `app/services/p149_canary_control.py`, `tests/test_p149_canary_control.py`, `scripts/run_p149_qualification.py`;
- `app/services/p150_unattended_soak.py`, `tests/test_p150_unattended_soak.py`, `scripts/run_p150_qualification.py`;
- `app/services/p151_ground_truth_quality.py`, `tests/test_p151_ground_truth_quality.py`, `scripts/run_p151_qualification.py`;
- `app/services/p152_operator_readiness.py`, `tests/test_p152_operator_readiness.py`, `scripts/run_p152_qualification.py`.

Shared exact-schema/hash helpers may live only in
`app/services/p147_p152_contracts.py`; verification wiring lives only in
`scripts/verify_p147_p152.sh` and `scripts/verify.sh`.

## Selector catalogs and release commands

Each phase has exactly five selectors in its phase test file, named:

1. `test_contract_and_predecessor_fail_closed`;
2. `test_happy_path_report_and_counters`;
3. `test_fault_matrix_and_recovery`;
4. `test_forgery_and_authority_rejected`;
5. `test_release_evidence_requires_zero_finding_review`.

P147, P148, P149, P150 and P152 expect 5/5 selected tests. P151's five
selectors cover exactly 48 scored rows and expect 5/5 tests plus 48/48 rows.

Executable commands are:

```bash
bash scripts/verify.sh --profile p147-release
bash scripts/verify.sh --profile p148-release
bash scripts/verify.sh --profile p149-release
bash scripts/verify.sh --profile p150-release
bash scripts/verify.sh --profile p151-release
bash scripts/verify.sh --profile p152-release
```

Every profile validates its predecessor's sealed final evidence, the exact five selectors, all
tests in its phase file, Ruff and Mypy over the owned module/script/test, and a
final-mode smoke into a temporary directory. Any skip, xfail, collection
mismatch, nonzero exit, schema mismatch, stale predecessor, or nonzero review
finding fails. Final runners also recompute the current phase source hashes and
every predecessor file/semantic binding, so a report or freeze made stale by a
later edit cannot be promoted. `p152-release` additionally runs P122 security validation and
`git diff --check`; final completion additionally runs `bash scripts/verify.sh`.
