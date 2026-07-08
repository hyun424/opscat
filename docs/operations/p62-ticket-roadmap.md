# OpsCat P62 Ticket Roadmap — Staging Read-only Connector Contract

P62 defines the contract required before OpsCat connects to any real staging observability system. It stays local/offline, validates provider-shaped manifests and sample responses, and preserves read-only/no-execution safety boundaries.

## Tickets

- P62-001 — Staging connector fixture: create Grafana, Sentry, Datadog, and unsafe-production sample connector entries.
- P62-002 — Provider contract parser: normalize endpoint refs, credential refs, scopes, operations, query plans, sample responses, and environment metadata.
- P62-003 — Read-only permission gate: block write/admin/mutation scopes, production environments, mutation operations, and raw secret leakage.
- P62-004 — Provider schema gate: validate provider-specific required response fields for Grafana metrics, Sentry events, and Datadog monitors/logs.
- P62-005 — Polling readiness gate: require explicit staging environment, safe timeout, safe rate-limit budget, and at least one query plan per ready connector.
- P62-006 — Operator handoff: produce clear ready/degraded/blocked connectors, reasons, and next safe step for attaching staging read-only credentials.
- P62-007 — CLI smoke: emit JSON and Markdown reports without live API calls.
- P62-008 — Release evidence: wire docs, verification, and safety counters into release evidence.

## Acceptance criteria

- At least three provider-shaped staging connectors are evaluated.
- Ready connectors cover Grafana, Sentry, and Datadog-compatible shapes.
- Unsafe production/admin connector is blocked.
- No live API calls, production mutation, remediation execution, shell execution, or default external model calls occur.
- The report exposes exact safety counters and provider schema compatibility.
