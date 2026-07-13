# P136 Incremental Local Export Observer Roadmap

## Objective

P136 turns P135's one-shot provider-shaped local export attachment into a
bounded, crash-safe incremental observer. It tails one untrusted append-only
JSONL index, attaches each declared immutable segment through P135, promotes
evidence exactly once, and survives partial writes, restarts, index rotation,
and crashes between durable writes.

P136 is still local-artifact observation. It adds no auth, credentials,
environment reads, provider API, network, DNS, socket, subprocess, shell,
notification delivery, action execution, remediation, staging mutation,
production mutation, or operator-replacement authority.

## Dependency boundary

- P134 remains the only observation-authority policy evaluator.
- P135 remains the only provider-shaped segment reader and normalizer.
- P136 may orchestrate P135 but must not weaken P134/P135 validation or parse a
  provider segment independently.
- P131 contributes cursor, partial-line, bounded-prefix, rotation, graceful-stop,
  and checkpoint patterns.
- P133 contributes event-first/cursor-second recovery, atomic writes, and the
  exclusive process lease.

## Finite authority model

P136 never treats a P134 receipt as an unlimited polling grant. Runtime inputs
contain the complete canonical bytes of one current P134 contract, its complete
receipt ledger, and the ordered complete receipt bytes selected for index reads;
hash-only references are insufficient. Before observing the index, P136 validates:

- the P134 contract, review, receipt ledger chain, every receipt's ledger
  membership, receipt distinctness, and cumulative contract counters;
- current cycle wall time against contract and review validity windows, including
  configured clock-rollback tolerance;
- `requested_level=OA1_LOCAL_ARTIFACT`, `method=LOCAL_READ_FILE`,
  `capability=telemetry.events.read`, attempt number, and the configured logical
  index `source_ref_hash`;
- each cycle's proposal estimates against the configured maximum whole-index byte
  and complete-line budgets, not merely the bytes newly appended;
- the complete finite pool against P134 cumulative request, byte, and record
  budgets.

One deterministic poll cycle reserves exactly one distinct allowed receipt. A
receipt becomes reserved by an atomically written, file-fsynced, and parent-
directory-fsynced `p136.index_read_intent.v1` **before** the index is opened or
read. The record binds the receipt hash and complete receipt bytes hash, P134
contract/ledger hashes, checkpoint hash and committed state, deterministic cycle
ID, maximum whole-index byte and complete-line budgets, cycle start time, and
expected source/method/capability.

The same receipt may be retried only from that valid durable marker and only for
that exact uncommitted cycle. A receipt without such a marker is never reusable
after an attempted read. Once the cycle checkpoint is durable, its receipt is
consumed permanently. Receipt-pool exhaustion stops observation fail closed;
replenishment is a future separately governed control-plane concern.

Every segment entry references a separate P134 OA1 receipt. P136 validates the
current contract and the entry receipt's ledger membership before constructing a
single-artifact P135 manifest. P135 alone performs the segment read, parsing,
redaction, P120 wrapping, execution receipt, and per-entry ledger validation.

## Configuration and input contract

`p136.incremental_observer_config.v1` is exact-key, canonical, and self-hashed.
It contains:

- `observer_id`, `config_version`, and `created_at`;
- `base_dir`, `data_root`, and `state_root` references represented in promoted
  evidence only by hashes;
- relative `index_path`, `checkpoint_path`, `index_intent_dir`, `journal_dir`,
  `promotion_dir`, and `lease_path`;
- `p134_contract_hash`, `p134_receipt_ledger_hash`,
  `index_source_ref_hash`, and ordered `index_read_receipt_hashes`;
- bounded `limits`;
- the exact forbidden-authority schema initialized to integer zero;
- `config_hash`.

The runtime invocation supplies canonical full P134 contract, review, receipt
ledger, and ordered receipt bytes whose hashes exactly match the config. The
runtime also supplies a deterministic mapping from each accepted index entry to
its per-entry P135 input bundle; no contract or receipt is loaded from the
environment, credential store, network, or a discovered path.

All configured paths resolve beneath declared local roots without symlink
parents. State paths are pairwise non-overlapping and do not overlap the data or
index path. State directories are owner-only; regular state files have one link.
No absolute path is promoted.

Required limits are bounded positive integers:

- poll interval, maximum cycles, and maximum receipt-pool size;
- maximum whole-index bytes and complete lines per cycle;
- maximum index line bytes and JSON depth/nodes/string bytes;
- maximum pending entries and promotions per cycle;
- maximum journal/promotion bytes;
- maximum consecutive failures and maximum clock rollback;
- maximum retained canonical entry identities needed to verify the configured
  bounded index;
- retention deletion is not enabled in P136; budget exhaustion blocks.

## Index entry contract

Each complete newline-terminated line is one exact-key
`p136.incremental_index_entry.v1` object:

- `entry_id`, global positive `entry_sequence`, and `segment_id`;
- `source_id`, `provider`, `format`, `signal_family`, and relative segment path;
- expected content hash, bytes, and records;
- segment authority receipt hash and capability;
- `created_at`;
- `previous_entry_hash` (`null` only for global sequence 1);
- `rotation_from_hash` (`null` except on the first **unseen** entry of a new
  index identity);
- `entry_hash`.

The entry hash covers every other field. Sequence and previous-hash continuity
are global across rotations. Reusing an entry or segment ID is accepted only
when the complete canonical entry exactly matches the checkpoint's bounded
canonical identity map. Conflicting reuse fails closed. Prompt-like or
credential-like text is forbidden in identity/path fields.

## Secure index read, partial lines, and rotation

Each cycle first durably reserves its P134 receipt. It then opens the configured
index descriptor-relative from the approved root with `O_NOFOLLOW`, rejects
symlinks, hardlinks, and non-regular files, and checks descriptor identity before
and after the bounded read. P136 reads the whole bounded index file so it can
recompute every previously consumed byte before accepting an append.

For the same file identity:

- `size < committed_cursor` is truncation and fails closed;
- a consumed-prefix mismatch is mutation and fails closed;
- only bytes after the committed cursor are candidates;
- a partial final line is stored in the checkpoint as pending evidence while
  the committed cursor remains at that line's starting byte.

The checkpoint's exact pending-partial state is either `null` or an object with
`file_identity_hash`, `line_start_cursor`, `pending_byte_hash`,
`pending_byte_length`, and `observed_index_size`. The observed size advances to
the size actually read, but the committed cursor and consumed-prefix hash remain
at the partial line start. A same-identity retry must reproduce the pending bytes
exactly as a prefix before a newline can complete the line.

For a changed file identity:

- any pending partial tied to the old identity causes fail-closed continuity
  rejection; P136 never splices or discards uncommitted partial bytes;
- the new file may begin with a bounded prefix of canonical entries already
  present in the checkpoint identity map;
- every replayed entry must match its stored canonical entry hash, sequence, and
  IDs exactly and is resolved without invoking P135 or rereading its segment;
- the first unseen entry must have the next global sequence,
  `previous_entry_hash` equal to the last committed entry hash, and
  `rotation_from_hash` equal to that same hash;
- an identity containing only proven replay entries may become the new
  checkpoint identity without another segment read;
- an empty new file or a new file ending before any complete continuity proof
  remains pending and cannot replace the committed index identity;
- any gap, rollback, fork, lineage mismatch, or conflicting replay fails closed.

Malformed complete lines become immutable denominator-visible rejection records
and advance only after that rejection is durable.

## P135 bridge, duplicate resolution, and ledger namespace

Duplicate, restart, and rotation replay resolution occurs **before** P135. If an
entry exactly matches a durable P136 promotion and canonical identity record,
P136 returns that promotion outcome and advances eligible index state without
opening the segment. A segment may be reread only when a fresh, unused segment
receipt has been allocated and the operation is a new governed attachment, not
duplicate recovery.

For every first-seen accepted entry, P136 constructs one P135 manifest and one
independent per-entry P135 receipt ledger. P136 never combines those results into
a fictional shared P135 ledger. A P136 promotion record stores and validates the
independent tuple:

`(p135_manifest, p135_artifact_spec, p134_segment_receipt, p135_execution_receipt, p135_receipt_ledger, p135_normalized_bundle)`.

The deterministic promotion key binds:

- P136 config and index entry hashes;
- P134 contract, receipt-ledger, and segment authority receipt hashes;
- P135 manifest, artifact spec, adapter version, observed content, normalized
  bundle, execution receipt, and independent per-entry ledger hashes.

Successful and denominator-visible failed P135 attachments are both durable
promotion outcomes. A provider parse failure cannot become a success. A
pre-read authority/path/budget failure becomes a P136 rejection outcome and does
not claim segment bytes were read. P136 guarantees promotion exactly once; it
does not claim attachment/read exactly once because a crash may require a newly
authorized governed retry.

The canonical evaluator records entry-hash-qualified segment-read and promotion
events. Duplicate counts are reconstructed from repeated hashes and bound into
each case before aggregate validation; they are never initialized as assumed
zero release claims.

## Durable ordering and recovery

The state machine is:

`UNLEASED -> LEASED -> LOAD -> RECOVER -> RESERVE_INDEX_READ -> READ_INDEX -> VALIDATE_ENTRY -> RESOLVE_DUPLICATE|ATTACH -> WRITE_PROMOTION_INTENT -> WRITE_PROMOTION -> ADVANCE_CHECKPOINT -> IDLE|STOP`.

One nonblocking `flock` lease is acquired before reading checkpoint, intent,
journal, promotion, or index state. The cycle and entry durable orders are:

1. select one unused P134 index-read receipt and derive deterministic cycle ID;
2. atomically write and fsync `p136.index_read_intent.v1`, then fsync its parent;
3. open/read/validate the bounded whole index;
4. resolve known duplicates from durable P136 state without P135;
5. for a first-seen entry, obtain and fully validate its independent P135 bundle;
6. atomically write and fsync deterministic `p136.promotion_intent.v1`, then
   fsync its parent;
7. atomically write and fsync immutable `p136.promotion_record.v1`, then fsync
   its parent;
8. atomically replace and fsync `p136.observation_checkpoint.v1`, then fsync its
   parent;
9. retain intents as audit evidence; P136 performs no retention deletion.

On restart:

- a valid index-read intent without a completed cycle resumes only that exact
  cycle, receipt, checkpoint hash, and bounded read; no new receipt is consumed;
- a read attempt lacking a valid durable reservation is non-resumable and its
  receipt cannot be reused;
- an entry without promotion intent is evaluated from the reserved cycle; P135
  may run only if no equivalent promotion exists and a valid unused segment
  receipt remains allocated;
- promotion intent without promotion is validated and promoted once;
- promotion without checkpoint is validated and checkpointed without P135;
- an equivalent durable promotion is duplicate evidence, not another promotion;
- conflicting reservation, intent, promotion, sequence, chain, checkpoint, or
  P135 per-entry bundle/receipt/ledger state fails closed.

Checkpoint state binds config, index identity, committed cursor,
consumed-prefix hash, observed index size, pending partial, next entry and
promotion sequences, last entry and promotion hashes, consumed/reserved
index-read receipts, bounded canonical entry identity map, promotion keys,
counters, timestamps, and exact-zero authority. It is exact-key, self-hashed,
and atomically durable.

## Runtime and stop semantics

The CLI supports one-cycle and bounded foreground-loop modes. The loop uses
monotonic cadence, consumes at most the configured receipt pool, and emits a
self-hashed termination receipt on normal completion, maximum cycles, receipt
exhaustion, failure-threshold stop, SIGINT, or SIGTERM. Lease conflict exits
before any checkpoint, index, or segment read.

Repeated failures are durably counted. Once the configured threshold is reached,
runtime stops fail closed with the prior valid checkpoint preserved. Wall-clock
rollback beyond configured tolerance is rejected while cadence and resource
measurement use monotonic clocks. Signal handlers only set a stop flag; the
termination receipt is written at the next safe boundary.

## Exact measurement schemas

`forbidden_authority` has exactly these integer keys, all measured and zero:

- `provider_call_count`, `live_connector_call_count`, `network_call_count`;
- `dns_lookup_count`, `socket_call_count`, `credential_read_count`;
- `environment_read_count`, `subprocess_launch_count`, `shell_execution_count`;
- `signal_count`, `delivery_count`, `remediation_count`;
- `staging_mutation_count`, `production_mutation_count`,
  `operator_replacement_count`.

`runtime_activity` has exactly these nonnegative integer keys:

- `index_stat_count`, `index_file_open_count`, `index_file_read_count`,
  `index_bytes_read`, `index_complete_lines_evaluated`,
  `index_partial_bytes_observed`, `index_read_intent_write_count`;
- `segment_stat_count`, `segment_file_open_count`, `segment_file_read_count`,
  `segment_bytes_read`, `segment_records_parsed`;
- `promotion_intent_write_count`, `promotion_record_write_count`,
  `checkpoint_write_count`, `directory_fsync_count`;
- `duplicate_resolution_count`, `recovery_replay_count`, `rotation_count`,
  `rejection_record_count`.

P136 aggregates segment activity only from independently validated P135
execution evidence; evaluator activity never inflates runtime activity.

`evaluator_activity` has exactly these nonnegative integer keys:

- `runner_invocation_count`, `profile_read_count`, `artifact_write_count`,
  `child_process_count`, `signal_delivery_count`.

`resource_usage` has exactly:

- integer `wall_time_ms`, measured with a monotonic clock;
- integer `cpu_time_ms` for the evaluator process and integer
  `child_cpu_time_ms`, both from `resource.getrusage`; the release CPU limit
  applies to their sum;
- integer `peak_memory_bytes`, measured as the P136 matrix's increase in process
  peak RSS over its start baseline, normalizing macOS `ru_maxrss` bytes and
  Linux `ru_maxrss` KiB so an embedding process's earlier high-water mark is not
  charged to P136;
- integer limits `wall_limit_ms=30000`, `cpu_limit_ms=15000`, and
  `peak_memory_limit_bytes=134217728`.

All exact-key maps reject booleans, negative values, unknown keys, and
self-reported/stamped counters. The canonical guard probes forbidden surfaces,
proves each probe is blocked, and keeps forbidden runtime counters zero because
the guarded operation never crosses the runtime boundary. Evaluator process and
signal activity is separately visible.

## Fixed release denominator

P136 uses exactly 50 principal cases:

1. Prometheus first-batch promotion;
2. Loki first-batch promotion;
3. Grafana first-batch promotion;
4. Sentry first-batch promotion;
5. OTLP first-batch promotion;
6. second append batch promotion;
7. partial final line deferred with exact pending state;
8. completed same-identity partial line promoted;
9. deterministic duplicate resolved without segment read;
10. restart duplicate resolved without segment read;
11. valid rotation continuity;
12. rotated replay prefix resolved without segment read;
13. malformed complete index line rejected;
14. duplicate JSON key index line rejected;
15. non-finite index value rejected;
16. oversized index line rejected;
17. whole-index byte budget rejected;
18. whole-index complete-line budget rejected;
19. index symlink/hardlink/non-regular rejected;
20. same-identity consumed-prefix mutation rejected;
21. same-identity truncation rejected;
22. rotation sequence gap rejected;
23. rotation lineage mismatch rejected;
24. entry ID conflict rejected;
25. segment ID conflict rejected;
26. denied, stale, or expired index receipt rejected;
27. receipt reuse without matching durable reservation rejected;
28. index receipt byte estimate exceeded;
29. index receipt record estimate exceeded;
30. wrong index level/method/capability/source rejected;
31. segment content/size mismatch rejected through P135;
32. provider parser failure promoted only as denominator failure;
33. crash after index-read intent before read resumes same reservation;
34. crash after index read before P135 resumes same reservation;
35. crash after promotion intent recovers exactly one promotion;
36. crash after promotion before checkpoint recovers without P135;
37. checkpoint/index-intent/journal/promotion tamper rejected;
38. pre-replace durability failure preserves prior state;
39. post-replace directory-fsync uncertainty stops;
40. competing lease performs no state/index/segment read;
41. exact config key/path topology violation rejected;
42. excess wall-clock rollback rejected;
43. receipt-pool exhaustion emits fail-closed termination;
44. consecutive-failure threshold emits fail-closed termination;
45. SIGINT emits a hash-bound safe-boundary termination receipt;
46. SIGTERM emits a hash-bound safe-boundary termination receipt;
47. forbidden runtime authority probes are blocked and measured;
48. P135 bridge manifest/receipt/ledger semantic tamper rejected;
49. empty or replay-only rotated identity remains pending or proves exact replay;
50. rotation after an old-identity pending partial is rejected.

Every case is substantive and carries exact expected outcome/error semantics;
case booleans alone are insufficient.

## Release gates

- Independent plan and code reviews have zero unresolved P0/P1/P2 findings.
- Targeted tests, Ruff, Mypy, docs checks, and full repository verification pass.
- Exactly 50/50 canonical cases pass with independently rebuilt totals.
- All five P135 provider profiles are promoted through the real bridge.
- Duplicate/restart/rotation/crash replay creates no duplicate promotion and no
  unauthorized duplicate segment read.
- Every actual index read is covered by one current P134 OA1 receipt and a
  durable pre-read reservation; every actual segment read is covered by one
  current unused segment receipt.
- Promoted records, checkpoint, reservations, journal, independent per-entry
  P135 manifests/bundles/receipts/ledgers, release evidence, and current source
  hashes independently revalidate.
- Runtime forbidden authority has the exact schema and exact integer zero.
- Runtime/evaluator activity and resources have exact schemas and measured
  values; wall is at most 30 seconds, self-plus-child CPU is at most 15 seconds,
  and peak RSS is at most 128 MiB.
- Release status is exactly
  `p136_incremental_local_observation_qualified`.

## Non-goals

- No live provider polling, OA2/OA3/OA4, credentials, auth, or OAuth.
- No directory discovery, arbitrary globbing, provider socket tailing, or
  request-controlled endpoint.
- No notification delivery, action execution, remediation, rollback, or
  staging/production mutation.
- No journal/promotion retention deletion.
- No same-UID malicious-writer resistance, multi-host consensus, or production
  operator-replacement claim.

## Ticket order

1. P136-001: config, full P134 authority inputs, pre-read reservation, entries.
2. P136-002: secure bounded scanner, cursor, pending partial, and rotation.
3. P136-003: duplicate-first P135 bridge and per-entry ledger namespace.
4. P136-004: reservation/promotion/checkpoint durability and crash recovery.
5. P136-005: lease, bounded loop CLI, exhaustion, failures, and signals.
6. P136-006: exact 50-case runner, schemas, and release evidence.
7. P136-007: independent review, docs, and claim boundaries.
8. P136-008: full verification, Lore commit, and private push.
