# P132 Final Summary

## Result

P132 qualifies the real credential-free P131 monitor for bounded, single-host
supervision. The promoted release status is
`p132_supervised_runtime_qualified`.

This is supervisor-readiness evidence, not a production SLO. It does not add
authentication, credentials, live connectors, paging, remediation, staging or
production mutation, multi-host failover, or operator-replacement authority.

## Implemented

- SIGTERM and SIGINT use an event-only signal handler, finish through normal
  control flow, persist a hash-bound stopped checkpoint and termination receipt,
  then release the exclusive lease.
- Watchdog and status fail immediately with `runtime_stopped`; forced process
  death remains distinguishable as `heartbeat_stale`.
- Health reports are bounded by count and bytes. Retention accepts only exact,
  owned, regular, non-symlink, schema-valid, hash-valid reports and refuses
  deletion unless the report directory is service-owned and not group/world
  writable.
- State, report, and receipt writes check a configured free-space floor.
  Pre-replace failures preserve the canonical file; post-replace directory-sync
  failures raise explicit durability uncertainty.
- Release evidence exercises low-space preservation, pre-replace preservation,
  post-replace reload/rewrite recovery, and interrupted-report bucket recovery;
  each case carries substantive hash-bound fields rather than a bare pass flag.
- systemd, launchd, and Compose examples use a closed `opscat-monitor` command,
  restart throttling, graceful stop, non-root execution, and no embedded secret
  or network/action path. Compose refuses to start until
  `OPSCAT_MONITOR_IMAGE_DIGEST` supplies an immutable 64-hex image-manifest
  digest; mutable tags are rejected by validation.
- A real subprocess harness proves clean signals, forced crash/restart, lease
  conflict rejection, current/stopped/stale/missing/tampered watchdog behavior,
  and checkpoint deduplication.

## Promoted evidence

`evals/p132/` contains:

- `endurance-report.json`: 1,000 expected and accepted observations, zero
  invalid, duplicate, or lost rows across 1,000 cycles; eight retained reports;
  all state, report-directory, total-artifact, memory, CPU, and wall-time gates
  pass.
- `process-matrix.json`: SIGTERM, SIGINT, forced crash/restart, and lease
  conflict cases all pass, as do all four storage-fault cases. The final run
  accepted three distinct observations exactly once and resumed twice.
- `supervisor-validation.json`: systemd, launchd, Compose, console entrypoint,
  and source hashes pass structural validation.
- `supervisor-ledger.json`: closed evaluator command and signal activity is
  disclosed separately from runtime authority.
- `release-evidence.json`: every gate passes and all artifacts are hash-bound.
- `raw/`: the bounded endurance telemetry, final checkpoint, retained reports,
  process checkpoint/receipt/config, and storage-fault canonical files referenced
  by the reports. Every promoted path is relative and the validator re-hashes
  these files plus current source and supervisor manifests.

The evaluator launched ten local monitor subprocesses, delivered two graceful
signals and one forced kill, observed one lease conflict, called watchdog five
times and status once, and recorded exact integer zero for arbitrary commands,
credentials, network, connector writes, remediation, staging mutation, and
production mutation. Runtime P121 authority counters also remain exact integer
zero.

## Reproduce

```bash
bash scripts/verify.sh --profile p132-release
```

Final promotion completed after an independent code review reported zero
unresolved P0, P1, or P2 findings and the full repository verification profile
passed with 78.64% measured coverage. The chained P122, P129, P130, P131, and
P132 release profiles were refreshed and passed before promotion. Details are
recorded in `docs/operations/p132-verification-handoff.md`.

## Next dependency

P133 may build a durable, redacted local dead-man notification outbox from P132
watchdog results. It must remain network-free and action-free; external delivery
requires a later reviewed authority contract.
