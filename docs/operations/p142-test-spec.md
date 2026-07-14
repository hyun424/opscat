# P142 Test Specification

## Contract tests

- Accept only the exact `p142.loopback_transport_config.v1` schema and reject
  unknown fields.
- Accept canonical dotted-quad `127.0.0.0/8` IPv4 literals except
  `127.0.0.0` and `127.255.255.255`, or the exact bracketed IPv6 literal
  `[::1]`, with an explicit decimal port in `1..65535` and a bounded path
  already in canonical origin form. Positive tests include an interior `127/8`
  address and `[::1]`; rejection tests include both excluded IPv4 endpoints.
- Reject hostnames including `localhost`, DNS resolution surfaces,
  non-loopback numeric addresses, every IPv4-mapped IPv6 literal including
  `[::ffff:127.0.0.1]`, alternate decimal/octal/hex/integer/abbreviated/mixed
  IPv4 forms, IPv6 zone IDs, bracketless IPv6, wildcard, unspecified,
  multicast, broadcast, link-local, private LAN, and public addresses.
- Reject authority or target text containing userinfo, query, or fragment;
  missing, zero, signed, non-decimal, or out-of-range ports; and parse/render
  ambiguity.
- Accept only `/` or ASCII origin-form segments matching
  `[A-Za-z0-9._~-]+`. Reject repeated slashes, `.`/`..` segments, percent
  escapes or encoded delimiters, backslashes, controls, whitespace,
  query/fragment delimiters, and any path requiring normalization.
- Reject proxy or environment-derived configuration, TLS, credentials, auth,
  cookies, bearer/API-key/header secrets, redirects, provider SDKs, arbitrary
  commands, P133 ack, action, remediation, staging mutation, and production
  mutation fields or values.
- Reject path traversal, symlink components, hardlinks, nonregular artifacts,
  local file replacement drift, and overlap between dependency read roots and
  P142 writable roots. Require every P142 writable root/directory to be owned by
  `os.geteuid()`, owner writable and searchable, and neither group nor world
  writable; keep P141/P133 read roots and exact public-reader lease paths
  separate from P142 output roots.

## P141 binding tests

- Consume only valid P141 envelopes whose hash, envelope ID, destination ID,
  source event hash, config hash, simulated receipt, and cursor position match.
- Require final P141 release evidence to be current and source-bound before any
  P142 release evidence can pass.
- Reject malformed envelopes, envelope-hash drift, receipt drift, P141 config
  drift, sequence gaps, predecessor mismatch, rewind, fork, contradictory
  replay, and cross-config or cross-envelope artifact reuse.
- Prove P142 never creates, modifies, or removes P141/P133 event, envelope,
  simulated receipt, cursor, acknowledgement, or release-evidence artifacts.
  Snapshot comparisons exclude only synchronization metadata at the exact P141
  and P133 lease paths written by their public-reader APIs; no other path or
  byte difference is allowed.

## Loopback transport tests

- Dispatch a valid envelope to a real local numeric-loopback HTTP sink and
  produce a deterministic receipt.
- Patch DNS, environment, proxy, TLS, auth, redirect, provider SDK, subprocess,
  shell, P133 ack, action, remediation, and mutation entry points to fail if
  called; valid loopback dispatch paths must still pass.
- Assert actual sockets are opened only after target parsing proves numeric
  loopback and produces packed bytes. IPv4 must use a raw `AF_INET` socket and
  `(socket.inet_ntop(AF_INET, packed), port)`; IPv6 must use a raw `AF_INET6`
  socket and `(socket.inet_ntop(AF_INET6, packed), port, 0, 0)`.
- Patch `http.client.HTTPConnection.connect`, `socket.create_connection`, and
  `socket.getaddrinfo` to fail on every valid and invalid runtime path. If
  `http.client.HTTPResponse` parses a response, prove it receives only the
  already connected raw socket and never establishes a connection.
- Assert redirect responses are recorded but never followed.
- Enforce request body, response body, connect timeout, response timeout, body
  read timeout, and total dispatch budgets.
- Reject unsupported methods, unsafe paths, oversized bodies, oversized
  responses, malformed responses, and response truncation without a recorded
  bounded failure.

## Retry, recovery, and idempotency tests

- Derive the base dispatch ID from P142 config hash, P141 envelope hash,
  destination ID, route ID, method, authority, path, and body hash, explicitly
  excluding ordinal. Derive each attempt ID from that dispatch ID plus its
  bounded zero-based ordinal.
- Replaying an already completed dispatch validates existing bytes and opens
  zero additional sockets.
- Persist a `p142.dispatch_attempt_journal.v1` whose every entry includes
  `attempt_ordinal` and its deterministic `attempt_id`. Assert each attempt is
  exactly a prefix of `pre_socket` -> `request_committed` ->
  `complete_response_observed` -> `receipt_written`, with no skipped, repeated,
  or reversed phase, and that `request_committed` is durable after connect but
  before the first request byte.
- Retry only a connection failure durably recorded while the attempt remains at
  `pre_socket`; append only the next contiguous ordinal and never reopen an
  ordinal. Complete HTTP responses, including `408`, `425`, `429`, and `5xx`,
  are terminal and cannot create another attempt. An incomplete or outcome-free
  `pre_socket` recovery state opens zero sockets and creates no next ordinal.
- Accept Retry-After delta-seconds only as unsigned base-10 integers. Accept its
  date form only as strict IMF-fixdate with literal `GMT`, parsed against an
  injected timezone-aware UTC wall clock. Compute
  `max(0, ceil(server_date_utc - injected_wall_clock_utc))` whole seconds; a
  stale date yields zero and no wait.
- Record valid bounded Retry-After values as advisory response evidence but
  perform no post-commit sleep or retry. Reject and record obsolete RFC
  850/asctime forms, malformed or ambiguous dates, non-UTC offsets/tokens,
  negative delta-seconds, and values above `max_retry_after_ms` or the remaining
  monotonic dispatch budget. Wall-clock values cannot extend that budget.
- Recover every durable journal phase. Replaying `request_committed` without a
  later complete response must open zero sockets, perform zero retries, and
  emit a terminal receipt with
  `failure_class="request_committed_response_unknown"`,
  `delivered_to_loopback=false`, `production_delivered=false`, and
  `acknowledged=false`. The journal remains at the `request_committed` prefix;
  no later phase, next ordinal, socket, or retry is allowed. Reconstruct a
  `complete_response_observed` result without reopening that attempt or creating
  another ordinal; validate and reuse `receipt_written` without a socket.
- Cover the socket-open-to-no-replay-barrier interval,
  response-before-`complete_response_observed`, receipt-before-cursor, and
  multi-destination partial crash windows.
- Fail closed on conflicting receipt, dispatch, cursor, or local response
  artifact replay.

## Durability and resource tests

- Serialize processes with a nonblocking P142 lease.
- Advance the P142 cursor only after every required durable receipt for an
  envelope exists and hash-validates.
- Enforce max artifact count, total bytes, per-receipt bytes, response bytes,
  request body bytes, and minimum free-space limits before writes.
- Reject P142 writable roots/directories with the wrong effective UID owner,
  missing owner write/search bits, or group/world write bits; prove P141/P133
  read roots are distinct and are never selected for P142 output.
- Preserve prior valid artifacts on temp-write, file-fsync, atomic-replace, and
  directory-fsync failures.
- Stop cleanly on SIGINT/SIGTERM and reject monotonic clock rollback or
  impossible timing evidence.

## Required exact-zero counters

The forbidden non-transport authority counter keyset is exactly:

```text
credential_read_count
environment_read_count
dns_socket_call_count
proxy_use_count
tls_handshake_count
authentication_attempt_count
redirect_follow_count
provider_sdk_call_count
non_loopback_socket_attempt_count
external_message_send_count
ticket_creation_count
p133_ack_write_count
approval_count
subprocess_shell_count
arbitrary_command_execution_count
action_execution_count
remediation_execution_count
staging_mutation_count
production_mutation_count
operator_replacement_count
authority_escape_count
```

The allowed transport activity counter keyset is exactly:

```text
loopback_socket_attempt_count
loopback_request_commit_count
loopback_request_byte_count
loopback_complete_response_count
loopback_response_byte_count
loopback_retry_count
loopback_transport_failure_count
loopback_http_2xx_count
loopback_http_3xx_count
loopback_http_4xx_count
loopback_http_5xx_count
```

Receipts, run output, matrices, and release evidence must have both exact
keysets, with no missing or unknown key. For every value,
`type(value) is int`; `bool` is invalid. Every forbidden value equals zero.
Every transport value is non-negative, budget-bounded, and exactly reconciled
to durable journal, socket, request/response byte, retry, failure, and status
evidence.

## Release gate

- Exact ordered 44-case catalog: 8 config/authority, 7 P141 binding, 8
  loopback transport, 8 retry/recovery, 5 durability/resource, 4
  non-transport authority, and 4 release-evidence cases.
- Validators reject skip, reorder, selector drift, optimistic pass flags,
  forged activity, forged source bindings, stale P141 dependency evidence,
  output hash drift, boolean counters, and hidden nonzero authority counters.
- Independent implementation review artifact with reviewer identity distinct
  from implementation identity.
- Independent `docs/operations/p142-plan-review.md` with reviewer identity
  distinct from plan author, APPROVED verdict, and exact hashes of the P142 plan
  and this test spec. This review is planned but is not created by the planning
  amendment.
- Source-bound freeze manifest and final release evidence bound to qualified
  P141 release evidence, the P142 plan, this test spec,
  `docs/operations/p142-plan-review.md`, source files, tests, profile, canonical
  matrix, freeze manifest, and independent implementation-review artifacts.
- Ruff, Mypy, targeted P142 tests, docs verification, and
  `bash scripts/verify.sh --profile p142-release`.

## Exact ordered catalog

The denominator remains exactly 44 cases with unchanged IDs and ordering.
Existing config selectors consolidate the new rejection inputs as follows:
CASE-02 covers userinfo/query/fragment and missing/zero/signed/non-decimal/
out-of-range ports; CASE-03 covers hostname/DNS, zone-ID, and bracketless-IPv6
forms; CASE-04 covers every IPv4-mapped IPv6 form and alternate
decimal/octal/hex/integer/abbreviated/mixed IPv4 form plus explicit rejection of
`127.0.0.0` and `127.255.255.255`; CASE-07 covers normalized-path ambiguity,
effective-UID ownership, owner write/search, group/world-write rejection, and
read/write-root separation. CASE-16/17 prove raw family-specific socket
construction from packed bytes; CASE-18/19 forbid all hostname-capable connect
helpers. CASE-26/27 fold the pre-socket-only retry and terminal HTTP-status
policy; CASE-28/29/30 fold the strict Retry-After clock, grammar, rounding, and
budget cases. No case ID is added or removed.

1. `P142-CASE-01 canonical_config` -> `tests/test_p142_loopback_transport_lab.py::test_config_accepts_closed_numeric_loopback_routes`
2. `P142-CASE-02 unknown_and_forbidden_fields_rejected` -> `tests/test_p142_loopback_transport_lab.py::test_config_rejects_unknown_and_authority_bearing_fields`
3. `P142-CASE-03 hostname_dns_and_localhost_rejected` -> `tests/test_p142_loopback_transport_lab.py::test_config_rejects_hostname_dns_and_localhost_targets`
4. `P142-CASE-04 non_loopback_numeric_rejected` -> `tests/test_p142_loopback_transport_lab.py::test_config_rejects_non_loopback_numeric_targets`
5. `P142-CASE-05 proxy_env_tls_auth_rejected` -> `tests/test_p142_loopback_transport_lab.py::test_config_rejects_proxy_env_tls_auth_and_credentials`
6. `P142-CASE-06 redirect_command_action_rejected` -> `tests/test_p142_loopback_transport_lab.py::test_config_rejects_redirect_command_action_and_mutation_surfaces`
7. `P142-CASE-07 path_symlink_hardlink_rejected` -> `tests/test_p142_loopback_transport_lab.py::test_path_symlink_hardlink_and_overlap_fail_closed`
8. `P142-CASE-08 budget_profile_bounds` -> `tests/test_p142_loopback_transport_lab.py::test_config_enforces_time_body_response_and_artifact_budgets`
9. `P142-CASE-09 p141_envelope_opened_bound` -> `tests/test_p142_loopback_transport_lab.py::test_valid_p141_opened_envelope_dispatches_to_loopback`
10. `P142-CASE-10 p141_envelope_updated_bound` -> `tests/test_p142_loopback_transport_lab.py::test_all_p141_transition_envelopes_bind_before_dispatch`
11. `P142-CASE-11 p141_envelope_reminder_bound` -> `tests/test_p142_loopback_transport_lab.py::test_all_p141_transition_envelopes_bind_before_dispatch`
12. `P142-CASE-12 p141_envelope_recovered_bound` -> `tests/test_p142_loopback_transport_lab.py::test_all_p141_transition_envelopes_bind_before_dispatch`
13. `P142-CASE-13 p141_hash_or_receipt_drift` -> `tests/test_p142_loopback_transport_lab.py::test_p141_hash_receipt_and_cursor_drift_fail_closed`
14. `P142-CASE-14 p141_cross_config_or_fork` -> `tests/test_p142_loopback_transport_lab.py::test_p141_cross_config_rewind_gap_and_fork_fail_closed`
15. `P142-CASE-15 p141_p133_reader_lease_only_immutability` -> `tests/test_p142_loopback_transport_lab.py::test_p141_and_p133_artifacts_are_immutable_except_exact_public_reader_leases`
16. `P142-CASE-16 loopback_ipv4_dispatch` -> `tests/test_p142_loopback_transport_lab.py::test_real_ipv4_loopback_http_dispatch_writes_receipt`
17. `P142-CASE-17 loopback_ipv6_dispatch` -> `tests/test_p142_loopback_transport_lab.py::test_real_ipv6_loopback_http_dispatch_writes_receipt`
18. `P142-CASE-18 socket_before_validation_blocked` -> `tests/test_p142_loopback_transport_lab.py::test_socket_cannot_open_before_numeric_loopback_validation`
19. `P142-CASE-19 dns_env_proxy_patched_zero` -> `tests/test_p142_loopback_transport_lab.py::test_dns_env_proxy_and_provider_entrypoints_are_never_called`
20. `P142-CASE-20 redirects_not_followed` -> `tests/test_p142_loopback_transport_lab.py::test_redirect_response_is_recorded_not_followed`
21. `P142-CASE-21 response_body_budget` -> `tests/test_p142_loopback_transport_lab.py::test_response_body_budget_and_truncation_are_bounded`
22. `P142-CASE-22 timeout_budget` -> `tests/test_p142_loopback_transport_lab.py::test_connect_response_body_and_total_timeouts_fail_closed`
23. `P142-CASE-23 malformed_response` -> `tests/test_p142_loopback_transport_lab.py::test_malformed_loopback_response_records_bounded_failure`
24. `P142-CASE-24 deterministic_dispatch_identity` -> `tests/test_p142_loopback_transport_lab.py::test_dispatch_and_attempt_ids_are_deterministic`
25. `P142-CASE-25 byte_identical_replay_no_socket` -> `tests/test_p142_loopback_transport_lab.py::test_completed_replay_is_byte_identical_and_opens_no_socket`
26. `P142-CASE-26 pre_socket_failures_retry_bounded` -> `tests/test_p142_loopback_transport_lab.py::test_only_pre_socket_connection_failures_advance_to_next_ordinal`
27. `P142-CASE-27 complete_statuses_terminal` -> `tests/test_p142_loopback_transport_lab.py::test_complete_http_statuses_never_retry_after_request_commit`
28. `P142-CASE-28 retry_after_seconds_advisory` -> `tests/test_p142_loopback_transport_lab.py::test_retry_after_seconds_is_bounded_advisory_without_post_commit_wait`
29. `P142-CASE-29 retry_after_imf_fixdate` -> `tests/test_p142_loopback_transport_lab.py::test_retry_after_imf_fixdate_uses_injected_utc_ceiling_and_monotonic_budget`
30. `P142-CASE-30 invalid_retry_after_rejected` -> `tests/test_p142_loopback_transport_lab.py::test_obsolete_ambiguous_non_utc_and_excessive_retry_after_is_rejected`
31. `P142-CASE-31 durable_attempt_journal_recovery` -> `tests/test_p142_loopback_transport_lab.py::test_attempt_journal_phases_recover_without_replaying_request_committed`
32. `P142-CASE-32 lease_conflict` -> `tests/test_p142_loopback_transport_lab.py::test_loopback_transport_lease_conflict_fails_before_dispatch`
33. `P142-CASE-33 cursor_requires_receipts` -> `tests/test_p142_loopback_transport_lab.py::test_cursor_advances_only_after_all_receipts_are_durable`
34. `P142-CASE-34 artifact_budget_and_free_space` -> `tests/test_p142_loopback_transport_lab.py::test_artifact_count_total_bytes_and_free_space_fail_before_writes`
35. `P142-CASE-35 fsync_replace_failures` -> `tests/test_p142_loopback_transport_lab.py::test_temp_write_fsync_replace_and_directory_fsync_failures_preserve_prior_state`
36. `P142-CASE-36 signal_and_clock_safety` -> `tests/test_p142_loopback_cli.py::test_run_stops_on_signal_and_rejects_clock_rollback`
37. `P142-CASE-37 no_p133_ack_or_p141_mutation` -> `tests/test_p142_loopback_transport_lab.py::test_no_p133_ack_and_no_p141_mutation_authority`
38. `P142-CASE-38 no_action_remediation_mutation` -> `tests/test_p142_loopback_transport_lab.py::test_action_remediation_and_mutation_entrypoints_are_never_called`
39. `P142-CASE-39 exact_zero_non_transport_authority` -> `tests/test_p142_loopback_cli.py::test_cli_outputs_exact_zero_non_transport_authority_counters`
40. `P142-CASE-40 no_subprocess_or_command_runtime` -> `tests/test_p142_loopback_transport_lab.py::test_runtime_source_and_valid_paths_do_not_use_commands_or_subprocesses`
41. `P142-CASE-41 exact_catalog` -> `tests/test_p142_runner.py::test_p142_catalog_is_exact_ordered_immutable_denominator`
42. `P142-CASE-42 matrix_anti_forgery` -> `tests/test_p142_runner.py::test_p142_matrix_rejects_skip_authority_activity_hash_and_boolean_forgery`
43. `P142-CASE-43 source_dependency_bindings` -> `tests/test_p142_release_evidence.py::test_p142_preliminary_and_final_evidence_bind_sources_p141_dependency_and_review`
44. `P142-CASE-44 final_does_not_rewrite_frozen_inputs` -> `tests/test_p142_release_evidence.py::test_p142_final_mode_does_not_rewrite_frozen_inputs`

## Honest evidence boundary

P142 proves only deterministic dispatch to an isolated numeric-loopback HTTP
lab with durable receipts. It does not prove production notification delivery,
provider compatibility, credential handling, TLS security, external alerting,
notification latency SLOs, P133 acknowledgement, remediation, action execution,
operator replacement, or production readiness.
