# P131 Operator Runbook

## Start

1. Copy `config/p131-monitor.example.json` and keep every source under an
   allowlisted data root.
2. Create the JSONL file before startup. Producers must append one complete JSON
   object and newline per observation.
3. Run `opscat-monitor run --config <path> --forever` under a process supervisor.
   Do not run it inside FastAPI or start more than one instance for the same
   lease path.

## Probe

```bash
opscat-monitor watchdog --state data/p131/runtime-state.json --timeout-seconds 180
opscat-monitor status --state data/p131/runtime-state.json
```

The watchdog exits `0` only for a current, hash-valid heartbeat. Status exits
`0` for liveness and reports readiness separately. The HTTP equivalents are
`GET /monitor/health` and `GET /monitor/readiness`.

## Interpret degradation

| Reason | Meaning | Safe response |
| --- | --- | --- |
| `state_missing` | Runtime never committed state or wrong state path | Inspect supervisor/config; do not infer telemetry health |
| `state_hash_invalid` | Partial write, tamper, or manual edit | Stop promotion, preserve file, restart only after root-cause review |
| `invalid_source_state` | Source checkpoint fields are missing, malformed, or internally inconsistent | Preserve the checkpoint and investigate before restart; do not trust readiness |
| `heartbeat_stale` | Runtime stopped progressing | Let the supervisor restart; inspect previous report and process logs |
| `runtime_stopped` | SIGTERM/SIGINT completed cleanly and a termination receipt was committed | Restart only when intended; verify receipt and supervisor policy |
| `heartbeat_in_future` | Clock skew exceeds five seconds | Repair host time before trusting freshness |
| `source_data_missing` | No complete observation accepted | Check producer and JSONL newline framing |
| `source_data_stale` | Process is alive but no fresh observation arrived | Check upstream collector/file delivery |
| `source_failure_limit_exceeded` | Repeated source read/parse failures | Inspect permissions, rotation, and JSONL validity |
| `canary_failed` | Internal ingestion/detection/policy-block probe failed | Treat runtime as not ready; no action is attempted |

## Recovery properties

- State is written using file `fsync`, atomic replace, and directory `fsync`.
- `max_report_files`, `max_report_dir_bytes`, and
  `min_artifact_free_bytes` bound artifact growth and fail before low-space
  writes. A directory-sync fault after replacement is reported as durability
  uncertain; reload the hash-valid canonical file and complete a later durable
  rewrite before treating it as qualified.
- File identity and byte cursor detect replacement/truncation.
- Recent observation hashes suppress replay after rotation.
- A partial final JSONL line is not committed until its newline arrives.
- The lease prevents two local processes from owning one runtime state.
- SIGTERM/SIGINT persist `lifecycle.phase=stopped` and a self-hashed receipt
  before lease release. The validated examples are under `deploy/p132/`.
- Data and artifact paths are traversed without following symlinks after their
  configured allowlist roots are resolved.

P131 never restarts services, modifies infrastructure, sends credentials,
executes shell/subprocess commands, or performs remediation.
