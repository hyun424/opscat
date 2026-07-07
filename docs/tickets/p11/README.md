# P11 Tickets — Incident Corpus Expansion

P11 expands P10's judgment benchmark from a tiny seed set into a broad deterministic local/mock incident corpus before adding LLM judgment. Auth remains deferred.

## Tickets

- [P11-001 — Incident Archetype Catalog](p11-001-incident-archetype-catalog.md)
- [P11-002 — Deterministic Corpus Generator](p11-002-deterministic-corpus-generator.md) — depends on P11-001
- [P11-003 — Corpus Audit Metrics](p11-003-corpus-audit-metrics.md) — depends on P11-002
- [P11-004 — Corpus Pack Writer](p11-004-corpus-pack-writer.md) — depends on P11-002, P11-003
- [P11-005 — Benchmark Smoke Selector](p11-005-benchmark-smoke-selector.md) — depends on P11-002, P11-003
- [P11-006 — Corpus Report CLI](p11-006-corpus-report-cli.md) — depends on P11-003, P11-004
- [P11-007 — Corpus Fixture Pack](p11-007-corpus-fixture-pack.md) — depends on P11-002, P11-004
- [P11-008 — Verification Integration](p11-008-verification-integration.md) — depends on P11-006, P11-007
- [P11-009 — P11 Release Evidence](p11-009-release-evidence.md) — depends on P11-001 through P11-008

## Boundary

No auth/session work, no external dataset download, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.

## Final Gate

`bash scripts/verify.sh --profile full` must pass before P11 closure.
