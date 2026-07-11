# Local performance and soak evidence

Run:

```bash
uv run --no-sync --extra dev python scripts/run_p122_performance_soak.py \
  --iterations 1000 --workdir /tmp/opscat-p122-soak \
  --output evals/p122/performance-soak.json
```

The report records Python/platform/CPU context, duration, local package-payload
install time, cold-start import time, per-demo timings, event and replay
throughput, maximum RSS, storage envelope, independent record denominators,
loss counters, and exact-zero authority counters. It also binds the executed
15-point P121 WAL crash/replay proof, including interrupted pending rollback
recovery. It measures a network-free fixture workload only and is not
production capacity evidence.

Schema marker: `p122.performance_soak.v2`. Release evidence rejects
`--iterations` below `1000`; tests may pass `--allow-short-test-run` through the
CLI or call the Python helper directly with a smaller denominator.

Observed-loss accounting is computed independently from incident, audit,
timeline, replay, and authority files written during the run. The
`release_stage_crash_replay` section actually raises and catches one controlled
crash at each of the 12 release stages, recovers each persisted pending journal,
and rereads the committed recovery record. Observability includes health,
readiness, metrics, correlated structured logs, diagnostics, fixture-secret
redaction, replay inspection, and an observed fail-closed authority rejection.

```json
{
  "schema_version": "p122.performance_soak.v2",
  "lost_replay_records": 0,
  "release_stage_crash_replay": {
    "point_count": 12,
    "injected_count": 12,
    "recovered_count": 12,
    "verified": true
  },
  "upstream_executed_crash_replay": {
    "point_count": 15,
    "pending_rollback_replayed": true
  }
}
```

## Troubleshooting

- `--iterations must be at least 1000`: rerun the release command without the
  test-only short-run escape hatch.
- Any nonzero `lost_*_records`: inspect the corresponding `replay-*.json` files
  in the workdir before accepting performance evidence.
- `pending_rollback_replayed = false`: block release because the P121 WAL crash
  proof did not replay interrupted rollback recovery.
- `readiness.ready = false`: inspect record loss, the 12 crash journals, and
  the authority rejection diagnostic before rerunning.
