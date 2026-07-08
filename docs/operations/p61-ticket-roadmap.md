# OpsCat P61 Ticket Roadmap — Local Shadow Connector Validation

P61 validates the first live-shaped connector step without touching real production: a local shadow observability source is read through a read-only connector contract, normalized into evidence, judged by the shadow commander, and connected back to P60 readiness boundaries.

## Tickets

- P61-001 — Local shadow fixture: define a live-shaped local source with metrics, logs, errors, deployments, empty-source, and malformed-payload cases.
- P61-002 — Read-only connector contract: implement `fetch_metrics`, `fetch_logs`, `fetch_errors`, and `fetch_deployments` with no write/restart/rollback operations.
- P61-003 — Evidence normalization: convert connector observations into supporting, counter, and missing evidence.
- P61-004 — Shadow judgment: produce top hypothesis, confidence, recommended action, and blocked execution state.
- P61-005 — P60 readiness link: preserve local/shadow readiness while keeping unattended production readiness false.
- P61-006 — CLI report: write JSON and Markdown artifacts for local review.
- P61-007 — Verification integration: wire P61 smoke into `scripts/verify.sh`.
- P61-008 — Release evidence: document artifacts, boundaries, and final verification result.

## Acceptance criteria

- Reads at least one metric, log, error, and deployment signal from the local shadow source.
- Empty and malformed local sources are tolerated and reported.
- Top hypothesis is `recent_deploy_regression` with confidence at least 0.9.
- Supporting evidence, counter-evidence, and missing evidence are present.
- Recommended action is report/draft-only and execution is blocked in shadow mode.
- Action execution, live API calls, production mutation, and remediation execution remain zero.
- P60 local/shadow readiness remains true and unattended production readiness remains false.
