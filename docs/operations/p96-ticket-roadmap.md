# OpsCat P96 Ticket Roadmap — Real Prometheus Read-only Shadow Connector

P96 moves OpsCat from connector-shaped simulation to one real, bounded observability read path. The first provider is Prometheus because it exposes a stable read-only HTTP API, works locally without credentials, and can supply the metric evidence needed by the existing investigation and LLM judgment layers.

Boundary: fixture mode remains the default. Real mode is explicit opt-in, performs GET requests only, accepts a configured base URL rather than request-controlled destinations, enforces a host allowlist and query budgets, redacts responses, persists only normalized evidence, and never executes remediation or production mutation.

- P96-001 — Security contract: define configured endpoint, scheme/host allowlist, GET-only transport, timeout, response-size, series-count, and range-point budgets.
- P96-002 — RED contract tests: cover fixture default, real instant/range reads, SSRF prevention, query budgets, provider failures, redaction, and incident evidence persistence.
- P96-003 — Prometheus connector: implement `prometheus.readonly` with `health.check`, `query.instant`, and `query.range` capabilities.
- P96-004 — Evidence bridge: persist successful normalized Prometheus observations as tenant/workspace-scoped incident evidence and timeline entries.
- P96-005 — Operator probe: add a CLI that runs fixture mode by default and real mode only when explicitly selected and configured.
- P96-006 — Product integration: expose connector metadata and documented environment configuration without adding auth work.
- P96-007 — Verification: run targeted tests, lint, typecheck, security checks, full regression, coverage, and clean-clone-safe docs checks.
- P96-008 — Release evidence: record the exact implemented boundary, commands, results, limitations, and P97 handoff.

