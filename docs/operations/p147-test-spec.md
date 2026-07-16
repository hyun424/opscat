# P147 Durable Offline Provider Shadow Test Specification

Schema/status: `p147.report.v1`, `p147.freeze_manifest.v1`,
`p147.final_review.v1`, `p147.release_evidence.v1`, and
`p147_durable_provider_shadow_qualified`. Artifacts and commands are the exact
P147 paths and `p147-release` command in the program plan.

1. Reject mutation capabilities, non-GET provider operations, unknown provider kinds, unallowlisted targets, and unsafe configuration fields.
2. Bound each cycle to 5 provider reads, 3 investigation calls, 2 retries,
   2-second timeout, 300-second window, 1,048,576 bytes, and 10,000 records.
3. Redact secrets and persist hashes/normalized evidence only.
4. Atomically persist cursor, heartbeat, incident dedupe keys, and self-hash; reject stale, corrupt, forked, or replayed state.
5. Restart resumes exactly once and deadman fires only after 30 missed seconds.
6. Evidence gaps select only closed read-only tools and stop at the investigation budget.
7. Default canonical run has zero credential, external-network, model, action, staging-mutation, and production-mutation counters.
8. Real-provider mode is explicit opt-in and its report is non-release.
9. Report binds P146 final evidence, sources, rows, counters, limitations, and self-hash.
10. Fixtures are `prometheus_ok`, `loki_jsonl_ok`, `sentry_style_ok`,
    `trace_fixture_ok`, `deployment_history_ok`, `restart_resume`,
    `deadman_30s`, and `provider_faults`; OA3/live staging is rejected.
