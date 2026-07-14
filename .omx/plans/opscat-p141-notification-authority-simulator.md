# P141 Notification-Only Authority Simulator

## Outcome

Qualify the first post-P140 notification boundary without sending anything.
P141 consumes validated P133 dead-man events, renders deterministic redacted
notification envelopes, and writes crash-safe **simulated** delivery receipts.
It grants no network, credential, acknowledgement, remediation, or production
mutation authority.

## Success criteria

1. Only exact, hash-valid P133 events may enter the simulator.
2. Destination identifiers come from a closed local allowlist and contain no
   address, URL, endpoint, token, secret, or credential reference.
3. Every attempt is deterministic and idempotent from the P133 event hash,
   destination, template version, and P141 configuration hash.
4. Receipts explicitly state `simulated=true`, `delivered=false`, and
   `acknowledged=false`; P141 never creates or changes a P133 acknowledgement.
5. Envelope content is schema-closed, size bounded, redacted, and derived from
   the P133 event projection only.
6. Cursor and receipt writes are atomic, fsync-backed, symlink resistant,
   single-writer leased, replay safe, and bounded by count/byte/free-space
   budgets.
7. Network, credential, message-send, ticket, action, remediation, and
   production-mutation counters are exact integer zero in every artifact.
8. A frozen qualification matrix, source bindings, independent review, and
   release evidence reproduce from tracked inputs.

## Authority boundary

- Allowed: local validated read of the configured P133 outbox; the exact P133
  lease-file synchronization write intrinsic to `list_outbox`; and local writes
  to P141-owned envelope, receipt, and cursor paths under explicit roots. P133
  event, cursor, acknowledgement, and retention data remain read-only.
- Simulated only: render a channel-neutral notification envelope and record the
  result a transport would have attempted.
- Forbidden: socket/network access, environment or credential reads, provider
  SDKs, webhook/address fields, free-form commands, external sends, P133 ack,
  approval, action execution, remediation, mutation, or operator replacement.
- Delivery receipt and human/operator acknowledgement are different concepts.
  A P141 simulated receipt can never satisfy the P133 acknowledgement contract.

## Closed schemas

- `p141.notification_config.v1`
- `p141.notification_envelope.v1`
- `p141.simulated_delivery_receipt.v1`
- `p141.notification_cursor.v1`
- `p141.notification_run.v1`

Canonical JSON hashing uses `stable_hash` over the complete object before the
object's own `*_hash` field is added. Artifact bytes use sorted, indented UTF-8
JSON with one trailing newline. Exact field sets are:

- config: `schema_version`, `simulator_id`, `allowed_artifact_roots`,
  `p133_config_path`, `envelope_dir`, `receipt_dir`, `cursor_path`,
  `destination_ids`, `transition_kinds`, `template_version`, polling and
  count/byte/free-space budgets;
- envelope: schema, envelope/attempt IDs, simulator/destination/template/config
  bindings, minimal `source_event`, closed `message`, exact-zero counters, hash;
- receipt: schema, attempt/envelope/event/destination bindings, processed time,
  `simulated=true`, `delivered=false`, `acknowledged=false`, counters, hash;
- cursor: schema/config binding, last completed sequence/event ID/event hash,
  processed time, counters, hash;
- run: schema/config/simulator/time, processed/replayed attempt counts, last
  sequence, simulation flags, zero delivery/ack counts, counters, hash.

The attempt ID is `stable_hash(config_hash, event_hash, destination_id,
template_version)`. The cursor advances once per event only after every
configured destination has a durable matching envelope and receipt. A partial
multi-destination crash leaves the cursor unchanged; replay validates and
reuses completed attempts byte-for-byte before completing missing attempts.

The forbidden exact-zero counter tuple is: credential reads, environment
reads, DNS/socket/network calls, provider SDK calls, external messages, ticket
creation, P133 acknowledgements, approvals, subprocess/shell, action execution,
remediation, staging mutation, production mutation, operator replacement, and
authority escape. Static and runtime tests cover categories that cannot be
incremented without already crossing the boundary.

## Processing model

1. Load the closed config through explicit paths and reject unknown or
   authority-bearing fields/values.
2. Acquire the P141 lease, then use only P133 `load_deadman_config` and
   `list_outbox`. Importing or calling `acknowledge_event`, retention, or writer
   internals is forbidden. Bind the qualified P133 release in release evidence.
3. Sort by sequence, validate chain continuity, and reject rewind, fork,
   missing predecessor, or conflicting replay.
4. For each new event and configured destination, build the deterministic
   envelope and attempt identifier.
5. Persist envelope and simulated receipt atomically; advance cursor only after
   both are durable. Existing identical artifacts are replayed; conflicting
   artifacts fail closed.
6. Stop before any partial budget overflow. Never touch the P133 ack directory.

## Tickets

### P141-001 — Contract and secure configuration

Define exact schemas, forbidden fields/values, local path scope, destination
allowlist, transition allowlist, size/count/free-space budgets, and config hash.

### P141-002 — P133 event binding and redacted envelopes

Use the P133 public reader, validate sequence/hash continuity, project only the
minimal incident/transition/reason/timestamp/evidence-hash fields, and render a
channel-neutral bounded envelope.

### P141-003 — Idempotent simulated transport

Derive attempt IDs, write exact simulated receipts, distinguish delivery from
acknowledgement, and reject contradictory replay.

### P141-004 — Durable runner and CLI

Add one-shot/list/run commands, single-writer lease, stop controller, bounded
loop, atomic writes, and JSON-only errors. No CLI option may carry a network
address or secret.

### P141-005 — Adversarial regression suite

Cover malformed/tampered P133 input, config injection, symlink/path escape,
chain forks, crash windows, replay, budget exhaustion, receipt tamper, P133 ack
non-mutation, network/env/subprocess prohibition, and signals.

### P141-006 — Frozen qualification matrix

Run an exact ordered 36-case deterministic catalog covering 6 config, 8 P133
binding, 8 envelope/receipt, 6 durability/resource, 4 authority/non-mutation,
and 4 release-evidence cases. Freeze per-case selectors/hashes/activity,
canonical matrix, and source-bound manifest.

Exact ordered catalog (selectors are pytest node IDs):

1. `P141-CASE-01 canonical_config` -> `test_config_round_trip_is_closed_local_and_destination_only`
2. `P141-CASE-02 unknown_field_rejected` -> the same config adversarial test
3. `P141-CASE-03 endpoint_secret_text_rejected` -> the same config adversarial test
4. `P141-CASE-04 path_symlink_hardlink_rejected` -> `test_receipt_tamper_symlink_and_budget_exhaustion_fail_closed`
5. `P141-CASE-05 destination_allowlist` -> the config adversarial test
6. `P141-CASE-06 transition_allowlist` -> `test_transition_allowlist_and_chain_are_closed`
7. `P141-CASE-07 opened_event` -> `test_one_event_creates_deterministic_envelopes_and_simulated_receipts_without_ack`
8. `P141-CASE-08 updated_event` -> `test_all_p133_transitions_form_one_bound_chain`
9. `P141-CASE-09 reminder_event` -> the transition-chain test
10. `P141-CASE-10 recovered_event` -> the transition-chain test
11. `P141-CASE-11 malformed_or_hash_drift` -> `test_tampered_p133_event_and_missing_chain_fail_closed`
12. `P141-CASE-12 p133_config_drift` -> `test_cross_config_and_cross_event_replay_fail_closed`
13. `P141-CASE-13 sequence_gap_or_rewind` -> the tampered-chain test
14. `P141-CASE-14 predecessor_fork` -> the tampered-chain test
15. `P141-CASE-15 deterministic_bytes` -> `test_replay_is_byte_identical_and_does_not_advance_attempt_counts`
16. `P141-CASE-16 redacted_projection` -> the one-event test
17. `P141-CASE-17 multi_destination` -> the one-event test
18. `P141-CASE-18 simulated_not_delivered_or_acked` -> the one-event test
19. `P141-CASE-19 cross_config_replay` -> `test_cross_config_and_cross_event_replay_fail_closed`
20. `P141-CASE-20 cross_event_replay` -> `test_list_rejects_self_consistent_artifacts_not_backed_by_p133`
21. `P141-CASE-21 envelope_tamper` -> `test_envelope_and_receipt_tamper_fail_closed`
22. `P141-CASE-22 receipt_tamper` -> `test_receipt_tamper_symlink_and_budget_exhaustion_fail_closed`
23. `P141-CASE-23 lease_conflict` -> `test_notification_lease_conflict_fails_before_writes`
24. `P141-CASE-24 envelope_only_crash` -> `test_partial_destination_crash_and_receipt_orphan_fail_closed`
25. `P141-CASE-25 receipt_before_cursor_crash` -> `test_cursor_failure_replays_existing_artifacts_without_duplication`
26. `P141-CASE-26 multi_destination_partial_crash` -> the partial-destination test
27. `P141-CASE-27 batch_budget_and_free_space` -> the budget test, asserting zero new artifacts/cursor
28. `P141-CASE-28 clock_rollback` -> `test_clock_rollback_fails_closed`
29. `P141-CASE-29 no_p133_ack_mutation` -> `test_cursor_cannot_skip_missing_artifact_and_p133_tree_is_byte_immutable`
30. `P141-CASE-30 no_p133_event_cursor_mutation` -> the same immutable-tree test
31. `P141-CASE-31 no_external_io_surface` -> `test_notification_authority_is_distinct_from_p121_and_source_has_no_external_io`
32. `P141-CASE-32 exact_zero_authority` -> `test_validate_process_and_list_commands_are_json_only`
33. `P141-CASE-33 exact_catalog` -> `test_p141_catalog_is_exact_ordered_immutable_denominator`
34. `P141-CASE-34 matrix_anti_forgery` -> `test_p141_matrix_rejects_skip_authority_and_hash_forgery`
35. `P141-CASE-35 source_dependency_bindings` -> `test_p141_preliminary_and_final_evidence_bind_sources_dependencies_and_review`
36. `P141-CASE-36 final_does_not_rewrite_frozen_inputs` -> `test_p141_final_mode_does_not_rewrite_frozen_inputs`

Every row records one subprocess launch as evaluator activity, the exact P133
and P141 zero-authority maps, return code, output hash, wall time, and row hash.
Release validation binds the public immutable `CONFIG_FIELDS`,
`ENVELOPE_FIELDS`, `SOURCE_EVENT_FIELDS`, `MESSAGE_FIELDS`, `RECEIPT_FIELDS`,
and `CURSOR_FIELDS` constants exported by `p141_notification_authority.py`;
field-set drift changes its source hash and invalidates the freeze manifest.

### P141-007 — Independent implementation review

Review contract separation, durability, privacy, authority counters, tests,
and limitations using an identity distinct from the implementer.

### P141-008 — Release verification and private main

Integrate `p141-release`, documentation, lint, typecheck, targeted/full tests,
coverage, source drift, secret scan, commit with Lore trailers, and push the
verified milestone to private `main`.

## Stop conditions

- Any P133 validation, ordering, or binding ambiguity.
- Unknown destination or transition.
- Any nonzero forbidden authority counter.
- Any field/value suggestive of endpoint, credential, command, or action.
- Any path outside roots, symlink, non-regular artifact, lease conflict,
  malformed/tampered replay, insufficient space, or budget overflow.
- Any attempt to acknowledge P133 or claim real delivery.

## Explicit limitations

- P141 proves only a local deterministic notification authority simulator.
- It does not prove provider compatibility, real delivery, latency, retries,
  credentials, authentication, production availability, or operator replacement.
- A later milestone must separately authorize and qualify any external
  notification transport.

## Concrete implementation and release paths

- runtime: `app/services/p141_notification_authority.py`,
  `app/services/p141_runner.py`, `app/p141_notification_cli.py`;
- deployment: networkless/non-root/read-only systemd and Compose examples under
  `deploy/p141/`, with only the P133 lease file and P141-owned tree writable;
- release: `app/services/p141_release_evidence.py`,
  `scripts/run_p141_notification_authority.py`;
- tests: `tests/fixtures/p141/`, `tests/test_p141_*.py`;
- tracked evals: `evals/p141/input/notification-authority-profile.json`,
  `evals/p141/output/{canonical-matrix,freeze-manifest,release-evidence}.json`,
  `evals/p141/final-implementation-review.json`;
- integration: `pyproject.toml` command `opscat-notification-authority` and
  `scripts/verify.sh --profile p141-release` after P133 and P140 dependency
  reproduction.

P141-008 edits exactly those two integration files: add the console-script
mapping, help/allowlist/array/profile function/case dispatch in `verify.sh`, run
P140 dependency reproduction first, execute the four P141 test modules, then
run the final P141 evidence script against frozen tracked inputs.
