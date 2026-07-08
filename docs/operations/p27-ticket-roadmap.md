# OpsCat P27 Ticket Roadmap — Connector Readiness and Permission Contract

P27 defines safe connector readiness before any live polling: declared capabilities, required permissions, health checks, rate-limit/backoff policy, credential redaction, and read-only enforcement.

Boundary: no auth, no production mutation, no remediation execution, no live writes, no default external model/API calls, no unattended production-operation claim.

## Tickets

### P27-001 Connector permission manifest

Acceptance:
- Declare source, capabilities, required scopes, read-only status, and denied mutation capabilities.
- Manifest serialization redacts secret-like fields.
- Unknown or write-capable manifests fail readiness.

### P27-002 Credential and secret boundary

Acceptance:
- Credential references are represented by names only, never values.
- Reports do not include API keys, bearer tokens, DSNs, or private keys.
- Missing credentials produce degraded readiness, not crashes.

### P27-003 Connector health model

Acceptance:
- Health states include ready, degraded, blocked, and unavailable.
- Timeout, rate-limit, permission, schema, and auth-failure reasons are distinct.
- Health payloads include evidence IDs and next safe retry time.

### P27-004 Rate-limit and retry policy

Acceptance:
- Backoff policy is deterministic and bounded.
- Rate limit responses do not trigger tight loops.
- Default polling remains disabled unless explicitly enabled by local config.

### P27-005 Read-only enforcement gate

Acceptance:
- Mutation-like capabilities are blocked even if a connector declares them.
- Allowed operations are read/query/list/health only.
- Violation evidence is auditable.

### P27-006 Readiness CLI and report

Acceptance:
- CLI evaluates manifests from fixtures.
- JSON/Markdown reports state local/mock/read-only boundary.
- Exit code can fail on blocked manifests while allowing degraded read-only sources.

### P27-007 Verification integration

Acceptance:
- Add targeted tests and smoke verification.
- Full verification remains secret-free and live-call-free.

### P27-008 Release evidence

Acceptance:
- Final summary and release evidence document readiness outcomes and limitations.
- Roadmap marks P27 implemented only after verification.
