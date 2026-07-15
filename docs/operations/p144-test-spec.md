# P144 Numeric-Loopback Provider Adapter Conformance — Test Specification

## Contract

P144 qualifies exactly 64 selector-bound cases. Every case executes through the
canonical P144 runner, emits selector proof and counter provenance, and is
included in the source-bound matrix. Skipped, reordered, duplicated, missing,
forged, or boolean-counter cases fail closed.

## Exact Case Catalog

| Case | Scenario | Required proof |
|---|---|---|
| P144-CASE-01 | closed config | exact config schema accepted |
| P144-CASE-02 | unknown config | unknown fields rejected |
| P144-CASE-03 | unsafe config names | endpoint/auth/provider/header fields rejected |
| P144-CASE-04 | unsafe config values | URLs, hosts, tokens, env expressions rejected |
| P144-CASE-05 | local paths | traversal, symlink, hardlink rejected |
| P144-CASE-06 | root ownership | unsafe permissions/ownership rejected |
| P144-CASE-07 | root overlap | read/write and write/write overlap rejected |
| P144-CASE-08 | budgets | bool, negative, overflow, inconsistent budgets rejected |
| P144-CASE-09 | P143 release | exact qualified dependency required |
| P144-CASE-10 | P143 stale | stale/self-hash-invalid evidence rejected |
| P144-CASE-11 | P143 projection graph | intent/profile/projection/result/run exact graph required |
| P144-CASE-12 | P143 projection rederive | coordinated projection forgery rejected |
| P144-CASE-13 | P142 release | exact qualified dependency required |
| P144-CASE-14 | P142 stale | stale/self-hash-invalid evidence rejected |
| P144-CASE-15 | transitive graph | P133/P141/P142/P143 graph mismatch rejected |
| P144-CASE-16 | production flags | true external/production delivery flags rejected |
| P144-CASE-17 | receiver ownership | address must come from live process-owned receiver |
| P144-CASE-18 | IPv4 loopback | `127.0.0.1` accepted |
| P144-CASE-19 | IPv6 loopback | `::1` accepted when available |
| P144-CASE-20 | hostname | localhost and DNS names rejected |
| P144-CASE-21 | external numeric | non-loopback numeric address rejected |
| P144-CASE-22 | Unix socket | Unix-domain socket path rejected |
| P144-CASE-23 | fixed method/path | exact POST and fixed path emitted |
| P144-CASE-24 | fixed headers | exact six values/order and index-zero request binding emitted |
| P144-CASE-25 | header injection | CRLF and request-controlled headers rejected |
| P144-CASE-26 | canonical body | byte-stable canonical JSON emitted |
| P144-CASE-27 | request size | oversized request rejected before socket |
| P144-CASE-28 | delivery ID | deterministic source-bound delivery ID |
| P144-CASE-29 | idempotency | P143 idempotency key preserved exactly |
| P144-CASE-30 | dedupe | P143 dedupe key bound but not authority-bearing |
| P144-CASE-31 | accepted 2xx | success statuses classified accepted |
| P144-CASE-32 | no-content 204 | empty success body handled |
| P144-CASE-33 | duplicate 208 | valid duplicate receipt classified accepted |
| P144-CASE-34 | duplicate 409 | exact duplicate body required |
| P144-CASE-35 | permanent 4xx | supported permanent failures never retry |
| P144-CASE-36 | transient 408/425 | transient classification and bounded retry |
| P144-CASE-37 | throttled 429 | Retry-After bounded retry |
| P144-CASE-38 | transient 5xx | deterministic distinct retry ID; only wire attempt header changes |
| P144-CASE-39 | retry exhausted | terminal transient failure after budget |
| P144-CASE-40 | invalid Retry-After | fail closed without wait |
| P144-CASE-41 | excessive Retry-After | budget overflow rejected |
| P144-CASE-42 | redirect | redirect rejected and never followed |
| P144-CASE-43 | malformed status | malformed response rejected |
| P144-CASE-44 | malformed headers | unsafe/duplicate framing and any Transfer-Encoding rejected |
| P144-CASE-45 | malformed JSON | malformed provider body rejected |
| P144-CASE-46 | oversized response | response budget enforced |
| P144-CASE-47 | truncated response | truncation detected and classified |
| P144-CASE-48 | connection failure | deterministic connection-failure receipt |
| P144-CASE-49 | timeout | bounded timeout classification |
| P144-CASE-50 | fixed response headers | only exact safe headers persisted |
| P144-CASE-51 | provider receipt | bounded receipt ID validated/redacted |
| P144-CASE-52 | completed replay | byte-identical replay opens no socket |
| P144-CASE-53 | conflicting replay | conflicting request/receipt fails closed |
| P144-CASE-54 | pre-send crash | recovers and sends at most once |
| P144-CASE-55 | post-send ambiguity | indeterminate state never auto-retries |
| P144-CASE-56 | attempt crash windows | attempt boundaries recover exactly |
| P144-CASE-57 | receipt crash windows | receipt boundaries recover exactly |
| P144-CASE-58 | cursor/run crash | cursor and run recover byte-identically |
| P144-CASE-59 | lease conflict | conflict blocks before socket |
| P144-CASE-60 | bounded progress | multi-cycle cursor progress cannot strand sources |
| P144-CASE-61 | counter reconciliation | allowed counters equal artifacts/receipts |
| P144-CASE-62 | forbidden entrypoints | exact forbidden counters remain integer zero |
| P144-CASE-63 | matrix anti-forgery | skip/reorder/hash/transcript/bool forgery rejected |
| P144-CASE-64 | final evidence | exact freeze, review, dependencies and limitations bound |

## Executable Selector Catalog

The runner constant `_P144_CASES` and the profile must equal this exact ordered
mapping. Each row executes `python -m pytest -q -s -p
app.services.p144_runner --p144-case-id <CASE> <selector>` with a 120-second
timeout and captures stdout/stderr bytes.

```text
P144-CASE-01 -> tests/test_p144_provider_adapter_lab.py::test_config_accepts_exact_closed_schema
P144-CASE-02 -> tests/test_p144_provider_adapter_lab.py::test_config_rejects_unknown_fields
P144-CASE-03 -> tests/test_p144_provider_adapter_lab.py::test_config_rejects_unsafe_field_names
P144-CASE-04 -> tests/test_p144_provider_adapter_lab.py::test_config_rejects_unsafe_values
P144-CASE-05 -> tests/test_p144_provider_adapter_lab.py::test_paths_reject_traversal_symlink_and_hardlink
P144-CASE-06 -> tests/test_p144_provider_adapter_lab.py::test_roots_reject_unsafe_owner_and_permissions
P144-CASE-07 -> tests/test_p144_provider_adapter_lab.py::test_roots_reject_overlap
P144-CASE-08 -> tests/test_p144_provider_adapter_lab.py::test_budgets_reject_bool_negative_overflow_and_inconsistency
P144-CASE-09 -> tests/test_p144_provider_adapter_lab.py::test_p143_exact_qualified_release_required
P144-CASE-10 -> tests/test_p144_provider_adapter_lab.py::test_p143_stale_or_invalid_release_rejected
P144-CASE-11 -> tests/test_p144_provider_adapter_lab.py::test_p143_projection_graph_required
P144-CASE-12 -> tests/test_p144_provider_adapter_lab.py::test_p143_projection_rederived_and_forgery_rejected
P144-CASE-13 -> tests/test_p144_provider_adapter_lab.py::test_p142_exact_qualified_release_required
P144-CASE-14 -> tests/test_p144_provider_adapter_lab.py::test_p142_stale_or_invalid_release_rejected
P144-CASE-15 -> tests/test_p144_provider_adapter_lab.py::test_transitive_dependency_graph_required
P144-CASE-16 -> tests/test_p144_provider_adapter_lab.py::test_external_and_production_delivery_flags_rejected
P144-CASE-17 -> tests/test_p144_provider_adapter_lab.py::test_receiver_capability_is_process_owned_and_unserializable
P144-CASE-18 -> tests/test_p144_provider_adapter_lab.py::test_ipv4_receiver_capability_accepted
P144-CASE-19 -> tests/test_p144_provider_adapter_lab.py::test_ipv6_receiver_capability_accepted_when_available
P144-CASE-20 -> tests/test_p144_provider_adapter_lab.py::test_hostnames_and_dns_entrypoints_rejected
P144-CASE-21 -> tests/test_p144_provider_adapter_lab.py::test_non_loopback_numeric_address_rejected
P144-CASE-22 -> tests/test_p144_provider_adapter_lab.py::test_unix_socket_rejected
P144-CASE-23 -> tests/test_p144_provider_adapter_lab.py::test_fixed_post_method_and_path_emitted
P144-CASE-24 -> tests/test_p144_provider_adapter_lab.py::test_fixed_headers_emitted_in_canonical_order
P144-CASE-25 -> tests/test_p144_provider_adapter_lab.py::test_header_injection_and_request_control_rejected
P144-CASE-26 -> tests/test_p144_provider_adapter_lab.py::test_canonical_request_body_is_byte_stable
P144-CASE-27 -> tests/test_p144_provider_adapter_lab.py::test_request_size_budget_rejected_before_socket
P144-CASE-28 -> tests/test_p144_provider_adapter_lab.py::test_delivery_id_is_deterministic_and_source_bound
P144-CASE-29 -> tests/test_p144_provider_adapter_lab.py::test_p143_idempotency_key_preserved
P144-CASE-30 -> tests/test_p144_provider_adapter_lab.py::test_p143_dedupe_key_is_non_authority_binding
P144-CASE-31 -> tests/test_p144_provider_adapter_lab.py::test_success_statuses_classify_accepted
P144-CASE-32 -> tests/test_p144_provider_adapter_lab.py::test_no_content_204_is_accepted
P144-CASE-33 -> tests/test_p144_provider_adapter_lab.py::test_208_valid_duplicate_is_accepted
P144-CASE-34 -> tests/test_p144_provider_adapter_lab.py::test_409_requires_exact_duplicate_body
P144-CASE-35 -> tests/test_p144_provider_adapter_lab.py::test_permanent_4xx_never_retries
P144-CASE-36 -> tests/test_p144_provider_adapter_lab.py::test_408_and_425_create_bounded_adapter_retry
P144-CASE-37 -> tests/test_p144_provider_adapter_lab.py::test_429_retry_after_creates_bounded_adapter_retry
P144-CASE-38 -> tests/test_p144_provider_adapter_lab.py::test_transient_5xx_retries_then_succeeds
P144-CASE-39 -> tests/test_p144_provider_adapter_lab.py::test_retry_budget_exhaustion_is_terminal
P144-CASE-40 -> tests/test_p144_provider_adapter_lab.py::test_invalid_retry_after_fails_without_wait
P144-CASE-41 -> tests/test_p144_provider_adapter_lab.py::test_excessive_retry_after_rejected
P144-CASE-42 -> tests/test_p144_provider_adapter_lab.py::test_redirect_is_rejected_and_never_followed
P144-CASE-43 -> tests/test_p144_provider_adapter_lab.py::test_malformed_status_rejected
P144-CASE-44 -> tests/test_p144_provider_adapter_lab.py::test_malformed_and_duplicate_framing_headers_rejected
P144-CASE-45 -> tests/test_p144_provider_adapter_lab.py::test_malformed_provider_json_rejected
P144-CASE-46 -> tests/test_p144_provider_adapter_lab.py::test_oversized_response_budget_enforced
P144-CASE-47 -> tests/test_p144_provider_adapter_lab.py::test_truncated_response_detected
P144-CASE-48 -> tests/test_p144_provider_adapter_lab.py::test_connection_failure_receipt_is_deterministic
P144-CASE-49 -> tests/test_p144_provider_adapter_lab.py::test_timeout_is_bounded_and_classified
P144-CASE-50 -> tests/test_p144_provider_adapter_lab.py::test_only_fixed_safe_response_headers_persisted
P144-CASE-51 -> tests/test_p144_provider_adapter_lab.py::test_provider_receipt_id_is_bounded_and_validated
P144-CASE-52 -> tests/test_p144_provider_adapter_lab.py::test_completed_replay_is_byte_identical_and_opens_no_socket
P144-CASE-53 -> tests/test_p144_provider_adapter_lab.py::test_conflicting_replay_artifacts_fail_closed
P144-CASE-54 -> tests/test_p144_provider_adapter_lab.py::test_pre_send_crash_recovers_at_most_once
P144-CASE-55 -> tests/test_p144_provider_adapter_lab.py::test_post_send_ambiguity_requires_review_and_never_retries
P144-CASE-56 -> tests/test_p144_provider_adapter_lab.py::test_attempt_crash_windows_recover_exactly
P144-CASE-57 -> tests/test_p144_provider_adapter_lab.py::test_receipt_crash_windows_recover_exactly
P144-CASE-58 -> tests/test_p144_provider_adapter_lab.py::test_cursor_and_run_crash_windows_recover_exactly
P144-CASE-59 -> tests/test_p144_provider_adapter_lab.py::test_lease_conflict_blocks_before_socket
P144-CASE-60 -> tests/test_p144_provider_adapter_lab.py::test_bounded_multi_cycle_progress_cannot_strand_sources
P144-CASE-61 -> tests/test_p144_provider_adapter_cli.py::test_cli_counters_reconcile_to_artifacts_and_transport
P144-CASE-62 -> tests/test_p144_provider_adapter_lab.py::test_forbidden_entrypoints_and_counters_remain_zero
P144-CASE-63 -> tests/test_p144_runner.py::test_matrix_rejects_skip_reorder_hash_transcript_and_boolean_forgery
P144-CASE-64 -> tests/test_p144_release_evidence.py::test_final_evidence_binds_freeze_review_dependencies_and_limitations
```

Each row has the exact `p144.release_case_result.v1` fields from the plan. The
runner source hash, selector proof, command argv, transcript hash, three counter
maps, and row hash are mandatory. The aggregate matrix has the exact
`p144.release_case_matrix.v1` fields and canonical hash formulas defined by the
plan.

## Crash Semantics

The implementation must inject crashes around every atomic prepare, write,
replace, and directory-fsync boundary. Recovery must either reproduce exact
bytes or fail before new I/O. `attempt_prepared` or `attempt_started` may resume
the same attempt only with durable proof that zero request bytes were committed.
`request_committed` without `transport_completed` maps the P142 semantic
`request_committed_response_unknown` to a terminal
`indeterminate_requires_review` receipt with `requires_review=true`,
`automatic_retry_allowed=false`, and no further socket attempt. A durable
complete response may be reclassified and persisted without reopening a socket.

## Request-Binding Erratum Proof

CASE 24 recomputes `request_binding_hash` from the exact validated request core,
derives the index-zero attempt ID, verifies all six persisted header values, and
rejects a canonically rehashed request when any one value is substituted. CASE
38 proves the persisted first-attempt header, journal attempt ID, and actual
wire attempt ID are equal; retry IDs differ deterministically by attempt index,
and retry wire bytes preserve body, delivery ID, and idempotency key. CASE 44
rejects `transfer-encoding` both alone and together with `content-length`,
including through the numeric-loopback socket path.

## Counter Contract

The matrix stores three disjoint exact maps from the P144 plan:
`adapter_counters`, P142-compatible `transport_counters`, and
`forbidden_counters`. Values must be integers and not booleans. Forbidden
counters must be zero. Adapter values re-derive from request, attempt, journal,
receipt, cursor, and run artifacts. Transport values re-derive from P144 socket
wrappers, canonical byte lengths, statuses, and attempt receipts; persisted
dependency counters are not added. Provider-level retry increments
`retry_schedule_count`, while `loopback_retry_count` is restricted to a
pre-request connection retry within one transport attempt.

## Final Review Contract

Preliminary freeze stores only the external review artifact path, not its hash.
Final qualification requires an external JSON object with:

- exact schema and field keysets;
- distinct implementation and reviewer identities;
- canonical lowercase UUIDv7 reviewer agent ID;
- UTC reviewed timestamp;
- decision `approve`;
- exact integer zeros for `p0`, `p1`, `p2`, and `p3`;
- exact plan, test-spec, plan-review, profile, matrix, freeze, source, and
  dependency bindings;
- exact required limitation set;
- canonical self hash.

Final mode must never rewrite the canonical matrix or freeze manifest.
The final evidence, not the freeze, binds the approved review hash; this avoids
a review/freeze hash cycle.

## Verification Commands

```bash
bash scripts/verify.sh --profile p144-release
bash scripts/verify.sh --profile p122-release
bash scripts/verify.sh --profile full
bash scripts/verify.sh --profile docs
```

Real external provider delivery remains out of scope.
