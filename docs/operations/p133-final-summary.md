# P133 Final Summary

## Result

P133 qualifies a credential-free, network-free local dead-man evidence outbox
for the independently supervised P131/P132 monitor. The promoted release status
is `p133_local_deadman_outbox_qualified`.

This is durable local evidence and operator acknowledgement, not notification
delivery or autonomous remediation. It does not add authentication, credentials,
provider APIs, live paging, command execution, connector writes, staging or
production mutation, multi-host failover, or operator-replacement authority.

## Implemented

- Seven closed watchdog reasons are normalized into a redacted snapshot. Unknown
  config fields, credential-like values, unsafe roots, symlinks, hard links,
  foreign files, invalid hashes, and boolean authority counters fail closed.
- A single active incident emits deterministic `opened`, `updated`, `reminder`,
  and `recovered` events. Heartbeat age is excluded from incident identity so an
  unchanged stale state deduplicates until its bounded reminder deadline.
- Immutable events are written and directory-synced before cursor advancement.
  Crash replay validates and reuses the canonical event rather than duplicating
  it; conflicting canonicals and uncertain durability are rejected.
- A derived local process lease serializes check, list, acknowledge, and
  retention operations. Directory-file-descriptor operations prevent cooperative
  path swaps between validation and write or deletion.
- Acknowledgements are local, immutable, self-hashed receipts. Retention prunes
  only exact owned and acknowledged events, reopens and compares exact bytes plus
  device/inode/size/change metadata immediately before deletion, removes the
  event before its receipt, and safely recovers an orphan receipt after an
  injected mid-cleanup crash.
- Retention also requires each deletion directory to be owned by the service UID
  and not group/world writable. This is a trusted cooperative single-writer
  boundary; malicious same-UID writers with directory access are not qualified.
- Closed CLI commands support one-shot and foreground operation. SIGTERM exits
  through normal control flow; evaluator-only no-sleep mode is bounded and is
  forbidden in supervisor manifests.
- systemd and Compose examples qualify the no-network, non-root, read-only P131,
  writable-P133 boundary. The launchd plist is structurally validated only; an
  external macOS sandbox or MDM policy is required for equivalent isolation.

## Promoted evidence

`evals/p133/` contains:

- `outbox-report.json`: 20/20 deterministic transition and fault cases pass,
  including ten emitted events, two deduplications, one recovery, two
  acknowledgements, two retained events, and one pruned event.
- `process-matrix.json`: eight real subprocess cases exercise stale detection,
  deduplication, reminder, recovery, list, acknowledgement, restart, exclusive
  lease contention, and SIGTERM shutdown using the real CLI.
- `supervisor-validation.json`: systemd and Compose isolation contracts qualify;
  launchd is recorded as `example_only_not_qualified` with its limitation.
- `authority-ledger.json`: runtime network, credential, connector, command,
  remediation, staging-mutation, and production-mutation authority remain exact
  integer zero; evaluator process and signal activity is disclosed separately.
- `release-evidence.json`: current source, manifests, promoted summaries, and raw
  process artifacts are hash-bound and all required gates pass.
- `raw/`: canonical watchdog, cursor, event, receipt, process, and fault artifacts
  referenced by the promoted reports.

The evaluator launched eight local subprocess cases and delivered one SIGTERM.
The canonical bounded run used 1,541 ms wall time, 464 ms self-plus-child CPU,
and 37,666,816 bytes peak resident memory, below the exact 60 s, 30 s, and
64 MiB release limits.

## Reproduce

```bash
bash scripts/verify.sh --profile p133-release
```

The promoted release evidence hash is
`sha256:ba47502a7b82cea2521c581716801563f4ea31746cc243dfbbbd639707ffe73f`.
Detailed verification and remaining boundaries are recorded in
`docs/operations/p133-verification-handoff.md`.

## Next dependency

P134 may add a separately supervised, store-and-forward delivery adapter with a
reviewed destination allowlist, explicit credentials boundary, delivery receipt
semantics, retry budget, and kill switch. P133 remains the source of truth and
must not gain network or remediation authority.
