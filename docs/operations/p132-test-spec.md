# P132 Test Specification

## Lifecycle

- Unit-test stop-aware waits without real sleeping.
- A subprocess SIGTERM smoke requires exit 0, matching receipt/state hashes,
  lease release, `runtime_stopped`, and signal-to-exit latency <= 3 seconds.
- SIGINT follows the same normal-control-flow path.
- Forced kill leaves a readable checkpoint; restart increments resume count
  and accepts only newly appended observations.
- Restart changes `lifecycle.phase` only after lease ownership and retains stop
  history.
- Validate exact lifecycle types, allowed reasons, timestamps, count, receipt
  schema, receipt self-hash, and final-state hash.

## Split-brain and restart control

- Two real processes compete for one lease; exactly one owns it and the loser
  returns `runtime_lease_unavailable`.
- Backoff is positive, non-decreasing, deterministic, capped at 30 seconds, and
  equals `[1, 2, 4, 8, 16, 30]`; 60 stable seconds reset the attempt count.
- Invoke watchdog as a separate module-form process and require exit status to
  agree with stopped, stale, missing, tampered, and current state.
- Supervisor manifests contain restart throttling and bounded stop timeouts.

## Endurance and resource envelope

- Run 1,000 injected-clock cycles with one generated local JSONL observation
  per cycle.
- Expected, accepted, duplicate, invalid, and lost denominators are explicit.
- Require state <= 1 MiB, retained reports <= 8, report directory <= 1 MiB,
  total promoted temporary artifacts <= 2 MiB, traced peak memory <= 64 MiB,
  CPU <= 30 seconds, and wall time <= 60 seconds.
- Recent hashes <= 20,000; per-cycle limits are 10 records/64 KiB and each line
  <= 4 KiB.
- Rotation, truncation, partial final line, malformed JSON, oversized line, and
  repeated event identity preserve existing P131 semantics.

## Storage safety

- Retention considers only exact P131 report names and requires regular
  non-symlink type, bounded parse, valid schema/hash, and matching runtime/config
  ownership; foreign, unreadable, or tampered candidates block cleanup.
- The report directory must be owned by the service UID and not group/world
  writable. Unsafe permissions block retention and preserve existing reports;
  malicious same-UID writers remain outside the qualified threat model.
- Retained count, directory bytes, and free-space config values are bounded
  positive integers.
- Low space before write fails closed.
- Temp-write, file-fsync, or replace failure preserves prior canonical state.
- Directory-fsync failure after replace may leave a newer canonical state, but
  it must be hash-valid, marked durability-uncertain by the evaluator,
  successfully reloaded, and durably rewritten before the case passes.
- Report-write interruption never advances `last_report_bucket` without a
  committed report.

## Supervisor manifests and command allowlists

- Parse and validate systemd, launchd, and Compose without launching them.
- Require closed `opscat-monitor run --config ... --forever`, restart
  throttling, graceful stop, and explicit local volume/config paths.
- Reject shell wrappers, inline secrets, credential fields, privileged mode,
  host networking, mutable image tags, and action/remediation commands.
- Validate module-form evaluator commands separately from the installed
  `opscat-monitor = app.monitor_cli:main` entrypoint.

## Evidence and authority

- Runtime authority keys exactly match `P121_AUTHORITY_COUNTER_KEYS`; every
  value has type `int` and value `0`.
- Evaluator activity reports exact child launches, SIGTERM, SIGINT, forced kill,
  watchdog calls, status calls, and lease conflicts separately.
- Evaluator arbitrary command, credential read, network call, connector write,
  remediation, staging mutation, and production mutation counters are exact
  integer zero.
- Release validation recomputes every gate and rejects missing fields, boolean
  counter substitution, stale hashes, source drift, and optimistic claims.

## Honest evidence boundary

Accelerated clocks, bounded subprocess smokes, fault injection, and single-host
leases cannot prove 24-hour production reliability, multi-host availability,
cloud supervisor behavior, external notification, or remediation effectiveness.
