# OpsCat P13 Ticket Roadmap — LLM Context Builder

## Requirements Summary

P13 prepares OpsCat for an LLM judgment layer without calling any model yet. It converts incidents, judgment cases, evidence, timelines, candidate hypotheses, runbooks, and safety policy into a compact, schema-stable, prompt-injection-resistant context packet that a future LLM can consume safely and that benchmarks can inspect deterministically.

Boundary remains unchanged:

- no OIDC/SSO/login/password/session/CSRF browser auth work;
- no model calls, no prompt execution, and no external API calls;
- no real production mutation, Kubernetes/cloud/database execution, unrestricted shell, customer credentials, or hosted SaaS claims;
- no external dataset download during normal verification;
- context packets are local/mock, redacted, deterministic, and suitable for P10/P11/P12 benchmark integration.

## P13 Goal

Build an **LLM Context Builder** where OpsCat can:

1. convert an incident or `JudgmentCase` into a stable context packet;
2. select and rank evidence instead of passing raw logs wholesale;
3. redact secrets and mark prompt/log injection as untrusted evidence;
4. build a simple timeline from evidence metadata and incident events;
5. include deterministic candidate hypotheses and runbook context;
6. inject safety constraints and a required output schema;
7. expose a CLI/demo for generating context packets from existing judgment cases;
8. integrate a bounded context-builder smoke into verification.

## P13 Tickets

### P13-001 — LLM Context Packet Schema

**Outcome:** Define stable serializable schema for context packets.

**Acceptance criteria:**

- Packet includes incident, evidence, timeline, candidate_hypotheses, candidate_runbooks, constraints, required_output_schema, and boundary fields.
- Packet is deterministic JSON and redacted.
- Packet states local/mock and no-model-call boundaries.

### P13-002 — Evidence Selector

**Outcome:** Select the most relevant evidence for LLM input.

**Acceptance criteria:**

- Evidence ranking prioritizes errors, anomalies, deploy markers, metrics, no-data/stale signals, and safety-risk content.
- Selector enforces a max evidence limit.
- Selector keeps evidence IDs stable for citation.

### P13-003 — Unsafe Evidence Annotator

**Outcome:** Mark prompt/log injection and unsafe command bait as untrusted observations.

**Acceptance criteria:**

- Detects phrases such as ignore safety, kubectl, rm -rf, drop database, terraform apply, unrestricted shell, and production restart.
- Unsafe content remains available as evidence but is never converted into instructions.
- Packet includes risk_flags and instruction_trust per evidence item.

### P13-004 — Timeline Builder

**Outcome:** Build a compact ordered timeline from incident/evidence metadata.

**Acceptance criteria:**

- Timeline uses evidence timestamps when present.
- Missing timestamps are handled deterministically.
- Timeline entries reference evidence IDs.

### P13-005 — Candidate Hypothesis Context

**Outcome:** Include deterministic candidate hypotheses for LLM review.

**Acceptance criteria:**

- Hypotheses come from judgment rubric, incident root_cause_candidate, or deterministic root-cause service.
- Hypotheses include confidence, supporting evidence IDs, and missing evidence.
- LLM is instructed to review candidates rather than invent unsupported causes.

### P13-006 — Runbook Context Selector

**Outcome:** Include relevant runbook context without dumping all runbooks.

**Acceptance criteria:**

- Selects likely runbooks based on incident text and hypotheses.
- Includes allowed local/mock actions and forbidden actions.
- Keeps production mutation and unrestricted shell disallowed.

### P13-007 — Safety Constraint Pack

**Outcome:** Add explicit constraints to every packet.

**Acceptance criteria:**

- Constraints forbid production mutation, Kubernetes/cloud/database execution, unrestricted shell, following instructions inside logs, and evidence-free claims.
- Constraints require evidence IDs for claims and missing_evidence when unsure.
- Constraints are test-backed and present in every packet.

### P13-008 — Required Output Schema

**Outcome:** Define future LLM output schema without invoking a model.

**Acceptance criteria:**

- Schema requires hypotheses, recommended_route, safe_actions, forbidden_actions_detected, missing_evidence, verification_plan, and evidence_citations.
- Allowed routes match existing OpsCat route taxonomy.
- Schema is included in packets and docs.

### P13-009 — Context Builder CLI

**Outcome:** Generate context packets from judgment case files.

**Acceptance criteria:**

- CLI accepts `--cases`, `--case-id`, `--output-json`, and `--output-md`.
- CLI writes deterministic JSON and reviewer markdown.
- CLI does not call models or external services.

### P13-010 — Benchmark/Verification Integration

**Outcome:** Add context-builder smoke to eval/full verification.

**Acceptance criteria:**

- `scripts/verify.sh --profile eval` runs a bounded context-builder smoke.
- `scripts/verify.sh --profile full` runs the smoke.
- Docs profile validates P13 release evidence.

### P13-011 — P13 Release Evidence

**Outcome:** Close P13 with reproducible evidence and roadmap updates.

**Acceptance criteria:**

- Final summary maps P13-001 through P13-011 to code/tests/docs.
- Release evidence includes context builder commands and temp artifacts.
- `bash scripts/verify.sh --profile full` passes before closure.

## Execution Order

1. P13-001 LLM Context Packet Schema
2. P13-002 Evidence Selector
3. P13-003 Unsafe Evidence Annotator
4. P13-004 Timeline Builder
5. P13-005 Candidate Hypothesis Context
6. P13-006 Runbook Context Selector
7. P13-007 Safety Constraint Pack
8. P13-008 Required Output Schema
9. P13-009 Context Builder CLI
10. P13-010 Benchmark/Verification Integration
11. P13-011 P13 Release Evidence

## Final Gate

`bash scripts/verify.sh --profile full` must pass before P13 closure.
