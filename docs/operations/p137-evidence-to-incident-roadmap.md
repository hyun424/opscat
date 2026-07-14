# P137 Evidence-to-Incident Investigation Agent Roadmap

## Objective

P137 turns P136's durable promoted local evidence stream into a bounded,
local-only investigation and triage agent. It consumes only a self-contained
P136 handoff bundle, validates it with the current P136 validators, builds
durable correlated incident state, ranks hypotheses with explicit support,
contradictions, and missing evidence, performs only a closed catalog of bounded
local selections over already-promoted evidence, and emits one terminal
classification for accepted incidents:

- `confirmed_incident`;
- `insufficient_evidence`;
- `benign_anomaly`;
- `aborted_fail_closed`.

Pre-ingest authority, schema, handoff, and P136 validation failures create no
incident classification. They return an exact `expected_error` and leave P137
state unchanged except for allowed evaluator output.

P137 adds no auth, credentials, environment reads, network, DNS, sockets,
provider APIs, notification delivery, action execution, remediation,
staging/production mutation, or operator-replacement authority. It does not
read provider exports, P136 indexes, or files outside the fixed P136 handoff
bundle and P137's own state.

## Dependency boundary

- P134 remains the only observation-authority policy evaluator.
- P135 remains the only provider-shaped segment reader and normalizer.
- P136 remains the only incremental observer and promotion source.
- P137 may ingest P136 promotion records only through
  `p137.p136_handoff_bundle.v1` after full P136 structural, authority, ledger,
  checkpoint, promotion-key, canonical-byte, and release-status validation.
- P137 aligns with the actual P136 promotion model: promotion records bind the
  `entry_hash`; durable checkpoint membership is checked through checkpoint
  `promotion_keys`. P137 does not require or invent a promotion hash chain.
- P137 never constructs P135 manifests, never consumes P134 receipts directly
  for new observation, and never reopens original provider artifacts.
- P137 reads only canonical P136 promotion records, embedded P135 normalized
  bundles, P136 denominator-visible failed promotions, P136 rejection metadata,
  the P136 handoff bundle, and P137's own durable state.

## Authority model

P137's runtime authority is investigation over already-promoted local evidence.
The closed authority catalog contains only:

1. load the fixed P136 handoff bundle path declared in config;
2. load P137's own checkpoint, lease, journal, incident, hypothesis, request,
   classification, heartbeat, readiness, termination, and ledger files;
3. run bounded in-memory correlation, ranking, and classification over validated
   canonical bytes;
4. execute one closed `LOCAL_SELECTION` request over already-loaded P137 atoms
   or already-promoted P136/P135 evidence content.

Every other runtime operation fails closed before execution.

The closed evidence request catalog contains exactly this lexical 15-entry
tuple. Config, matrix rows, tickets, and tests must use this exact order:

1. `compare_current_window_to_promoted_baseline`;
2. `fetch_record_by_evidence_id`;
3. `join_records_by_entity_and_window`;
4. `select_records_by_content_hash`;
5. `select_records_by_entity_ref`;
6. `select_records_by_label_hash`;
7. `select_records_by_provider`;
8. `select_records_by_risk_flag`;
9. `select_records_by_signal_family`;
10. `select_records_by_system_id`;
11. `select_records_by_time_window`;
12. `select_rejections_by_reason`;
13. `summarize_log_preview_hashes`;
14. `summarize_numeric_samples`;
15. `summarize_topology_refs`.

OTLP evidence is represented as promoted metrics in P137. P137 has no separate
distributed-telemetry request category.

Each request is deterministic, bounded, read-only, and evaluated against the
validated promoted-evidence store. No request accepts a path, URL, provider
query, shell fragment, regex with unbounded backtracking, natural-language tool
instruction, endpoint, credential key, or action verb.

## Input and configuration contract

`p137.triage_agent_config.v1` is exact-key, canonical, and self-hashed. It has:

- `schema_version`;
- `agent_id`;
- `config_version`;
- `created_at`;
- `base_dir_ref_hash`;
- `state_root_ref_hash`;
- `handoff_root_ref_hash`;
- `p136_handoff_bundle_path`;
- `p136_handoff_chain_root_hash`;
- `checkpoint_path`;
- `lease_path`;
- `journal_dir`;
- `incident_dir`;
- `hypothesis_dir`;
- `request_dir`;
- `classification_dir`;
- `heartbeat_path`;
- `readiness_path`;
- `termination_dir`;
- `ledger_path`;
- `validated_p136_release_status`;
- `allowed_request_catalog`;
- `correlation_policy`;
- `ranking_policy`;
- `classification_policy`;
- `continuous_mode`;
- `limits`;
- `forbidden_authority`;
- `config_hash`.

Path fields are relative, component-normalized, and resolve under declared local
roots without symlink parents. State paths are pairwise non-overlapping and do
not overlap the fixed handoff bundle path. Promoted artifacts never include
absolute paths.

`validated_p136_release_status` must equal
`p136_incremental_local_observation_qualified`. `allowed_request_catalog` must
be exactly the lexical 15-entry tuple above. `p136_handoff_chain_root_hash` pins
the immutable P136 handoff chain root; config does not pin every future bundle
hash. Bundle advancement is governed by the sequenced handoff and P137
checkpoint rules below.

The runtime invocation supplies complete canonical bytes for the fixed P136
handoff bundle. Hash-only references are insufficient.

`limits` has exactly these positive integer keys:

- `max_promotions_per_cycle`;
- `max_records_per_cycle`;
- `max_incidents_open`;
- `max_correlation_window_ms`;
- `max_incident_duration_ms`;
- `max_hypotheses_per_incident`;
- `max_support_edges_per_hypothesis`;
- `max_contradiction_edges_per_hypothesis`;
- `max_missing_evidence_items_per_hypothesis`;
- `max_evidence_requests_per_incident`;
- `max_request_input_records`;
- `max_request_output_records`;
- `max_request_output_bytes`;
- `max_journal_bytes`;
- `max_ledger_records`;
- `max_consecutive_failures`;
- `max_cycle_wall_ms`;
- `max_agent_wall_ms`;
- `max_cpu_ms`;
- `max_peak_memory_bytes`;
- `max_cycles`;
- `poll_interval_ms`;
- `heartbeat_interval_ms`;
- `readiness_stale_after_ms`;
- `handoff_version_stale_after_ms`.

All integers reject booleans. Budget exhaustion blocks or classifies an
accepted incident `aborted_fail_closed` according to the matrix case. P137
performs no retention deletion.

## P136 handoff bundle

P136 owns an explicit `p136.p137_handoff_publisher.v1` step after durable P136
checkpoint advancement. P137-002 implements only the P136-owned sequenced
fixed-path publisher plus the P137-side validation adapter for that publisher's
object. The P137-side adapter must not read P136 indexes, provider artifacts, or
construct new P136 promotions.

The publisher chain is sequenced and immutable:

- publisher genesis has `bundle_sequence=1`;
- publisher genesis has `previous_bundle_hash=null`;
- the immutable `handoff_chain_root_hash` is derived from the self-hashed
  publisher genesis record, not from P137 config;
- the root is persisted in publisher state before any later bundle can be
  allocated;
- every later bundle allocates `next_bundle_sequence =
  publisher_state.last_bundle_sequence + 1`;
- every later bundle sets `previous_bundle_hash =
  publisher_state.last_bundle_hash`;
- every bundle binds the P136 checkpoint hash and checkpoint promotion map to
  the bundle hash;
- each publish uses intent, state, recovery, atomic replace, file fsync, and
  parent-directory fsync;
- crash recovery republishes identical bytes idempotently and rejects different
  bytes at the same deterministic sequence/path.

P137 config only pins the fixed relative handoff path and the chain root. It
does not create the chain root and does not allocate bundle sequences.

`p137.p136_handoff_bundle.v1` is a durable, self-contained P136 handoff object
written by that publisher to the fixed relative path
`handoff/p137/p136_handoff_bundle.v1.json` by atomic replace, file fsync, and
parent-directory fsync before P137 reads it. The P137 config must name that
exact path and the chain-root hash. Continuous mode polls only this fixed path
and never discovers alternate paths.

The bundle is exact-key, canonical, and self-hashed. It has:

- `schema_version`;
- `bundle_version`;
- `bundle_sequence`;
- `previous_bundle_hash`;
- `handoff_chain_root_hash`;
- `created_at`;
- `p136_config`;
- `p136_config_hash`;
- `p136_runtime_authority`;
- `now`;
- `p136_checkpoint`;
- `p136_checkpoint_hash`;
- `canonical_entry_map`;
- `promotion_map`;
- `p136_independent_review`;
- `p136_independent_review_hash`;
- `p136_release_evidence`;
- `p136_release_evidence_hash`;
- `descriptors`;
- `canonical_byte_hashes`;
- `fixed_handoff_path`;
- `write_durability`;
- `bundle_hash`.

`p136_runtime_authority` is an exact flat object with:

- `contract`;
- `review_receipt`;
- `receipt_ledger`;
- `index_receipts`;
- `segment_receipts`;
- `contract_bytes`;
- `review_receipt_bytes`;
- `receipt_ledger_bytes`;
- `index_receipt_bytes`;
- `segment_receipt_bytes`.

The handoff JSON encodes every byte payload as canonical lowercase hexadecimal
encoding of the exact source bytes. Decoding is strict:

- the encoded value is a nonempty even-length string;
- every character is in `[0-9a-f]`;
- reject whitespace, prefixes such as `0x`, uppercase characters, separators,
  padding, and every non-hex character;
- decode with `bytes.fromhex(source)`;
- `decoded.hex()` must equal the original source string exactly;
- the decoded bytes must hash to the matching `canonical_byte_hashes` entry and
  byte length in `descriptors`;
- P137 passes decoded bytes unchanged for every byte field the P136 validators
  consume, preserving the exact P136 canonical JSON bytes. It must not parse
  and re-emit those validator-consumed bytes before validation. Segment receipt
  bytes are the exception: P137 validates and exact-object-compares them to
  `segment_receipts` before passing only the mappings into P136 validation.

`p136_config` is the complete P136 config. `p136_runtime_authority` is the
complete authority input needed by P136 validation, including contract, review,
ledger, index receipt, and segment receipt canonical bytes. `now` is the exact
runtime instant supplied to P136 validators. `p136_independent_review` is the
final P136 implementation review for the frozen source used to produce the
qualified evidence. `p136_release_evidence` must carry
`p136_incremental_local_observation_qualified`.

`canonical_entry_map` maps each included `entry_hash` to the complete canonical
P136 index entry and its canonical bytes. `promotion_map` maps each included
`entry_hash` to the complete canonical P136 promotion record, its canonical
bytes, its embedded `promotion_key`, the complete embedded P135 normalized
bundle or denominator-visible failure bundle, and all P134/P135 hash bindings
required by the existing P136 validators. `descriptors` bind only relative
deterministic paths, object types, object hashes, byte lengths, and fsync
status. `canonical_byte_hashes` maps each included object type and object hash
to the hash of the exact canonical bytes supplied in the bundle.

P137 validates segment receipt bytes before constructing P136 authority. It
strict-decodes `segment_receipt_bytes`, validates their canonical byte hash and
descriptor length, JSON-parses the decoded canonical bytes, and exact-object
compares the parsed object to `segment_receipts`. Only after that comparison
passes may P137 construct the P136 validator authority.

The bundle-to-P136-runtime adapter constructs the P136 validator runtime only
from `p136_config`, the flattened authority fields, `now`, `p136_checkpoint`,
`canonical_entry_map`, and `promotion_map`. It passes decoded canonical
contract, review-receipt, receipt-ledger, index-receipt, entry, and promotion
bytes directly from the bundle. `validate_observer_runtime_authority` receives
only the byte fields it actually validates for contract, review receipt,
receipt ledger, and index receipts, plus the validated `segment_receipts`
mappings. `validate_promotion_record` consumes the `segment_receipts` mappings
through the supplied runtime; P136 is not claimed to validate segment receipt
bytes. The adapter must not accept nested canonical-byte wrapper objects and
must not call P136 validators positionally. It has no provider reader, index
reader, segment reader, path resolver, environment reader, credential reader,
or network client.

P137 validation must be able to invoke current P136 validators over the bundle
without provider rereads, P136 index rereads, P135 manifest construction, path
discovery, environment reads, or network access.

Direct P137 handoff tests must call the current P136 validators exactly as
runtime will call them:

- `validate_incremental_observer_config(p136_config)`;
- `validate_observer_runtime_authority(p136_config, authority, now=now)` with
  only contract, review, ledger, and index receipt byte fields plus
  `segment_receipts` mappings;
- `validate_promotion_record(promotion, expected_entry=expected_entry, runtime=runtime)`.

Those tests assert P137 independently validated `segment_receipt_bytes`, P136
promotion validation consumed `segment_receipts` mappings, and provider, index,
segment, path-discovery, environment, network, and credential reads stayed
zero.

## Validated P136 ingest

P137 accepts a promotion only when all of these checks pass:

- the P136 handoff bundle self-hash, fixed path, canonical bytes, descriptors,
  and durability metadata validate;
- P136 release evidence structurally validates and carries the exact qualified
  status;
- the final P136 implementation review exists, is source-bound to the release
  evidence, and has zero unresolved P0/P1/P2 findings;
- P136 config, checkpoint self-hash, consumed-prefix hash, `promotion_keys`,
  counters, and forbidden-authority zero fields validate;
- promotion record self-hash, promotion key, `entry_hash`, P134 contract/ledger/
  receipt hashes, P135 manifest/bundle/execution-receipt/ledger hashes, and
  denominator-visible status validate;
- checkpoint membership is exact:
  `checkpoint.promotion_keys[promotion.entry_hash]` must equal the complete
  canonical promotion record in `promotion_map[promotion.entry_hash]`;
- the embedded `promotion_key` is separately recomputed from that complete
  canonical promotion record and must equal the record's embedded value;
- embedded P135 normalized bundles and denominator-failure bundles validate
  without re-reading the original segment;
- no promoted object contains absolute paths, credentials, endpoint secrets,
  unredacted raw provider payloads, prompt-like instructions, or action verbs in
  executable fields;
- P136 forbidden authority counters are exact integer zero.

Accepted records are converted into `p137.evidence_atom.v1` objects:

- `schema_version`;
- `atom_id`;
- `promotion_record_hash`;
- `promotion_key`;
- `p136_entry_hash`;
- `p135_bundle_hash`;
- `source_id`;
- `provider`;
- `format`;
- `signal_family`;
- `system_id`;
- `entity_ref_hash`;
- `window`;
- `signal_name`;
- `numeric_value`;
- `numeric_unit`;
- `evidence_state`;
- `severity_code`;
- `metric_breach_code`;
- `marker_code`;
- `counter_signal_code`;
- `state_reason_codes`;
- `denominator_visible`;
- `content_hash`;
- `label_hashes`;
- `topology_ref_hashes`;
- `deploy_config_ref_hashes`;
- `risk_flags`;
- `redacted_preview_hash`;
- `ordinal`;
- `atom_hash`.

P137 stores hashes and bounded redacted preview hashes only. It never promotes
raw log bodies, queries, exception text, secrets, or absolute paths.

The P136 handoff validator has explicit negative cases for an absent
`promotion.entry_hash` key in `checkpoint.promotion_keys`, an altered canonical
promotion record value under the correct key, and a nested wrong
`promotion_key` inside an otherwise correctly keyed canonical promotion record.

## Incident state and correlation

`p137.incident_state.v1` is exact-key, self-hashed, and append-derived. It has:

- `schema_version`;
- `incident_id`;
- `incident_sequence`;
- `status`;
- `created_at`;
- `updated_at`;
- `correlation_key`;
- `primary_system_id`;
- `entity_ref_hashes`;
- `time_window`;
- `source_promotion_record_hashes`;
- `evidence_atom_hashes`;
- `rejection_hashes`;
- `hypothesis_hashes`;
- `request_hashes`;
- `attempted_request_hashes`;
- `classification_hash`;
- `previous_incident_hash`;
- `incident_hash`.

Legal nonterminal statuses are `open`, `correlating`, `investigating`,
`ready_to_classify`, and `classification_pending`. Legal terminal statuses are
the four P137 classifications. The transition graph is:

`open -> correlating -> investigating -> ready_to_classify -> classification_pending -> confirmed_incident|insufficient_evidence|benign_anomaly|aborted_fail_closed`

Additional fail-closed transitions are legal from any nonterminal state to
`aborted_fail_closed` only when the failure occurs after an incident exists and
P137 can still complete both the classification record write and ledger CAS.
Failures that cannot safely complete both writes return classification `none`
with the exact error and termination reason. No terminal state may transition.

Correlation keys are deterministic tuples selected from:

- exact `system_id`;
- exact `entity_ref_hash`;
- overlapping time window;
- provider/signal family;
- shared label hash;
- shared content hash;
- P136 rejection reason.

Free-form text similarity, LLM calls, embeddings, network lookup, provider
lookup, and operator prompts are not correlation inputs.

## Hypotheses

`p137.hypothesis.v1` is exact-key, canonical, self-hashed, and incident-scoped:

- `schema_version`;
- `hypothesis_id`;
- `incident_id`;
- `hypothesis_sequence`;
- `category`;
- `statement_code`;
- `scope`;
- `support`;
- `contradictions`;
- `missing_evidence`;
- `score`;
- `rank`;
- `classification_vote`;
- `previous_hypothesis_hash`;
- `hypothesis_hash`.

`category` is one of `availability`, `latency`, `error_rate`,
`resource_saturation`, `data_quality`, `telemetry_gap`, `security_signal`,
`deployment_change`, `topology_change`, `benign_pattern`, or `unknown`.
`statement_code` is exactly one of this closed small set:

- `metric_spike_with_correlated_logs`;
- `error_rate_regression`;
- `latency_regression`;
- `resource_saturation_signal`;
- `data_quality_drop`;
- `telemetry_gap_only`;
- `security_signal_cluster`;
- `deployment_correlated_change`;
- `topology_correlated_change`;
- `scheduled_or_known_benign_noise`;
- `unknown_insufficient_context`.

No statement may contain free-form text.

Each support or contradiction edge has exactly:

- `edge_id`;
- `evidence_atom_hash`;
- `relation`;
- `weight`;
- `window`;
- `reason_code`;
- `edge_hash`.

Each missing-evidence item has exactly:

- `missing_id`;
- `request_kind`;
- `request_need_class`;
- `expected_value_code`;
- `why_needed_code`;
- `blocking`;
- `unavailable_need_hash`;
- `item_hash`.

`request_need_class` is exactly one of:

- `LOCAL_SELECTION`: a request may execute only if it names a catalog entry and
  its inputs are already validated P137/P136 atoms or promoted bytes.
- `EXTERNAL_UNAVAILABLE`: the need requires unavailable provider, network,
  credential, operator, or action authority. It is recorded as missing evidence
  and is never executed or converted into a request.

### Closed statement, reason, edge, and classifier rules

`classification_policy` is an exact-key object with only these keys:

- `schema_version`;
- `statement_rules`;
- `reason_rules`;
- `relation_rules`;
- `metric_thresholds`;
- `baseline_delta_warning_bps`;
- `baseline_delta_critical_bps`;
- `score_formula_id`;
- `tie_policy`;
- `denominator_failure_policy`;
- `policy_hash`.

It rejects unknown keys and any free-form rule text. `score_formula_id` must be
`p137_integer_semantic_score_v1`. `tie_policy` must be
`semantic_tuple_tie_yields_insufficient_evidence`.

The atom classifier input enums are closed:

- `evidence_state`: `promoted_success`, `denominator_visible_failure`,
  `context_only`;
- `severity_code`: `sev0`, `sev1`, `sev2`, `sev3`, `sev4`, `unknown`;
- `metric_breach_code`: `none`, `above_warning`, `above_critical`,
  `below_warning`, `below_critical`, `baseline_delta_warning`,
  `baseline_delta_critical`;
- `marker_code`: `none`, `known_benign_schedule`, `topology_noise`,
  `deployment_marker`, `topology_marker`, `security_marker`, `data_quality_marker`;
- `counter_signal_code`: `none`, `weak_counter_signal`,
  `decisive_counter_signal`;
- `state_reason_codes`: zero or more of `parser_failure`,
  `redaction_failure`, `provenance_failure`, `local_catalog_selectable`,
  `p135_adapter_failure`,
  `provider_authority_required`, `network_authority_required`,
  `credential_authority_required`, `operator_authority_required`,
  `action_authority_required`.

Promotion and record inputs normalize into those atom fields by exact formula
before any statement rule runs. The source fields are the accepted P136
promotion record, the embedded P135 record, and that record's embedded P120
record:

- `promotion.status=denominator_failure` requires
  `p120_record.evidence_state=fail_closed` and maps to
  `evidence_state=denominator_visible_failure`;
- `promotion.status=success` with `p120_record.evidence_state=valid` maps to
  `evidence_state=promoted_success`;
- `promotion.status=success` with each other allowed P120 state
  (`missing_evidence`, `contradiction`, `ood`, `investigate_more`, `abstain`,
  `escalate`, `fail_closed`) maps to `evidence_state=context_only`;
- `promotion.status=denominator_failure` with any P120 state other than
  `fail_closed` is invalid and rejects atom conversion with
  `denominator_failure_state_mismatch`;
- `signal_name` is exactly `p120_record.signal_name`;
- `numeric_value` is exactly `p120_record.value` when the value type is finite
  `int` or finite `float`; booleans are rejected with
  `p120_numeric_value_bool`; nonnumeric values map to `null` because P120 permits
  deploy marker strings and failure records;
- `numeric_unit` is exactly `p120_record.unit` when `numeric_value` is not
  `null`; when `numeric_value` is `null`, `numeric_unit` is `null`;
- `severity_code = lower(p120_record.severity)` when it is one of `sev0`,
  `sev1`, `sev2`, `sev3`, or `sev4`; missing or unknown severity maps to
  `unknown`;
- `label_hashes` is the lexical list of hashes of P120 `labels` entries by
  key/value pair. `topology_ref_hashes` and `deploy_config_ref_hashes` are the
  lexical lists of hashes of P120 `topology_refs` and `deploy_config_refs`;
- `risk_flags` is the lexical deduplicated list from the P135 record
  `risk_flags`. P120 does not define or supply `risk_flags`;
- `marker_code` precedence is `known_benign_schedule`, `topology_noise`,
  `deployment_marker`, `topology_marker`, `security_marker`,
  `data_quality_marker`, `none`. P135 `risk_flags` select `security_marker` for
  `prompt_like_text`, `credential_like_text`, or `unsafe_action_request`;
  nonempty P120 `deploy_config_refs` selects `deployment_marker`; nonempty P120
  `topology_refs` selects `topology_marker`; P120 `modality=topology` with empty
  `topology_refs` selects `topology_noise`; P120 `signal_name=data_quality`
  selects `data_quality_marker` when no higher precedence marker applies;
- `counter_signal_code` is `decisive_counter_signal` if P135 `risk_flags`
  contains `decisive_counter_signal`, else `weak_counter_signal` if it contains
  `weak_counter_signal`, else `none`;
- for `promotion.status=denominator_failure`, the existing P135
  denominator-failure bundle validation must pass before P137 atom conversion.
  `bundle.failure_reason` must be a nonempty closed-safe string, must exactly
  equal the sole P120 `state_reasons` element, and must exactly equal the
  normalized failure label value when that label is present. P137 does not
  enumerate P135 failure strings and does not substring-match them. Any
  validator-accepted P135 denominator failure maps deterministically to
  `state_reason_codes=["local_catalog_selectable", "p135_adapter_failure"]`
  and `request_need_class=LOCAL_SELECTION`. This is a total source-bound
  mapping for arbitrary validated P135 `failure_reason` strings;
- for `promotion.status=success` and context-only P120 records,
  `state_reason_codes` is the sorted deduplicated mapping of P120
  `state_reasons` after validating every source reason against the closed table
  below. Unknown P120 state reason strings reject atom conversion with
  `p120_state_reason_unmapped`; they are not guessed from substrings.

Closed P120 `state_reasons` mapping for success and context-only records:

| P120 `state_reasons` value | Atom `state_reason_codes` value |
| --- | --- |
| `unsupported_modality`, `unsupported_modality_hidden`, `missing_telemetry_record_id`, `missing_source_id`, `missing_system_id`, `missing_service_id`, `missing_entity_ref`, `missing_modality`, `missing_observed_at`, `missing_window`, `missing_signal_name`, `missing_unit`, `nullable_metric_preserved`, `missing_redaction_receipt`, `invalid_normalization_version`, `telemetry_dropped_from_denominator`, `invalid_evidence_state` | `parser_failure` |
| `redaction_failure` | `redaction_failure` |
| `authority_drift_visible`, `p120_raw_ref_source_hash_mismatch`, `p120_raw_ref_record_id_mismatch`, `record_source_hash_mismatch`, `record_source_id_mismatch`, `record_source_schema_mismatch` | `provenance_failure` |
| `timestamp_uncertainty_visible`, `timestamp_skew_visible`, `delayed_record_visible`, `duplicate_record_visible`, `reorder_visible`, `contradictory_telemetry_visible`, `stale_record` | `local_catalog_selectable` |
| `provider_authority_required` | `provider_authority_required` |
| `network_authority_required` | `network_authority_required` |
| `credential_authority_required` | `credential_authority_required` |
| `operator_authority_required` | `operator_authority_required` |
| `action_authority_required` | `action_authority_required` |

`metric_breach_code` is `none` when `numeric_value` or `numeric_unit` is
`null`. Otherwise, look up
`classification_policy.metric_thresholds[signal_name][numeric_unit]`, an
exact-key record with integer `warning_lower`, `critical_lower`,
`warning_upper`, and `critical_upper` fields where unavailable bounds are
encoded as `null`. Values at or beyond critical bounds map to
`below_critical` or `above_critical`; values at or beyond warning bounds map to
`below_warning` or `above_warning`; otherwise the code is `none`. Baseline
comparison uses
`abs(current_numeric_value - baseline_numeric_value) * 10000 /
max(abs(baseline_numeric_value), 1)`. A result greater than or equal to
`baseline_delta_critical_bps` maps to `baseline_delta_critical`; a result
greater than or equal to `baseline_delta_warning_bps` maps to
`baseline_delta_warning`.

Statement rules are evaluated in the table order below; the first matching row
wins, so every valid input has exactly one statement code and category.

The total deterministic statement mapping is:

| Input predicate | Statement code | Category |
| --- | --- | --- |
| `evidence_state=promoted_success` and `signal_name=error_rate` and `metric_breach_code` is `above_warning` or `above_critical` | `error_rate_regression` | `error_rate` |
| `evidence_state=promoted_success` and `signal_name=latency` and `metric_breach_code` is `above_warning` or `above_critical` | `latency_regression` | `latency` |
| `evidence_state=promoted_success` and `signal_name` is `cpu`, `memory`, `disk`, or `queue_depth` and `metric_breach_code` is not `none` | `resource_saturation_signal` | `resource_saturation` |
| `evidence_state=promoted_success` and `signal_name=data_quality` and `metric_breach_code` is not `none` | `data_quality_drop` | `data_quality` |
| `evidence_state=promoted_success` and `marker_code=security_marker` | `security_signal_cluster` | `security_signal` |
| `evidence_state=promoted_success` and `marker_code=deployment_marker` | `deployment_correlated_change` | `deployment_change` |
| `evidence_state=promoted_success` and `marker_code=topology_marker` | `topology_correlated_change` | `topology_change` |
| `evidence_state=promoted_success` and `marker_code` is `known_benign_schedule` or `topology_noise` | `scheduled_or_known_benign_noise` | `benign_pattern` |
| `evidence_state=promoted_success` and `metric_breach_code` is `baseline_delta_warning` or `baseline_delta_critical` and at least one of `label_hashes`, `content_hash`, or `redacted_preview_hash` is nonempty | `metric_spike_with_correlated_logs` | `availability` |
| `evidence_state=denominator_visible_failure` and local/external mapping below yields blocking missing evidence | `telemetry_gap_only` | `telemetry_gap` |
| Any other valid atom input | `unknown_insufficient_context` | `unknown` |

The total deterministic reason/relation mapping is:

| Input predicate | Reason code | Relation | Weight |
| --- | --- | --- | ---: |
| Same system and overlapping window | `same_system_time_window` | `supports_secondary` | 2 |
| Same entity and overlapping window | `same_entity_time_window` | `supports_secondary` | 2 |
| Same provider and signal family | `provider_signal_overlap` | `supports_secondary` | 2 |
| Shared label hash | `label_hash_overlap` | `supports_secondary` | 2 |
| Shared content hash | `content_hash_overlap` | `supports_secondary` | 2 |
| P136 rejection within correlation window | `p136_rejection_nearby` | `missing_required_local` or `missing_external_unavailable` | -4 |
| `metric_breach_code` is warning or critical | `numeric_threshold_exceeded` | `supports_primary` | 4 |
| Shared `redacted_preview_hash` cluster is nonempty | `log_preview_cluster` | `supports_secondary` | 2 |
| `marker_code=topology_marker` | `topology_change_detected` | `supports_secondary` | 2 |
| `metric_breach_code` is `baseline_delta_warning` or `baseline_delta_critical` | `promoted_baseline_delta` | `supports_primary` | 4 |
| Closed request fetch matched requested evidence ID | `fetch_record_match` | `supports_secondary` | 2 |
| `marker_code=known_benign_schedule` | `known_benign_schedule` | `supports_benign` | 3 |
| `counter_signal_code=decisive_counter_signal` | `decisive_counter_signal` | `contradicts_decisive` | -5 |
| `counter_signal_code=weak_counter_signal` | `weak_counter_signal` | `contradicts_soft` | -2 |
| Local catalog need remains unfilled | `required_local_selection_missing` | `missing_required_local` | -4 |
| External authority is required | `external_authority_unavailable` | `missing_external_unavailable` | -4 |

Denominator-visible failures map by total rule:

- validated P135 denominator-failure bundles always map to
  `state_reason_codes=["local_catalog_selectable", "p135_adapter_failure"]`
  and `request_need_class=LOCAL_SELECTION` by the source-bound generic
  conversion above, regardless of the failure-reason string contents;
- if a non-P135-adapter record's `state_reason_codes` contains
  `local_catalog_selectable` and contains none
  of the external-authority reason codes, request need class is
  `LOCAL_SELECTION`;
- if a non-P135-adapter record's `state_reason_codes` contains any of
  `provider_authority_required`,
  `network_authority_required`, `credential_authority_required`,
  `operator_authority_required`, or `action_authority_required`, request need
  class is `EXTERNAL_UNAVAILABLE`;
- if both local and external reasons are present, `EXTERNAL_UNAVAILABLE` wins;
- if neither local nor external reasons are present, schema validation fails
  with `denominator_failure_reason_unmapped`.

The `EXTERNAL_UNAVAILABLE` rule is driven only by closed external-authority
state reason codes. It is never inferred from arbitrary P135
`failure_reason` substrings.

`reason_code` is exactly one of:

- `same_system_time_window`;
- `same_entity_time_window`;
- `provider_signal_overlap`;
- `label_hash_overlap`;
- `content_hash_overlap`;
- `p136_rejection_nearby`;
- `numeric_threshold_exceeded`;
- `log_preview_cluster`;
- `topology_change_detected`;
- `promoted_baseline_delta`;
- `fetch_record_match`;
- `known_benign_schedule`;
- `decisive_counter_signal`;
- `weak_counter_signal`;
- `required_local_selection_missing`;
- `external_authority_unavailable`.

Evidence state maps to candidate edges by closed rule:

| Evidence state | Allowed candidate edge rules |
| --- | --- |
| `promoted_success` with metric threshold or baseline delta | `supports_primary` for non-benign incident statements. |
| `promoted_success` with provider/signal, label, content, or fetch match only | `supports_secondary`. |
| `promoted_success` with known benign schedule or topology-noise marker | `supports_benign`. |
| `denominator_visible_failure` from P136/P135 parser, redaction, or provenance rejection | `missing_required_local` or `missing_external_unavailable`, depending on whether the only needed follow-up is a local catalog selection. |
| `promoted_success` carrying a decisive counter-signal | `contradicts_decisive`. |
| `promoted_success` carrying a weak counter-signal | `contradicts_soft`. |
| Context-only atom with no classifier effect | `neutral_context`. |

Any evidence-state/reason-code combination outside this table fails schema
validation before ranking.

| Relation | Edge list | Weight | Classifier effect |
| --- | --- | ---: | --- |
| `supports_primary` | support | 4 | Counts toward a non-benign confirmation when category is not `benign_pattern`. |
| `supports_secondary` | support | 2 | Adds support but cannot confirm alone. |
| `supports_benign` | support | 3 | Counts only toward `benign_anomaly`. |
| `contradicts_decisive` | contradictions | -5 | Blocks `confirmed_incident`. |
| `contradicts_soft` | contradictions | -2 | Reduces rank but does not block alone. |
| `missing_required_local` | missing_evidence | -4 | Blocks confirmation until the one-shot local request is attempted or reused. |
| `missing_optional_local` | missing_evidence | -1 | Reduces rank and does not block alone. |
| `missing_external_unavailable` | missing_evidence | -4 | Blocks confirmation when marked blocking; never executes. |
| `neutral_context` | support | 0 | Preserves context without changing classification. |

Classification is exact:

| Condition | Expected label |
| --- | --- |
| Non-benign top hypothesis has at least one `supports_primary`, no `contradicts_decisive`, and no blocking missing evidence | `confirmed_incident` |
| Top hypothesis category is `benign_pattern`, has `supports_benign`, and has no blocking missing evidence | `benign_anomaly` |
| Blocking missing evidence remains, local request attempts are exhausted, external unavailable evidence is required, or deterministic top-hypothesis ties remain unresolved | `insufficient_evidence` |
| Accepted incident hits authority, schema, durability, budget, signal-before-classification, or unknown runtime failure and the classification record write and ledger CAS both succeed | `aborted_fail_closed` |
| Corrupt state, CAS failure, lease/resource failure, or any failure where classification write or ledger CAS does not succeed | classification `none`; exact `expected_error` and/or `termination_reason` only |

Scores are deterministic integer tuples, never probabilities:

- `support_weight`;
- `contradiction_weight`;
- `missing_required_count`;
- `freshness_weight`;
- `source_diversity_weight`;
- `rank_score`.

The exact formulas are:

- `support_weight = sum(weight for support edges)`;
- `contradiction_weight = sum(abs(weight) for contradiction edges)`;
- `missing_required_count = count(missing_evidence where blocking=true)`;
- `freshness_weight = max(0, 3 - age_bucket)`, where `age_bucket` is the integer
  floor of the newest supporting atom age divided by the configured correlation
  window; no support yields `0`;
- `source_diversity_weight = min(3, count(distinct provider values among support
  edges))`;
- `rank_score = support_weight - contradiction_weight -
  (4 * missing_required_count) + freshness_weight + source_diversity_weight`.

The semantic ranking tuple is:

`(rank_score, support_weight, -contradiction_weight, -missing_required_count, freshness_weight, source_diversity_weight)`.

Unresolved ties are detected on that pre-hash semantic score tuple. Lexical
hypothesis hash is used only to produce stable storage order for tied
hypotheses; it never resolves the semantic tie for classification. If the top
semantic tuple is shared by two or more incompatible hypotheses, classification
is `insufficient_evidence`.

## Evidence requests

`p137.evidence_request.v1` records every bounded local selection:

- `schema_version`;
- `request_id`;
- `incident_id`;
- `request_sequence`;
- `catalog_name`;
- `parameters`;
- `input_atom_hashes`;
- `budget`;
- `attempted_request_hash`;
- `result_summary`;
- `runtime_activity`;
- `previous_request_hash`;
- `request_hash`.

The request must name one catalog entry from `allowed_request_catalog`.
Parameters are exact-key catalog-specific objects containing only hashes,
integer bounds, timestamps, enums, and closed labels. A request may read only
validated P137 evidence atoms or already-promoted P136/P135 bytes supplied in
the handoff bundle. It must not open original provider paths, perform directory
discovery, inspect environment variables, call subprocesses, or allocate beyond
budget.

Every planned `LOCAL_SELECTION` derives a one-shot `attempted_request_hash` over
incident hash, catalog name, parameters, input atom hashes, budget, and request
sequence before execution. The incident and ledger store a duplicate-free list
of attempted request hashes. If the hash already exists, P137 may only reuse the
durable request bytes. It must not execute the same local selection again.
Conflicting bytes at the deterministic request path fail closed.

`EXTERNAL_UNAVAILABLE` needs never create `p137.evidence_request.v1` records.
They remain missing-evidence items and can drive `insufficient_evidence`.

## Classification and ledger

`p137.classification_record.v1` is exact-key and self-hashed:

- `schema_version`;
- `classification_id`;
- `incident_id`;
- `classification_sequence`;
- `classification`;
- `decided_at`;
- `top_hypothesis_hash`;
- `support_summary_hashes`;
- `contradiction_summary_hashes`;
- `missing_evidence_hashes`;
- `confidence_code`;
- `decision_reasons`;
- `authority_counters`;
- `runtime_activity`;
- `resource_usage`;
- `previous_classification_hash`;
- `classification_hash`.

Classification rules are the table above. Pre-ingest failures do not create
classification records.

`p137.investigation_ledger.v1` chains incidents, hypotheses, requests, and
classifications:

- `schema_version`;
- `config_hash`;
- `next_incident_sequence`;
- `next_request_sequence`;
- `next_classification_sequence`;
- `incident_hashes`;
- `classification_hashes`;
- `attempted_request_hashes`;
- `counters`;
- `authority_counters`;
- `runtime_activity`;
- `evaluator_activity`;
- `resource_usage`;
- `previous_ledger_hash`;
- `ledger_hash`.

Ledger validation recomputes every hash, sequence, transition, counter,
attempted request hash, and classification derivation. Rehashed forged counters
or detached classifications fail closed.

## Durability, lease, idempotency, CAS, and hash namespaces

The runtime state machine is:

`UNLEASED -> LEASED -> LOAD -> RECOVER -> VALIDATE_HANDOFF -> INGEST_P136 -> CORRELATE -> RANK_HYPOTHESES -> REQUEST_EVIDENCE -> CLASSIFY -> WRITE_CLASSIFICATION -> ADVANCE_LEDGER -> IDLE|STOP`.

One nonblocking exclusive lease is acquired before reading P137 state or the
P136 handoff bundle. Lease conflict exits before any ingest, request,
classification, checkpoint, or ledger write activity and returns
`expected_error=lease_conflict`. It may write only an evaluator-owned case
artifact outside P137 runtime state.

Durable order:

1. acquire lease;
2. load and validate config, prior ledger, and checkpoint;
3. recover any valid intents or durable records;
4. validate the fixed P136 handoff bundle with current P136 validators;
5. atomically write and fsync `p137.ingest_intent.v1`, then fsync parent;
6. atomically write and fsync incident state, then fsync parent;
7. atomically write and fsync hypothesis records, then fsync parent;
8. atomically write and fsync each evidence request record, then fsync parent;
9. atomically write and fsync classification intent, then fsync parent;
10. atomically write and fsync classification record, then fsync parent;
11. atomically replace and fsync ledger/checkpoint, then fsync parent.

All writes use deterministic paths derived from config hash, incident ID,
sequence, and content hash. Equivalent bytes are idempotent. Existing different
bytes at an equivalent path fail closed. Checkpoint and ledger replacement is
CAS-bound to the prior ledger hash. A CAS predecessor mismatch returns
`expected_error=ledger_cas_predecessor_mismatch` and `termination_reason=cas_failure`
with classification `none`, because P137 cannot claim terminal state without a
successful ledger CAS. Every record links the prior hash in its namespace; the
ledger links all namespace heads. P137 does not depend on a P136 promotion hash
chain.

`p137.checkpoint.v1` stores:

- `schema_version`;
- `config_hash`;
- `last_accepted_bundle_sequence`;
- `last_accepted_bundle_hash`;
- `last_accepted_ledger_hash`;
- `last_accepted_checkpoint_hash`;
- `checkpoint_hash`.

P137 rejects bundle rollback when `bundle_sequence` is lower than
`last_accepted_bundle_sequence`, rejects replay/fork when the same sequence has
a different bundle hash, rejects a future bundle whose `previous_bundle_hash`
does not equal `last_accepted_bundle_hash`, and rejects torn replacement when
the fixed-path bytes, descriptor length/hash, `bundle_hash`, and directory fsync
metadata do not match.

P137 defines no reserved write capacity. A case may produce
`aborted_fail_closed` only when the classification record write and ledger CAS
both succeed within the measured case limit. If a corrupt state, CAS conflict,
lease failure, resource exhaustion, or disk/resource condition prevents those
writes, the outcome is classification `none` with the exact matrix
`expected_error` and `termination_reason`.

Recovery rules:

- intent without record resumes the same deterministic operation;
- incident without hypotheses resumes ranking from the incident hash;
- hypotheses without requests resume bounded request planning;
- request records without classification are reused and never re-executed unless
  the recorded bytes are identical and budget remains;
- classification without ledger is ledgered without recomputing or reclassifying;
- corrupt, stale, forked, or semantically inconsistent state fails closed and
  preserves the last valid ledger with classification `none` unless an already
  durable classification record can be ledgered through a successful CAS.

## Runtime and bounded continuous mode

The CLI supports one-cycle mode and bounded local foreground-loop mode.
Continuous mode is finite. It stops at `max_cycles`, receipt/input exhaustion,
`max_consecutive_failures`, stale handoff version, stale readiness, budget
exhaustion, SIGINT, SIGTERM, or lease conflict.

`continuous_mode` has exactly:

- `enabled`;
- `max_cycles`;
- `poll_interval_ms`;
- `fixed_handoff_path`;
- `expected_bundle_version`;
- `handoff_version_polling`;
- `heartbeat_interval_ms`;
- `readiness_path`;
- `readiness_stale_after_ms`;
- `handoff_version_stale_after_ms`.

When enabled, each cycle:

1. acquires the lease;
2. polls only `fixed_handoff_path`;
3. validates the bundle version and bundle hash;
4. processes at most `max_promotions_per_cycle`;
5. writes a heartbeat record at the configured cadence;
6. writes readiness `ready`, `degraded`, or `stale` with exact reasons;
7. sleeps by monotonic cadence until the next finite cycle.

P137 does not claim live provider monitoring, notification delivery, operator
handoff, action execution, or unbounded always-on operation. It is a bounded
local poller over a fixed handoff path.

`p137.heartbeat.v1` binds `agent_id`, `config_hash`, `cycle_sequence`,
`monotonic_elapsed_ms`, `last_valid_ledger_hash`, readiness state, and
`heartbeat_hash`.

`p137.termination_receipt.v1` is exact-key and self-hashed:

- `schema_version`;
- `agent_id`;
- `config_hash`;
- `stop_reason`;
- `safe_boundary`;
- `last_valid_ledger_hash`;
- `open_incident_hashes`;
- `terminal_classification_hashes`;
- `runtime_activity`;
- `evaluator_activity`;
- `resource_usage`;
- `authority_counters`;
- `termination_hash`.

`stop_reason` is one of `max_cycles_reached`, `no_new_promotions`,
`budget_exhausted`, `failure_threshold_reached`, `handoff_version_stale`,
`readiness_stale`, `sigint`, `sigterm`, `lease_conflict`, or
`aborted_fail_closed`. Signal handlers set only a stop flag. A signal-driven
`aborted_fail_closed` is authoritative only when the classification record write
and ledger CAS both succeed. If the signal arrives before those writes can
safely complete, P137 returns classification `none` with the exact signal
termination reason and preserves the last valid ledger. Termination receipts
never imply notification delivery or operator handoff.

## Static and runtime authority guards

Static checks must prove P137 runtime code introduces no provider SDK usage,
network client, socket use, DNS resolution, credential lookup, environment
reads, subprocess/shell execution, notification delivery, action/remediation
module, or staging/production mutation path.

Runtime guard probes are evaluator-injected fake callables only. The evaluator
passes blocked callables for provider, network, DNS, socket, credential,
environment, subprocess, shell, signal, delivery, remediation, mutation, and
operator-replacement surfaces. P137 runtime may receive those fake callables
only through the test harness guard boundary; production/runtime imports remain
statically banned. A successful probe proves the fake callable was rejected
before invocation. Runtime forbidden counters remain exact integer zero because
the guarded operation never crosses the runtime boundary.

`forbidden_authority` has exactly these integer keys, all measured and zero:

- `provider_call_count`;
- `live_connector_call_count`;
- `network_call_count`;
- `dns_lookup_count`;
- `socket_call_count`;
- `credential_read_count`;
- `environment_read_count`;
- `subprocess_launch_count`;
- `shell_execution_count`;
- `signal_count`;
- `delivery_count`;
- `remediation_count`;
- `staging_mutation_count`;
- `production_mutation_count`;
- `operator_replacement_count`.

`runtime_activity` has exactly these nonnegative integer keys:

- `lease_acquire_count`;
- `state_read_count`;
- `handoff_bundle_open_count`;
- `handoff_bundle_read_count`;
- `handoff_bundle_bytes_read`;
- `p136_validator_invocation_count`;
- `promotion_record_read_count`;
- `promotion_bytes_validated`;
- `evidence_atom_count`;
- `ingest_intent_write_count`;
- `evidence_atom_write_count`;
- `incident_write_count`;
- `hypothesis_write_count`;
- `evidence_request_write_count`;
- `attempted_request_hash_write_count`;
- `classification_write_count`;
- `ledger_write_count`;
- `heartbeat_write_count`;
- `readiness_write_count`;
- `termination_receipt_write_count`;
- `directory_fsync_count`;
- `recovery_replay_count`;
- `cas_retry_count`;
- `duplicate_atom_count`;
- `duplicate_request_count`;
- `rejection_record_count`.

Counter semantics are exact:

- `lease_acquire_count` increments once per successful runtime lease
  acquisition attempt admitted into P137 runtime;
- `state_read_count` counts reads of P137 checkpoint, ledger, lease, journal,
  incident, hypothesis, request, classification, heartbeat, readiness,
  termination, and ledger state files;
- `handoff_bundle_open_count`, `handoff_bundle_read_count`, and
  `handoff_bundle_bytes_read` count only the fixed P136 handoff bundle path;
- `p136_validator_invocation_count` counts direct calls into current P136
  validators over supplied bundle bytes;
- `promotion_record_read_count` and `promotion_bytes_validated` count canonical
  promotion records accepted from the bundle;
- `evidence_atom_count` counts converted atoms, while
  `evidence_atom_write_count` counts durable atom writes;
- `ingest_intent_write_count`, `incident_write_count`,
  `hypothesis_write_count`, `evidence_request_write_count`,
  `attempted_request_hash_write_count`, `classification_write_count`,
  `ledger_write_count`, `heartbeat_write_count`, `readiness_write_count`, and
  `termination_receipt_write_count` count durable writes of those exact P137
  record types;
- `directory_fsync_count`, `recovery_replay_count`, `cas_retry_count`,
  `duplicate_atom_count`, `duplicate_request_count`, and
  `rejection_record_count` count measured filesystem durability, recovery,
  CAS, duplicate, and rejection events.

Duplicate atom and request counts are probe-derived from repeated entry hashes,
promotion keys, and attempted request hashes. They are never initialized as
assumed zero release claims.

`evaluator_activity` has exactly these nonnegative integer keys:

- `runner_invocation_count`;
- `profile_read_count`;
- `handoff_fixture_write_count`;
- `artifact_write_count`;
- `fake_guard_callable_count`;
- `child_process_count`;
- `signal_delivery_count`.

Evaluator activity never inflates runtime activity.

`resource_usage` has exactly:

- integer `wall_time_ms`, measured by the canonical runner with a monotonic
  clock;
- integer `cpu_time_ms` for the evaluator process and integer
  `child_cpu_time_ms`, both from `resource.getrusage`; the release CPU limit
  applies to their sum;
- integer `peak_memory_bytes`, measured as the P137 matrix interval's increase
  in process peak RSS over its start baseline, normalizing macOS `ru_maxrss`
  bytes and Linux `ru_maxrss` KiB so an embedding process's earlier high-water
  mark is not charged to P137;
- integer limits `wall_limit_ms=30000`, `cpu_limit_ms=15000`, and
  `peak_memory_limit_bytes=134217728`.

All exact-key maps reject booleans, negative values, unknown keys, and
self-reported or stamped counters.

## Fixed 60-case release matrix

The canonical P137 runner executes exactly these 60 cases. Every case carries an
explicit category, exact expected label or exact expected error, expected
classification scope, termination reason, and named delta profile. Aggregate
booleans alone are insufficient.

Delta profiles are machine-readable exact-key maps emitted by the source-bound
fixture builder. Every profile includes all forbidden-authority keys, every
forbidden-authority delta is integer `0`, and every runtime/write delta is an
integer. Byte deltas are not constants: `handoff_bundle_bytes_read` is measured
from the fixed-path framed file as `len(canonical_handoff_bundle_bytes) + 1` for
its required newline delimiter, and
`promotion_bytes_validated` is materialized as
`sum(len(canonical_promotion_bytes) for included promotions)` for that case
fixture. The final matrix evidence must contain those concrete integers, never
symbolic formulas or placeholder strings.

Each delta profile is either an exact full map containing every
`runtime_activity`, `forbidden_authority`, `evaluator_activity`, and
`resource_usage` key, or an explicitly source-bound exact override applied over
the canonical zero full map for those schemas. Override profiles may mention
only canonical schema keys. The materialized matrix row must contain the full
post-override map, so no profile-only alias can appear in final evidence.

The named profile set is exact:

- `dp_no_runtime_write`;
- `dp_pre_ingest_reject`;
- `dp_classified_no_request`;
- `dp_classified_with_request`;
- `dp_abort_written`;
- `dp_recovery_after_ingest_intent`;
- `dp_recovery_after_incident_write`;
- `dp_recovery_after_request_write`;
- `dp_recovery_after_classification_before_ledger`;
- `dp_continuous_control`;
- `dp_signal_no_classification`;
- `dp_corrupt_state_no_write`;
- `dp_evaluator_guard`;
- `dp_resource_preclassification_stop`.

Resource-exhaustion cases set a case-specific low measured limit below the
runner-owned preclassification measurement and validate the exact
`dp_resource_preclassification_stop` write deltas before failure.

`dp_signal_no_classification` has exact integer deltas:
`lease_acquire_count=1`, `state_read_count=1`,
`handoff_bundle_read_count=0`, `termination_receipt_write_count=1`,
`heartbeat_write_count=0`, `ingest_intent_write_count=0`,
`evidence_atom_write_count=0`,
`incident_write_count=0`, `hypothesis_write_count=0`,
`evidence_request_write_count=0`, `attempted_request_hash_write_count=0`,
`classification_write_count=0`, `ledger_write_count=0`,
`handoff_bundle_bytes_read=0`, and `promotion_bytes_validated=0`.

`dp_corrupt_state_no_write` has exact integer deltas:
`lease_acquire_count=1`, `state_read_count=1`,
`handoff_bundle_read_count=0`, `termination_receipt_write_count=1`,
`heartbeat_write_count=0`, `ingest_intent_write_count=0`,
`evidence_atom_write_count=0`,
`incident_write_count=0`, `hypothesis_write_count=0`,
`evidence_request_write_count=0`, `attempted_request_hash_write_count=0`,
`classification_write_count=0`, `ledger_write_count=0`,
`handoff_bundle_bytes_read=0`, and `promotion_bytes_validated=0`.

| # | Category | Case | Expected label | Expected error | Termination reason | Scope | Delta profile |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | ingest | Ingest single Prometheus metric promotion and create one atom. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 2 | ingest | Ingest single Loki log promotion and validate preview hash. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 3 | ingest | Ingest single Grafana topology promotion. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 4 | ingest | Ingest single Sentry event promotion. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 5 | ingest | Ingest single OTLP metric promotion. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 6 | handoff | Reject unqualified P136 release status. | `none` | `p136_release_status_unqualified` | `pre_ingest_rejected` | pre-ingest | `dp_pre_ingest_reject` |
| 7 | handoff | Reject bundle sequence rollback below P137 checkpoint. | `none` | `p136_handoff_sequence_rollback` | `pre_ingest_rejected` | pre-ingest | `dp_pre_ingest_reject` |
| 8 | handoff | Reject same-sequence fork with different bundle hash. | `none` | `p136_handoff_same_sequence_fork` | `pre_ingest_rejected` | pre-ingest | `dp_pre_ingest_reject` |
| 9 | handoff | Reject previous-hash discontinuity from the last accepted bundle hash. | `none` | `p136_handoff_previous_hash_discontinuity` | `pre_ingest_rejected` | pre-ingest | `dp_pre_ingest_reject` |
| 10 | handoff | Reject torn fixed-path replacement by descriptor length/hash, bundle hash, and parent fsync mismatch. | `none` | `p136_handoff_torn_fixed_path_replacement` | `pre_ingest_rejected` | pre-ingest | `dp_pre_ingest_reject` |
| 11 | handoff | Reject absent `promotion.entry_hash` key in checkpoint `promotion_keys`. | `none` | `p136_checkpoint_promotion_entry_absent` | `pre_ingest_rejected` | pre-ingest | `dp_pre_ingest_reject` |
| 12 | handoff | Reject altered canonical promotion record value under the correct checkpoint key. | `none` | `p136_checkpoint_promotion_record_mismatch` | `pre_ingest_rejected` | pre-ingest | `dp_pre_ingest_reject` |
| 13 | handoff | Reject nested `promotion_key` tamper after recomputing embedded promotion key. | `none` | `p136_embedded_promotion_key_mismatch` | `pre_ingest_rejected` | pre-ingest | `dp_pre_ingest_reject` |
| 14 | authority | Reject noncanonical authority hexadecimal bytes, nonzero P136 forbidden counters, or promoted forbidden fields. | `none` | `p136_handoff_authority_contract_invalid` | `pre_ingest_rejected` | pre-ingest | `dp_pre_ingest_reject` |
| 15 | guard | Evaluator-injected fake guard callables are blocked before the runtime boundary. | `none` | `guard_probe_blocked_before_boundary` | `evaluator_only` | evaluator-only | `dp_evaluator_guard` |
| 16 | correlation | Correlate same system/time metrics and logs into one incident. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 17 | correlation | Keep different systems separate. | `insufficient_evidence` | `none` | `none` | accepted incidents | `dp_classified_no_request` |
| 18 | correlation | Correlate shared entity hash across providers. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 19 | correlation | Correlate denominator-visible P136 rejection with nearby telemetry. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 20 | correlation | Reject correlation window budget exceeded after incident creation. | `aborted_fail_closed` | `none` | `aborted_fail_closed` | accepted incident | `dp_abort_written` |
| 21 | correlation | Preserve stable incident ID on restart duplicate ingest. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_recovery_after_ingest_intent` |
| 22 | hypothesis | Rank error-rate hypothesis above telemetry-gap when support dominates. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 23 | hypothesis | Rank telemetry-gap hypothesis when only missing-source evidence exists. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 24 | hypothesis | Rank benign-pattern hypothesis with scheduled-noise support. | `benign_anomaly` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 25 | hypothesis | Record decisive contradiction that suppresses confirmation. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 26 | hypothesis | Record blocking missing local evidence after one-shot request attempt. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 27 | hypothesis | Record blocking external unavailable need without executing it. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 28 | hypothesis | Preserve unresolved semantic tie even though lexical hash orders storage. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 29 | budget | Enforce hypothesis, support-edge, contradiction-edge, and missing-evidence budgets. | `aborted_fail_closed` | `none` | `aborted_fail_closed` | accepted incident | `dp_abort_written` |
| 30 | request | Execute `compare_current_window_to_promoted_baseline`. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 31 | request | Execute `fetch_record_by_evidence_id`. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 32 | request | Execute `join_records_by_entity_and_window`. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 33 | request | Execute `select_records_by_content_hash`. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 34 | request | Execute `select_records_by_entity_ref`. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 35 | request | Execute `select_records_by_label_hash`. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 36 | request | Execute `select_records_by_provider`. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 37 | request | Execute `select_records_by_risk_flag`. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 38 | request | Execute `select_records_by_signal_family`. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 39 | request | Execute `select_records_by_system_id`. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 40 | request | Execute `select_records_by_time_window`. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 41 | request | Execute `select_rejections_by_reason`. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 42 | request | Execute `summarize_log_preview_hashes`. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 43 | request | Execute `summarize_numeric_samples`. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 44 | request | Execute `summarize_topology_refs`. | `benign_anomaly` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 45 | signal | SIGINT at a safe boundary before handoff read returns no classification. | `none` | `signal_before_handoff_safe_boundary` | `sigint` | runtime termination | `dp_signal_no_classification` |
| 46 | durability | Corrupt durable state hash mismatch preserves last valid ledger and returns no classification. | `none` | `p137_state_corrupt_hash_mismatch` | `corrupt_state` | state rejection | `dp_corrupt_state_no_write` |
| 47 | classification | Confirm incident with multi-source support and no blocking gaps. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 48 | classification | Classify insufficient evidence after bounded local requests are exhausted. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_classified_with_request` |
| 49 | classification | Classify benign anomaly with benign support and no blocking gaps. | `benign_anomaly` | `none` | `none` | accepted incident | `dp_classified_no_request` |
| 50 | lease | Lease conflict before handoff/state read performs zero ingest/request/classification writes. | `none` | `lease_conflict` | `lease_conflict` | pre-ingest | `dp_no_runtime_write` |
| 51 | continuous | Bounded continuous mode writes one heartbeat and stops at `max_cycles` without path discovery. | `none` | `none` | `max_cycles_reached` | runtime termination | `dp_continuous_control` |
| 52 | readiness | Stale readiness stops finite loop before ingest. | `none` | `readiness_stale` | `readiness_stale` | runtime termination | `dp_continuous_control` |
| 53 | handoff | Stale handoff version stops finite loop before accepting the bundle. | `none` | `handoff_version_stale` | `handoff_version_stale` | runtime termination | `dp_continuous_control` |
| 54 | signal | SIGTERM before classification write and ledger CAS returns no classification. | `none` | `signal_before_classification_unsafe` | `sigterm` | runtime termination | `dp_signal_no_classification` |
| 55 | recovery | Crash after ingest intent recovers exactly once without duplicate atoms. | `insufficient_evidence` | `none` | `none` | accepted incident | `dp_recovery_after_ingest_intent` |
| 56 | recovery | Crash after incident write recovers exactly once without duplicate incident state. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_recovery_after_incident_write` |
| 57 | recovery | Crash after request write reuses durable request bytes and does not re-execute the selection. | `confirmed_incident` | `none` | `none` | accepted incident | `dp_recovery_after_request_write` |
| 58 | recovery | Crash after `aborted_fail_closed` classification write before ledger CAS advances that durable classification exactly once after successful CAS. | `aborted_fail_closed` | `none` | `aborted_fail_closed` | accepted incident | `dp_recovery_after_classification_before_ledger` |
| 59 | durability | CAS predecessor conflict preserves prior ledger and cannot claim terminal classification. | `none` | `ledger_cas_predecessor_mismatch` | `cas_failure` | state rejection | `dp_no_runtime_write` |
| 60 | resource | Case-specific low measured resource limit trips before classification intent. | `none` | `resource_limit_exceeded` | `resource_exhausted` | state rejection | `dp_resource_preclassification_stop` |

Required totals:

- 60 expected, 60 passed, 0 failed;
- all four terminal classifications represented among accepted incidents;
- all 15 evidence request catalog entries represented;
- Grafana and Loki integration rows consume the exact atom tuples returned by
  the real P136 handoff validator; the remaining provider/scenario rows are
  frozen source-bound P137 component fixtures and make no P136 or live-provider
  authenticity claim;
- zero provider/network/credential/action/remediation authority;
- zero reads of original provider artifacts;
- denominator includes explicit guard, lease, bounded continuous mode, heartbeat,
  readiness, stale handoff, SIGINT, SIGTERM, corrupt state, CAS, recovery, and
  resource-exhaustion cases;
- recovery cases prove idempotency and hash namespace continuity;
- probe-derived duplicate atom and request counts match case fixtures;
- every row references a named exact delta profile, and all forbidden-authority
  deltas are zero;
- evaluator expectations are scenario-authored independently of observations
  and final release assembly rederives them from frozen case-input oracle maps;
  resource expectations are fixed budgets, including a 15 s self-plus-child
  CPU ceiling, rather than copies of measured usage;
- fixture-tree bytes and every runtime case input, including probe identity and
  the exact validated effective P137 config, are content-bound into the matrix
  and explicit per-case config freeze hashes;
- exact release status `p137_local_evidence_triage_qualified`.

## Release gates

- P137 roadmap, test spec, and ticket docs are current with source.
- Plan-readiness review is separate from final implementation review. The
  plan-readiness review may approve only the roadmap, test spec, and tickets.
- The preliminary canonical matrix may run only to a temporary directory. That
  run freezes source hashes, release-gate script bytes, profile bytes, fixture
  bytes, generated case-input bytes, generated case-evidence bytes, and matrix
  output.
- Final frozen-source implementation review is created only after that freeze,
  is source-bound to the frozen source/docs/profile/fixtures/matrix output, and
  has zero unresolved P0/P1/P2 findings.
- Final `p137-release` structural validation runs only after the final review
  artifact exists and consumes the frozen matrix plus review artifacts. It must
  not regenerate reviewed inputs. Any source, profile, fixture, or matrix-output
  change after review invalidates the review and loops back to the preliminary
  matrix freeze.
- Targeted tests, static authority scan, evaluator-injected runtime guard
  probes, Ruff, Mypy, docs checks, and full repository verification pass.
- Canonical 60-case runner passes with independently rebuilt totals and exact
  delta-profile validation.
- Release evidence includes source hashes for P134/P135/P136/P137 validators,
  P137 runtime, runner, release gate, fixtures, docs, the P136 handoff bundle,
  generated case-input/evidence byte hashes, and the canonical matrix output.
- Runtime forbidden authority has the exact schema and exact integer zero.
- Runtime/evaluator activity and resources have exact observed and expected
  full-map schemas. Release totals are rebuilt from case maps plus explicit
  observed matrix overhead maps; wall is at most 30 seconds, self-plus-child CPU
  is at most 15 seconds, and peak RSS growth is at most 128 MiB.

## Verification sequence

1. Plan-readiness review of only the P137 roadmap, test spec, and tickets.
2. Targeted failing P137 contract/schema tests, then implementation until green.
3. P136 handoff validation tests with valid and adversarial promotion bundles.
4. Correlation, hypothesis, request, classification, and ledger tests.
5. Evidence request catalog tests, including forbidden request attempts.
6. Durability, recovery, lease, signal, CAS, hash namespace, heartbeat,
   readiness, staleness, bounded-loop, and budget tests.
7. Static authority scan and evaluator-injected guard probes.
8. Targeted Ruff and Mypy.
9. Preliminary canonical 60-case run to a temporary directory; freeze source
   hashes, release-gate script bytes, `p137-release` profile bytes, fixture
   bytes, generated case-input/evidence bytes, and matrix output.
10. Final frozen-source implementation review over the frozen source, docs,
    profile, fixtures, and matrix output; resolve all P0/P1/P2 findings.
11. `bash scripts/verify.sh --profile p137-release`; structural validation
    consumes the frozen matrix and final review and must not regenerate reviewed
    inputs.
12. Full repository verification in a loopback-capable local environment.
13. Secret/path scan, `git diff --check`, Lore commit, private push, and
    local/remote/private-state confirmation.

## Non-goals

- No live provider polling, OA2/OA3/OA4, credentials, auth, OAuth, or provider
  API calls.
- No directory discovery, arbitrary globbing, provider socket tailing,
  request-controlled endpoint, or environment/config discovery.
- No notification delivery, action execution, remediation, rollback, or
  staging/production mutation.
- No execution of `EXTERNAL_UNAVAILABLE` missing evidence needs.
- No unbounded always-on claim; continuous mode is finite and fixed-path only.
- No journal/request/classification retention deletion.
- No same-UID malicious-writer resistance, multi-host consensus, or production
  operator-replacement claim.

## Ticket order

1. P137-001: config, schemas, exact maps, and P136 handoff bundle contract.
2. P137-002: P136 handoff ingest and promotion-key validation.
3. P137-003: deterministic correlation and incident state.
4. P137-004: hypotheses, relation table, request-need split, and ranking.
5. P137-005: 15-entry bounded local request catalog.
6. P137-006: classification and investigation ledger.
7. P137-007: recovery, lease, signals, CAS, heartbeat, readiness, and budgets.
8. P137-008: exact 60-case runner, schemas, and release evidence.
9. P137-009: docs, plan-readiness review, and release evidence structure.
10. P137-010: final frozen-source review, full verification, Lore commit, and
    private push.
