# P133 Local Dead-Man Outbox

## Outcome

Persist a durable, redacted local notification outbox whenever the independent
P131 watchdog reports that the monitor is stopped, stale, missing, or invalid.
P133 closes the gap between detecting a dead monitor and leaving evidence that
another local process or a human can inspect after the fact.

P133 does not send anything over the network. It introduces no authentication,
credential access, connector, paging provider, remediation, arbitrary command,
staging mutation, production mutation, or operator-replacement authority.

## Why this follows P132

P132 proves that the real monitor can be supervised and that a separate process
can distinguish current, stopped, stale, missing, and tampered state. P133 turns
those watchdog outcomes into crash-safe local incident transitions. The dead-man
process is intentionally separate from the monitored process so monitor death
cannot suppress the outbox writer.

## Delivery slices

1. **Contract, redaction, and authority** - define closed configuration,
   normalized watchdog snapshots, self-hashed event/cursor/ack schemas, safe
   path roots, and exact-zero authority counters.
2. **Incident transitions and deduplication** - open one incident for an
   unhealthy transition, emit updates only when the reason/fingerprint changes,
   emit bounded reminders after a fixed interval, and emit one recovery event.
3. **Durability and idempotency** - write immutable events before advancing the
   cursor, reuse the same deterministic event after a crash between those
   writes, reject tamper/symlinks, and disclose post-replace durability doubt.
4. **Retention, disk pressure, and local acknowledgement** - retain all
   unacknowledged events, prune only exact owned acknowledged events, fail closed
   when the budget cannot be recovered, and keep acknowledgement non-authoritative.
5. **Independent runtime integration** - add closed `deadman-run`,
   `deadman-check`, `outbox-list`, and `outbox-ack` CLI surfaces plus systemd,
   and Compose qualified sidecar contracts plus an explicitly unqualified
   launchd structural example with no shell or external endpoint.
6. **Release evidence** - run deterministic transition/fault scenarios and real
   subprocess smokes, hash-bind raw evidence and current sources, and add a
   dedicated `p133-release` profile.

## Configuration contract

`p133.deadman_config.v1` has only these fields:

- `allowed_artifact_roots`: non-empty local roots;
- `state_path`: the P131 state file, inside an allowed root;
- `outbox_dir`, `cursor_path`, and `ack_dir`: local artifacts inside an allowed
  root and distinct from the P131 state path;
- `runtime_ref`: a bounded non-secret local label that is hashed before it is
  persisted in an event;
- `check_interval_seconds`, `heartbeat_timeout_seconds`, and
  `reminder_interval_seconds`: bounded positive integers;
- `max_event_files`, `max_outbox_bytes`, `max_event_bytes`, and
  `min_artifact_free_bytes`: bounded positive integers;
- `schema_version` exactly `p133.deadman_config.v1`.

Unknown keys, URLs, provider fields, credential-like names or values, shell
fragments, action names, non-local paths, symlinked parents, and booleans
substituted for integers fail closed. `outbox_dir` and `ack_dir` must be distinct
non-overlapping directories; neither may contain the other. `cursor_path` and
`state_path` may not equal, contain, or be contained by either directory or each
other. All four paths are pairwise non-overlapping after resolution. The config
hash excludes no field and binds every persisted P133 artifact.

## Redacted watchdog snapshot

P133 calls `evaluate_watchdog` in-process. Source readiness and
`monitor_status_snapshot` are explicitly out of scope. It persists only:

- a reason from the closed P131 watchdog reason set;
- `healthy` as a boolean;
- the hash-valid P131 `state_hash` when available;
- a finite bounded heartbeat age when available;
- `runtime_ref_hash`, never the raw runtime label or any filesystem path.

The exact P131-to-P133 reason map is:

- `heartbeat_current` -> `heartbeat_current` and healthy;
- `runtime_stopped` -> `runtime_stopped`;
- `heartbeat_stale` -> `heartbeat_stale`;
- `state_missing` -> `state_missing`;
- `heartbeat_missing` or `heartbeat_in_future` -> `heartbeat_invalid`;
- `state_invalid`, `state_hash_invalid`, `authority_not_exact_zero`,
  `runtime_execution_boundary_violated`, `invalid_source_state`,
  `invalid_canary_state`, `invalid_lifecycle_state`,
  `source_manifest_mismatch`, or `invalid_timestamp` -> `state_invalid`;
- every absent, non-string, contradictory, or future unknown reason ->
  `watchdog_contract_invalid` and unhealthy.

The exact persisted allowlist contains seven total values:
`heartbeat_current`, `runtime_stopped`, `heartbeat_stale`, `state_missing`,
`heartbeat_invalid`, `state_invalid`, and `watchdog_contract_invalid`.
`heartbeat_current` is the sole healthy value and is persisted only on a
`recovered` event; the other six are unhealthy. The raw error reason is never
copied into an event. Raw exceptions, source payloads, source IDs, paths,
environment variables,
hostnames, URLs, credentials, arbitrary metadata, and raw P131 runtime IDs are
not persisted. A snapshot fingerprint hashes the normalized reason, health,
state hash, and runtime-reference hash. The persisted heartbeat age is excluded
from incident identity because it changes on every stale check and would turn
one unchanged outage into an unbounded stream of false `updated` events.

## Incident and deduplication contract

The self-hashed `p133.deadman_cursor.v1` stores the config hash, next sequence,
last check time, and at most one active incident. The active incident stores its
deterministic incident ID, opened time, last reason, last snapshot fingerprint,
last event ID, and last emitted time.

- Healthy with no active incident emits nothing.
- Unhealthy with no active incident emits `opened`.
- A changed unhealthy reason or snapshot fingerprint emits `updated`.
- An unchanged unhealthy snapshot before the reminder interval emits nothing.
- An unchanged unhealthy snapshot at or after the interval emits `reminder`.
- Healthy with an active incident emits exactly one `recovered` and closes it.
- Clock rollback beyond five seconds, invalid timestamps, or an event sequence
  regression fails closed rather than creating duplicate or reordered evidence.

Every event uses schema `p133.deadman_event.v1`, a monotonically increasing
sequence, deterministic event and incident IDs, transition kind, normalized
snapshot, one `occurred_at` timestamp, previous-event link, config hash,
exact-zero authority, and `event_hash`. An opening incident ID hashes the config
hash, next sequence, and snapshot fingerprint. Event ID hashes config hash,
sequence, incident ID, transition kind, snapshot fingerprint, and previous event
ID; it excludes wall-clock time and random values.

## Crash consistency

For an emitting transition P133 writes the immutable event first, then advances
the cursor. The first attempt sets `occurred_at` to that check's injected UTC
time. If the process dies after event replacement but before cursor replacement,
retry derives the same event ID without using the new wall clock, loads the
existing event, and accepts its original `occurred_at` only when config,
sequence, incident, kind, snapshot fingerprint, previous link, schema, and hash
all match the pending transition. It then advances the cursor exactly once using
the existing event's time for `last_emitted_at`; `last_checked_at` becomes the
retry check time. A conflicting existing event fails closed.

Pre-replace failures preserve the prior canonical cursor, event, or ack file.
A post-replace directory-sync failure may leave a newer hash-valid artifact;
P133 reports durability uncertainty and requires reload plus a later durable
rewrite in qualification. It never claims the old inode survived.

## Acknowledgement and retention

`outbox-ack` accepts one exact event ID, verifies the immutable event, and writes
a self-hashed `p133.deadman_ack.v1` containing the event ID/hash, config hash,
and acknowledgement time. It does not resolve the incident, change watchdog
health, suppress a required reminder, invoke a provider, or grant action
authority.
Retrying acknowledgement validates and returns the already durable ack bytes,
including the original acknowledgement timestamp.

Retention may delete only an event with a matching valid ack. Before deletion it
revalidates the exact regular non-symlink, single-link file identity and content
hash. Every check, list, acknowledgement, and retention operation is serialized
by an exclusive local process lease; deletion uses a validated parent-directory
descriptor. Cleanup is intentionally ordered, not claimed atomic: unlink and fsync the
event directory first, then unlink and fsync the ack directory. A crash after the
first step leaves a valid orphan ack; the next cleanup may remove that ack only
after validating its schema/hash/config and proving the referenced event is
absent. This ordering cannot produce an existing event whose ack was removed by
P133. Any other event-without-ack or orphan shape fails closed. Unacknowledged,
foreign, malformed, tampered, hard-linked, or symlinked files are never removed.
If count/byte pressure remains, the current transition is not committed and
P133 returns `outbox_budget_exhausted`.

Portable POSIX APIs cannot atomically assert an inode identity and unlink a
pathname. Deletion therefore also requires the immediate outbox/ack directory to
be owned by the service UID and not group/world writable. The process lease and
permission check establish a trusted cooperative single-writer boundary. P133
does not claim protection against a malicious same-UID process with write access
to those directories.

## Closed command contract

Allowed installed commands are exactly:

- `opscat-monitor deadman-run --config <local-path> --forever`;
- `opscat-monitor deadman-run --config <local-path> --max-cycles <positive>`;
- `opscat-monitor deadman-check --config <local-path>`;
- `opscat-monitor outbox-list --config <local-path>`;
- `opscat-monitor outbox-ack --config <local-path> --event-id <sha256-id>`.

The service module never executes subprocesses. The release harness may invoke
only the equivalent closed module-form CLI commands in generated temporary
directories. The installed parser also accepts
`deadman-run --config <generated-local-path> --max-cycles <positive> --no-sleep`,
but `--no-sleep` is an evaluator-only bounded-test flag: it requires
`--max-cycles`, is rejected with `--forever`, and is forbidden in every
supervisor manifest. Qualified systemd and Compose manifests use immutable image
digests where applicable, non-root users, read-only monitor-state mounts,
writable outbox mounts, closed argv arrays, restart throttling, and no shell,
network, provider, secret, or action surface. The parsed launchd plist is
retained only as an example because it cannot express equivalent network and
filesystem isolation on its own.

## Required artifacts

- Service: `app/services/p133_deadman_outbox.py`
- Release evidence: `app/services/p133_release_evidence.py`
- CLI integration: `app/monitor_cli.py`
- Runner: `scripts/run_p133_deadman_outbox.py`
- Tests: `tests/test_p133_deadman_outbox.py`,
  `tests/test_p133_release_evidence.py`
- Manifests: `deploy/p133/opscat-deadman.service`,
  `deploy/p133/io.opscat.deadman.plist`,
  `deploy/p133/compose.deadman.yaml`
- Input: `evals/p133/input/outbox-profile.json`
- Outputs: `evals/p133/outbox-report.json`,
  `evals/p133/process-matrix.json`,
  `evals/p133/supervisor-validation.json`,
  `evals/p133/authority-ledger.json`, and
  `evals/p133/release-evidence.json`
- Verify profile: `bash scripts/verify.sh --profile p133-release`

## Promoted profile

- 30-second check interval, 180-second heartbeat timeout, and 300-second
  reminder interval;
- at most 32 event files, 1 MiB outbox bytes, 32 KiB per event, and 1 MiB free
  artifact space;
- at most 3 seconds subprocess shutdown latency, 2 MiB promoted raw artifacts,
  64 MiB measured peak process/child memory, 30 measured CPU seconds, and 60
  measured wall seconds;
- exact transition matrix for healthy, stale, stopped, missing, tampered,
  reminder, recovery, acknowledgement, retention, crash retry, low space, and
  post-replace recovery.

These are local qualification limits, not notification-delivery or production
availability SLOs.

## Promotion gates

- Transition counts, emitted event counts, dedupe counts, reminders,
  recoveries, acknowledgements, and retained/pruned counts have explicit exact
  denominators.
- The crash-between-event-and-cursor case produces one event and one sequence.
- Every promoted event/cursor/ack is schema-valid, self-hash-valid, config-bound,
  redacted, and linked consistently.
- Low-space and budget exhaustion preserve the prior cursor and do not lose an
  unacknowledged event.
- Tampered, foreign, hard-linked, and symlinked retention candidates block
  cleanup and remain present.
- Retention reopens the candidate through its directory descriptor, compares
  exact canonical bytes and device/inode/mode/link/size/change timestamps, then
  rechecks the pathname immediately before unlink. Same-inode, same-size rewrites
  between validation and deletion therefore fail closed.
- Group/world-writable or foreign-owned retention directories block deletion;
  same-UID malicious directory writers are outside the qualified threat model.
- Acknowledgement changes no health, incident, reminder, or authority field.
- Real subprocess checks use only closed commands and expose all process activity
  separately from runtime authority.
- The release runner records wall time, self/child CPU time, and peak
  self/child resident memory and fails the promoted resource gate when any
  profile bound is exceeded or replaced with a boolean/non-integer value.
- Runtime and evaluator arbitrary-command, credential, network, connector-write,
  remediation, staging-mutation, and production-mutation counters are exact
  integer zero.
- Current source, manifest, input, raw-artifact, report, and release hashes pass;
  Ruff, Mypy, targeted tests, P131/P132 regression, `p133-release`, and full
  repository verification pass.

## Stop conditions

- A notification is marked delivered, or any external delivery is implied.
- The monitored process itself is responsible for writing dead-man events.
- Paths, raw runtime IDs, arbitrary errors, source data, or credentials enter an
  event.
- A retry can append a second event for one sequence or transition.
- An acknowledgement resolves an incident or suppresses a due reminder.
- Retention deletes an unacknowledged, unowned, changed, linked, or tampered file.
- The service executes a subprocess, opens a network path, or mutates monitored
  state.
- Any claim implies production paging, 24/7 availability, production autonomy,
  remediation effectiveness, or operator replacement.
