# OpsCat P28 Final Summary — Read-only Polling Runtime

P28 adds a bounded local/mock polling runtime that runs only after P27 readiness checks. It schedules read-only fixture jobs, skips degraded or unavailable sources, blocks unsafe jobs, converts successful fixture responses through P26 adapters, and emits telemetry snapshots plus proactive trend windows.

Boundary: no-auth/local-mock by default; fixture/local transport only; no live API calls; no live writes; no production mutation; no remediation execution; no default external model/API calls; does not claim unattended production operation.

## Tickets Completed

- P28-001 Polling job schema: source, fixture transport, interval, timeout, enabled flag, requested capabilities, and batch bounds are represented.
- P28-002 Deterministic scheduler: tick-based execution runs bounded local polling without wall-clock flakiness.
- P28-003 Fixture transport: polling reads local fixture payloads only and simulates timeout/rate-limit/malformed-style failure states.
- P28-004 Adapter pipeline integration: successful polls feed P26 adapters and produce proactive TrendWindows.
- P28-005 Runtime report CLI: `scripts/run_read_only_polling.py` writes JSON and Markdown reports.
- P28-006 Safety regression tests: readiness-blocked and mutating jobs cannot poll; retry state prevents tight loops; reports remain redacted.
- P28-007 Verification integration: `read_only_polling_smoke` runs in the verification profile.
- P28-008 Release evidence: roadmap, release evidence, and this summary document the runtime boundary.

## Implemented Artifacts

- `app/services/read_only_polling_runtime.py`
- `scripts/run_read_only_polling.py`
- `evals/polling/jobs/p28_polling_jobs.json`
- `evals/polling/jobs/p28_unsafe_jobs.json`
- `evals/polling/jobs/p28_failure_jobs.json`
- `tests/test_read_only_polling_runtime.py`
- `tests/test_p28_release_evidence.py`
- `docs/operations/p28-ticket-roadmap.md`

## Behavior Summary

- P27 readiness is required before polling.
- Only ready sources with read/query/list/health/metadata capabilities can poll.
- Degraded, unavailable, missing-readiness, and readiness-blocked sources are skipped or blocked with retry evidence.
- Successful fixture responses feed P26 adapters and produce telemetry snapshots and proactive trend windows.
- The runtime is fixture/local transport only and does not claim unattended production operation.

## Verification Commands

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_read_only_polling_runtime.py tests/test_p28_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev python scripts/run_read_only_polling.py --jobs evals/polling/jobs/p28_polling_jobs.json --readiness evals/connectors/readiness/read_only_sources.json --ticks 1 --output-json /tmp/opscat-read-only-polling-latest.json --output-md /tmp/opscat-read-only-polling-latest.md`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

## Known Boundaries

P28 is a local/mock read-only polling runtime. It does not call live APIs, does not manage auth, does not mutate production systems, and does not execute remediation. P29 should use polling output to evaluate telemetry-grounded judgment quality.
