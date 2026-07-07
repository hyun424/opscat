# OpsCat P11 Ticket Roadmap — Incident Corpus Expansion

## Requirements Summary

P11 expands P10's small benchmark seed into a broad, deterministic, local/mock incident corpus before adding an LLM judgment layer. The goal is to make future LLM improvements measurable instead of anecdotal.

Boundary remains unchanged:

- no OIDC/SSO/login/password/session/CSRF browser auth work;
- no real production mutation, Kubernetes/cloud/database execution, unrestricted shell, customer credentials, or hosted SaaS claims;
- no external dataset download required for normal verification;
- corpus cases are local, redacted, deterministic, license-safe, and suitable for benchmark regression;
- automatic actions remain local/mock, allowlisted, policy-gated, simulated, audited, reversible, and test-backed.

## P11 Goal

Build a credible **Incident Corpus & Evaluation Expansion** layer where OpsCat can:

1. define an incident archetype catalog across common SRE failure modes;
2. generate at least 50 deterministic judgment cases from local templates;
3. audit case uniqueness, tags, evidence completeness, safety coverage, route coverage, and taxonomy balance;
4. select a stable benchmark smoke subset from the larger corpus;
5. produce JSON/Markdown corpus reports for reviewer evidence;
6. integrate corpus audit into verification before any LLM judgment layer is added.

## P11 Tickets

### P11-001 — Incident Archetype Catalog

**Outcome:** Define a reusable catalog of failure-mode archetypes for corpus generation.

**Acceptance criteria:**

- Catalog covers deploy regression, DB saturation, memory leak, CPU spike, queue backlog, downstream timeout, rate limit, disk full, cert expiry, DNS failure, crashloop, bad config, noisy false positive, no-data, partial outage, cascading failure, and log/prompt injection.
- Each archetype declares hypotheses, tags, evidence hints, expected route, and forbidden actions.
- Catalog remains deterministic and local/mock only.

### P11-002 — Deterministic Corpus Generator

**Outcome:** Generate judgment cases from archetypes without network calls.

**Acceptance criteria:**

- Generated IDs are stable and unique.
- At least 50 cases are generated from the catalog.
- Every case includes incident, evidence, rubric, tags, and local/mock boundary.

### P11-003 — Corpus Audit Metrics

**Outcome:** Validate corpus quality before it is used for LLM evaluation.

**Acceptance criteria:**

- Audit reports total cases, route counts, tag counts, source counts, duplicate IDs, missing evidence, missing hypotheses, and safety case counts.
- Audit fails when minimum case count, minimum archetype count, safety coverage, no-data coverage, false-positive coverage, or route diversity is missing.
- Audit output is deterministic JSON-serializable.

### P11-004 — Corpus Pack Writer

**Outcome:** Persist corpus packs as stable JSON fixtures.

**Acceptance criteria:**

- Writer sorts cases by ID.
- Writer redacts secrets and unsafe tokens from serialized fields where applicable.
- Fixture lives under `evals/judgment/corpus/`.

### P11-005 — Benchmark Smoke Selector

**Outcome:** Select a bounded, stable subset from the larger corpus for fast verification.

**Acceptance criteria:**

- Selector chooses diverse cases by route and tags.
- Selector is deterministic.
- Selector can include existing P10 seed cases plus P11 corpus cases.

### P11-006 — Corpus Report CLI

**Outcome:** Add a CLI that audits and reports corpus quality.

**Acceptance criteria:**

- CLI writes JSON and Markdown reports.
- CLI exits non-zero when quality gates fail.
- CLI does not download datasets or call external services.

### P11-007 — Corpus Fixture Pack

**Outcome:** Add a built-in expanded corpus fixture.

**Acceptance criteria:**

- Fixture contains at least 50 cases.
- Fixture includes safety/injection, no-data, false-positive, conflicting-signal, and cascading-failure scenarios.
- Fixture is local/mock and redacted.

### P11-008 — Verification Integration

**Outcome:** Include corpus audit in eval/full verification profiles.

**Acceptance criteria:**

- `scripts/verify.sh --profile eval` runs corpus audit.
- `scripts/verify.sh --profile full` runs corpus audit.
- Docs profile validates P11 release evidence.

### P11-009 — P11 Release Evidence

**Outcome:** Close P11 with reproducible evidence and roadmap updates.

**Acceptance criteria:**

- Final summary maps P11-001 through P11-009 to code/tests/docs.
- Release evidence includes corpus audit commands and artifacts.
- `bash scripts/verify.sh --profile full` passes before closure.

## Execution Order

1. P11-001 Incident Archetype Catalog
2. P11-002 Deterministic Corpus Generator
3. P11-003 Corpus Audit Metrics
4. P11-004 Corpus Pack Writer
5. P11-005 Benchmark Smoke Selector
6. P11-006 Corpus Report CLI
7. P11-007 Corpus Fixture Pack
8. P11-008 Verification Integration
9. P11-009 Release Evidence

## Final Gate

`bash scripts/verify.sh --profile full` must pass before P11 closure.
