# OpsCat P27 Final Summary — Connector Readiness and Permission Contract

P27 adds the read-only connector readiness layer that must pass before live-like polling is allowed. It evaluates connector manifests for declared capabilities, required scopes, credential references, health state, retry/backoff posture, and mutation risk.

Boundary: no-auth/local-mock by default; no live writes; no production credentials; no remediation execution; no production mutation; no default external model/API calls; does not claim unattended production operation.

## Tickets Completed

- P27-001 Connector permission manifest: source, capabilities, required scopes, read-only flag, denied mutation capabilities, and evidence IDs are represented.
- P27-002 Credential and secret boundary: reports keep credential references such as `PROMETHEUS_TOKEN_REF` and redact secret-like values.
- P27-003 Connector health model: ready, degraded, blocked, and unavailable states distinguish missing credentials, rate limits, auth failure, schema/permission risks, and mutation declarations.
- P27-004 Rate-limit and retry policy: deterministic bounded retry seconds prevent tight retry loops.
- P27-005 Read-only enforcement gate: mutation-like capabilities are blocked even when a connector declares them.
- P27-006 Readiness CLI and report: `scripts/run_connector_readiness.py` writes JSON and Markdown readiness reports.
- P27-007 Verification integration: targeted tests and `connector_readiness_smoke` are integrated into verification.
- P27-008 Release evidence: roadmap, release evidence, and this summary document the safety boundary.

## Implemented Artifacts

- `app/services/connector_readiness.py`
- `scripts/run_connector_readiness.py`
- `evals/connectors/readiness/read_only_sources.json`
- `evals/connectors/readiness/unsafe_sources.json`
- `evals/connectors/readiness/degraded_sources.json`
- `tests/test_connector_readiness_contract.py`
- `tests/test_p27_release_evidence.py`
- `docs/operations/p27-ticket-roadmap.md`

## Behavior Summary

- Ready manifests can use only read/query/list/health/metadata capabilities.
- Missing credential references degrade readiness instead of crashing.
- Rate-limit and auth-failure states produce bounded retry intervals.
- Write/delete/restart/shell/kubectl/deploy/rollback-style capabilities are denied and route the manifest to blocked.
- The report is a read-only connector readiness artifact; it does not run connector polling or remediation.

## Verification Commands

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_connector_readiness_contract.py tests/test_p27_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev python scripts/run_connector_readiness.py --manifests evals/connectors/readiness/read_only_sources.json --output-json /tmp/opscat-connector-readiness-latest.json --output-md /tmp/opscat-connector-readiness-latest.md`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

## Known Boundaries

P27 is readiness and permission evaluation only. It does not perform live observability API calls, does not implement auth, does not store production credentials, and does not claim unattended production operation. P28 should use this contract before scheduling read-only polling.
