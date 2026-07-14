# P137 Test Specification

## Contract and schema

- Accept only exact-key, self-hashed P137 configs, P136 handoff bundles,
  evidence atoms, incidents, hypotheses, evidence requests, classifications,
  ledgers, intents, checkpoints, heartbeats, readiness records, termination
  receipts, and release evidence.
- Reject unknown or missing fields, booleans in integer fields, invalid
  timestamps, unsafe paths, overlapping roots/state paths, duplicate IDs,
  invalid hashes, prompt/action-shaped executable fields, and credential/
  network/command-shaped configuration.
- Require complete canonical `p137.p136_handoff_bundle.v1` bytes at the fixed
  path; hash-only P136 release, checkpoint, or promotion references are
  insufficient.
- Config pins `p136_handoff_chain_root_hash`; it does not pin every future
  bundle hash. The P137 checkpoint stores last accepted bundle sequence and hash.
- P136 publisher genesis starts at `bundle_sequence=1`, has
  `previous_bundle_hash=null`, derives the immutable chain root from the
  self-hashed publisher genesis record, persists that root in publisher state,
  allocates next sequences from publisher state, chains previous bundle hashes,
  binds checkpoints to bundle hashes, and publishes by intent, state recovery,
  atomic replace, file fsync, and parent fsync. P137 config only pins fixed path
  plus chain root.
- Require P136 release status exactly
  `p136_incremental_local_observation_qualified`.
- Validate all P137 exact-key maps for forbidden authority, runtime activity,
  evaluator activity, resource usage, counters, duplicate counts, attempted
  request hashes, and score tuples.
- Require `allowed_request_catalog` to equal the lexical 15-entry tuple from the
  roadmap in exact order.

## P136 handoff ingest

- Recompute the P136 handoff bundle self-hash, sequence, previous-bundle hash,
  chain-root hash, fixed-path binding, canonical byte hashes, descriptors, P136
  config, flattened P136 runtime authority, `now`, qualified P136 release
  evidence, final P136 implementation review, checkpoint, canonical entry map,
  promotion map, P134/P135 hash bindings, and forbidden-authority counters before
  atom creation.
- Decode byte payloads from canonical lowercase hexadecimal encoding of exact
  bytes. Reject empty strings, odd length, characters outside `[0-9a-f]`,
  whitespace, prefixes, uppercase, separators, `bytes.fromhex`/`decoded.hex()`
  mismatch, hash mismatch, and descriptor length mismatch. Flatten decoded
  authority bytes into exact fields `contract`, `review_receipt`,
  `receipt_ledger`, `index_receipts`, `segment_receipts`, `contract_bytes`,
  `review_receipt_bytes`, `receipt_ledger_bytes`, `index_receipt_bytes`, and
  `segment_receipt_bytes`, preserving exact P136 canonical JSON bytes.
  P137 itself strict-decodes, canonical-byte-hash/length validates,
  JSON-parses, and exact-object-compares `segment_receipt_bytes` to
  `segment_receipts` before constructing P136 authority.
- Accept only promotions where
  `checkpoint.promotion_keys[promotion.entry_hash]` equals the complete
  canonical promotion record in the bundle's promotion map.
- Separately recompute the embedded `promotion_key` from the complete canonical
  promotion record and reject absent checkpoint entries, altered checkpoint
  values, and nested promotion-key tamper.
- Validate P136 promotion records through `entry_hash`, exact checkpoint
  membership, and embedded promotion-key recomputation. Do not require a
  promotion hash chain.
- Direct tests invoke `validate_incremental_observer_config(p136_config)`,
  `validate_observer_runtime_authority(p136_config, authority, now=now)` with
  only the byte fields that validator actually validates for contract, review,
  ledger, and index receipts plus validated `segment_receipts` mappings, and
  `validate_promotion_record(promotion, expected_entry=expected_entry,
  runtime=runtime)` over supplied bundle bytes. `validate_promotion_record`
  consumes `segment_receipts` mappings; P136 is not claimed to validate segment
  receipt bytes.
- Validate embedded P135 normalized bundles and denominator-failure bundles
  without reopening original provider artifacts.
- Convert successful and denominator-visible failed promotions into bounded
  `p137.evidence_atom.v1` records.
- Reject absolute paths, credentials, endpoints, raw provider payload leakage,
  prompt-like text in executable fields, and nonzero forbidden counters.
- Assert original provider file stat/open/read activity, P136 index rereads,
  path discovery, environment reads, network calls, and credential reads are
  exactly zero.

## Correlation and incident state

- Correlate only by exact system ID, entity hash, overlapping time window,
  provider/signal family, label hash, content hash, or P136 rejection reason.
- Reject free-form text similarity, embeddings, provider lookup, network lookup,
  operator prompts, regex discovery, and path discovery.
- Verify legal incident transitions and reject every terminal-state transition.
- Prove restart duplicate ingest preserves stable incident IDs and creates no
  duplicate atoms; duplicate counts must be probe-derived from repeated
  promotion keys and entry hashes.
- Enforce open-incident, correlation-window, incident-duration, journal, and
  ledger budgets.

## Hypotheses and ranking

- Generate only closed-category, closed-statement hypotheses.
- Persist support, contradiction, and missing-evidence edges with exact hashes,
  deterministic weights, reason codes, request need class, windows, and bounded
  counts.
- Enforce the closed relation/weight/classifier table from the roadmap.
- Split request needs into `LOCAL_SELECTION` and `EXTERNAL_UNAVAILABLE`.
  Unavailable needs are recorded as missing evidence and are never executed.
- Validate the closed statement-code set, closed reason-code set,
  atom-field enums, total input-to-statement mapping, denominator-failure
  mapping, evidence-state-to-edge rules, and exact integer score formulas from
  the roadmap.
- P135 `promotion.status=denominator_failure` conversions require existing
  P135 failure-bundle validation, a nonempty closed-safe
  `bundle.failure_reason`, exact equality to the sole P120 `state_reasons`
  element and the normalized failure label value where present, and then map
  arbitrary validator-accepted failure strings to
  `state_reason_codes=["local_catalog_selectable", "p135_adapter_failure"]`
  and `request_need_class=LOCAL_SELECTION`.
- Success/context-only P120 `state_reasons` remain closed; unknown reasons
  reject with `p120_state_reason_unmapped`. The generic P135 failure conversion
  never infers `EXTERNAL_UNAVAILABLE` from substrings; external unavailable
  mapping requires closed external-authority reason codes.
- Weak counter input maps to exact reason code `weak_counter_signal` with
  `contradicts_soft` weight `-2`; decisive counter input remains
  `decisive_counter_signal` with `contradicts_decisive` weight `-5`.
- Rank by deterministic semantic score tuple. Lexical hypothesis hash may order
  storage only; it must not resolve an unresolved semantic tie for
  classification.
- Verify contradiction suppression, blocking missing-evidence behavior, benign
  pattern ranking, unavailable external evidence behavior, and deterministic tie
  handling.
- Reject probability floats, booleans-as-integers, free-form classifications,
  unbounded evidence edges, and invented evidence.

## Bounded evidence requests

- Execute every closed catalog request exactly once in the canonical matrix and
  in the roadmap's lexical order:
  `compare_current_window_to_promoted_baseline`,
  `fetch_record_by_evidence_id`, `join_records_by_entity_and_window`,
  `select_records_by_content_hash`, `select_records_by_entity_ref`,
  `select_records_by_label_hash`, `select_records_by_provider`,
  `select_records_by_risk_flag`, `select_records_by_signal_family`,
  `select_records_by_system_id`, `select_records_by_time_window`,
  `select_rejections_by_reason`, `summarize_log_preview_hashes`,
  `summarize_numeric_samples`, and `summarize_topology_refs`.
- Reject any non-catalog request, unknown parameter, path, URL, provider query,
  shell text, natural-language instruction, credential key, mutation verb, or
  unbounded regex.
- Derive a one-shot `attempted_request_hash` before each local selection.
  Replaying an existing equivalent request returns the durable request bytes;
  conflicting bytes at the same deterministic path fail closed; the same local
  selection is not executed twice.
- Enforce request input-record, output-record, output-byte, per-incident request,
  wall, CPU, and memory budgets.

## Classification and ledger

- Confirm incidents only when a non-benign top hypothesis has primary support,
  no blocking missing evidence, and no decisive contradiction.
- Classify insufficient evidence for blocking missing evidence, unavailable
  external needs, unresolved ties, or exhausted bounded local requests.
- Classify benign anomalies only from supported benign-pattern hypotheses with
  no blocking missing evidence.
- Classify accepted incidents as `aborted_fail_closed` only when the
  classification record write and ledger CAS both succeed.
- Corrupted state, CAS failure, lease conflict, and resource exhaustion that
  cannot safely write both classification and ledger return classification
  `none`, exact `expected_error`, exact `termination_reason`, and preserve the
  last valid ledger.
- Pre-ingest failures create no incident classification and must report the
  exact expected error from the matrix.
- Recompute every classification from durable incidents, hypotheses, requests,
  attempted request hashes, and atoms; forged summaries or counters fail closed.
- Ledger validation recomputes every sequence, transition, hash link, CAS
  predecessor, counter, duplicate count, resource value, and terminal
  classification.

## Durability, lease, recovery, signals, heartbeat, and budgets

- Acquire one nonblocking exclusive lease before any P137 state or P136 handoff
  bundle read. Competitors perform zero ingest/request/classification.
- Write/fsync/directory-fsync ingest intent before incident state, incident
  before hypotheses, requests before classification, classification before
  ledger, and ledger with CAS against the prior hash.
- Crash after ingest intent, incident write, request write, or classification
  write before ledger CAS recovers exactly once without duplicate atoms,
  requests, classifications, or ledger entries.
- Equivalent deterministic paths are idempotent; conflicting existing bytes fail
  closed.
- Corrupt, stale, forked, truncated, or semantically inconsistent state fails
  closed while preserving the last valid ledger. It writes
  `aborted_fail_closed` only when the classification record write and ledger CAS
  can complete; otherwise it reports classification `none`.
- Reject P136 handoff rollback, fork, and torn replacement by comparing
  `bundle_sequence`, `previous_bundle_hash`, fixed-path bytes, descriptor
  length/hash, `bundle_hash`, and the P137 checkpoint's last accepted
  sequence/hash.
- Bounded continuous mode uses finite `max_cycles`, fixed handoff path/version
  polling, monotonic cadence, heartbeat writes, readiness states, and staleness
  checks. It never discovers paths or claims unbounded monitoring.
- SIGINT/SIGTERM set only a stop flag. Signal-driven `aborted_fail_closed` is
  authoritative only when classification write and ledger CAS succeed; otherwise
  classification is `none` with exact signal termination/error. Signal delivery
  is evaluator-visible and not runtime authority.
- Budget exhaustion blocks rather than deleting evidence or widening authority.

## Static and runtime authority guards

- Static scans fail on P137 runtime imports or calls for provider SDKs, network
  clients, sockets, DNS, credentials, environment reads, subprocess/shell,
  notification delivery, action/remediation modules, or staging/production
  mutation.
- Runtime guard probes are evaluator-injected fake callables only. The runtime
  must reject each fake callable before invocation, while production/runtime
  imports remain statically banned.
- Promotable runtime forbidden counters remain exact integer zero for provider,
  live connector, network, DNS, socket, credential, environment, subprocess,
  shell, signal, delivery, remediation, staging mutation, production mutation,
  and operator replacement.
- Runtime activity records only P137 handoff/state reads, P136 validation over
  supplied bytes, local selection requests, and P137 state writes. Evaluator
  activity never inflates runtime activity.

## Exact measurement and leak safety

- Validate the exact `forbidden_authority`, `runtime_activity`,
  `evaluator_activity`, `resource_usage`, and named counter-delta profile key
  sets defined by the roadmap; reject booleans, negatives, unknown keys, and
  stamped/self-reported values.
- Every delta profile uses exactly the canonical `runtime_activity` key names,
  including `lease_acquire_count`, `state_read_count`,
  `termination_receipt_write_count`, `ingest_intent_write_count`,
  `evidence_atom_write_count`, `evidence_request_write_count`, and
  `attempted_request_hash_write_count`. Stale profile-only aliases are invalid.
- Measure wall time with a runner-owned monotonic clock.
- Measure self and child CPU with `resource.getrusage`; the 15 s limit applies
  to the sum.
- Normalize the P137 matrix interval's macOS/Linux peak RSS growth to bytes,
  rather than charging an embedding process's earlier peak.
- Derive duplicate atom and request counts from repeated entry-hash,
  promotion-key, and attempted-request-hash probe events. Case summaries and
  aggregate release totals must equal those measurements; fixed zero fields are
  not accepted.
- Every canonical matrix row references a named delta profile. All forbidden
  authority deltas are exact zero. Byte deltas are fixture-derived integers:
  `handoff_bundle_bytes_read = len(canonical_handoff_bundle_bytes)` and
  `promotion_bytes_validated = sum(len(canonical_promotion_bytes))`; final
  evidence contains only materialized integers.
- Profile evidence must either contain exact full maps for every canonical
  schema key or declare source-bound exact overrides over the canonical zero
  full map and materialize full post-override maps per row.
- Resource-exhaustion cases use a case-specific low measured limit compared to
  runner-owned measurement and verify the exact expected write deltas before
  failure.
- Promoted artifacts contain no absolute path, credentials, prompt injection
  text, raw secret values, or unredacted provider payload.

## Canonical 60-case runner

The canonical runner executes exactly the 60 cases enumerated in
`p137-evidence-to-incident-roadmap.md`, validates each exact expected label or
exact expected error, and independently rebuilds all totals. Required totals:

- 60 expected, 60 passed, 0 failed;
- all four terminal classifications represented among accepted incidents;
- all 15 evidence request catalog entries represented;
- all five P135 provider profiles represented through P136 promotions, with
  OTLP counted as metrics;
- zero original provider artifact reads;
- zero provider/network/credential/action/remediation authority;
- all recovery, lease, CAS, hash namespace, guard, bounded continuous-mode,
  heartbeat, readiness, stale handoff, SIGINT, SIGTERM, corrupt-state, and
  resource cases represented in the denominator;
- explicit rollback, same-sequence fork, previous-hash discontinuity, torn
  fixed-path replacement, crash-after-ingest-intent, crash-after-incident-write,
  crash-after-request-write, and crash-after-classification-before-ledger-CAS
  rows represented;
- resource usage within 30 s wall, 15 s self-plus-child CPU, and 128 MiB peak
  RSS growth;
- exact release status `p137_local_evidence_triage_qualified`;
- a final frozen-source implementation-review artifact over the frozen source,
  profile, fixtures, and preliminary matrix output is mandatory input to
  release-evidence validation.

## Verification sequence

1. Plan-readiness review for the roadmap, test spec, and tickets only.
2. Targeted failing P137 contract/schema tests, then implementation until green.
3. P136 handoff validation tests with valid and adversarial bundles.
4. Correlation, hypothesis, request, classification, and ledger tests.
5. Durability, recovery, lease, signal, CAS, heartbeat, readiness, staleness,
   bounded-loop, and budget tests.
6. Static authority scan and evaluator-injected runtime guard probes.
7. Targeted Ruff and Mypy.
8. Preliminary canonical 60-case run to a temporary directory, freezing source
   hashes, profile bytes, fixture bytes, and matrix output.
9. Final frozen-source implementation review and resolution against the frozen
   source, docs, profile, fixtures, and matrix output.
10. `bash scripts/verify.sh --profile p137-release`, structurally consuming the
    frozen matrix plus final review without regenerating reviewed inputs.
11. Full repository verification in a loopback-capable local environment.
12. Secret/path scan, `git diff --check`, Lore commit, private push, and
    local/remote/private-state confirmation.

The standalone runner defaults release output to `evals/p137/output`, separate
from `evals/p137/final-implementation-review.json`, and cleanup must preserve
profile, handoff, and review inputs even when a caller chooses an overlapping
directory.
