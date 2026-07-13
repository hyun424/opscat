# P131 Always-on Monitoring Runtime

## Outcome

Turn the existing one-shot, fixture-oriented polling surfaces into a standalone
read-only process that can remain running, prove that it is still observing
fresh data, recover from restart without duplicating records, and expose
machine-checkable health evidence.

P131 does **not** add authentication, credentials, connector writes, shell
execution, remediation execution, staging mutation, or production mutation.

## Delivery slices

1. **Runtime contract** — strict configuration, source allowlisting, exact-zero
   P121 authority counters, bounded resource limits, and a monotonic scheduler contract.
2. **Durable observation loop** — local JSONL tailing with atomic checkpoints,
   rotation handling, and duplicate suppression.
3. **Self-monitoring** — heartbeat, source freshness, consecutive-failure state,
   synthetic canary, readiness, and daily summaries.
4. **Independent watchdog** — a separate command that fails when the runtime
   heartbeat is missing, stale, malformed, or hash-invalid.
5. **Operator surface** — safe health/readiness endpoints and packaged CLI
   commands for bounded smoke runs or continuous foreground operation.
6. **Release evidence** — deterministic fixture run, restart replay, dead-man
   failure probes, tests, static checks, and fail-closed release gates.

## Safety boundaries

- P131 sources are `local_jsonl` only. A local collector may write exported
  telemetry to that file, but P131 itself performs no network call.
- Direct Prometheus polling is intentionally deferred: P121 counts every live
  connector call as non-zero authority, so claiming both real polling and exact
  zero authority would be dishonest without a new reviewed observation contract.
- The runtime emits observations and reports only. It cannot execute an action.
- Continuous operation is explicit (`--forever`); verification remains bounded.
- A healthy process with stale source data is **not ready**.
- A valid internal heartbeat does not replace an external watchdog.

## Stop conditions

- Configuration requests mutation, credentials, unrestricted network, or an
  unsupported source type.
- The checkpoint is malformed or fails its self-hash.
- The failure streak exceeds its configured limit.
- The synthetic canary fails.
- The runtime loses its exclusive lease.
