# OpsCat P23 Ticket Roadmap — Incident Scenario Corpus Expansion

P23 expands the incident judgment/drill corpus from a tiny seed set into a broad local/mock scenario suite for operator-replacement evaluation. The goal is not production autonomy; it is a larger, safer test bench for judging whether the agent classifies incidents, cites evidence, blocks dangerous actions, and escalates ambiguous cases.

Boundary: no auth, no production credentials, no hosted SaaS operation, no Kubernetes/cloud/database mutation, no unrestricted shell, no default external model/API calls, no remediation execution, and no unattended production-operation claim.

## Tickets

### P23-001 Scenario taxonomy
Define scenario categories and minimum coverage targets across deploy, database, connection pool, queue, storage, cache, network, downstream dependency, traffic spike, false positive, observability gap, security/prompt-injection, and data pipeline incidents.

Acceptance:
- At least 12 distinct scenario tags are represented.
- Connection pool has at least 8 focused scenarios.
- Safety/adversarial cases are present.

### P23-002 Bulk seed corpus generation
Expand `evals/judgment/seed/cases.json` with deterministic local/mock scenarios.

Acceptance:
- At least 60 total cases.
- Unique IDs.
- Every case has incident, evidence, rubric, tags.
- Every required evidence ID exists in evidence/signals.

### P23-003 Corpus quality contract tests
Add tests that enforce schema quality, category coverage, action-safety constraints, and route distribution.

Acceptance:
- Tests fail on the old 4-case corpus.
- Tests pass after corpus expansion.

### P23-004 Drill compatibility
Ensure P22 night-shift drill can run over the expanded corpus with bounded `max-cases` and no remediation execution.

Acceptance:
- P22 smoke still passes.
- A P23 corpus sample drill report is generated.

### P23-005 Verification integration
Add P23 release evidence tests to verification docs profile.

Acceptance:
- `scripts/verify.sh` includes P23 release evidence tests.
- Full verification remains offline/local-mock.

### P23-006 Release evidence
Document scenario count, categories, connection-pool coverage, verification, and boundaries.

Acceptance:
- P23 final summary exists.
- Release evidence and roadmap mark P23 implemented.
