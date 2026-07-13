# P133 Test Specification

## Configuration and redaction

- Accept only the exact `p133.deadman_config.v1` shape and bounded integer
  profile; reject unknown keys, booleans as integers, URL/provider/secret/action
  fields, path escapes, symlink parents, path overlap, and unsafe labels.
- Normalize every P131 watchdog outcome through a closed reason allowlist.
- Assert the exact seven-value normalized allowlist: healthy
  `heartbeat_current` plus the six unhealthy values `runtime_stopped`,
  `heartbeat_stale`, `state_missing`, `heartbeat_invalid`, `state_invalid`, and
  `watchdog_contract_invalid`. Cover every exact P131 reason in the documented
  mapping and require absent, non-string, contradictory, and unknown reasons to
  become the generic
  `watchdog_contract_invalid` without persisting the raw value.
- Do not consume P131 readiness/status output in P133.
- Prove events contain no raw path, runtime ID, environment value, source data,
  hostname, URL, token-like value, or arbitrary exception string.
- Require exact P121 authority keys with integer-zero values in every event,
  cursor-derived report, runtime ledger, and release artifact.

## Transition state machine

- Healthy startup emits zero events.
- First stale, stopped, missing, and invalid/tampered outcomes each open one
  incident in isolated fixtures.
- Same fingerprint before the reminder interval is deduplicated.
- Increasing heartbeat age with the same reason and state hash does not change
  the incident fingerprint or create update churn.
- Reason/fingerprint change emits one linked `updated` event.
- Same fingerprint at the exact reminder boundary emits one `reminder`; later
  checks before the next boundary are deduplicated.
- Recovery emits one `recovered`, closes the incident, and a second healthy
  check emits nothing.
- Acknowledgement does not close an incident or reset reminder time.
- Future time, excessive clock rollback, invalid cursor sequence, and invalid
  timestamps fail closed.

## Durability and replay

- Event write happens before cursor advancement.
- Inject a crash after event replace and before cursor replace; a later-clock
  retry must derive the same timestamp-independent event ID, reuse the existing
  original `occurred_at`, and advance once without duplicate bytes.
- Conflicting existing event content fails closed.
- Temp-write, file-fsync, and pre-replace failures preserve prior canonical
  files.
- Post-replace directory-fsync failures expose durability uncertainty and pass
  qualification only after hash-valid reload and later durable rewrite.
- Cursor/event/ack self-hash, config hash, event links, sequence, and filename
  identity are recomputed on every load.

## Acknowledgement and retention

- Ack requires a current owned event and exact SHA-256 event ID; a duplicate
  ack validates and returns the already durable bytes, preserving the original
  acknowledgement timestamp.
- Ack of missing, foreign, tampered, symlinked, or changed event fails closed.
- Retention prunes oldest acknowledged events only when count or byte budget is
  exceeded.
- Reopen through the validated parent directory descriptor and revalidate exact
  canonical bytes, device, inode, link count, regular-file type, size,
  modification/change timestamps, schema, and hash immediately before deletion.
  A hash-valid same-inode, same-size rewrite between initial validation and
  unlink must fail closed and remain present.
- Serialize checks, list, acknowledgement, and retention across P133 processes;
  delete through a validated parent directory descriptor.
- Require the immediate retention directory to be owned by the service UID and
  not group/world writable; unsafe permissions block deletion and preserve the
  prior cursor/event. Malicious same-UID writers remain explicitly unqualified.
- Delete event then fsync, delete ack then fsync; inject a crash between steps,
  validate the orphan ack, and remove it on retry. Prove P133 cannot create an
  existing event whose ack is absent because of its cleanup ordering.
- Unacknowledged, unreadable, foreign, hard-linked, symlinked, or tampered files
  block cleanup and remain present.
- Low-space or unrecoverable budget pressure leaves the prior cursor and current
  active incident unchanged.

## Runtime and supervisor integration

- `deadman-check` performs one check and returns 0 for healthy, 1 for an
  unhealthy watchdog outcome, and 2 for configuration/storage failure.
- `deadman-run --max-cycles` runs an exact count; `--forever` is mutually
  exclusive. `--no-sleep` exists only as an installed/module-form evaluator
  flag, requires positive `--max-cycles`, and is rejected in supervisor
  manifests and with `--forever`.
- `outbox-list` is read-only and returns only redacted summaries.
- `outbox-ack` accepts only exact event IDs and performs no external action.
- Real subprocess smokes prove stale open, duplicate suppression, reminder,
  recovery, list, ack, restart, and graceful stop within three seconds.
- Parse and qualify the systemd and Compose sidecar manifests; reject shells,
  URLs, mutable tags, host/privileged mode, secrets, writable monitor state,
  unrestricted argv, and missing restart throttling. Parse the launchd plist
  structurally but require it to remain explicitly unqualified until an
  equivalent macOS filesystem/network isolation policy exists.

## Release evidence

- Execute the promoted deterministic transition/fault matrix and record exact
  denominators for all expected and observed events.
- Persist bounded raw event/cursor/ack fixtures under `evals/p133/raw/` and use
  only relative promoted paths.
- Re-hash current source, CLI, manifests, profile, reports, ledger, and raw files
  during validation; reject copied/stale declared hashes.
- Reject missing fields, booleans substituted for counters, optimistic pass
  flags without substantive evidence, hidden evaluator process activity, and
  any non-zero runtime/evaluator authority counter.
- Run P131 and P132 regressions in the dedicated profile and run the full suite
  before promotion.

## Honest evidence boundary

Local outbox persistence proves neither external delivery nor notification
latency. Accelerated time, injected faults, bounded subprocesses, and single-host
files cannot prove 24-hour reliability, multi-host availability, supervisor
behavior on every OS, production autonomy, or operator replacement.
