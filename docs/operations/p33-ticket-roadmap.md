# OpsCat P33 Ticket Roadmap — Live Connector Dry-run Harness

P33 adds a live-connector-shaped dry-run harness. It validates connector configuration, read-only permission posture, schema compatibility, timeout/retry/backoff settings, and mock transport health without making live API calls. Boundary: no auth feature work, no live API calls by default, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## Tickets

- P33-001 — Connector dry-run config schema: define local connector manifests with provider, endpoint reference, credential reference, permission scopes, expected schema fields, and mock response samples.
- P33-002 — Permission audit: mark read-only connectors ready and block/degrade write/admin-scoped connectors.
- P33-003 — Mock transport probe: simulate latency, timeout, rate-limit, retry, and health states without live API calls.
- P33-004 — Schema drift detector: compare expected and observed mock fields and report missing/extra fields.
- P33-005 — Connector health score: aggregate readiness, permission safety, schema compatibility, and transport health.
- P33-006 — Operator handoff report: summarize which connectors are ready, degraded, blocked, and why.
- P33-007 — Verification integration: add P33 smoke to `scripts/verify.sh` and docs contract tests.
- P33-008 — Release evidence: record P33 artifacts, metrics, and safety boundary.

## Acceptance criteria

- At least three connector manifests are evaluated.
- No live API call is made during normal verification.
- Write/admin-scoped connector is not marked ready.
- Schema drift is detected and reported without failing the entire benchmark.
- Health score is at least 0.75 with unsafe auto/live behavior count 0.
- JSON and Markdown reports are generated.
