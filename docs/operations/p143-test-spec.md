# P143 Provider-Neutral Egress Contract Lab — Test Specification

## Contract

The release denominator is exactly 52 ordered cases. Every case executes in its
own subprocess selector, captures stdout and stderr, records a source-bound
runner identity, reconciles exact local counters, and records exact-zero
forbidden authority counters. Skips, duplicate selectors, reorderings, boolean
counters, copied hashes, or optimistic pass flags invalidate the matrix.

## Exact Ordered Selector Catalog

The implementation must encode this literal ordered mapping in
`app.services.p143_runner._CASES`. Every case executes exactly its listed pytest
selector in a fresh subprocess. Selectors are unique; aliases and dynamically
discovered tests are forbidden.

```text
P143-CASE-01 -> tests/test_p143_egress_contract_lab.py::test_config_accepts_exact_closed_schema
P143-CASE-02 -> tests/test_p143_egress_contract_lab.py::test_config_rejects_unknown_fields
P143-CASE-03 -> tests/test_p143_egress_contract_lab.py::test_config_rejects_p143_authority_words
P143-CASE-04 -> tests/test_p143_egress_contract_lab.py::test_config_rejects_endpoint_url_and_webhook_fields
P143-CASE-05 -> tests/test_p143_egress_contract_lab.py::test_config_rejects_auth_token_header_and_secret_fields
P143-CASE-06 -> tests/test_p143_egress_contract_lab.py::test_config_rejects_dns_proxy_tls_and_provider_sdk_fields
P143-CASE-07 -> tests/test_p143_egress_contract_lab.py::test_paths_reject_traversal_symlink_and_hardlink
P143-CASE-08 -> tests/test_p143_egress_contract_lab.py::test_roots_reject_wrong_owner_and_writable_permissions
P143-CASE-09 -> tests/test_p143_egress_contract_lab.py::test_roots_reject_read_write_overlap
P143-CASE-10 -> tests/test_p143_egress_contract_lab.py::test_budgets_reject_boolean_negative_and_overflow
P143-CASE-11 -> tests/test_p143_egress_contract_lab.py::test_p142_exact_qualified_release_required
P143-CASE-12 -> tests/test_p143_egress_contract_lab.py::test_p142_stale_release_evidence_rejected
P143-CASE-13 -> tests/test_p143_egress_contract_lab.py::test_p142_receipt_schema_drift_rejected
P143-CASE-14 -> tests/test_p143_egress_contract_lab.py::test_p142_receipt_hash_drift_rejected
P143-CASE-15 -> tests/test_p143_egress_contract_lab.py::test_p142_production_delivered_true_rejected
P143-CASE-16 -> tests/test_p143_egress_contract_lab.py::test_p141_envelope_binding_required
P143-CASE-17 -> tests/test_p143_egress_contract_lab.py::test_p141_envelope_hash_drift_rejected
P143-CASE-18 -> tests/test_p143_egress_contract_lab.py::test_p133_p141_p142_dependency_graph_is_immutable
P143-CASE-19 -> tests/test_p143_egress_contract_lab.py::test_opened_transition_intent_built
P143-CASE-20 -> tests/test_p143_egress_contract_lab.py::test_updated_transition_intent_built
P143-CASE-21 -> tests/test_p143_egress_contract_lab.py::test_reminder_transition_intent_built
P143-CASE-22 -> tests/test_p143_egress_contract_lab.py::test_recovered_transition_intent_built
P143-CASE-23 -> tests/test_p143_egress_contract_lab.py::test_intent_id_is_deterministic
P143-CASE-24 -> tests/test_p143_egress_contract_lab.py::test_idempotency_key_is_deterministic
P143-CASE-25 -> tests/test_p143_egress_contract_lab.py::test_dedupe_key_is_deterministic
P143-CASE-26 -> tests/test_p143_egress_contract_lab.py::test_severity_mapping_is_closed
P143-CASE-27 -> tests/test_p143_egress_contract_lab.py::test_unsupported_severity_fails_closed
P143-CASE-28 -> tests/test_p143_egress_contract_lab.py::test_truncation_is_deterministic_and_recorded
P143-CASE-29 -> tests/test_p143_egress_contract_lab.py::test_evidence_refs_preserved_without_raw_secrets
P143-CASE-30 -> tests/test_p143_egress_contract_lab.py::test_provider_neutral_projection_is_byte_stable
P143-CASE-31 -> tests/test_p143_egress_contract_lab.py::test_chat_shadow_profile_compatibility_pass
P143-CASE-32 -> tests/test_p143_egress_contract_lab.py::test_email_shadow_profile_compatibility_pass
P143-CASE-33 -> tests/test_p143_egress_contract_lab.py::test_pager_shadow_profile_compatibility_pass
P143-CASE-34 -> tests/test_p143_egress_contract_lab.py::test_incident_comment_shadow_profile_compatibility_pass
P143-CASE-35 -> tests/test_p143_egress_contract_lab.py::test_unsupported_channel_fails_closed
P143-CASE-36 -> tests/test_p143_egress_contract_lab.py::test_missing_required_capability_fails_closed
P143-CASE-37 -> tests/test_p143_egress_contract_lab.py::test_payload_size_limit_fails_closed
P143-CASE-38 -> tests/test_p143_egress_contract_lab.py::test_evidence_reference_limit_fails_closed
P143-CASE-39 -> tests/test_p143_egress_contract_lab.py::test_retry_classification_is_local_evidence_only
P143-CASE-40 -> tests/test_p143_egress_contract_lab.py::test_rate_limit_semantics_are_manifest_only
P143-CASE-41 -> tests/test_p143_egress_contract_lab.py::test_valid_processing_opens_no_socket
P143-CASE-42 -> tests/test_p143_egress_contract_lab.py::test_forbidden_network_environment_provider_entrypoints_stay_zero
P143-CASE-43 -> tests/test_p143_egress_contract_lab.py::test_no_subprocess_or_shell_path_exists
P143-CASE-44 -> tests/test_p143_egress_contract_lab.py::test_completed_replay_opens_no_io_and_is_byte_identical
P143-CASE-45 -> tests/test_p143_egress_contract_lab.py::test_intent_prepare_and_write_crashes_recover_byte_identically
P143-CASE-46 -> tests/test_p143_egress_contract_lab.py::test_projection_prepare_and_write_crashes_recover_byte_identically
P143-CASE-47 -> tests/test_p143_egress_contract_lab.py::test_result_cursor_and_run_crashes_recover_byte_identically
P143-CASE-48 -> tests/test_p143_egress_contract_lab.py::test_conflicting_replay_artifact_fails_closed
P143-CASE-49 -> tests/test_p143_egress_contract_lab.py::test_lease_conflict_fails_before_processing
P143-CASE-50 -> tests/test_p143_egress_contract_cli.py::test_cli_emits_exact_int_only_counter_keysets
P143-CASE-51 -> tests/test_p143_runner.py::test_matrix_rejects_skip_reorder_hash_and_boolean_forgery
P143-CASE-52 -> tests/test_p143_release_evidence.py::test_final_evidence_binds_all_frozen_inputs_and_review
```

Each row records `case_id`, `scenario`, exact `selectors`, `runner`,
`runner_source_sha256`, `command_argv`, `captured_streams`, `timeout_seconds`,
`exit_code`, `duration_ms`, base64 stdout/stderr bytes, transcript SHA-256,
selector result, exact forbidden counters, exact allowed counters, and a row
hash. The matrix records the ordered catalog hash, runner source hash,
expected/passed/failed totals, aggregate counters, rows, and matrix hash.
Validation recomputes every hash and aggregate from canonical bytes; it rejects
missing/extra/reordered rows, selector reuse, skips/xfails, optimistic flags,
boolean counters, nonzero forbidden counters, unbounded local counters, copied
transcripts, source drift, and catalog drift.

## Canonical Cases

1. `P143-CASE-01` canonical closed config accepted
2. `P143-CASE-02` unknown fields rejected
3. `P143-CASE-03` forbidden authority words rejected
4. `P143-CASE-04` endpoint, URL, and webhook fields rejected
5. `P143-CASE-05` auth, token, header, and secret fields rejected
6. `P143-CASE-06` DNS, proxy, TLS, and provider SDK fields rejected
7. `P143-CASE-07` traversal, symlink, and hardlink paths rejected
8. `P143-CASE-08` wrong owner or group/world-writable roots rejected
9. `P143-CASE-09` read/write root overlap rejected
10. `P143-CASE-10` integer budgets reject booleans and overflow
11. `P143-CASE-11` exact qualified P142 release evidence and config binding required
12. `P143-CASE-12` stale P142 evidence rejected
13. `P143-CASE-13` P142 dispatch, journal, attempt, and receipt schema drift rejected
14. `P143-CASE-14` P142 receipt hash drift rejected
15. `P143-CASE-15` P142 `production_delivered=true` rejected
16. `P143-CASE-16` P141 envelope binding required
17. `P143-CASE-17` P141 envelope hash drift rejected
18. `P143-CASE-18` P133, P141, and complete P142 dependency graph immutability proven
19. `P143-CASE-19` opened transition intent built
20. `P143-CASE-20` updated transition intent built
21. `P143-CASE-21` reminder transition intent built
22. `P143-CASE-22` recovered transition intent built
23. `P143-CASE-23` deterministic intent ID
24. `P143-CASE-24` deterministic idempotency key
25. `P143-CASE-25` deterministic dedupe key
26. `P143-CASE-26` severity mapping is closed
27. `P143-CASE-27` unsupported severity fails closed
28. `P143-CASE-28` title/body truncation is deterministic and recorded
29. `P143-CASE-29` evidence references preserved without raw secrets
30. `P143-CASE-30` provider-neutral projection is byte-stable
31. `P143-CASE-31` chat shadow profile compatibility pass
32. `P143-CASE-32` email shadow profile compatibility pass
33. `P143-CASE-33` pager shadow profile compatibility pass
34. `P143-CASE-34` incident-comment shadow profile compatibility pass
35. `P143-CASE-35` unsupported channel fails closed
36. `P143-CASE-36` missing required capability fails closed
37. `P143-CASE-37` payload-size limit fails closed
38. `P143-CASE-38` evidence-reference limit fails closed
39. `P143-CASE-39` retry classification remains local evidence only
40. `P143-CASE-40` rate-limit semantics remain manifest-only
41. `P143-CASE-41` valid processing opens no socket
42. `P143-CASE-42` DNS, environment, proxy, HTTP, and provider entrypoints remain zero
43. `P143-CASE-43` no subprocess or shell command path exists
44. `P143-CASE-44` completed replay opens no I/O and is byte-identical
45. `P143-CASE-45` crash after intent preparation/write recovers byte-identically
46. `P143-CASE-46` crash after projection preparation/write recovers byte-identically
47. `P143-CASE-47` crash after result write before cursor recovers
48. `P143-CASE-48` conflicting replay artifact fails closed
49. `P143-CASE-49` lease conflict fails before processing
50. `P143-CASE-50` exact counter keysets and int-only values
51. `P143-CASE-51` matrix anti-forgery rejects skip, reorder, and boolean counters
52. `P143-CASE-52` release evidence binds source, tests, plan, critique, dependencies,
   profile, manifest, matrix, and independent review

## Mandatory Crash Windows

- Before and after intent atomic replace.
- Before and after projection atomic replace.
- Before and after capability-result atomic replace.
- After result durability but before cursor write.
- After cursor write but before run artifact write.
- After run artifact replace but before the `run_written` journal phase.
- During file fsync, replace, and directory fsync.

For every window, the test must prove one of two outcomes:

1. Exact prepared bytes are recovered without external or provider I/O; or
2. Processing fails closed before cursor advancement.

## Mandatory Tamper Cases

- Modified config, P141 envelope, P142 receipt, intent, projection, result,
  journal, cursor, profile, matrix, freeze, review, and release evidence hashes.
- Modified P142 release/config/profile/dispatch/attempt/journal/P141 binding or
  illegal P142 journal phase graph.
- Same ID with conflicting canonical bytes.
- Stale cursor, sequence gap, same-sequence event fork, and incomplete
  multi-profile batch.
- Symlink, hardlink, FIFO, directory substitution, wrong owner, and writable root.
- Hidden nonzero forbidden counter, missing counter, extra counter, negative local
  counter, boolean counter, and counter/artifact mismatch.

## Mandatory Security Patches

Tests patch these entrypoints to raise if touched during a valid run:

- `socket.socket`, `socket.create_connection`, `socket.getaddrinfo`
- environment reads
- subprocess and shell execution
- HTTP client and TLS helpers
- provider SDK imports or adapters
- P133 acknowledgement writers
- approval, action, remediation, ticket, staging, and production mutation APIs

P143-owned runtime counters use the exact 38-key forbidden set defined in the
approved plan and must all be integer zero. Historical P142 dependency evidence
may contain nonzero loopback transport counters; those values are validated as
immutable dependency data but are never copied into P143 runtime counters.

The word `production_delivered` is permitted only as an allowlisted read-only
P142 receipt dependency field and must be the literal boolean `false`. It is
forbidden in all P143-owned config/API/CLI/profile/output schemas.

## Frozen Dependency and Release Constants

- P141 status: `p141_notification_authority_simulator_qualified`
- P141 evidence hash:
  `sha256:d3028cf9f15c4f3936084182924eee8e1241f88ac67669502bcf36eac9ece788`
- P142 status: `p142_loopback_transport_lab_qualified`
- P142 evidence hash:
  `sha256:1d9f00eb142739a5da04fd0de3ebd19dc62a20ec94252d7a4d4f6b14ed02c254`
- Plan and test-spec hashes: exact SHA-256 values recorded by the approved
  `docs/operations/p143-plan-review.md` and then embedded as
  `EXPECTED_PLAN_SHA256` and `EXPECTED_TEST_SPEC_SHA256` in the release module.
- Source path tuple and required limitation keyset: exactly those listed in the
  approved P143 plan.
- Final review schema requires a source-bound preliminary freeze hash, reviewer
  agent ID, `APPROVE`, exact P0/P1/P2/P3 integer zeros, exact limitations, and a
  recomputed canonical review hash.

## Verification Commands

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p143_egress_contract_lab.py \
  tests/test_p143_egress_contract_cli.py \
  tests/test_p143_runner.py \
  tests/test_p143_release_evidence.py
uv run --no-sync --extra dev ruff check app scripts tests
uv run --no-sync --extra dev mypy app scripts tests
bash scripts/verify.sh --profile p143-release
bash scripts/verify.sh --profile p122-release
bash scripts/verify.sh --profile full
bash scripts/verify.sh --profile docs
```

## Acceptance

P143 cannot be qualified by test count alone. Qualification requires an exact
52/52 matrix, no skipped selectors, source-bound preliminary evidence,
independent implementation approval, exact-zero forbidden authority, reconciled
allowed activity, reproducible final evidence, clean staged secret checks, and a
clean local/remote private-main commit match.
