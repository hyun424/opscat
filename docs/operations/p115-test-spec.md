# P115 test specification

## Governance and boundaries

- Reject any P115 artifact without `schema_version`.
- Reject unknown major schema versions.
- Reject P114 inputs that are not sealed by source lattice, selected hypothesis
  or abstention, evidence IDs, freeze receipt, and replay receipt.
- Reject hidden truth, blind labels, provider-private reasoning, action text
  from P114, credentials, commands, or mutation requests in candidate-visible
  envelopes.
- Runtime authority scan requires exact-zero auth, credential, shell,
  subprocess, Kubernetes, Ansible, cloud, database mutation, production adapter,
  network mutation, executor, and online policy-write counters.

## Diagnosis-to-action boundary

- Preserve evidence IDs, missing-evidence markers, uncertainty, expected utility
  placeholders, validation handles, and rollback handles.
- Reject unknown evidence IDs, invented hypotheses, post-freeze P114 artifacts,
  candidate-visible scorer truth, and action labels embedded in diagnosis
  metadata.
- Verify deterministic serialization and hash stability across repeated runs.

## Ontology and schemas

- Validate `p115.diagnosis_action_boundary.v1`, `p115.incident_case.v1`,
  `p115.action_pack.v1`, `p115.outcome_contract.v1`, `p115.action_label.v1`,
  `p115.paired_score.v1`, `p115.partition_manifest.v1`, and
  `p115.release_evidence.v1`.
- Reject duplicate IDs, missing partition groups, invalid timestamps, invalid
  topology handles, missing visible evidence handles, unknown action-pack IDs,
  and inconsistent release roles.
- Preserve nullable values distinctly from zero-valued metrics.

## Action-pack catalog

- Require signer/key ID, action family, prerequisites, contraindications,
  reversibility class, blast-radius estimate, expected effect, expected
  evidence, validation query, rollback plan, and executor-disabled metadata.
- Reject unsigned packs, duplicate action IDs, missing rollback for reversible
  actions, absent validation, contradictory prerequisites, hidden outcome hints,
  command bodies, credentials, and production target selectors.
- Verify that declarative validation and rollback fields cannot be invoked as
  executable authority in P115.

## Hidden outcome and leakage

- Keep `p115.outcome_contract.v1` evaluator-owned and absent from candidate
  input, candidate reports, logs, prompts, baseline fixtures, and release
  summaries.
- Detect leakage through nested keys, filenames, path names, action IDs, pack
  descriptions, ordering, topology handles, validation query names, rollback
  names, and generated Markdown.
- Reject holdout contamination by exact duplicate, near duplicate, shared
  incident group, shared topology/time leakage, and action-pack family leakage.

## First-class abstention labels

- Score `no_action`, `investigate_more`, and `escalate` as valid labels.
- Require correct `investigate_more` when mandatory evidence classes are absent.
- Require correct `no_action` when natural recovery dominates or intervention
  expected harm exceeds benefit.
- Require correct `escalate` for permanently human-authorized operations,
  destructive data changes, credential/security changes, irreversible
  migrations, and broad traffic shifts.
- Penalize unnecessary action even when the final state recovers.

## Counterfactual paired scoring

- Final scoring requires imported P116 measured outcomes for action, no-action,
  and wrong-action arms.
- Recompute recovery, harm, unnecessary action, collateral damage, recurrence,
  and rollback predicates from raw measured observations.
- Do not trust submitted success fields or textual expected outcomes.
- Missing P116 outcomes produce `p115_contract_ready` only and nonzero exit for
  final release scoring.
- Report exact numerator, denominator, nullable value, partition, scenario
  family, action family, and confidence interval where applicable.

## Scenario matrix and partitions

- Require at least 15 scenario families and at least 300 cases.
- Require nonzero development and holdout denominators for every scenario
  family and for each required first-class label.
- Split by source, service, topology, incident family, time, and action-pack
  family. Row-level splits are invalid.
- Freeze partition manifest before opening hidden outcomes or importing P116
  measured results.

## Baselines and proposal benchmark

- Deterministic baseline must be byte-stable across two runs.
- Safe null baseline must avoid action when evidence, prerequisites,
  contraindications, validation, rollback, or authority boundaries are
  incomplete.
- Optional LLM proposal benchmark may select only frozen action-pack IDs or
  `no_action`, `investigate_more`, and `escalate`.
- Malformed JSON, unknown IDs, invented actions, commands, credentials,
  mutation language, shell text, or missing evidence citations fail closed to
  deterministic fallback.

## Release evidence

- Release bundle binds hashes for schemas, action packs, scenario matrix,
  partition manifest, baselines, evaluator, authority scan, P116 imported
  outcome records, score reports, contamination report, and independent review.
- `p115-release` fails unless all required denominators are nonzero, all safety
  zero gates pass, P116 measured paired outcomes exist, and reviewer identity is
  distinct from implementation author.
- Self-review, stale hashes, mismatched P116 imports, and aggregate masking are
  release blockers.

## Named RED cases

- `p114_hidden_truth_leak`, `post_freeze_p114_input`,
  `invented_evidence_id`, and `action_text_in_diagnosis`.
- `unsigned_action_pack`, `credential_in_action_pack`,
  `executable_command_in_validation`, `missing_rollback`,
  `contraindication_hint_leak`, and `production_target_selector`.
- `nested_outcome_label_leak`, `filename_outcome_leak`,
  `action_id_order_leak`, `rollback_name_label_leak`, and
  `markdown_release_truth_leak`.
- `row_level_split_leak`, `near_duplicate_holdout`,
  `shared_topology_time_leak`, and `action_family_split_leak`.
- `missing_p116_outcomes_final_score`, `submitted_success_lie`,
  `natural_recovery_credit`, `wrong_action_recovery_credit`,
  `harmful_action_selected`, and `unnecessary_action_selected`.
- `missing_family_denominator`, `aggregate_masks_family_failure`,
  `nullable_metric_as_zero`, and `stale_release_hash`.
- `auth_counter_nonzero`, `credential_counter_nonzero`,
  `executor_counter_nonzero`, `subprocess_counter_nonzero`,
  `kubernetes_counter_nonzero`, and `production_adapter_counter_nonzero`.
