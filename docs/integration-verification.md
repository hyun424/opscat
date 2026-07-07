# OpsCat Integration Verification Report

Verification updated on 2026-07-07 KST after the P4 eval/QA evidence implementation pass. See [`docs/release-evidence.md`](release-evidence.md) for the release evidence index.

## Latest inspected state

- Source: current worktree `/Users/gimdonghyeon/projects/opscat`
- External credentials used: none
- Production systems touched: none
- Runtime mode: local/mock only

## Summary

The local/mock MVP is green for the current P4 eval/QA evidence scope. The previous syntax/import blockers are resolved. The current build includes:

- default asynchronous mock webhook ingestion (`202 Accepted`) with local durable `WorkflowJob` persistence;
- explicit synchronous demo compatibility via `?process_now=true`;
- immutable `ActionExecutionAttempt` records for approved action execution and verification;
- connector call idempotency replay/conflict protection with redacted persisted results;
- workspace-scoped server-rendered operator dashboard routes;
- updated migrations through `0007_connector_call_records`;
- P4 deterministic eval runner with 23 golden scenarios and JSON/Markdown reports;
- Connector eval runner with 7 fake/local safety scenarios and JSON/Markdown reports;
- browser-contract dashboard E2E tests and eval coverage taxonomy gates.

OpsCat remains intentionally **not production-grade**: demo identity is header-based, workflow queueing is local SQLite/process-bound, connectors are mock/fixture/dry-run only, and no real provider side effects are enabled.

## Smoke-check evidence

| Check | Result | Evidence |
| --- | --- | --- |
| `python3 -m compileall -q app tests scripts` | PASS | App, tests, and scripts compile. |
| `uv run --no-sync --extra dev ruff check app tests scripts` | PASS | Ruff reports all checks passed. |
| `uv run --no-sync --extra dev mypy app tests scripts` | PASS | Mypy reports success across 104 source files. |
| `uv run --no-sync --extra dev pytest -q` | PASS | Regression suite passes, including P4 eval, connector eval, dashboard E2E, taxonomy, and release-evidence tests. |
| `uv run --no-sync --extra dev python scripts/coverage_gate.py --json-output <tmp>/coverage-summary.json` | PASS | Total coverage 67.73% against 60.00% minimum. |
| `uv run --no-sync --extra dev python scripts/run_evals.py --output-json /tmp/opscat-evals.json --output-md /tmp/opscat-evals.md` | PASS | 23 deterministic golden eval scenarios pass and reports are written. |
| `uv run --no-sync --extra dev python scripts/run_connector_evals.py --output-json /tmp/opscat-connector-evals.json --output-md /tmp/opscat-connector-evals.md` | PASS | Connector eval runner covers 7 fake/local safety scenarios. |
| Target P4 tests | PASS | `tests/test_operator_dashboard_e2e.py`, `tests/test_connector_evals.py`, `tests/test_portfolio_evidence_docs.py`, `tests/test_eval_coverage_taxonomy.py`, and `tests/test_release_evidence_index.py` are included in the full regression/release gate. |
| `python scripts/demo.py` | PASS via release gate | Deterministic local demo is part of `scripts/verify.sh`. |
| `docker compose config` | PASS via release gate | Compose config validates without contacting production systems. |
| Generated artifact hygiene | PASS via release gate | Tracked generated artifact scan is included in `scripts/verify.sh`. |

## Verified behavior

### Webhook and workflow

- `POST /webhooks/alerts/mock` creates/updates an incident, persists a scoped workflow job, returns queued state, and does not run full investigation on the request path.
- `process_next_workflow_job()` claims a pending local job, runs deterministic investigation, records start/completion timeline and audit evidence, and leaves the incident in a proposal/escalation state.
- Duplicate alerts reuse the existing incident/job through scoped fingerprint/dedupe keys.

### Action execution attempts

- Approval of a persisted proposed action creates one append-only execution attempt with precondition, execution, post-check, retry eligibility, failure class, and redacted result fields.
- Failed post-checks escalate humans instead of silently resolving.
- Re-approving an already executed action returns current state without duplicating execution side effects.

### Connector idempotency

- Same tenant/workspace/connector/capability/idempotency key with the same request hash replays the stored redacted result and emits `connector_call_replayed`.
- Same key with a different request hash fails closed with `connector_idempotency_conflict` and does not invoke the provider.
- Failed connector calls emit evidence/timeline/escalation once per idempotent call.

### Operator dashboard

- `GET /operator` lists only the principal's tenant/workspace incidents.
- `GET /operator/incidents/{incident_id}` uses service-layer scope checks and returns 404 for cross-workspace reads.
- The dashboard escapes incident content and shows evidence, timeline, action policy/status, execution attempts, and report links.

## Remaining production gaps

1. Replace local header demo identity with real authn/authz (OIDC/SSO/service accounts).
2. Replace local SQLite/process queue with production workflow infrastructure, leases, dead-letter operations, and metrics.
3. Deploy real connector agents with customer-controlled credentials and network boundaries.
4. Add CSRF/session model or separate authenticated frontend before enabling browser mutation forms.
5. Add load/soak tests, CI, deployment guides, backup/restore, and OpsCat self-observability.

## P4 eval coverage

The P4 release evidence index is [`docs/release-evidence.md`](release-evidence.md).

The golden corpus now covers bad deploys, external dependency timeouts/rate limits, worker backlog and heartbeat loss, duplicate/stale/false-positive alerts, low-confidence ambiguity, missing runbooks, protected auth/security/data domains, verification failure, prompt-injection-like log text, and secret-bearing alerts.

These evals prove local/mock decision quality only. They do not replace future live connector evals, real incident replay, load/soak testing, or production auth/security validation.


## P5 final verification

P5 final verification command:

```bash
bash scripts/verify.sh --profile full
```

Result: PASS — the full local/mock release gate completed with `Verification complete (full)`.

Boundary: auth remains deferred; OpsCat is local/mock and does not claim real customer production readiness, live provider mutation, or production credential handling.
